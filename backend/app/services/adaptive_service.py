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
from collections import defaultdict
from datetime import datetime, timezone
from typing import List, Optional

from app.models import MCQQuestion
from app.services.store import store
from app.services.vector_store import vector_store
from app.services import question_service, knowledge_graph_service, recommendation_service

PERF_COLLECTION = "concept_performance"
SESSION_COLLECTION = "adaptive_sessions"
MAX_QUESTIONS = 20
MASTERY = 0.8
SPACED_DAYS = 3
LOW_UNSEEN = 8  # grow the bank when a user has fewer than this many unseen questions left


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


async def _question_bank(course_id: str) -> List[MCQQuestion]:
    doc = await store.get("questions", course_id)
    if not doc:
        return []
    return [MCQQuestion(**q) for q in doc["questions"]]


async def _seen_question_ids(user_id: str, course_id: str) -> set:
    """Question ids this user has answered across past sessions for this course."""
    sessions = await store.query("quiz_sessions", "user_id", user_id)
    return {
        a.get("question_id")
        for s in sessions
        if s.get("course_id") == course_id
        for a in s.get("answers", [])
    }


async def _pick_next(
    user_id: str, course_id: str, bank: List[MCQQuestion], answered_ids: List[str], seen: set
) -> Optional[MCQQuestion]:
    unanswered = [q for q in bank if q.id not in answered_ids]
    if not unanswered:
        return None

    # Prefer questions this user hasn't seen across past sessions; only fall back
    # to already-seen ones for deliberate review (spaced repetition).
    unseen = [q for q in unanswered if q.id not in seen]
    working = unseen if unseen else unanswered

    concepts = {q.concept for q in working}

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
        if candidates:
            candidates.sort(key=lambda x: x[1])
            target = candidates[0][0]
        else:
            # All in-play concepts mastered — keep serving fresh material for
            # reinforcement instead of stopping (supports continued practice).
            target = working[0].concept

    acc = perf[target]["accuracy"] if perf[target] else None
    want = _band_difficulty(acc)

    # Feature 6 integration: don't serve a HARD question on a concept until its
    # prerequisites are reasonably solid (>= 70% accuracy). Cap at medium otherwise.
    if want == "hard":
        prereqs = await knowledge_graph_service.get_prerequisites(course_id, target)
        for pre in prereqs:
            p = await _get_perf(user_id, pre)
            if not p or p["attempts"] == 0 or p["accuracy"] < 0.7:
                want = "medium"
                break

    pool = [q for q in working if q.concept == target]
    preferred = [q for q in pool if q.difficulty == want]
    return preferred[0] if preferred else (pool[0] if pool else working[0])


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


async def start(user_id: str, course_id: str) -> dict:
    bank = await _question_bank(course_id)
    if not bank:
        # Questions not generated yet — warm them up and tell the client to wait.
        await question_service.ensure_generated(course_id)
        return {"status": "preparing"}

    # What this user has already answered across past sessions (for prefer-unseen).
    seen = await _seen_question_ids(user_id, course_id)

    # If this user is running low on unseen questions, grow the bank in the
    # background so next time there's fresh material.
    if len([q for q in bank if q.id not in seen]) < LOW_UNSEEN:
        await question_service.top_up(course_id)

    session_id = str(uuid.uuid4())
    first = await _pick_next(user_id, course_id, bank, [], seen)
    session = {
        "session_id": session_id,
        "user_id": user_id,
        "course_id": course_id,
        "answered_ids": [],
        "answers": [],
        "seen": list(seen),
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


async def _record_quiz_session(session: dict) -> None:
    """Persist a completed adaptive run as a quiz session so progress, the
    dashboard, recommendations and course insights have history to work from."""
    answers = session.get("answers", [])
    if not answers:
        return
    meta = vector_store.get_course_meta(session["course_id"]) or {}

    agg: dict = defaultdict(lambda: {"attempts": 0, "correct": 0})
    for a in answers:
        agg[a["concept"]]["attempts"] += 1
        agg[a["concept"]]["correct"] += 1 if a["correct"] else 0
    breakdown = [
        {
            "concept": c,
            "attempts": v["attempts"],
            "correct": v["correct"],
            "accuracy": round(v["correct"] / v["attempts"], 3) if v["attempts"] else 0.0,
        }
        for c, v in agg.items()
    ]
    breakdown.sort(key=lambda c: c["accuracy"])

    record = {
        "session_id": session["session_id"],
        "user_id": session["user_id"],
        "course_id": session["course_id"],
        "course_title": meta.get("course_title", session["course_id"]),
        "score": sum(1 for a in answers if a["correct"]),
        "total": len(answers),
        "answers": [
            {"question_id": a["question_id"], "concept": a["concept"], "difficulty": "",
             "correct": a["correct"], "time_taken_ms": a.get("time_taken_ms", 0), "lecture": ""}
            for a in answers
        ],
        "concept_breakdown": breakdown,
        "completed_at": _now().isoformat(),
    }
    await store.set("quiz_sessions", session["session_id"], record)
    await recommendation_service.invalidate(session["user_id"])


async def answer(
    session_id: str, question_id: str, correct: bool, concept: str, time_taken_ms: int = 0
) -> dict:
    session = await store.get(SESSION_COLLECTION, session_id)
    if not session or session.get("done"):
        return {"status": "done", "summary": None}

    user_id = session["user_id"]
    bank = await _question_bank(session["course_id"])

    await _update_perf(user_id, concept, correct)
    session["answered_ids"].append(question_id)
    session["answers"].append(
        {"question_id": question_id, "concept": concept, "correct": correct, "time_taken_ms": time_taken_ms}
    )
    session["count"] += 1

    # End conditions: hit the cap, or mastered everything AND no fresh questions
    # left (if fresh material remains, keep going for reinforcement).
    seen = set(session.get("seen", []))
    answered = set(session["answered_ids"])
    fresh_left = any(q.id not in answered and q.id not in seen for q in bank)
    ended = session["count"] >= MAX_QUESTIONS or (
        await _all_concepts_mastered(user_id, bank) and not fresh_left
    )
    nxt = None if ended else await _pick_next(user_id, session["course_id"], bank, session["answered_ids"], seen)
    if nxt is None:
        session["done"] = True
        await store.set(SESSION_COLLECTION, session_id, session)
        await _record_quiz_session(session)
        return {"status": "done", "summary": await _mastery_summary(user_id, bank)}

    await store.set(SESSION_COLLECTION, session_id, session)
    return {
        "status": "active",
        "question": nxt.model_dump(),
        "progress": {"answered": session["count"], "cap": MAX_QUESTIONS},
    }
