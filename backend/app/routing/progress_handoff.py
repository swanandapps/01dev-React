"""
Turns the existing `journey_service.get_journey()` payload (already built
for the dashboard) into one chat-friendly message, so PROGRESS_LOOKUP
requests reuse the real analytics instead of getting an ungrounded or
declined non-answer from the RAG path.
"""
from app.services.journey_service import get_journey


async def build_progress_message(student_id: str) -> str:
    journey = await get_journey(student_id)
    ai = journey.get("ai") or {}
    parts = [ai.get("narrative", "").strip()]
    focus = ai.get("focus", "").strip()
    if focus:
        parts.append(focus)
    return " ".join(p for p in parts if p)
