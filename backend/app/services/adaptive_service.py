"""
Feature 5 — Adaptive practice.

Replaces the fixed question order with intelligent selection. After each answer
the system updates the student's per-concept performance and picks the next
question by accuracy band:

  accuracy < 50%   -> serve an EASY question on that concept
  50% <= acc < 80% -> serve a MEDIUM question
  acc >= 80%       -> serve a HARD question, or move on to the next concept

Rules:
  - never repeat an already-answered question in the same session
  - spaced repetition: a concept unseen for 3+ days is resurfaced regardless of accuracy
  - session ends when all lecture concepts reach >= 80% accuracy OR 20 questions answered

Per-concept performance (attempts/correct/accuracy/last_seen) is persisted per
user so spaced repetition works across sessions, and feeds recommendations (F7).
"""

import uuid
from datetime import datetime, timezone
from typing import List, Optional

from app.models import MCQQuestion
from app.services.store import store
from app.services import question_service

PERF_COLLECTION = "concept_performance"
SESSION_COLLECTION = "adaptive_sessions"
MAX_QUESTIONS = 20
MASTERY = 0.8
SPACED_DAYS = 3


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _perf_id(user_id: str, concept: str) -> str:
    return f"{user_id}__{concept}"


async def _get_perf(user_id: str, concept: str) -> Optional[dict]:
    return await store.get(PERF_COLLECTION, _perf_id(user_id, concept))


async def _update_perf(user_id: str, concept: str, correct: bool) -> None:
    doc = await _get_perf(user_id, concept) or {
        "user_id": user_id,
        "concept": concept,
        "attempts": 0,
        "correct": 0,
        "accuracy": 0.0,
    }
    doc["attempts"] += 1
    doc["correct"] += 1 if correct else 0
    doc["accuracy"] = round(doc["correct"] / doc["attempts"], 3)
    doc["last_seen"] = _now().isoformat()
    await store.set(PERF_COLLECTION, _perf_id(user_id, concept), doc)


def _days_since(iso: str) -> float:
    try:
        seen = datetime.fromisoformat(iso)
        return (_now() - seen).total_seconds() / 86400.0
    except (ValueError, TypeError):
        return 0.0


def _band_difficulty(accuracy: Optional[float]) -> str:
    if accuracy is None or accuracy < 0.5:
        return "easy"
    if accuracy < MASTERY:
        return "medium"
    return "hard"


async def _question_bank(lecture_id: str) -> List[MCQQuestion]:
    doc = await store.get("questions", lecture_id)
    if not doc:
        return []
    return [MCQQuestion(**q) for q in doc["questions"]]


async def _pick_next(
    user_id: str, bank: List[MCQQuestion], answered_ids: List[str]
) -> Optional[MCQQuestion]:
    unanswered = [q for q in bank if q.id not in answered_ids]
    if not unanswered:
        return None

    concepts = {q.concept for q in unanswered}

    # Load this user's performance for the concepts still in play.
    perf = {c: await _get_perf(user_id, c) for c in concepts}

    # Spaced repetition — resurface a concept unseen for 3+ days.
    stale = [
        c for c in concepts
        if perf[c] and perf[c].get("last_seen") and _days_since(perf[c]["last_seen"]) >= SPACED_DAYS
    ]
    if stale:
        target = sorted(stale, key=lambda c: perf[c]["last_seen"])[0]
    else:
        # Otherwise focus the weakest not-yet-mastered concept that still has questions.
        candidates = []
        for c in concepts:
            acc = perf[c]["accuracy"] if perf[c] else None
            if acc is None or acc < MASTERY:
                candidates.append((c, acc if acc is not None else -1.0))
        if not candidates:
            return None  # everything still available is already mastered → end
        candidates.sort(key=lambda x: x[1])
        target = candidates[0][0]

    acc = perf[target]["accuracy"] if perf[target] else None
    want = _band_difficulty(acc)

    pool = [q for q in unanswered if q.concept == target]
    preferred = [q for q in pool if q.difficulty == want]
    return preferred[0] if preferred else (pool[0] if pool else unanswered[0])


async def _all_concepts_mastered(user_id: str, bank: List[MCQQuestion]) -> bool:
    concepts = {q.concept for q in bank}
    for c in concepts:
        p = await _get_perf(user_id, c)
        if not p or p["attempts"] == 0 or p["accuracy"] < MASTERY:
            return False
    return True


async def _mastery_summary(user_id: str, bank: List[MCQQuestion]) -> dict:
    concepts = sorted({q.concept for q in bank})
    mastery = []
    revisit = []
    for c in concepts:
        p = await _get_perf(user_id, c)
        acc = p["accuracy"] if p else 0.0
        attempts = p["attempts"] if p else 0
        mastery.append({"concept": c, "accuracy": acc, "attempts": attempts, "mastered": acc >= MASTERY and attempts > 0})
        if attempts == 0 or acc < MASTERY:
            revisit.append(c)
    mastery.sort(key=lambda m: m["accuracy"])
    return {"mastery": mastery, "revisit": revisit}


async def start(user_id: str, lecture_id: str) -> dict:
    bank = await _question_bank(lecture_id)
    if not bank:
        # Questions not generated yet — warm them up and tell the client to wait.
        await question_service.ensure_generated(lecture_id)
        return {"status": "preparing"}

    session_id = str(uuid.uuid4())
    first = await _pick_next(user_id, bank, [])
    session = {
        "session_id": session_id,
        "user_id": user_id,
        "lecture_id": lecture_id,
        "answered_ids": [],
        "count": 0,
        "done": False,
        "started_at": _now().isoformat(),
    }
    await store.set(SESSION_COLLECTION, session_id, session)
    return {
        "status": "active",
        "session_id": session_id,
        "question": first.model_dump() if first else None,
        "progress": {"answered": 0, "cap": MAX_QUESTIONS},
    }


async def answer(session_id: str, question_id: str, correct: bool, concept: str) -> dict:
    session = await store.get(SESSION_COLLECTION, session_id)
    if not session or session.get("done"):
        return {"status": "done", "summary": None}

    user_id = session["user_id"]
    bank = await _question_bank(session["lecture_id"])

    await _update_perf(user_id, concept, correct)
    session["answered_ids"].append(question_id)
    session["count"] += 1

    # End conditions.
    ended = session["count"] >= MAX_QUESTIONS or await _all_concepts_mastered(user_id, bank)
    nxt = None if ended else await _pick_next(user_id, bank, session["answered_ids"])
    if nxt is None:
        session["done"] = True
        await store.set(SESSION_COLLECTION, session_id, session)
        return {"status": "done", "summary": await _mastery_summary(user_id, bank)}

    await store.set(SESSION_COLLECTION, session_id, session)
    return {
        "status": "active",
        "question": nxt.model_dump(),
        "progress": {"answered": session["count"], "cap": MAX_QUESTIONS},
    }
