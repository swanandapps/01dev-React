"""
Feature 4 — Quiz sessions.

Persists a completed practice session (score, per-question result, concept,
difficulty, time taken) and computes a per-concept breakdown for the end
screen. Sessions are the input to adaptive practice (F5) and recommendations (F7).
"""

import uuid
from collections import defaultdict
from datetime import datetime, timezone
from typing import List

from app.models import ConceptScore, QuizSession, QuizSubmit
from app.services.store import store
from app.services.vector_store import vector_store

COLLECTION = "quiz_sessions"


def _concept_breakdown(answers) -> List[ConceptScore]:
    agg: dict = defaultdict(lambda: {"attempts": 0, "correct": 0})
    for a in answers:
        agg[a.concept]["attempts"] += 1
        agg[a.concept]["correct"] += 1 if a.correct else 0
    out = []
    for concept, v in agg.items():
        acc = round(v["correct"] / v["attempts"], 3) if v["attempts"] else 0.0
        out.append(ConceptScore(concept=concept, attempts=v["attempts"], correct=v["correct"], accuracy=acc))
    # Weakest concepts first — useful for the "revisit" list.
    out.sort(key=lambda c: c.accuracy)
    return out


async def save_session(submit: QuizSubmit) -> QuizSession:
    meta = vector_store.get_course_meta(submit.course_id) or {}
    score = sum(1 for a in submit.answers if a.correct)

    session = QuizSession(
        session_id=str(uuid.uuid4()),
        user_id=submit.user_id,
        course_id=submit.course_id,
        course_title=meta.get("course_title", submit.course_id),
        score=score,
        total=len(submit.answers),
        answers=submit.answers,
        concept_breakdown=_concept_breakdown(submit.answers),
        completed_at=datetime.now(timezone.utc).isoformat(),
    )
    await store.set(COLLECTION, session.session_id, session.model_dump())
    return session


async def list_sessions(user_id: str) -> List[dict]:
    sessions = await store.query(COLLECTION, "user_id", user_id)
    sessions.sort(key=lambda s: s.get("completed_at", ""), reverse=True)
    return sessions
