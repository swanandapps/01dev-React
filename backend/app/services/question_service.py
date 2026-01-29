"""
Feature 3 — Question generation (per course).

One GPT call per course produces 12 MCQs drawn from across the course's lectures
(mix: 5 easy, 5 medium, 2 hard), each with 4 options, a correct index, a
one-sentence explanation, a concept tag, a difficulty, and the lecture it came
from. Stored so the quiz (F4) and adaptive layer (F5) can reuse them.
"""

import asyncio
import random
from datetime import datetime, timezone

from app.models import MCQQuestion, QuestionSet
from app.services.llm import llm, GEN_MODEL
from app.services.store import store
from app.services.vector_store import vector_store

COLLECTION = "questions"

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
        asyncio.create_task(_generate(course_id))
    return {"status": "generating", "questions": None}


async def _generate(course_id: str) -> None:
    try:
        meta = vector_store.get_course_meta(course_id)
        transcript = vector_store.get_course_transcript(course_id)
        if not meta or not transcript:
            return

        data = await llm.generate_json(
            SYSTEM_PROMPT,
            f"Course: {meta['course_title']} ({meta['lecture_count']} lectures)\n\n"
            f"Transcripts:\n{transcript}",
            max_tokens=2600,
        )
        if not data or "questions" not in data:
            return

        questions = []
        for i, q in enumerate(data["questions"]):
            opts = q.get("options", [])
            if len(opts) != 4:
                continue
            ci = q.get("correct_index", 0)
            ci = ci if isinstance(ci, int) and 0 <= ci <= 3 else 0
            diff = q.get("difficulty", "medium")
            diff = diff if diff in ("easy", "medium", "hard") else "medium"

            # Shuffle so the correct answer isn't always first.
            correct_option = opts[ci]
            shuffled = opts[:]
            random.shuffle(shuffled)
            ci = shuffled.index(correct_option)

            questions.append(
                MCQQuestion(
                    id=f"{course_id}-q{i + 1}",
                    question=q.get("question", ""),
                    options=shuffled,
                    correct_index=ci,
                    explanation=q.get("explanation", ""),
                    concept=q.get("concept", "General"),
                    difficulty=diff,
                    lecture=q.get("lecture", ""),
                )
            )

        if not questions:
            return

        qset = QuestionSet(
            course_id=course_id,
            course_title=meta["course_title"],
            questions=questions,
            model=GEN_MODEL,
            generated_at=datetime.now(timezone.utc).isoformat(),
        )
        await store.set(COLLECTION, course_id, qset.model_dump())
    except Exception as e:  # noqa: BLE001
        print(f"question_service: generation failed for {course_id}: {e}")
    finally:
        _in_progress.discard(course_id)
