import pytest

from app.services import skill_graph_service
from app.services.store import InMemoryStore


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
