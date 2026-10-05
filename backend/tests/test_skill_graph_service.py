import pytest

from app.services import skill_graph_service
from app.services.store import InMemoryStore


from app.services import concept_resolver as _cr

_REAL_RESOLVE = _cr.resolve


@pytest.fixture(autouse=True)
def _identity_resolver(monkeypatch):
    # record_observation resolves concept names; keep these tests off the real
    # store/embeddings. Tests that exercise resolution override this.
    from app.services import concept_resolver

    async def _id(candidate, course_id=None):
        return candidate

    monkeypatch.setattr(concept_resolver, "resolve", _id)


@pytest.mark.asyncio
async def test_populates_a_zeroed_row_per_concept(monkeypatch):
    from app.services import knowledge_graph_service

    async def fake_has_graph(course_id):
        assert course_id == "js-fundamentals"
        return True

    async def fake_get_graph(course_id):
        return {
            "course_id": course_id,
            "concepts": [
                {"course_id": course_id, "name": "closures", "description": "..."},
                {"course_id": course_id, "name": "hoisting", "description": "..."},
            ],
            "relationships": [
                {"course_id": course_id, "source": "hoisting", "target": "closures", "type": "prerequisite_of"},
            ],
        }

    written: dict[str, dict] = {}

    async def fake_query(collection, field, value):
        assert collection == "concept_performance"
        assert field == "user_id"
        return list(written.values())

    async def fake_set(collection, doc_id, data):
        assert collection == "concept_performance"
        written[doc_id] = data

    monkeypatch.setattr(knowledge_graph_service, "has_graph", fake_has_graph)
    monkeypatch.setattr(knowledge_graph_service, "get_graph", fake_get_graph)
    monkeypatch.setattr(skill_graph_service.store, "query", fake_query)
    monkeypatch.setattr(skill_graph_service.store, "set", fake_set)

    created = await skill_graph_service.ensure_populated("student-1", "js-fundamentals")

    assert created == 2
    row = written["student-1__closures"]
    assert row == {
        "user_id": "student-1", "concept": "closures",
        "attempts": 0, "correct": 0, "accuracy": 0.0,
        "course_id": "js-fundamentals", "created_by": "pre_population",
    }


@pytest.mark.asyncio
async def test_is_idempotent_and_never_overwrites_real_progress(monkeypatch):
    from app.services import knowledge_graph_service

    async def fake_has_graph(course_id):
        return True

    async def fake_get_graph(course_id):
        return {
            "course_id": course_id,
            "concepts": [{"course_id": course_id, "name": "closures", "description": "..."}],
            "relationships": [],
        }

    existing_row = {
        "user_id": "student-1", "concept": "closures",
        "attempts": 5, "correct": 4, "accuracy": 0.8,
        "course_id": "js-fundamentals", "last_seen": "2026-09-01T00:00:00+00:00",
    }
    written = {"student-1__closures": existing_row}

    async def fake_query(collection, field, value):
        return list(written.values())

    async def fake_set(collection, doc_id, data):
        written[doc_id] = data

    monkeypatch.setattr(knowledge_graph_service, "has_graph", fake_has_graph)
    monkeypatch.setattr(knowledge_graph_service, "get_graph", fake_get_graph)
    monkeypatch.setattr(skill_graph_service.store, "query", fake_query)
    monkeypatch.setattr(skill_graph_service.store, "set", fake_set)

    created = await skill_graph_service.ensure_populated("student-1", "js-fundamentals")

    assert created == 0
    assert written["student-1__closures"] == existing_row  # untouched


@pytest.mark.asyncio
async def test_no_graph_yet_is_a_silent_noop(monkeypatch):
    from app.services import knowledge_graph_service

    async def fake_has_graph(course_id):
        return False

    async def fail_if_called(course_id):
        raise AssertionError("get_graph must not be called when has_graph is False")

    monkeypatch.setattr(knowledge_graph_service, "has_graph", fake_has_graph)
    monkeypatch.setattr(knowledge_graph_service, "get_graph", fail_if_called)

    created = await skill_graph_service.ensure_populated("student-1", "js-fundamentals")

    assert created == 0


