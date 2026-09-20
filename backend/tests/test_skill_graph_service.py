import pytest

from app.services import skill_graph_service


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

    async def fake_get(collection, doc_id):
        return written.get(doc_id)

    async def fake_set(collection, doc_id, data):
        assert collection == "concept_performance"
        written[doc_id] = data

    monkeypatch.setattr(knowledge_graph_service, "has_graph", fake_has_graph)
    monkeypatch.setattr(knowledge_graph_service, "get_graph", fake_get_graph)
    monkeypatch.setattr(skill_graph_service.store, "get", fake_get)
    monkeypatch.setattr(skill_graph_service.store, "set", fake_set)

    created = await skill_graph_service.ensure_populated("student-1", "js-fundamentals")

    assert created == 2
    row = written["student-1__closures"]
    assert row == {
        "user_id": "student-1", "concept": "closures",
        "attempts": 0, "correct": 0, "accuracy": 0.0,
        "course_id": "js-fundamentals", "source": "pre_populated",
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

    async def fake_get(collection, doc_id):
        return written.get(doc_id)

    async def fake_set(collection, doc_id, data):
        written[doc_id] = data

    monkeypatch.setattr(knowledge_graph_service, "has_graph", fake_has_graph)
    monkeypatch.setattr(knowledge_graph_service, "get_graph", fake_get_graph)
    monkeypatch.setattr(skill_graph_service.store, "get", fake_get)
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
