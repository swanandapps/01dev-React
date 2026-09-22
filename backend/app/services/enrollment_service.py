"""
Course enrollment — the system of record for "which courses does this
student have access to". Lives in Postgres, not Firestore: Firebase stays
scoped to auth + storage, everything the backend/Hermes needs to query
belongs in the same store as the rest of the student data (memory, skill
graph, quiz history). See the data-architecture decision this followed.

One doc per student: {student_id, courses: [{id, title, purchased_at}]}.
"""
from datetime import datetime, timezone

from app.services.store import store

COLLECTION = "enrollments"


async def get_enrolled_courses(student_id: str) -> list[dict]:
    doc = await store.get(COLLECTION, student_id)
    return (doc or {}).get("courses", [])


async def enroll(student_id: str, course_id: int, course_title: str, purchased_at: str | None = None) -> list[dict]:
    """Idempotent — re-enrolling in a course you already have doesn't duplicate it.
    `purchased_at` defaults to now; the Firestore migration passes a real historical
    timestamp when one exists instead of stamping "now" on old purchases."""
    courses = await get_enrolled_courses(student_id)
    if any(c["id"] == course_id for c in courses):
        return courses
    courses.append({
        "id": course_id,
        "title": course_title,
        "purchased_at": purchased_at or datetime.now(timezone.utc).isoformat(),
    })
    await store.set(COLLECTION, student_id, {"student_id": student_id, "courses": courses})
    return courses