@pytest.mark.asyncio
async def test_prerequisite_view_combines_target_and_prereqs_in_two_queries(monkeypatch):
    from app.services import knowledge_graph_service

    query_calls = []

    async def fake_get_prerequisites(course_id, concept):
        assert (course_id, concept) == ("js-fundamentals", "closures")
        return ["scope", "functions"]

    async def fake_query(collection, field, value):
        query_calls.append((collection, field, value))
        assert collection == "concept_performance"
        assert (field, value) == ("user_id", "student-1")
        return [
            {"user_id": "student-1", "concept": "closures", "attempts": 5, "correct": 3, "accuracy": 0.6},
            {"user_id": "student-1", "concept": "scope", "attempts": 2, "correct": 0, "accuracy": 0.0},
            # "functions" deliberately has NO row — never attempted at all.
        ]

    monkeypatch.setattr(knowledge_graph_service, "get_prerequisites", fake_get_prerequisites)
    monkeypatch.setattr(skill_graph_service.store, "query", fake_query)

    view = await skill_graph_service.get_prerequisite_view("student-1", "js-fundamentals", "closures")

    # Exactly one query for prerequisites (via get_prerequisites) + one
    # store.query for ALL this student's performance — never one query
    # per prerequisite, no matter how many prerequisites there are.
    assert len(query_calls) == 1

    assert view["concept"] == "closures"
    assert view["accuracy"] == 0.6
    assert view["attempted"] is True

    prereqs = {p["concept"]: p for p in view["prerequisites"]}
    assert prereqs["scope"]["accuracy"] == 0.0
    assert prereqs["scope"]["attempted"] is True  # 2 attempts, genuinely scored 0%
    assert prereqs["functions"]["accuracy"] is None  # never attempted — NOT a fake 0.0
    assert prereqs["functions"]["attempted"] is False

    # Weakest prerequisite must only consider ones actually attempted —
    # "functions" has no real score to compare, so "scope" wins even
    # though its accuracy (0.0) looks "worse" than functions' None.
    assert view["weakest_prerequisite"]["concept"] == "scope"


@pytest.mark.asyncio
async def test_prerequisite_view_handles_no_attempted_prerequisites(monkeypatch):
    from app.services import knowledge_graph_service

    async def fake_get_prerequisites(course_id, concept):
        return ["scope"]

    async def fake_query(collection, field, value):
        return []  # nothing attempted yet at all, including the target concept

    monkeypatch.setattr(knowledge_graph_service, "get_prerequisites", fake_get_prerequisites)
    monkeypatch.setattr(skill_graph_service.store, "query", fake_query)

    view = await skill_graph_service.get_prerequisite_view("student-1", "js-fundamentals", "closures")

    assert view["accuracy"] is None
    assert view["attempted"] is False
    assert view["weakest_prerequisite"] is None


