"""
Ties the per-student `concept_performance` table (already written by
adaptive_service on graded quiz answers) to the per-COURSE concept graph
that already exists (knowledge_graph_service: concepts + prerequisite/
part-of/related-to edges, shared by every student).

`concept_performance` itself is not a graph — it's a flat set of per-
(student, concept) values. This module is what makes those values sit ON
the shared graph's nodes: the moment a student's first graded event for a
course happens, every concept node in that course's graph gets a zeroed
row up front, instead of rows appearing one at a time as concepts happen
to come up. Collection name and field shape (concept/attempts/correct/
accuracy/last_seen) are unchanged — journey_service, course_insight_service,
recommendation_service, and tutor_service all read this collection directly
and must keep working without modification.
"""
from app.services import knowledge_graph_service
from app.services.store import store

PERF_COLLECTION = "concept_performance"


def _perf_id(user_id: str, concept: str) -> str:
    return f"{user_id}__{concept}"


async def ensure_populated(user_id: str, course_id: str) -> int:
    """Back-fill a zeroed concept_performance row for every concept in this
    course's graph that this student doesn't already have a row for.
    Idempotent: never touches a row that already exists (real progress is
    never reset). Silent no-op if the course has no graph built yet —
    building one is a separate, deliberately-triggered operation."""
    if not await knowledge_graph_service.has_graph(course_id):
        return 0

    graph = await knowledge_graph_service.get_graph(course_id)
    created = 0
    for concept in graph["concepts"]:
        name = concept["name"]
        doc_id = _perf_id(user_id, name)
        if await store.get(PERF_COLLECTION, doc_id):
            continue
        await store.set(PERF_COLLECTION, doc_id, {
            "user_id": user_id,
            "concept": name,
            "attempts": 0,
            "correct": 0,
            "accuracy": 0.0,
            "course_id": course_id,
            "source": "pre_populated",
        })
        created += 1
    return created
