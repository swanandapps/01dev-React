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
# Recorded run 2026-10-06 (358-chunk seed, text-embedding-3-small); @8.1 / @1.1 = question prefixed
# with the lecture being watched. Prefixing inflates off-topic scores to 0.50-0.61 at 8.1.
#   match  bare 0.681  @8.1 0.626  @1.1 0.669  title 0.755  how do I publish my package with np
#   match  bare 0.696  @8.1 0.644  @1.1 0.643  title 0.839  what does npm link do
#   match  bare 0.479  @8.1 0.556  @1.1 0.494  title 0.658  what is an IIFE and why do we use it
#   match  bare 0.666  @8.1 0.696  @1.1 0.619  title 0.695  how do I attach my library to the window object
#   match  bare 0.422  @8.1 0.616  @1.1 0.404  title 0.958  what are ES modules
#   match  bare 0.623  @8.1 0.597  @1.1 0.585  title 0.645  how do regular expressions help build the library methods
#   none   bare 0.182  @8.1 0.502  @1.1 0.317  title 0.195  how do I bake sourdough bread
#   none   bare 0.452  @8.1 0.573  @1.1 0.457  title 0.318  how does React reconciliation work
#   none   bare 0.193  @8.1 0.540  @1.1 0.322  title 0.203  what is a SQL join
#   none   bare 0.257  @8.1 0.520  @1.1 0.300  title 0.200  how does kubernetes schedule pods
#   none   bare 0.392  @8.1 0.560  @1.1 0.391  title 0.342  what is the CSS box model
#   none   bare 0.406  @8.1 0.606  @1.1 0.416  title 0.305  how does the event loop work
#   ?      bare 0.316  @8.1 0.635  @1.1 0.407  title 0.244  give me an example
#   ?      bare 0.448  @8.1 0.617  @1.1 0.424  title 0.720  take me to ES modules
#   ?      bare 0.618  @8.1 0.608  @1.1 0.622  title 0.577  take me to where you publish the npm package
# bare: none max 0.452 | match min 0.422 | TRANSCRIPT_THRESHOLD 0.54 | RELATED_THRESHOLD 0.4
# title: none max 0.342 | match min 0.645 | TITLE_THRESHOLD 0.6
WATCHING = "8.1 - The `npm link` command"
WATCHING_B = "1.1 - What is this course"
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
    print(f"{'label':8} {'bare':>5} {'pref@8.1':>8} {'pref@1.1':>8} {'title':>5}  best bare lecture | best title lecture | question")
    for q, label in LABELLED + [(q, "?") for q in UNLABELLED]:
        (b, bt), (p, pt), (p2, _), (t, tt) = await bare(q), await prefixed(q, WATCHING), await prefixed(q, WATCHING_B), await title(q)
        if label != "?":
            bare_by[label].append(b)
            title_by[label].append(t)
        print(f"{label:8} {b:5.3f} {p:8.3f} {p2:8.3f} {t:5.3f}  {bt[:30]:30} | {tt[:30]:30} | {q}")
    print(f"\nbare: none max {max(bare_by['none']):.3f} | match min {min(bare_by['match']):.3f}"
          f" | TRANSCRIPT_THRESHOLD {cl.TRANSCRIPT_THRESHOLD} | RELATED_THRESHOLD {cl.RELATED_THRESHOLD}")
    print(f"title: none max {max(title_by['none']):.3f} | match min {min(title_by['match']):.3f}"
          f" | TITLE_THRESHOLD {cl.TITLE_THRESHOLD}")


asyncio.run(main())
