"""
ONE-TIME generator for the demo courses' question banks.

For each course in app/data/demo/taxonomy.json, asks the LLM for a QuestionSet
grounded ONLY in that course's transcript chunks (app/data/seed_transcripts.json)
and restricted to the course's FIXED concept tags: 6 questions per tag
(2 easy, 2 medium, 2 hard), each tied to a real lecture title of the course.

Why fixed tags: question_service lets the LLM invent free-text tags
("useMemo hook"), which never match the seeded knowledge graph / performance
tags (`use-memo`) — silently breaking insights, weak-concept hints and
prerequisite gating. Seeding these banks makes every layer share one taxonomy.

Every question is validated (4 distinct options, correct_index 0-3, tag in the
taxonomy, difficulty easy/medium/hard, lecture exists); a course is retried up
to 2x if it doesn't yield 2 valid questions per (tag, difficulty) — valid
questions are kept and a retry asks only for the slots still missing.

Output: app/data/demo/question_banks.json — {slug: QuestionSet dict}. Commit it;
it's reviewable content. scripts/seed_demo_account.py loads it.

Run (never against prod — no store is touched, but blank it anyway):
  cd backend && env DATABASE_URL= FIREBASE_SERVICE_ACCOUNT_JSON= GOOGLE_APPLICATION_CREDENTIALS= \
      LANGSMITH_TRACING=false .venv/bin/python scripts/build_demo_question_banks.py
"""
import asyncio
import json
import os
import random
import sys
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

BACKEND = Path(__file__).resolve().parent.parent
DEMO_DIR = BACKEND / "app" / "data" / "demo"
TAXONOMY_PATH = DEMO_DIR / "taxonomy.json"
BANKS_PATH = DEMO_DIR / "question_banks.json"
TRANSCRIPTS_PATH = BACKEND / "app" / "data" / "seed_transcripts.json"

PER_DIFFICULTY = 2
DIFFICULTIES = ("easy", "medium", "hard")
MAX_RETRIES = 2

SYSTEM_PROMPT = """You are an expert assessment designer for the 0.1% Dev learning platform.
Given ONE course's lecture transcripts (each section marked with [Lecture: ...]) and a FIXED
list of concept tags, write multiple-choice questions grounded ONLY in those transcripts.
Do not test facts that are not supported by the transcripts.

Return a JSON object with EXACTLY this shape:
{
  "questions": [
    {
      "question": "the question text",
      "options": ["A", "B", "C", "D"],          // exactly 4 distinct, plausible options
      "correct_index": 0,                         // 0-3, index of the correct option
      "explanation": "one sentence on why it's correct, grounded in the transcript",
      "concept": "<one of the given concept tags, copied EXACTLY>",
      "difficulty": "easy",                       // "easy" | "medium" | "hard"
      "lecture": "<the exact [Lecture: ...] title this question is from>"
    }
  ]
}
Write exactly the number of questions requested per (concept, difficulty) slot.
- easy: recall a single fact stated in the lecture.
- medium: apply the idea to a small, concrete scenario.
- hard: reason about a pitfall, an ordering, or a trade-off the lecture describes.
Use ONLY the given concept tags (never invent or reword a tag). Never repeat a question."""


def load_taxonomy() -> dict:
    return json.loads(TAXONOMY_PATH.read_text())["courses"]


def load_chunks(slug: str) -> list[dict]:
    chunks = [c for c in json.loads(TRANSCRIPTS_PATH.read_text()) if c["course_id"] == slug]
    chunks.sort(key=lambda c: (c["lecture_id"], c["start_time"]))
    return chunks


def lecture_titles(chunks: list[dict]) -> list[str]:
    return list(dict.fromkeys(c["lecture_title"] for c in chunks))


def transcript_text(chunks: list[dict]) -> str:
    parts, current = [], None
    for c in chunks:
        if c["lecture_id"] != current:
            current = c["lecture_id"]
            parts.append(f"\n[Lecture: {c['lecture_title']}]")
        parts.append(c["text"])
    return "\n\n".join(parts).strip()


def _norm(text: str) -> str:
    return " ".join(str(text).strip().lower().split())


def question_errors(q: dict, tags: set, lectures: set) -> list[str]:
    """Why a raw LLM question is invalid ([] = valid)."""
    errs = []
    if not isinstance(q, dict):
        return ["not an object"]
    if not _norm(q.get("question", "")):
        errs.append("empty question")
    opts = q.get("options")
    if not isinstance(opts, list) or len(opts) != 4:
        errs.append("options must be a list of 4")
    elif len({_norm(o) for o in opts}) != 4 or any(not _norm(o) for o in opts):
        errs.append("options must be 4 distinct non-empty strings")
    ci = q.get("correct_index")
    if not isinstance(ci, int) or isinstance(ci, bool) or not 0 <= ci <= 3:
        errs.append("correct_index must be an int 0-3")
    if q.get("concept") not in tags:
        errs.append(f"concept {q.get('concept')!r} not in taxonomy")
    if q.get("difficulty") not in DIFFICULTIES:
        errs.append(f"difficulty {q.get('difficulty')!r} invalid")
    if q.get("lecture") not in lectures:
        errs.append(f"lecture {q.get('lecture')!r} not a lecture of this course")
    if not _norm(q.get("explanation", "")):
        errs.append("empty explanation")
    return errs


