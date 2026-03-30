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
import random
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

        # When topping up, tell the model what already exists so it diverges.
        prompt = SYSTEM_PROMPT
        if existing:
            stems = "\n".join(f"- {q['question']}" for q in existing[-25:])
            prompt += f"\n\nDo NOT repeat or lightly reword any of these existing questions:\n{stems}"

        data = await llm.generate_json(
            prompt,
            f"Course: {meta['course_title']} ({meta['lecture_count']} lectures)\n\n"
            f"Transcripts:\n{transcript}",
            max_tokens=2600,
        )
        if not data or "questions" not in data:
            return

        new = _build_questions(course_id, data["questions"], start_index=len(existing), avoid_norms=avoid_norms)
        if not new:
            return

        merged = (existing + [q.model_dump() for q in new])[:MAX_BANK]
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


def _build_questions(course_id: str, raw: list, start_index: int, avoid_norms: set) -> List[MCQQuestion]:
    out: List[MCQQuestion] = []
    seen = set(avoid_norms)
    for q in raw:
        opts = q.get("options", [])
        if len(opts) != 4:
            continue
        norm = _norm(q.get("question", ""))
        if not norm or norm in seen:  # dedupe within batch and against the bank
            continue
        seen.add(norm)

        ci = q.get("correct_index", 0)
        ci = ci if isinstance(ci, int) and 0 <= ci <= 3 else 0
        diff = q.get("difficulty", "medium")
        diff = diff if diff in ("easy", "medium", "hard") else "medium"

        # Shuffle so the correct answer isn't always first.
        correct_option = opts[ci]
        shuffled = opts[:]
        random.shuffle(shuffled)
        ci = shuffled.index(correct_option)

        out.append(
            MCQQuestion(
                id=f"{course_id}-q{start_index + len(out) + 1}",
                question=q.get("question", ""),
                options=shuffled,
                correct_index=ci,
                explanation=q.get("explanation", ""),
                concept=q.get("concept", "General"),
                difficulty=diff,
                lecture=q.get("lecture", ""),
            )
        )
    return out
