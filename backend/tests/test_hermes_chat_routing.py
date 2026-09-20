import json

import pytest
from fastapi.testclient import TestClient

from app.main import app


@pytest.fixture
def client(monkeypatch):
    # Never touch Postgres/OpenAI/audit storage from this test — it's
    # asserting routing behavior, not the downstream services' correctness.
    from app.services import audit_service, memory_service

    async def _noop_log_event(**kwargs):
        return None

    async def _empty_memory_context(*args, **kwargs):
        return ""

    async def _empty_recent_turns(*args, **kwargs):
        return []

    async def _noop_record_turn(*args, **kwargs):
        return None

    monkeypatch.setattr(audit_service, "log_event", _noop_log_event)
    monkeypatch.setattr(memory_service, "memory_context", _empty_memory_context)
    monkeypatch.setattr(memory_service, "recent_turns", _empty_recent_turns)
    monkeypatch.setattr(memory_service, "record_turn", _noop_record_turn)
    return TestClient(app)


def _sse_events(raw_text: str) -> list[dict]:
    events = []
    for line in raw_text.splitlines():
        if line.startswith("data:"):
            events.append(json.loads(line[len("data:"):].strip()))
    return events


def test_quiz_intent_short_circuits_before_any_model_call(client, monkeypatch):
    # If routing is broken and this falls through to the real grounded/agentic
    # path, these would be hit and (without network) raise — the test fails
    # loudly instead of silently calling out to OpenAI/Hermes.
    from app.services import grounding

    async def _fail_if_called(*args, **kwargs):
        raise AssertionError("retrieval must not run for a QUIZ_GENERATE request")

    monkeypatch.setattr(grounding, "retrieve", _fail_if_called)

    resp = client.post(
        "/api/hermes/chat",
        json={
            "question": "Can you quiz me on closures?",
            "user_id": "test-student",
            "course_slug": "js-fundamentals",
        },
    )
    assert resp.status_code == 200
    events = _sse_events(resp.text)
    tokens = "".join(e["value"] for e in events if e.get("type") == "token")
    assert "QuizMe" in tokens
    assert any(e.get("type") == "done" for e in events)


def test_course_question_intent_is_unaffected(client, monkeypatch):
    # Not asserting the full grounded-answer path here (that's rag_service's
    # own concern) — only that a normal question is NOT diverted into the
    # quiz hand-off.
    from app.services import grounding

    async def _empty_retrieve(*args, **kwargs):
        return []

    monkeypatch.setattr(grounding, "retrieve", _empty_retrieve)

    resp = client.post(
        "/api/hermes/chat",
        json={
            "question": "What is a closure?",
            "user_id": "test-student",
            "course_slug": "js-fundamentals",
        },
    )
    assert resp.status_code == 200
    events = _sse_events(resp.text)
    tokens = "".join(e["value"] for e in events if e.get("type") == "token")
    assert "QuizMe" not in tokens


def test_progress_intent_calls_journey_service_not_the_model(client, monkeypatch):
    from app.routing import progress_handoff
    from app.services import grounding

    async def _fail_if_called(*args, **kwargs):
        raise AssertionError("retrieval must not run for a PROGRESS_LOOKUP request")

    async def _fake_get_journey(user_id):
        assert user_id == "test-student"
        return {"ai": {"narrative": "You're making steady progress.", "insights": [], "focus": "Keep it up."}}

    monkeypatch.setattr(grounding, "retrieve", _fail_if_called)
    monkeypatch.setattr(progress_handoff, "get_journey", _fake_get_journey)

    resp = client.post(
        "/api/hermes/chat",
        json={
            "question": "What's my progress so far?",
            "user_id": "test-student",
            "course_slug": "js-fundamentals",
        },
    )
    assert resp.status_code == 200
    events = _sse_events(resp.text)
    tokens = "".join(e["value"] for e in events if e.get("type") == "token")
    assert "You're making steady progress." in tokens
