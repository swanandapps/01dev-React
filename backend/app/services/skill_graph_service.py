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
from datetime import datetime, timezone

from app.services import knowledge_graph_service
from app.services.store import store

PERF_COLLECTION = "concept_performance"

_VALID_CONFIDENCE = {"weak", "developing", "strong"}

# NOTE on doc-id scoping: `_perf_id` (imported from adaptive_service below) is
# keyed as f"{user_id}__{concept}" — GLOBAL across courses, not scoped by
# course_id. This is inherited from adaptive_service's pre-existing scheme,
# not something introduced or fixed here. The `course_id` field this module
# writes onto a row is therefore "whichever course's ensure_populated() call
# first created this row" metadata ONLY — it is NOT safe to trust as "the
# course the student is currently engaged with", because if two courses share
# a concept name, the second course's ensure_populated() sees the row already
# exists (same doc id, since concept name alone determines it) and skips it,
# leaving the stale first-writer's course_id in place. get_prerequisite_view
# below matches purely on concept name for the same reason and never filters
# by course_id. A real fix requires a coordinated doc-id migration across both
# adaptive_service and this module — out of scope for this change.


async def ensure_populated(user_id: str, course_id: str) -> int:
    """Back-fill a zeroed concept_performance row for every concept in this
    course's graph that this student doesn't already have a row for.
    Idempotent: never touches a row that already exists (real progress is
    never reset). Silent no-op if the course has no graph built yet —
    building one is a separate, deliberately-triggered operation.

    Fetches this student's existing rows ONCE (one store.query, same
    fetch-everything-then-filter-in-memory pattern get_prerequisite_view
    already uses below) instead of one store.get per concept — this runs as
    the first line of adaptive_service.start(), on every session start, so an
    N+1 here would mean N sequential DB round-trips before serving the first
    question, every time."""
    # Local import: adaptive_service imports this module at module load time,
    # so a top-level `from app.services.adaptive_service import _perf_id`
    # here would deadlock into a partial-init ImportError whenever
    # adaptive_service happens to be the first of the two to be imported
    # (which it is, via app.main). Importing inside the function defers this
    # until both modules are fully loaded.
    from app.services.adaptive_service import _perf_id

    if not await knowledge_graph_service.has_graph(course_id):
        return 0

    graph = await knowledge_graph_service.get_graph(course_id)
    existing_rows = await store.query(PERF_COLLECTION, "user_id", user_id)
    existing_concepts = {r["concept"] for r in existing_rows}

    created = 0
    for concept in graph["concepts"]:
        name = concept["name"]
        if name in existing_concepts:
            continue
        await store.set(PERF_COLLECTION, _perf_id(user_id, name), {
            "user_id": user_id,
            "concept": name,
            "attempts": 0,
            "correct": 0,
            "accuracy": 0.0,
            "course_id": course_id,
            "created_by": "pre_population",
        })
        created += 1
    return created


def _view(row: dict | None) -> dict:
    """Translate a raw concept_performance row (or its absence) into an
    honest view: attempts == 0 (including a pre-populated-but-untouched
    row from Task 1) means NO real signal exists yet — report accuracy as
    None, never the stored 0.0 placeholder, which would look like a real
    (bad) score instead of "not tried".

    Also surfaces record_observation's chat_confidence*/note fields (added
    below), so a chat-inferred observation written for a concept is actually
    visible on the next get_concept_confidence/get_prerequisite_view call —
    without this the write and read tools didn't compose. `chat_confidence`
    is a conversational impression (may be absent); `accuracy` is a real
    graded score (or None if never graded) — the two are different signals,
    not interchangeable."""
    attempts = (row or {}).get("attempts", 0)
    attempted = attempts > 0
    return {
        "concept": (row or {}).get("concept"),
        "accuracy": (row or {}).get("accuracy") if attempted else None,
        "attempts": attempts,
        "attempted": attempted,
        "chat_confidence": (row or {}).get("chat_confidence"),
        "chat_confidence_note": (row or {}).get("chat_confidence_note"),
    }


async def get_prerequisite_view(user_id: str, course_id: str, concept: str) -> dict:
    """One-shot view of `concept`'s confidence plus every one of its
    prerequisites' confidence, for this student. Two queries total no
    matter how many prerequisites exist: the course's prerequisite edges
    (knowledge_graph_service, already a single query), and ALL of this
    student's concept_performance rows in one store.query — the same
    fetch-everything-then-filter-in-memory pattern journey_service and
    friends already use, not a new capability."""
    prereq_names = await knowledge_graph_service.get_prerequisites(course_id, concept)
    rows = await store.query(PERF_COLLECTION, "user_id", user_id)
    by_concept = {r["concept"]: r for r in rows}

    target = _view(by_concept.get(concept) or {"concept": concept})
    prerequisites = [_view(by_concept.get(name) or {"concept": name}) for name in prereq_names]

    attempted_prereqs = [p for p in prerequisites if p["attempted"]]
    weakest = min(
        attempted_prereqs,
        key=lambda p: p["accuracy"] if p["accuracy"] is not None else 0.0,
        default=None,
    )

    return {**target, "prerequisites": prerequisites, "weakest_prerequisite": weakest}


# `user_id` below is MODEL-SUPPLIED (Hermes passes whatever it was told
# student_id is) and is NOT server-verified against the authenticated
# session. There is a concrete path — student-authored text re-entering the
# model's context via memory_context/search_history results — by which the
# model could be misdirected into writing an observation onto a different
# student's row. This is a deliberate, accepted scoping decision for the
# current single-learner deployment, NOT a claim that it's already safe for
# multi-tenant use. See "Known limitations" in
# docs/superpowers/plans/2026-09-20-skill-tools-and-observations.md.
async def record_observation(
    user_id: str, course_id: str, concept: str, confidence: str, note: str,
) -> dict:
    """Log a chat-inferred observation about a student's grasp of a concept —
    NOT a graded score. Writes to separate chat_confidence* fields on the same
    concept_performance row ensure_populated/_update_perf use; attempts/correct/
    accuracy (the graded-event fields 4 other services depend on) are never
    touched here — for the existing-row case this is now enforced by the write
    itself (store.update, an additive merge), not just by what this function
    computes: adaptive_service._update_perf does its own read-modify-write on
    the SAME doc id from a different request path, and a store.set here would
    silently revert a graded quiz answer that lands between this function's
    read and write. Creates a zeroed row first if this student has no row for
    this concept yet, so an observation can happen before any graded event."""
    if confidence not in _VALID_CONFIDENCE:
        raise ValueError(f"confidence must be one of {sorted(_VALID_CONFIDENCE)}, got {confidence!r}")

    # Local import: same circular-import hazard ensure_populated documents
    # above (adaptive_service imports this module at load time) — deferred
    # here until both modules are fully loaded.
    from app.services.adaptive_service import _perf_id

    doc_id = _perf_id(user_id, concept)
    chat_fields = {
        "chat_confidence": confidence,
        "chat_confidence_note": note,
        "chat_confidence_updated_at": datetime.now(timezone.utc).isoformat(),
    }
    row = await store.get(PERF_COLLECTION, doc_id)
    if row is None:
        row = {
            "user_id": user_id, "concept": concept,
            "attempts": 0, "correct": 0, "accuracy": 0.0,
            "course_id": course_id, "created_by": "chat_observation",
        }
        await store.set(PERF_COLLECTION, doc_id, {**row, **chat_fields})
    else:
        await store.update(PERF_COLLECTION, doc_id, chat_fields)
    return {**row, **chat_fields}
