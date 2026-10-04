"""Measure transcript/catalog similarity scores on labelled questions and pick
course_lookup thresholds from the data (same method Lab used for its 0.64).

Run from backend/ (blank DATABASE_URL keeps it off the production DB):
    env DATABASE_URL= .venv/bin/python scripts/calibrate_lookup.py
"""
import asyncio
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from dotenv import load_dotenv  # noqa: E402

load_dotenv(Path(__file__).resolve().parents[1] / ".env")

if not os.getenv("OPENAI_API_KEY"):
    print("calibrate_lookup: OPENAI_API_KEY is not set. Thresholds are only meaningful "
          "for OpenAI embeddings (the local hash fallback is not comparable) — aborting.")
    sys.exit(2)

from app.services import catalog_index, course_lookup as cl  # noqa: E402

# (question, covered_by_a_transcript, covered_by_the_catalog)
LABELLED = [
    ("how do I publish an npm library", True, True),
    ("how does npm link work", True, True),
    ("what is prototype inheritance in javascript", True, True),
    ("how does the websocket handshake work", True, True),
    ("what are hidden classes in V8", True, True),
    ("when should I use useMemo for computed state", True, True),
    ("explain the event loop and microtasks", True, True),
    ("long polling vs websockets, which should I use", True, True),
    ("does React.memo need useCallback", True, True),
    ("how do I write a lexer for my own language", False, True),
    ("how do I build an abstract syntax tree", False, True),
    ("what is time-travel debugging in a state library", False, True),
    ("how do I build a router for a web framework", False, True),
    ("what does TurboFan do in V8", False, True),
    ("how does pub/sub work in a real-time system", False, True),
    ("how do I avoid polluting the window object", False, True),
    ("how do I bake sourdough bread", False, False),
    ("what's the best gaming laptop in 2026", False, False),
    ("explain photosynthesis", False, False),
    ("how do I file my taxes", False, False),
    ("who won the football world cup", False, False),
    ("how do I set up kubernetes autoscaling", False, False),
    ("write me a poem about the sea", False, False),
]


def best_threshold(pos: list[float], neg: list[float]) -> tuple[float, float, float, float]:
    """Return (threshold, accuracy, lo, hi): the midpoint of the first contiguous run
    of grid thresholds (0.10–0.80, step 0.01) that reach the maximum accuracy, so the
    chosen value sits mid-gap rather than just above the highest negative."""
    def acc(i: int) -> float:
        t = i / 100
        return (sum(s >= t for s in pos) + sum(s < t for s in neg)) / (len(pos) + len(neg))

    grid = range(10, 81)
    scores = {i: acc(i) for i in grid}
    best = max(scores.values())
    lo = hi = min(i for i in grid if scores[i] == best)
    while hi + 1 in scores and scores[hi + 1] == best:
        hi += 1
    mid = round((lo + hi) / 2)  # integer hundredths: deterministic, no float-rounding surprises
    return mid / 100, best, lo / 100, hi / 100


async def main() -> None:
    await catalog_index.ensure_built()
    rows = []
    for q, in_transcript, in_catalog in LABELLED:
        t = await cl._transcript_hits(q)
        c = await catalog_index.search(q, top_k=1)
        rows.append((q, in_transcript, in_catalog, t[0][1] if t else 0.0, c[0][1] if c else 0.0))
    print(f"{'question':55} {'T?':3} {'C?':3} {'t_score':>8} {'c_score':>8}")
    for q, it, ic, ts, cs in rows:
        print(f"{q[:55]:55} {'Y' if it else '-':3} {'Y' if ic else '-':3} {ts:8.3f} {cs:8.3f}")
    t_thr, t_acc, t_lo, t_hi = best_threshold([r[3] for r in rows if r[1]], [r[3] for r in rows if not r[1]])
    c_thr, c_acc, c_lo, c_hi = best_threshold([r[4] for r in rows if r[2]], [r[4] for r in rows if not r[2]])
    print(f"\nTRANSCRIPT_THRESHOLD = {t_thr:.2f}   (accuracy {t_acc:.0%}, max-accuracy range {t_lo:.2f}–{t_hi:.2f})")
    print(f"CATALOG_THRESHOLD    = {c_thr:.2f}   (accuracy {c_acc:.0%}, max-accuracy range {c_lo:.2f}–{c_hi:.2f})")


if __name__ == "__main__":
    asyncio.run(main())
