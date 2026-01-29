"""
Feature 2 — Study guide generation (per course).

One GPT call per course turns the aggregated lecture transcripts into a
structured study guide, stored (Firestore in prod, in-memory locally) so it
loads instantly next time. Generation runs in the background; the client polls
status until "ready".
"""

import asyncio
from datetime import datetime, timezone

from app.models import StudyGuide
from app.services.llm import llm, GEN_MODEL
from app.services.store import store
from app.services.vector_store import vector_store

COLLECTION = "study_guides"

# Courses currently being generated, to avoid duplicate concurrent GPT calls.
_in_progress: set[str] = set()

SYSTEM_PROMPT = """You are an expert instructional designer for the 0.1% Dev learning platform.
Given a course's lecture transcripts (each section marked with [Lecture: ...]), produce a
structured study guide grounded ONLY in those transcripts. Cover the course as a whole.
Do not invent facts that are not supported by the transcripts.

Return a JSON object with EXACTLY this shape:
{
  "key_concepts": [ {"name": "...", "description": "one clear sentence"} ],   // exactly 5
  "summary": "a 3-paragraph summary, paragraphs separated by \\n\\n",
  "practice_questions": [ {"question": "...", "answer": "..."} ],             // exactly 5
  "misconceptions": [ "a common misconception, one sentence" ]                // exactly 3
}
Keep it concise, accurate, and educational."""


async def get_status(course_id: str) -> dict:
    doc = await store.get(COLLECTION, course_id)
    if doc:
        return {"status": "ready", "guide": doc}
    if course_id in _in_progress:
        return {"status": "generating", "guide": None}
    return {"status": "none", "guide": None}


async def ensure_generated(course_id: str) -> dict:
    existing = await store.get(COLLECTION, course_id)
    if existing:
        return {"status": "ready", "guide": existing}
    if course_id not in _in_progress:
        _in_progress.add(course_id)
        asyncio.create_task(_generate(course_id))
    return {"status": "generating", "guide": None}


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
            max_tokens=1800,
        )
        if not data:
            return

        guide = StudyGuide(
            course_id=course_id,
            course_title=meta["course_title"],
            key_concepts=data.get("key_concepts", []),
            summary=data.get("summary", ""),
            practice_questions=data.get("practice_questions", []),
            misconceptions=data.get("misconceptions", []),
            model=GEN_MODEL,
            generated_at=datetime.now(timezone.utc).isoformat(),
        )
        await store.set(COLLECTION, course_id, guide.model_dump())
    except Exception as e:  # noqa: BLE001
        print(f"study_guide: generation failed for {course_id}: {e}")
    finally:
        _in_progress.discard(course_id)
