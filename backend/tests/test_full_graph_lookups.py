"""With the full graph, a concept name can belong to several courses (event-loop is taught in JavaScript Deep
Dive and in Product Engineering). Looking up "which course is this concept from" must prefer a course the
student is enrolled in, or the tutor reads the wrong course's prerequisites. And the tutor's strengths report
lists what the student hasn't practised yet, so "what haven't I practised?" is answered from data."""
import pytest

from app.services import enrollment_service, journey_service, knowledge_graph_service
from app.services.store import store


async def _concept(course, name, chapter):
    await store.set("concepts", f"{course}::{name}", {"course_id": course, "name": name, "description": "d",
                                                      "chapter": chapter})


@pytest.mark.asyncio
async def test_a_shared_concept_resolves_to_the_students_own_course(monkeypatch):
    await _concept("product-engineering", "fg-event-loop", "Chapter 3 - Async")
    await _concept("javascript-deep-dive", "fg-event-loop", "Chapter 6 - Concurrency")

    async def enrolled(student_id):
        return [{"id": 9, "title": "JavaScript Deep Dive"}]
    monkeypatch.setattr(enrollment_service, "get_enrolled_courses", enrolled)
    assert await knowledge_graph_service.find_course_for_concept("fg-event-loop", "fg-student") == "javascript-deep-dive"


@pytest.mark.asyncio
async def test_the_report_lists_unpractised_concepts_in_teaching_order(monkeypatch):
    uid = "fg-report-student"
    await _concept("javascript-deep-dive", "fg-closure", "Chapter 2 - Scope and Closures")
    await _concept("javascript-deep-dive", "fg-call-stack", "Chapter 1 - How JavaScript Runs")
    await _concept("javascript-deep-dive", "fg-prototypes", "Chapter 4 - Objects")
    await store.set("concept_performance", f"{uid}__fg-prototypes",
                    {"user_id": uid, "concept": "fg-prototypes", "attempts": 4, "correct": 1, "accuracy": 0.25})
    await store.set("concept_performance", f"{uid}__fg-closure",          # back-filled row: still "not tried"
                    {"user_id": uid, "concept": "fg-closure", "attempts": 0, "correct": 0, "accuracy": 0.0})

    async def enrolled(student_id):
        return [{"id": 9, "title": "JavaScript Deep Dive"}]
    monkeypatch.setattr(enrollment_service, "get_enrolled_courses", enrolled)
    report = await journey_service.get_strengths_report(uid)
    todo = report["not_yet_practised"]["javascript-deep-dive"]
    assert todo.index("fg-call-stack") < todo.index("fg-closure") and "fg-prototypes" not in todo
