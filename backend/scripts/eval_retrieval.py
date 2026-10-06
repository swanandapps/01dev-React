"""Retrieval eval runner (spec §5). Runs a system over the eval sets in player and/or ask mode and
writes backend/eval/retrieval/reports/<label>.json + .md, appending one line per mode to HISTORY.md.

LOCAL ONLY — the in-memory store; run from backend/ with the key inline and the database off:
  env OPENAI_API_KEY=... DATABASE_URL= .venv/bin/python scripts/eval_retrieval.py --system legacy --label phase1-baseline
Options: --modes player,ask  --limit N (first N rows per set, trial)  --only <slug>  --concurrency 6
         --compare <earlier label>  --all-launched (adds mode ask_all)  --latency-sample N (default 60)
"""
import argparse
import asyncio
import contextlib
import hashlib
import json
import os
import subprocess
import sys
from dataclasses import asdict
from datetime import datetime
from pathlib import Path
from typing import Optional

BACKEND = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND))

from app.eval.retrieval_metrics import (Prediction, Row, compare, percentile, per_course,  # noqa: E402
                                        render_markdown, summarize, summarize_clean)

SETS = [BACKEND / "eval" / "retrieval" / "generated_set.json", BACKEND / "eval" / "retrieval" / "hand_set.json"]
REPORTS = BACKEND / "eval" / "retrieval" / "reports"
TARGETS = {"recall@5": (">=", 0.9), "coverage_accuracy": (">=", 0.9), "false_cite_rate": ("<=", 0.03),
           "latency_p95_ms": ("<=", 1500.0)}
HISTORY_HEADER = ("| label | system | mode | recall@1 | recall@5 | mrr | shown@3 | coverage | false_cite | navigate "
                  "| p50 ms | p95 ms | rows |\n|---|---|---|---|---|---|---|---|---|---|---|---|---|\n")


def load_rows(paths=SETS, limit: Optional[int] = None, only: Optional[str] = None) -> dict[str, Row]:
    rows: dict[str, Row] = {}
    for p in paths:
        items = [Row.from_dict(d) for d in json.loads(Path(p).read_text())]
        items = [r for r in items if not only or r.scope_course == only]
        for r in items[:limit] if limit else items:
            rows[r.id] = r
    return rows


def rows_for_mode(rows: list[Row], mode: str) -> list[Row]:
    if mode in ("ask", "ask_all"):
        # No navigation on the Ask page; a cross-course row is taught somewhere in the library.
        rows = [r for r in rows if r.intent != "navigate" and r.style != "cross_course"]
        if mode == "ask":  # the Ask page cites only launched courses (F1): other courses' rows are out of scope
            from app.eval.retrieval_systems import launched_slugs
            launched = set(launched_slugs("ask"))
            rows = [r for r in rows if r.scope_course in launched]
        return rows
    return list(rows)


async def run_system(system, rows: list[Row], mode: str, concurrency: int = 6) -> list[Prediction]:
    sem = asyncio.Semaphore(concurrency)

    async def one(r: Row) -> Prediction:
        async with sem:
            try:
                return await system.predict(r, mode)
            except Exception as e:  # noqa: BLE001 — a failed row is reported, never fatal
                return Prediction(r.id, mode, [], "not_covered", None, error=repr(e))

    return list(await asyncio.gather(*(one(r) for r in rows)))


def latency_sample_rows(rows: list[Row], n: int) -> list[Row]:
    """A fixed, system-independent sample: the n rows with the smallest sha1(id)."""
    return sorted(rows, key=lambda r: hashlib.sha1(r.id.encode()).hexdigest())[:n]


async def run_latency_sample(system, rows: list[Row], mode: str, n: int) -> list[Prediction]:
    """Production-shaped latency: one decision at a time (concurrency 1), no ranking pass, no embedding memo."""
    out = []
    for r in latency_sample_rows(rows, n):
        try:
            out.append(await system.predict(r, mode, rank=False))
        except Exception as e:  # noqa: BLE001
            out.append(Prediction(r.id, mode, [], "not_covered", None, error=repr(e)))
    return out


