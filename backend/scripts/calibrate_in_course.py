"""Measure in-course (player) scores on labelled questions for Build a Custom Library:
bare-question chunk score, the same question prefixed with the lecture being watched (shows the
inflation), and the lecture-title score. Check RELATED / TRANSCRIPT / TITLE thresholds. Needs the real
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
WATCHING = "8.1 - The `npm link` command"
# (question, label): "match" = a lecture of this course answers it; "none" = nothing in this
# course is about it. (closure / semver / symlink were dropped: no transcript mentions them.)
LABELLED = [
    ("how do I publish my package with np", "match"),
    ("what does npm link do", "match"),
    ("what is an IIFE and why do we use it", "match"),
    ("how do I attach my library to the window object", "match"),
    ("what are ES modules", "match"),
    ("how do regular expressions help build the library methods", "match"),
    ("how do I bake sourdough bread", "none"),
    ("how does React reconciliation work", "none"),
    ("what is a SQL join", "none"),
    ("how does kubernetes schedule pods", "none"),
    ("what is the CSS box model", "none"),
    ("how does the event loop work", "none"),
]
UNLABELLED = ["give me an example", "take me to ES modules", "take me to where you publish the npm package"]


async def bare(q: str):
    rows = await cl.search_in_course(q, SLUG, top_k=1)
    return (rows[0][1], rows[0][0].lecture_title) if rows else (0.0, "-")


async def prefixed(q: str, lecture: str):
    rows = await cl.search_in_course(f"{lecture} {q}", SLUG, top_k=1)
    return (rows[0][1], rows[0][0].lecture_title) if rows else (0.0, "-")


async def title(q: str):
    sc = await cl._title_scores(q, SLUG)
    t = max(sc, key=sc.get)
    return sc[t], t


async def main() -> None:
    bare_by = {"match": [], "none": []}
    title_by = {"match": [], "none": []}
    print(f"{'label':8} {'bare':>5} {'pref@8.1':>8} {'title':>5}  best bare lecture | best title lecture | question")
    for q, label in LABELLED + [(q, "?") for q in UNLABELLED]:
        (b, bt), (p, pt), (t, tt) = await bare(q), await prefixed(q, WATCHING), await title(q)
        if label != "?":
            bare_by[label].append(b)
            title_by[label].append(t)
        print(f"{label:8} {b:5.3f} {p:8.3f} {t:5.3f}  {bt[:30]:30} | {tt[:30]:30} | {q}")
    print(f"\nbare: none max {max(bare_by['none']):.3f} | match min {min(bare_by['match']):.3f}"
          f" | TRANSCRIPT_THRESHOLD {cl.TRANSCRIPT_THRESHOLD} | RELATED_THRESHOLD {cl.RELATED_THRESHOLD}")
    print(f"title: none max {max(title_by['none']):.3f} | match min {min(title_by['match']):.3f}"
          f" | TITLE_THRESHOLD {cl.TITLE_THRESHOLD}")


asyncio.run(main())
