"""
Feature 3 — Question generation (per course), as a bounded growing bank.

The question bank is a *cache that grows to a cap*, not a fixed set:
- the first access generates a batch (BATCH_SIZE),
- `top_up()` generates more batches in the background — deduped against what
  exists — until the bank reaches MAX_BANK,
- a course has finite transcript content, so dedupe makes the bank naturally
  plateau well before any hard cap.

Each MCQ has 4 options, a correct index, an explanation, a concept tag, a
difficulty, and the lecture it came from. Adaptive practice (F5) prefers
questions a given user hasn't seen yet, and only repeats as deliberate review.
"""

import asyncio
import hashlib
import random
import re
from datetime import datetime, timezone
from typing import List

from app.models import MCQQuestion, QuestionSet
from app.services.llm import llm, GEN_MODEL
from app.services.store import store
from app.services.vector_store import vector_store

COLLECTION = "questions"
BATCH_SIZE = 12   # questions per generation call
MAX_BANK = 50     # hard cap per course (dedupe usually plateaus earlier)

_in_progress: set[str] = set()

SYSTEM_PROMPT = """You are an expert assessment designer for the 0.1% Dev learning platform.
Given a course's lecture transcripts (each section marked with [Lecture: ...]), write
multiple-choice questions grounded ONLY in those transcripts, spanning the whole course.
Do not test facts that are not supported by the transcripts.

Return a JSON object with EXACTLY this shape:
{
  "questions": [
    {
      "question": "the question text",
      "options": ["A", "B", "C", "D"],          // exactly 4 plausible options
      "correct_index": 0,                         // 0-3, index of the correct option
      "explanation": "one sentence on why it's correct",
      "concept": "a short concept tag (2-4 words)",
      "difficulty": "easy",                       // "easy" | "medium" | "hard"
      "lecture": "the [Lecture: ...] title this question is from"
    }
  ]
}
Produce EXACTLY 12 questions with this difficulty mix: 5 easy, 5 medium, 2 hard.
Use 4-6 distinct concept tags across the questions (several questions share a concept)
so adaptive practice has multiple questions per concept at different difficulties.
Spread questions across the course's lectures. Vary the correct answer position."""


def _norm(text: str) -> str:
    return " ".join(text.strip().lower().split())


def _tag_key(tag: str) -> str:
    """Forgives only case / whitespace / hyphen-underscore differences:
    "Use Memo" and " use_memo " both key to "use-memo"; "useMemo hook" does not."""
    return re.sub(r"[\s_-]+", "-", tag.strip().lower()).strip("-")


async def _course_tags(course_id: str) -> list[dict]:
    """The course's fixed concept tags from the knowledge graph ({name, description}).
    Queried here rather than via knowledge_graph_service, which imports this module."""
    rows = await store.query("concepts", "course_id", course_id)
    return sorted(({"name": r["name"], "description": r.get("description") or ""}
                   for r in rows if r.get("name")), key=lambda t: t["name"])


def _tag_instructions(tags: list[dict], existing: list) -> str:
    counts = {t["name"]: 0 for t in tags}
    for q in existing:
        if q.get("concept") in counts:
            counts[q["concept"]] += 1
    lines = "\n".join(f"- {t['name']}" + (f": {t['description']}" if t["description"] else "") for t in tags)
    fewest = ", ".join(sorted(counts, key=lambda n: (counts[n], n)))
    return (
        "\n\nALLOWED CONCEPT TAGS (this overrides the concept-tag guidance above): the \"concept\" "
        "field MUST be exactly one of these tags, copied verbatim. Never invent, rename or combine tags; "
        f"questions with any other tag are discarded.\n{lines}\n"
        f"Spread the questions across these tags, favouring the ones the bank has fewest of "
        f"(fewest first): {fewest}"
    )


def _question_id(course_id: str, question: str, correct_option: str) -> str:
    """Content-based, so a new question can never take an id that older banks
    (and other students' recorded answers) already use."""
    return f"{course_id}-h{hashlib.sha1((question + correct_option).encode()).hexdigest()[:10]}"


async def get_status(course_id: str) -> dict:
    doc = await store.get(COLLECTION, course_id)
    if doc:
        return {"status": "ready", "questions": doc}
    if course_id in _in_progress:
        return {"status": "generating", "questions": None}
    return {"status": "none", "questions": None}


async def ensure_generated(course_id: str) -> dict:
    existing = await store.get(COLLECTION, course_id)
    if existing:
        return {"status": "ready", "questions": existing}
    if course_id not in _in_progress:
        _in_progress.add(course_id)
        asyncio.create_task(_generate(course_id, initial=True))
    return {"status": "generating", "questions": None}