def build_run(label: str, system_name: str, rows: dict[str, Row], preds_by_mode: dict[str, list[Prediction]],
              config: Optional[dict] = None, latency_by_mode: Optional[dict[str, list[Prediction]]] = None) -> dict:
    """Decision metrics come from `preds_by_mode` (main pass); when `latency_by_mode` is given, latency comes
    from that sample pass instead (main-pass latencies are contaminated by concurrency and are zeroed)."""
    modes, preds_out, latency = {}, [], {}
    for m, ps in preds_by_mode.items():
        overall, clean = summarize(rows, ps), summarize_clean(rows, ps)
        lp = (latency_by_mode or {}).get(m)
        if lp is not None:
            ok = [p for p in lp if p.error is None]
            for s, sample in ((overall, ok), (clean, [p for p in ok if rows[p.row_id].is_clean])):
                lats = [p.latency_ms for p in sample]
                s["latency_p50_ms"], s["latency_p95_ms"] = percentile(lats, 50), percentile(lats, 95)
            latency[m] = {"n": len(ok), "rows": [{"row_id": p.row_id, "latency_ms": p.latency_ms} for p in ok]}
        modes[m] = {"overall": overall, "clean": clean, "per_course": per_course(rows, ps)}
        preds_out += [{**asdict(p), **({"latency_ms": 0.0} if lp is not None else {})} for p in ps]
    run = {"label": label, "system": system_name, "created": datetime.now().isoformat(timespec="seconds"),
           "config": config or {}, "modes": modes, "predictions": preds_out}
    if latency:
        run["latency_sample"] = latency
    return run


def check_targets(summary: dict) -> list[str]:
    misses = []
    for key, (op, target) in TARGETS.items():
        v = summary.get(key)
        if v is None:
            continue
        if (op == ">=" and v < target) or (op == "<=" and v > target):
            misses.append(f"{key} {v:.3f} (target {op} {target:g})")
    return misses


def _f(v) -> str:
    return "—" if v is None else (f"{v:.0f}" if v > 1.0 else f"{v:.3f}")


def write_report(run: dict, out_dir: Path = REPORTS, compare_to: Optional[str] = None) -> tuple[Path, Path]:
    out_dir = Path(out_dir)
    base = None
    if compare_to:  # fail before writing anything
        base_path = out_dir / f"{compare_to}.json"
        if not base_path.exists():
            raise FileNotFoundError(f"--compare: no earlier run labelled {compare_to!r} ({base_path})")
        base = json.loads(base_path.read_text())
    out_dir.mkdir(parents=True, exist_ok=True)
    j, md = out_dir / f"{run['label']}.json", out_dir / f"{run['label']}.md"
    j.write_text(json.dumps(run, indent=1) + "\n")
    text = render_markdown(run)
    cfg = run.get("config") or {}
    if cfg:
        text += "\nRun configuration: " + json.dumps(cfg) + "\n"
    for mode, data in run["modes"].items():
        misses = check_targets(data["overall"])
        n = (run.get("latency_sample") or {}).get(mode, {}).get("n")
        text += (f"\nTargets ({mode}): " + ("all met" if not misses else "MISSED — " + "; ".join(misses))
                 + (f" [latency from a sequential sample of {n} decisions]" if n else "") + "\n")
    if base:
        text += "\n" + compare(base, run)
    md.write_text(text)
    hist = out_dir / "HISTORY.md"
    lines = hist.read_text().splitlines(keepends=True) if hist.exists() else \
        ["# Retrieval eval history\n", "\n", *HISTORY_HEADER.splitlines(keepends=True)]
    for mode, data in run["modes"].items():
        prefix = f"| {run['label']} | {run['system']} | {mode} |"
        lines = [ln for ln in lines if not ln.startswith(prefix)]  # re-running a label replaces its line
        o = data["overall"]
        n = sum(v for k, v in o["counts"].items() if k != "errors")
        lines.append(f"{prefix} {_f(o['recall@1'])} | {_f(o['recall@5'])} | {_f(o['mrr'])} | {_f(o['shown@3'])} | "
                     f"{_f(o['coverage_accuracy'])} | {_f(o['false_cite_rate'])} | {_f(o['navigate_accuracy'])} | "
                     f"{_f(o['latency_p50_ms'])} | {_f(o['latency_p95_ms'])} | {n} |\n")
    hist.write_text("".join(lines))
    return j, md


def make_system(name: str):
    from app.eval import retrieval_systems as rs
    return {"legacy": rs.LegacySystem, "v2": rs.V2System}[name]()


def _memoize_question_embeddings():
    """MAIN pass only (never timed): within a mode the same question is embedded by several code paths, so
    embed it once to save API calls. Returns an undo function; the latency sample runs WITHOUT it."""
    from app.services.embeddings import embedding_service
    orig, memo = embedding_service.embed, {}

    async def embed(text: str):
        if text not in memo:
            memo[text] = await orig(text)
        return memo[text]

    embedding_service.embed = embed

    def undo():
        embedding_service.embed = orig

    return memo, undo