def add_valid(raw: list, buckets: dict, seen: set, tags: list[str], lectures: list[str]) -> list[str]:
    """Fold valid, de-duplicated raw questions into buckets[(tag, difficulty)].
    Returns the problems found (invalid questions) for logging."""
    tag_set, lecture_set = set(tags), set(lectures)
    problems = []
    for i, q in enumerate(raw or []):
        errs = question_errors(q, tag_set, lecture_set)
        if errs:
            problems.append(f"q{i}: {'; '.join(errs)}")
            continue
        key = _norm(q["question"])
        if key in seen:
            continue
        seen.add(key)
        buckets[(q["concept"], q["difficulty"])].append(q)
    return problems


def missing_buckets(buckets: dict, tags: list[str]) -> dict:
    """{(tag, difficulty): how many more are needed}."""
    return {
        (t, d): PER_DIFFICULTY - len(buckets[(t, d)])
        for t in tags for d in DIFFICULTIES if len(buckets[(t, d)]) < PER_DIFFICULTY
    }


def finalize(buckets: dict, slug: str, tags: list[str]) -> list[dict]:
    """PER_DIFFICULTY per (tag, difficulty) in tag order, ids {slug}-q{n},
    options deterministically shuffled so the answer isn't always option 0."""
    out: list[dict] = []
    for t in tags:
        for d in DIFFICULTIES:
            for q in buckets[(t, d)][:PER_DIFFICULTY]:
                qid = f"{slug}-q{len(out) + 1}"
                correct = str(q["options"][q["correct_index"]]).strip()
                opts = [str(o).strip() for o in q["options"]]
                random.Random(qid).shuffle(opts)
                out.append({
                    "id": qid,
                    "question": q["question"].strip(),
                    "options": opts,
                    "correct_index": opts.index(correct),
                    "explanation": q["explanation"].strip(),
                    "concept": t,
                    "difficulty": d,
                    "lecture": q["lecture"],
                })
    return out


async def build_course(slug: str, course: dict) -> dict:
    """Up to 1 + MAX_RETRIES attempts. Valid questions are kept across attempts;
    a retry asks only for the (tag, difficulty) slots still missing."""
    from app.services.llm import GEN_MODEL, llm

    chunks = load_chunks(slug)
    lectures = lecture_titles(chunks)
    tags = [c["name"] for c in course["concepts"]]
    tag_lines = "\n".join(f"- {c['name']}: {c['description']}" for c in course["concepts"])
    header = (
        f"Course: {course['title']} ({len(lectures)} lectures)\n"
        f"Lecture titles (use exactly): {json.dumps(lectures)}\n\n"
        f"Concept tags (use exactly):\n{tag_lines}\n\n"
        f"Transcripts:\n{transcript_text(chunks)}\n\n"
    )
    buckets: dict = defaultdict(list)
    seen: set = set()
    for attempt in range(1, MAX_RETRIES + 2):
        need = missing_buckets(buckets, tags)
        if not need:
            break
        ask = "\n".join(f"- concept {t!r}, difficulty {d!r}: exactly {n}" for (t, d), n in need.items())
        avoid = "\n".join(f"- {q['question']}" for qs in buckets.values() for q in qs)
        user = header + f"Write EXACTLY these questions ({sum(need.values())} total):\n{ask}"
        if avoid:
            user += f"\n\nDo NOT repeat or reword these existing questions:\n{avoid}"
        data = await llm.generate_json(SYSTEM_PROMPT, user, temperature=0.4, max_tokens=9000)
        problems = add_valid((data or {}).get("questions"), buckets, seen, tags, lectures)
        left = missing_buckets(buckets, tags)
        print(f"  [{slug}] attempt {attempt}: invalid={len(problems)} still-missing={sum(left.values())}"
              + (f" {problems}" if problems else ""))
    if missing_buckets(buckets, tags):
        raise SystemExit(f"{slug}: incomplete bank after {MAX_RETRIES + 1} attempts — nothing written")
    return {
        "course_id": slug,
        "course_title": course["title"],
        "questions": finalize(buckets, slug, tags),
        "model": GEN_MODEL,
        "generated_at": datetime.now(timezone.utc).isoformat(),
    }


async def main() -> None:
    from app.services.llm import llm

    if not llm.available:
        raise SystemExit("OPENAI_API_KEY not set — cannot generate banks.")
    taxonomy = load_taxonomy()
    banks = {}
    for slug, course in taxonomy.items():
        print(f"Generating {slug} ...")
        banks[slug] = await build_course(slug, course)
        print(f"  {slug}: {len(banks[slug]['questions'])} questions")
    BANKS_PATH.write_text(json.dumps(banks, indent=2, ensure_ascii=False) + "\n")
    print(f"Wrote {BANKS_PATH}")


if __name__ == "__main__":
    # Never touch a real store from this script: blank the store backends
    # BEFORE app modules (or .env) are loaded; load_dotenv never overrides.
    for var in ("DATABASE_URL", "FIREBASE_SERVICE_ACCOUNT_JSON", "GOOGLE_APPLICATION_CREDENTIALS"):
        os.environ[var] = ""
    os.environ.setdefault("LANGSMITH_TRACING", "false")
    sys.path.insert(0, str(BACKEND))
    from dotenv import load_dotenv

    load_dotenv(BACKEND / ".env")
    asyncio.run(main())
