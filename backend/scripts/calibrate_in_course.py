"""Measure in-course (player) transcript scores on labelled questions for Build a Custom
Library and suggest course_lookup.RELATED_THRESHOLD (spec §3.2). Needs the real
transcripts in seed_transcripts.json.

Run from backend/ (blanks DATABASE_URL itself — in-memory store, never production):
    .venv/bin/python scripts/calibrate_in_course.py
"""
import asyncio
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from dotenv import load_dotenv  # noqa: E402

os.environ["DATABASE_URL"] = ""
load_dotenv(Path(__file__).resolve().parents[1] / ".env")

if not os.getenv("OPENAI_API_KEY"):
    print("calibrate_in_course: OPENAI_API_KEY is not set — thresholds are only meaningful "
          "for OpenAI embeddings. Aborting.")
    sys.exit(2)

from app.services import course_lookup as cl  # noqa: E402

SLUG = "custom-library"
# (question, label): "match" = a lecture of this course answers it; "related" = a lecture
# touches on it; "none" = nothing in this course is about it.
LABELLED = [
    ("how do I publish my package with np", "match"),
    ("what does npm link do", "match"),
    ("what is an IIFE and why do we use it", "match"),
    ("how do I attach my library to the window object", "match"),
    ("what are ES modules", "match"),
    ("how do regular expressions help build the library methods", "match"),
    ("what is a closure in javascript", "related"),
    ("how does semantic versioning decide the next version number", "related"),
    ("what is a symlink", "related"),
    ("how do I write unit tests with jest", "related"),
    ("how do I bake sourdough bread", "none"),
    ("how does React reconciliation work", "none"),
    ("what is a SQL join", "none"),
    ("how does kubernetes schedule pods", "none"),
    ("what is the CSS box model", "none"),
]
UNLABELLED = ["how does the event loop work", "give me an example", "take me to where you publish the npm package"]


async def best(q: str):
    rows = await cl.search_in_course(q, SLUG, top_k=1)
    return (rows[0][1], rows[0][0].lecture_title, rows[0][0].start_time) if rows else (0.0, "-", 0)


async def main() -> None:
    scored = []
    for q, label in LABELLED + [(q, "?") for q in UNLABELLED]:
        s, title, t = await best(q)
        if label != "?":
            scored.append((label, s))
        print(f"{label:8} {s:.3f}  {title[:44]:44} {t // 60:02d}:{t % 60:02d}  {q}")
    none_max = max(s for l, s in scored if l == "none")
    related_min = min(s for l, s in scored if l == "related")
    match_min = min(s for l, s in scored if l == "match")
    print(f"\nnone max {none_max:.3f} | related min {related_min:.3f} | match min {match_min:.3f} "
          f"| TRANSCRIPT_THRESHOLD {cl.TRANSCRIPT_THRESHOLD} | current RELATED_THRESHOLD {cl.RELATED_THRESHOLD}")
    cap = round(cl.TRANSCRIPT_THRESHOLD - 0.02, 2)
    if related_min > none_max:
        pick = round((none_max + related_min) / 2, 2)
        how = "midpoint of none-max and related-min"
    else:
        pick = round(none_max + 0.01, 2)
        how = "no clean split — just above the best 'none'"
    print(f"suggested RELATED_THRESHOLD = {min(pick, cap):.2f} ({how}; capped at {cap})")


asyncio.run(main())
