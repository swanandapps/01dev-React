"""Retrieval eval runner (spec §5). Runs a system over the eval sets in player and/or ask mode and
writes backend/eval/retrieval/reports/<label>.json + .md, appending one line per mode to HISTORY.md.

LOCAL ONLY — the in-memory store; run from backend/ with the key inline and the database off:
  env OPENAI_API_KEY=... DATABASE_URL= .venv/bin/python scripts/eval_retrieval.py --system legacy --label phase1-baseline
Options: --modes player,ask  --limit N (first N rows per set, trial)  --only <slug>  --concurrency 6
         --compare <earlier label>
"""
import argparse
import asyncio
import json
import os
import sys
from dataclasses import asdict
from datetime import datetime
from pathlib import Path
from typing import Optional

BACKEND = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND))

from app.eval.retrieval_metrics import (Prediction, Row, compare, per_course, render_markdown,  # noqa: E402
                                        summarize, summarize_clean)

SETS = [BACKEND / "eval" / "retrieval" / "generated_set.json", BACKEND / "eval" / "retrieval" / "hand_set.json"]
REPORTS = BACKEND / "eval" / "retrieval" / "reports"
TARGETS = {"recall@5": (">=", 0.9), "coverage_accuracy": (">=", 0.9), "false_cite_rate": ("<=", 0.03),
           "latency_p95_ms": ("<=", 1500.0)}
HISTORY_HEADER = ("| label | system | mode | recall@1 | recall@5 | mrr | coverage | false_cite | navigate "
                  "| p50 ms | p95 ms | rows |\n|---|---|---|---|---|---|---|---|---|---|---|---|\n")


def load_rows(paths=SETS, limit: Optional[int] = None, only: Optional[str] = None) -> dict[str, Row]:
    rows: dict[str, Row] = {}
    for p in paths:
        items = [Row.from_dict(d) for d in json.loads(Path(p).read_text())]
        items = [r for r in items if not only or r.scope_course == only]
        for r in items[:limit] if limit else items:
            rows[r.id] = r
    return rows


def rows_for_mode(rows: list[Row], mode: str) -> list[Row]:
    if mode == "ask":
        # No navigation on the Ask page; a cross-course row is taught somewhere in the library; and the Ask
        # page cites only launched courses (F1), so rows of unlaunched courses are out of scope for it.
        from app.services import catalog_service
        launched = {c["slug"] for c in catalog_service.all_courses() if c.get("launched")}
        return [r for r in rows if r.intent != "navigate" and r.style != "cross_course" and r.scope_course in launched]
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


def build_run(label: str, system_name: str, rows: dict[str, Row], preds_by_mode: dict[str, list[Prediction]]) -> dict:
    return {"label": label, "system": system_name, "created": datetime.now().isoformat(timespec="seconds"),
            "modes": {m: {"overall": summarize(rows, ps), "clean": summarize_clean(rows, ps),
                      "per_course": per_course(rows, ps)}
                      for m, ps in preds_by_mode.items()},
            "predictions": [asdict(p) for ps in preds_by_mode.values() for p in ps]}


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
    out_dir.mkdir(parents=True, exist_ok=True)
    j, md = out_dir / f"{run['label']}.json", out_dir / f"{run['label']}.md"
    j.write_text(json.dumps(run, indent=1) + "\n")
    text = render_markdown(run)
    for mode, data in run["modes"].items():
        misses = check_targets(data["overall"])
        text += f"\nTargets ({mode}): " + ("all met" if not misses else "MISSED — " + "; ".join(misses)) + "\n"
    if compare_to:
        base = json.loads((out_dir / f"{compare_to}.json").read_text())
        text += "\n" + compare(base, run)
    md.write_text(text)
    hist = out_dir / "HISTORY.md"
    lines = hist.read_text() if hist.exists() else "# Retrieval eval history\n\n" + HISTORY_HEADER
    for mode, data in run["modes"].items():
        o = data["overall"]
        n = sum(v for k, v in o["counts"].items() if k != "errors")
        lines += (f"| {run['label']} | {run['system']} | {mode} | {_f(o['recall@1'])} | {_f(o['recall@5'])} | "
                  f"{_f(o['mrr'])} | {_f(o['coverage_accuracy'])} | {_f(o['false_cite_rate'])} | "
                  f"{_f(o['navigate_accuracy'])} | {_f(o['latency_p50_ms'])} | {_f(o['latency_p95_ms'])} | {n} |\n")
    hist.write_text(lines)
    return j, md


def make_system(name: str):
    from app.eval import retrieval_systems as rs
    return {"legacy": rs.LegacySystem}[name]()


def _memoize_question_embeddings():
    """Within one mode the same question is embedded by several code paths: embed it once."""
    from app.services.embeddings import embedding_service
    orig, memo = embedding_service.embed, {}

    async def embed(text: str):
        if text not in memo:
            memo[text] = await orig(text)
        return memo[text]

    embedding_service.embed = embed
    return memo


async def _main(a) -> int:
    from app.services.vector_store import vector_store
    if os.getenv("DATABASE_URL"):
        print("Refusing to run: DATABASE_URL is set (the eval is local-only; pass DATABASE_URL=)")
        return 2
    from app.eval.retrieval_systems import own_every_course
    from app.services import course_lookup as cl
    await vector_store.initialize()
    await own_every_course()
    if "player" in a.modes:
        await cl.prewarm_titles()  # as the server does at startup
    if "ask" in a.modes:
        from app.services import catalog_index
        await catalog_index.ensure_built()  # built once per process; keep that one-off cost out of the latencies
    rows = load_rows(limit=a.limit, only=a.only)
    system = make_system(a.system)
    memo = _memoize_question_embeddings()
    preds = {}
    for mode in a.modes.split(","):
        memo.clear()
        todo = rows_for_mode(list(rows.values()), mode)
        print(f"[{mode}] {len(todo)} rows …")
        preds[mode] = await run_system(system, todo, mode, a.concurrency)
    run = build_run(a.label, system.name, rows, preds)
    j, md = write_report(run, compare_to=a.compare)
    print(md.read_text())
    errors = sum(p.error is not None for ps in preds.values() for p in ps)
    if errors:
        print(f"WARNING: {errors} rows errored (see {j}); numbers exclude them")
    return 0


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--system", default="legacy", choices=["legacy", "v2"])
    ap.add_argument("--label", required=True)
    ap.add_argument("--modes", default="player,ask")
    ap.add_argument("--limit", type=int)
    ap.add_argument("--only")
    ap.add_argument("--concurrency", type=int, default=6)
    ap.add_argument("--compare")
    return asyncio.run(_main(ap.parse_args(argv)))


if __name__ == "__main__":
    sys.exit(main())