async def top_up(course_id: str) -> None:
    """Grow the bank toward MAX_BANK in the background (deduped). No-op if the
    bank doesn't exist yet, is already at the cap, or generation is in flight."""
    doc = await store.get(COLLECTION, course_id)
    if not doc or len(doc.get("questions", [])) >= MAX_BANK:
        return
    if course_id in _in_progress:
        return
    _in_progress.add(course_id)
    asyncio.create_task(_generate(course_id, initial=False))


async def _generate(course_id: str, initial: bool) -> None:
    try:
        meta = vector_store.get_course_meta(course_id)
        transcript = vector_store.get_course_transcript(course_id)
        if not meta or not transcript:
            return

        existing = [] if initial else (await store.get(COLLECTION, course_id) or {}).get("questions", [])
        avoid_norms = {_norm(q["question"]) for q in existing}
        tags = await _course_tags(course_id)

        # When topping up, tell the model what already exists so it diverges.
        prompt = SYSTEM_PROMPT
        if existing:
            stems = "\n".join(f"- {q['question']}" for q in existing[-25:])
            prompt += f"\n\nDo NOT repeat or lightly reword any of these existing questions:\n{stems}"
        # A course with a concept graph is tag-locked: the rest of the app keys on these tags.
        if tags:
            prompt += _tag_instructions(tags, existing)

        data = await llm.generate_json(
            prompt,
            f"Course: {meta['course_title']} ({meta['lecture_count']} lectures)\n\n"
            f"Transcripts:\n{transcript}",
            max_tokens=2600,
        )
        if not data or "questions" not in data:
            return

        new = _build_questions(
            course_id, data["questions"], avoid_norms=avoid_norms,
            avoid_ids={q["id"] for q in existing},
            allowed_tags=[t["name"] for t in tags] or None,
        )
        new = new[:max(0, MAX_BANK - len(existing))]  # existing questions are never dropped
        if not new:
            return

        merged = existing + [q.model_dump() for q in new]
        qset = QuestionSet(
            course_id=course_id,
            course_title=meta["course_title"],
            questions=[MCQQuestion(**q) for q in merged],
            model=GEN_MODEL,
            generated_at=datetime.now(timezone.utc).isoformat(),
        )
        await store.set(COLLECTION, course_id, qset.model_dump())
    except Exception as e:  # noqa: BLE001
        print(f"question_service: generation failed for {course_id}: {e}")
    finally:
        _in_progress.discard(course_id)


def _build_questions(
    course_id: str, raw: list, avoid_norms: set, avoid_ids: set = frozenset(),
    allowed_tags: list[str] | None = None,
) -> List[MCQQuestion]:
    """Validate raw LLM questions. With `allowed_tags`, a question's concept must
    match one of them up to case/whitespace/hyphen (stored as the canonical tag);
    anything else is dropped. Without it, concept tags are free text."""
    canonical = {_tag_key(t): t for t in allowed_tags} if allowed_tags else None
    out: List[MCQQuestion] = []
    seen = set(avoid_norms)
    ids = set(avoid_ids)
    for q in raw:
        if not isinstance(q, dict):
            continue
        opts = q.get("options", [])
        if not isinstance(opts, list) or len(opts) != 4:
            continue
        concept = q.get("concept") or "General"
        if canonical is not None:
            concept = canonical.get(_tag_key(str(concept)))
            if concept is None:
                continue
        norm = _norm(q.get("question", ""))
        if not norm or norm in seen:  # dedupe within batch and against the bank
            continue

        ci = q.get("correct_index", 0)
        ci = ci if isinstance(ci, int) and 0 <= ci <= 3 else 0
        diff = q.get("difficulty", "medium")
        diff = diff if diff in ("easy", "medium", "hard") else "medium"

        correct_option = opts[ci]
        qid = _question_id(course_id, q.get("question", ""), str(correct_option))
        if qid in ids:  # never reuse an id the bank already has
            continue
        seen.add(norm)
        ids.add(qid)

        # Shuffle so the correct answer isn't always first.
        shuffled = opts[:]
        random.shuffle(shuffled)
        ci = shuffled.index(correct_option)

        out.append(
            MCQQuestion(
                id=qid,
                question=q.get("question", ""),
                options=shuffled,
                correct_index=ci,
                explanation=q.get("explanation", ""),
                concept=concept,
                difficulty=diff,
                lecture=q.get("lecture", ""),
            )
        )
    return out