def _git_sha() -> str:
    try:
        sha = subprocess.run(["git", "rev-parse", "--short", "HEAD"], cwd=BACKEND, capture_output=True, text=True).stdout.strip()
        dirty = subprocess.run(["git", "status", "--porcelain", "--untracked-files=no"], cwd=BACKEND,
                               capture_output=True, text=True).stdout.strip()
        return sha + ("+dirty" if dirty else "")
    except Exception:  # noqa: BLE001
        return "unknown"


async def _main(a) -> int:
    os.environ.setdefault("RAG_EMBED_CACHE", str(BACKEND / "data" / "cache" / "embeddings"))
    from app.services.embeddings import embedding_service
    from app.services.vector_store import vector_store
    if os.getenv("DATABASE_URL"):
        print("Refusing to run: DATABASE_URL is set (the eval is local-only; pass DATABASE_URL=)")
        return 2
    if not embedding_service.use_openai:
        print("Refusing to run: no OpenAI embeddings (OPENAI_API_KEY missing); keyword-fallback numbers are meaningless")
        return 2
    if a.compare and not (REPORTS / f"{a.compare}.json").exists():
        print(f"Refusing to run: --compare label {a.compare!r} has no report in {REPORTS}")
        return 2
    from app.eval import retrieval_systems as rs
    from app.services import course_lookup as cl
    modes = a.modes.split(",")
    if a.all_launched and "ask_all" not in modes:
        modes.append("ask_all")
    await vector_store.initialize()
    await rs.own_every_course()
    if "player" in modes:
        await cl.prewarm_titles()  # as the server does at startup
    if any(m.startswith("ask") for m in modes):
        from app.services import catalog_index
        await catalog_index.ensure_built()  # built once per process; keep that one-off cost out of the latencies
    rows = load_rows(limit=a.limit, only=a.only)
    system = make_system(a.system)
    preds, latency, todo_by_mode = {}, {}, {}
    for mode in modes:
        todo_by_mode[mode] = rows_for_mode(list(rows.values()), mode)
    for mode in modes:  # main pass: decision metrics (concurrent, embeddings memoised, latency ignored)
        todo = todo_by_mode[mode]
        print(f"[{mode}] main pass: {len(todo)} rows …", flush=True)
        _, undo = _memoize_question_embeddings()
        try:
            with (rs.all_courses_launched() if mode == "ask_all" else contextlib.nullcontext()):
                preds[mode] = await run_system(system, todo, mode, a.concurrency)
        finally:
            undo()
    for mode in modes:  # latency pass: sequential, nothing else running, no memo
        todo = todo_by_mode[mode]
        print(f"[{mode}] latency sample: {min(a.latency_sample, len(todo))} decisions, concurrency 1 …", flush=True)
        with (rs.all_courses_launched() if mode == "ask_all" else contextlib.nullcontext()):
            latency[mode] = await run_latency_sample(system, todo, mode, a.latency_sample)
    config = {"modes": modes, "concurrency": a.concurrency, "limit": a.limit, "only": a.only,
              "latency_sample": a.latency_sample, "git_sha": _git_sha(), "chunk_count": len(vector_store.chunks),
              "launched": {m: rs.launched_slugs("ask" if m == "ask" else "all") for m in modes if m.startswith("ask")}}
    run = build_run(a.label, system.name, rows, preds, config=config, latency_by_mode=latency)
    j, md = write_report(run, compare_to=a.compare)
    print(md.read_text())
    errors = sum(p.error is not None for ps in list(preds.values()) + list(latency.values()) for p in ps)
    if errors:
        print(f"WARNING: {errors} rows errored (see {j}); numbers exclude them")
    return 0


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--system", default="legacy", choices=["legacy", "v2"])
    ap.add_argument("--label", required=True)
    ap.add_argument("--modes", default="player,ask")
    ap.add_argument("--all-launched", action="store_true", help="also run mode ask_all (every course treated as launched)")
    ap.add_argument("--limit", type=int)
    ap.add_argument("--only")
    ap.add_argument("--concurrency", type=int, default=6)
    ap.add_argument("--latency-sample", type=int, default=60)
    ap.add_argument("--compare")
    return asyncio.run(_main(ap.parse_args(argv)))


if __name__ == "__main__":
    sys.exit(main())
