"""
Feature 3 — Question generation from a lecture.

One GPT call per lecture produces 10 MCQs (mix: 4 easy, 4 medium, 2 hard),
each with 4 options, a correct index, a one-sentence explanation, a concept
tag, and difficulty. Stored so the quiz (Feature 4) and adaptive layer
(Feature 5) can reuse them. Generation runs in the background.
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
Given a single lecture transcript, write multiple-choice questions grounded ONLY in that transcript.
Do not test facts that are not supported by the transcript.

Return a JSON object with EXACTLY this shape:
{
  "questions": [
    {
      "question": "the question text",
      "options": ["A", "B", "C", "D"],          // exactly 4 plausible options
      "correct_index": 0,                         // 0-3, index of the correct option
      "explanation": "one sentence on why it's correct",
      "concept": "a short concept tag (2-4 words)",
      "difficulty": "easy"                        // "easy" | "medium" | "hard"
    }
  ]
}
Produce EXACTLY 10 questions with this difficulty mix: 4 easy, 4 medium, 2 hard.
Use only 3-5 distinct concept tags across all 10 questions, so that several
questions share a concept (this powers adaptive practice — a concept needs
multiple questions at different difficulties).
Vary the position of the correct answer across questions."""


async def get_status(lecture_id: str) -> dict:
    doc = await store.get(COLLECTION, lecture_id)
    if doc:
        return {"status": "ready", "questions": doc}
    if lecture_id in _in_progress:
        return {"status": "generating", "questions": None}
    return {"status": "none", "questions": None}


async def ensure_generated(lecture_id: str) -> dict:
    existing = await store.get(COLLECTION, lecture_id)
    if existing:
        return {"status": "ready", "questions": existing}
    if lecture_id not in _in_progress:
        _in_progress.add(lecture_id)
        asyncio.create_task(_generate(lecture_id))
    return {"status": "generating", "questions": None}


async def _generate(lecture_id: str) -> None:
    try:
        meta = vector_store.get_lecture_meta(lecture_id)
        transcript = vector_store.get_lecture_transcript(lecture_id)
        if not meta or not transcript:
            return

        data = await llm.generate_json(
            SYSTEM_PROMPT,
            f"Lecture: {meta['lecture_title']} (course: {meta['course_title']})\n\n"
            f"Transcript:\n{transcript}",
            max_tokens=2200,
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

            # Models tend to always place the correct answer first — shuffle so
            # the correct option lands in a varied, non-gameable position.
            correct_option = opts[ci]
            shuffled = opts[:]
            random.shuffle(shuffled)
            ci = shuffled.index(correct_option)

            questions.append(
                MCQQuestion(
                    id=f"{lecture_id}-q{i + 1}",
                    question=q.get("question", ""),
                    options=shuffled,
                    correct_index=ci,
                    explanation=q.get("explanation", ""),
                    concept=q.get("concept", "General"),
                    difficulty=diff,
                )
            )

        if not questions:
            return

        qset = QuestionSet(
            lecture_id=lecture_id,
            course_id=meta["course_id"],
            lecture_title=meta["lecture_title"],
            course_title=meta["course_title"],
            questions=questions,
            model=GEN_MODEL,
            generated_at=datetime.now(timezone.utc).isoformat(),
        )
        await store.set(COLLECTION, lecture_id, qset.model_dump())
    except Exception as e:  # noqa: BLE001
        print(f"question_service: generation failed for {lecture_id}: {e}")
    finally:
        _in_progress.discard(lecture_id)
