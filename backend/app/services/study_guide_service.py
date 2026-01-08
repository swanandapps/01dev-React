"""
Feature 2 — Study guide generation.

One GPT call per lecture turns the transcript into a structured study guide,
stored (Firestore in prod, in-memory locally) so it loads instantly next time.
Generation runs in the background; the client polls status until "ready".
"""

import asyncio
from datetime import datetime, timezone
from typing import Optional

from app.models import StudyGuide
from app.services.llm import llm, GEN_MODEL
from app.services.store import store
from app.services.vector_store import vector_store

COLLECTION = "study_guides"

# Lectures currently being generated, to avoid duplicate concurrent GPT calls.
_in_progress: set[str] = set()

SYSTEM_PROMPT = """You are an expert instructional designer for the 0.1% Dev learning platform.
Given a single lecture transcript, produce a structured study guide grounded ONLY in that transcript.
Do not invent facts that are not supported by the transcript.

Return a JSON object with EXACTLY this shape:
{
  "key_concepts": [ {"name": "...", "description": "one clear sentence"} ],   // exactly 5
  "summary": "a 3-paragraph summary, paragraphs separated by \\n\\n",
  "practice_questions": [ {"question": "...", "answer": "..."} ],             // exactly 5
  "misconceptions": [ "a common misconception, one sentence" ]                // exactly 3
}
Keep it concise, accurate, and educational."""


async def get_status(lecture_id: str) -> dict:
    """Return {status, guide?}. status: ready | generating | none."""
    doc = await store.get(COLLECTION, lecture_id)
    if doc:
        return {"status": "ready", "guide": doc}
    if lecture_id in _in_progress:
        return {"status": "generating", "guide": None}
    return {"status": "none", "guide": None}


async def ensure_generated(lecture_id: str) -> dict:
    """
    Kick off generation if the guide doesn't exist yet. Returns the current
    status immediately (non-blocking) so the UI can show "Generating…".
    """
    existing = await store.get(COLLECTION, lecture_id)
    if existing:
        return {"status": "ready", "guide": existing}

    if lecture_id not in _in_progress:
        _in_progress.add(lecture_id)
        asyncio.create_task(_generate(lecture_id))

    return {"status": "generating", "guide": None}


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
            max_tokens=1800,
        )
        if not data:
            return

        guide = StudyGuide(
            lecture_id=lecture_id,
            course_id=meta["course_id"],
            lecture_title=meta["lecture_title"],
            course_title=meta["course_title"],
            key_concepts=data.get("key_concepts", []),
            summary=data.get("summary", ""),
            practice_questions=data.get("practice_questions", []),
            misconceptions=data.get("misconceptions", []),
            model=GEN_MODEL,
            generated_at=datetime.now(timezone.utc).isoformat(),
        )
        await store.set(COLLECTION, lecture_id, guide.model_dump())
    except Exception as e:  # noqa: BLE001 — background task must not crash silently-bubble
        print(f"study_guide: generation failed for {lecture_id}: {e}")
    finally:
        _in_progress.discard(lecture_id)
