"""
Durable store for eval / RAGAS / GEPA results.

Turns "we ran it once and read the terminal" into "quality is tracked over time":
- appends every run to an append-only history log (`data/eval_results/history.jsonl`)
- writes one JSON snapshot per run

Stdlib only, so it's importable from every venv in the repo (main backend, RAGAS).
This is the foundation self-improvement needs — you can't accumulate gains or spot
regressions without a record.
"""
import json
from datetime import datetime, timezone
from pathlib import Path

_DIR = Path(__file__).resolve().parents[2] / "data" / "eval_results"  # backend/data/eval_results
_HISTORY = _DIR / "history.jsonl"


def record(kind: str, metrics: dict, meta: dict | None = None) -> dict:
    """Append one result row (kind = accuracy | ragas | gepa | gepa_apply)."""
    _DIR.mkdir(parents=True, exist_ok=True)
    row = {
        "ts": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "kind": kind,
        "metrics": metrics,
        "meta": meta or {},
    }
    with _HISTORY.open("a") as f:
        f.write(json.dumps(row) + "\n")
    stamp = row["ts"].replace(":", "").replace("-", "")
    (_DIR / f"{kind}-{stamp}.json").write_text(json.dumps(row, indent=2))
    return row


def history(kind: str | None = None, limit: int = 50) -> list[dict]:
    """Read back recorded runs (newest last), optionally filtered by kind."""
    if not _HISTORY.exists():
        return []
    rows = [json.loads(ln) for ln in _HISTORY.read_text().splitlines() if ln.strip()]
    if kind:
        rows = [r for r in rows if r.get("kind") == kind]
    return rows[-limit:]


def _print_trend() -> None:
    rows = history(limit=500)
    if not rows:
        print("No results recorded yet. Run an eval (accuracy.py / ragas_eval.py / GEPA).")
        return
    by_kind: dict[str, list] = {}
    for r in rows:
        by_kind.setdefault(r["kind"], []).append(r)
    for kind, rs in by_kind.items():
        print(f"\n=== {kind}  ({len(rs)} runs) ===")
        for r in rs[-10:]:
            m = "  ".join(f"{k}={v}" for k, v in r["metrics"].items())
            print(f"  {r['ts']}   {m}")


if __name__ == "__main__":
    _print_trend()