@pytest.mark.asyncio
async def test_ensure_populated_and_get_prerequisite_view_agree_on_never_attempted(monkeypatch):
    """Composition test: prove Task 1's pre-populated row and Task 2's
    None-vs-0.0 "never attempted" logic actually agree end-to-end, against
    the SAME real InMemoryStore instance (not separate monkeypatched
    closures per test) — store.get/store.set/store.query all seeing the
    same underlying data is exactly what's under test here."""
    from app.services import knowledge_graph_service

    real_store = InMemoryStore()
    monkeypatch.setattr(skill_graph_service, "store", real_store)

    async def fake_has_graph(course_id):
        return True

    async def fake_get_graph(course_id):
        return {
            "course_id": course_id,
            "concepts": [
                {"course_id": course_id, "name": "closures", "description": "..."},
                {"course_id": course_id, "name": "hoisting", "description": "..."},
            ],
            "relationships": [
                {"course_id": course_id, "source": "hoisting", "target": "closures", "type": "prerequisite_of"},
            ],
        }

    async def fake_get_prerequisites(course_id, concept):
        assert concept == "closures"
        return ["hoisting"]

    monkeypatch.setattr(knowledge_graph_service, "has_graph", fake_has_graph)
    monkeypatch.setattr(knowledge_graph_service, "get_graph", fake_get_graph)
    monkeypatch.setattr(knowledge_graph_service, "get_prerequisites", fake_get_prerequisites)

    created = await skill_graph_service.ensure_populated("student-1", "js-fundamentals")
    assert created == 2

    view = await skill_graph_service.get_prerequisite_view("student-1", "js-fundamentals", "closures")

    # The pre-populated "closures" row was never attempted (attempts == 0),
    # so ensure_populated's zeroed row and get_prerequisite_view's
    # attempts-> None translation must genuinely agree: accuracy is None,
    # never the stored 0.0 placeholder.
    assert view["accuracy"] is None
    assert view["attempted"] is False

    hoisting = view["prerequisites"][0]
    assert hoisting["concept"] == "hoisting"
    assert hoisting["accuracy"] is None
    assert hoisting["attempted"] is False
    assert view["weakest_prerequisite"] is None


@pytest.mark.asyncio
async def test_record_observation_adds_fields_without_touching_graded_data():
    from app.services import skill_graph_service

    written = {
        "student-1__closures": {
            "user_id": "student-1", "concept": "closures",
            "attempts": 5, "correct": 4, "accuracy": 0.8,
            "course_id": "js-fundamentals",
        }
    }

    async def fake_get(collection, doc_id):
        return written.get(doc_id)

    async def fake_set(collection, doc_id, data):
        raise AssertionError("existing-row case must use store.update (additive merge), not store.set")

    async def fake_update(collection, doc_id, changes):
        written[doc_id].update(changes)

    import unittest.mock as mock
    with mock.patch.object(skill_graph_service.store, "get", fake_get), \
         mock.patch.object(skill_graph_service.store, "set", fake_set), \
         mock.patch.object(skill_graph_service.store, "update", fake_update):
        result = await skill_graph_service.record_observation(
            "student-1", "js-fundamentals", "closures", "weak",
            "Struggled to explain closures in their own words.",
        )

    row = written["student-1__closures"]
    # Graded fields untouched.
    assert row["attempts"] == 5
    assert row["correct"] == 4
    assert row["accuracy"] == 0.8
    # New observational fields present.
    assert row["chat_confidence"] == "weak"
    assert row["chat_confidence_note"] == "Struggled to explain closures in their own words."
    assert "chat_confidence_updated_at" in row
    assert result["chat_confidence"] == "weak"
    assert result["chat_confidence_note"] == "Struggled to explain closures in their own words."


@pytest.mark.asyncio
async def test_record_observation_creates_row_if_none_exists():
    from app.services import skill_graph_service

    written: dict = {}

    async def fake_get(collection, doc_id):
        return written.get(doc_id)

    async def fake_set(collection, doc_id, data):
        written[doc_id] = data

    import unittest.mock as mock
    with mock.patch.object(skill_graph_service.store, "get", fake_get), \
         mock.patch.object(skill_graph_service.store, "set", fake_set):
        await skill_graph_service.record_observation(
            "student-2", "js-fundamentals", "hoisting", "strong", "Explained it correctly unprompted.",
        )

    row = written["student-2__hoisting"]
    assert row["attempts"] == 0
    assert row["chat_confidence"] == "strong"


