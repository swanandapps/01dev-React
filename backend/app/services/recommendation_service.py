"""
Feature 7 — Personalized recommendations (per course).

A "what to study next" card. One GPT call reads the student's quiz history and
per-concept performance and returns 2-3 course recommendations with one-line
reasons (which can name a weak concept for precision). Cached per user for 24h;
invalidated when they complete a new quiz.
"""

from datetime import datetime, timezone
from typing import List

from app.services.llm import llm
from app.services.store import store
from app.services.vector_store import vector_store

COLLECTION = "recommendations"
CACHE_HOURS = 24

SYSTEM_PROMPT = """You are a learning advisor for the 0.1% Dev platform.
Given a student's performance summary and the list of available courses, recommend
2-3 courses to study next. Prefer courses that address weak concepts or that the student
hasn't completed; a reason may name a specific weak concept. For a brand-new student with
no history, suggest good starting courses.

Return a JSON object with EXACTLY this shape:
{
  "recommendations": [
    {"course_id": "<an available course_id>", "reason": "one short sentence"}
  ]
}
Use ONLY course_ids from the provided list. Return 2 or 3 recommendations."""


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _fresh(generated_at: str) -> bool:
    try:
        age_h = (_now() - datetime.fromisoformat(generated_at)).total_seconds() / 3600.0
        return age_h < CACHE_HOURS
    except (ValueError, TypeError):
        return False


async def invalidate(user_id: str) -> None:
    await store.delete(COLLECTION, user_id)


async def _build_summary(user_id: str) -> tuple[str, List[dict]]:
    sessions = await store.query("quiz_sessions", "user_id", user_id)
    perf = await store.query("concept_performance", "user_id", user_id)
    courses = vector_store.get_all_courses()

    completed = {s["course_id"] for s in sessions}
    lines = []
    if sessions:
        avg = sum(s["score"] / max(s["total"], 1) for s in sessions) / len(sessions)
        lines.append(f"Completed {len(sessions)} quiz(zes); average score {round(avg * 100)}%.")
        done = [c["title"] for c in courses if c["course_id"] in completed]
        if done:
            lines.append("Quizzed courses: " + ", ".join(done) + ".")
    else:
        lines.append("New student — no quiz history yet.")

    weak = sorted([p for p in perf if p["accuracy"] < 0.7 and p["attempts"] > 0], key=lambda p: p["accuracy"])
    if weak:
        lines.append("Weak concepts: " + ", ".join(f"{p['concept']} ({round(p['accuracy']*100)}%)" for p in weak[:6]) + ".")

    available = "\n".join(f"- {c['course_id']}: {c['title']} ({c['lecture_count']} lectures)" for c in courses)
    summary = "\n".join(lines) + "\n\nAvailable courses:\n" + available
    return summary, courses


async def get_recommendations(user_id: str, force: bool = False) -> dict:
    cached = await store.get(COLLECTION, user_id)
    if cached and not force and _fresh(cached.get("generated_at", "")):
        return {**cached, "cached": True}

    summary, courses = await _build_summary(user_id)
    by_id = {c["course_id"]: c for c in courses}

    data = await llm.generate_json(SYSTEM_PROMPT, summary, max_tokens=600)
    recs = []
    if data:
        for r in data.get("recommendations", []):
            cid = r.get("course_id")
            if cid in by_id:
                recs.append({
                    "course_id": cid,
                    "course_title": by_id[cid]["title"],
                    "reason": r.get("reason", ""),
                })

    if not recs:
        for c in courses[:2]:
            recs.append({"course_id": c["course_id"], "course_title": c["title"], "reason": "A good place to start."})

    result = {"user_id": user_id, "recommendations": recs, "generated_at": _now().isoformat()}
    await store.set(COLLECTION, user_id, result)
    return {**result, "cached": False}
