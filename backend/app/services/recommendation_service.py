"""
Feature 7 — Personalized recommendations.

A "what to study next" card. One GPT call reads the student's quiz history and
per-concept performance and returns 2-3 lecture recommendations with one-line
reasons. Cached per user for 24h; invalidated when they complete a new quiz.

Reads the store directly (not quiz_service) to avoid an import cycle —
quiz completion invalidates this cache from the endpoint layer.
"""

from datetime import datetime, timezone
from typing import List

from app.services.llm import llm
from app.services.store import store
from app.services.vector_store import vector_store

COLLECTION = "recommendations"
CACHE_HOURS = 24

SYSTEM_PROMPT = """You are a learning advisor for the 0.1% Dev platform.
Given a student's performance summary and the list of available lectures, recommend
2-3 lectures to study next. Prefer lectures that address weak concepts or that the
student hasn't completed. For a brand-new student with no history, suggest good
starting lectures.

Return a JSON object with EXACTLY this shape:
{
  "recommendations": [
    {"lecture_id": "<an available lecture_id>", "reason": "one short sentence"}
  ]
}
Use ONLY lecture_ids from the provided list. Return 2 or 3 recommendations."""


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
    lectures = vector_store.list_lectures()

    completed = {s["lecture_id"] for s in sessions}
    lines = []
    if sessions:
        avg = sum(s["score"] / max(s["total"], 1) for s in sessions) / len(sessions)
        lines.append(f"Completed {len(sessions)} quiz(zes); average score {round(avg * 100)}%.")
        done = [l["lecture_title"] for l in lectures if l["lecture_id"] in completed]
        if done:
            lines.append("Completed lectures: " + ", ".join(done) + ".")
    else:
        lines.append("New student — no quiz history yet.")

    weak = sorted([p for p in perf if p["accuracy"] < 0.7 and p["attempts"] > 0], key=lambda p: p["accuracy"])
    if weak:
        lines.append("Weak concepts: " + ", ".join(f"{p['concept']} ({round(p['accuracy']*100)}%)" for p in weak[:6]) + ".")

    available = "\n".join(f"- {l['lecture_id']}: {l['lecture_title']} ({l['course_title']})" for l in lectures)
    summary = "\n".join(lines) + "\n\nAvailable lectures:\n" + available
    return summary, lectures


async def get_recommendations(user_id: str, force: bool = False) -> dict:
    cached = await store.get(COLLECTION, user_id)
    if cached and not force and _fresh(cached.get("generated_at", "")):
        return {**cached, "cached": True}

    summary, lectures = await _build_summary(user_id)
    by_id = {l["lecture_id"]: l for l in lectures}

    data = await llm.generate_json(SYSTEM_PROMPT, summary, max_tokens=600)
    recs = []
    if data:
        for r in data.get("recommendations", []):
            lid = r.get("lecture_id")
            if lid in by_id:
                recs.append({
                    "lecture_id": lid,
                    "lecture_title": by_id[lid]["lecture_title"],
                    "course_title": by_id[lid]["course_title"],
                    "reason": r.get("reason", ""),
                })

    # Fallback: if the model returned nothing usable, suggest the first lectures.
    if not recs:
        for l in lectures[:2]:
            recs.append({
                "lecture_id": l["lecture_id"],
                "lecture_title": l["lecture_title"],
                "course_title": l["course_title"],
                "reason": "A good place to start.",
            })

    result = {"user_id": user_id, "recommendations": recs, "generated_at": _now().isoformat()}
    await store.set(COLLECTION, user_id, result)
    return {**result, "cached": False}