@pytest.mark.asyncio
async def test_record_observation_composes_with_get_prerequisite_view(monkeypatch):
    """Composition test: prove the write and read tools actually form a loop.
    An agent that calls record_skill_observation must be able to see that
    same observation on its very next get_concept_confidence call — same
    turn or a later session — via get_prerequisite_view's `chat_confidence`/
    `chat_confidence_note` fields. Against a real InMemoryStore (not
    monkeypatched closures), same style as
    test_ensure_populated_and_get_prerequisite_view_agree_on_never_attempted,
    since store.get/store.set/store.update/store.query genuinely sharing
    state is exactly what's under test here."""
    from app.services import knowledge_graph_service

    real_store = InMemoryStore()
    monkeypatch.setattr(skill_graph_service, "store", real_store)

    async def fake_get_prerequisites(course_id, concept):
        assert concept == "closures"
        return ["scope"]

    monkeypatch.setattr(knowledge_graph_service, "get_prerequisites", fake_get_prerequisites)

    # Observation on the target concept itself (no existing row — create path).
    await skill_graph_service.record_observation(
        "student-1", "js-fundamentals", "closures", "weak",
        "Struggled to explain closures in their own words.",
    )
    # Observation on one of its prerequisites, on top of an already-graded row
    # (existing-row path — proves store.update doesn't clobber graded fields).
    await real_store.set("concept_performance", "student-1__scope", {
        "user_id": "student-1", "concept": "scope",
        "attempts": 3, "correct": 2, "accuracy": 0.667,
        "course_id": "js-fundamentals",
    })
    await skill_graph_service.record_observation(
        "student-1", "js-fundamentals", "scope", "strong",
        "Explained variable scope correctly unprompted.",
    )

    view = await skill_graph_service.get_prerequisite_view("student-1", "js-fundamentals", "closures")

    assert view["chat_confidence"] == "weak"
    assert view["chat_confidence_note"] == "Struggled to explain closures in their own words."

    scope_prereq = view["prerequisites"][0]
    assert scope_prereq["concept"] == "scope"
    assert scope_prereq["chat_confidence"] == "strong"
    assert scope_prereq["chat_confidence_note"] == "Explained variable scope correctly unprompted."
    # The graded fields on the prerequisite must have survived the observation write.
    assert scope_prereq["accuracy"] == 0.667
    assert scope_prereq["attempted"] is True


async def test_record_observation_resolves_the_concept_name(monkeypatch):
    # The model may name a concept loosely ("React.memo"); it must land on the
    # canonical row rather than creating a near-duplicate.
    from app.services import concept_resolver

    real_store = InMemoryStore()
    monkeypatch.setattr(skill_graph_service, "store", real_store)
    calls = []

    async def fake_resolve(candidate, course_id=None):
        calls.append((candidate, course_id))
        return "react-memo"

    monkeypatch.setattr(concept_resolver, "resolve", fake_resolve)

    await skill_graph_service.record_observation(
        "s1", "react-perf", "React.memo", "strong", "explained it unprompted")

    # Model-supplied course_id must never reach the resolver (R4).
    assert calls == [("React.memo", None)]
    assert await real_store.get("concept_performance", "s1__react-memo") is not None
    assert await real_store.get("concept_performance", "s1__React.memo") is None


async def test_record_observation_junk_course_id_creates_no_course_scoped_node(monkeypatch):
    # Real resolver, in-memory store, stubbed embeddings: a junk model-supplied
    # course_id must not leak into any created concept node.
    from app.services import concept_resolver

    from app.services import embeddings

    async def fake_embed(text):
        return [0.0, 0.0, 1.0]

    monkeypatch.setattr(embeddings.embedding_service, "embed", fake_embed)
    real_resolve = _REAL_RESOLVE
    monkeypatch.setattr(concept_resolver, "resolve", real_resolve)  # undo autouse stub
    real_store = InMemoryStore()
    monkeypatch.setattr(skill_graph_service, "store", real_store)
    monkeypatch.setattr(concept_resolver, "store", real_store)

    await skill_graph_service.record_observation(
        "s1", "all-courses", "Brand New Idea", "weak", "n")

    nodes = await real_store.list_all("concepts")
    assert nodes, "resolver should have created a node"
    assert all(n.get("course_id") is None for n in nodes)
