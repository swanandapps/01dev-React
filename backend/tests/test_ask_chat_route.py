import json

import pytest
from fastapi.testclient import TestClient

from app.auth import current_student
from app.main import app
from app.services import audit_service, chat_pipeline, memory_service, skill_graph_service


def _events(text):
    return [json.loads(l[5:].strip()) for l in text.splitlines() if l.startswith("data:")]


@pytest.fixture
def client(monkeypatch):
    async def noop(*a, **k):
        return None
    async def empty_list(*a, **k):
        return []
    async def zero(*a, **k):
        return 0
    monkeypatch.setattr(audit_service, "log_event", noop)
    monkeypatch.setattr(memory_service, "recent_turns", empty_list)
    monkeypatch.setattr(skill_graph_service, "ensure_populated", zero)
    app.dependency_overrides[current_student] = lambda: "token-uid"
    yield TestClient(app)
    app.dependency_overrides.clear()


def test_course_question_streams_through_chat_turn_with_token_identity(client, monkeypatch):
    seen = {}

    async def fake_turn(req, model=None):
        seen["req"] = req
        yield {"type": "sources", "sources": [], "insufficient_context": False, "offer_general": False}
        yield {"type": "token", "value": "hi"}
        yield {"type": "done"}

    monkeypatch.setattr(chat_pipeline, "chat_turn", fake_turn)
    r = client.post("/api/hermes/chat", json={"question": "what is npm link", "user_id": "someone-else",
                                               "course_slug": "all-courses"})
    assert r.status_code == 200
    assert [e["type"] for e in _events(r.text)] == ["sources", "token", "done"]
    assert seen["req"].student_id == "token-uid"
    assert seen["req"].scope.course_slug is None and seen["req"].memory_slug == "all-courses"


def test_quiz_request_is_handed_off_without_the_agent(client, monkeypatch):
    async def must_not_run(req, model=None):
        raise AssertionError("agent should not run for quiz hand-off")
        yield

    monkeypatch.setattr(chat_pipeline, "chat_turn", must_not_run)
    r = client.post("/api/hermes/chat", json={"question": "quiz me on closures", "course_slug": "all-courses"})
    tokens = "".join(e.get("value", "") for e in _events(r.text) if e["type"] == "token")
    assert r.status_code == 200 and tokens.strip()


def test_quiz_hand_off_survives_an_audit_failure(client, monkeypatch):
    async def audit_down(**kw):
        raise RuntimeError("store unavailable")
    monkeypatch.setattr(audit_service, "log_event", audit_down)
    r = client.post("/api/hermes/chat", json={"question": "quiz me on closures", "course_slug": "all-courses"})
    events = _events(r.text)
    assert r.status_code == 200
    assert [e["type"] for e in events][0] == "sources" and events[-1]["type"] == "done"
    assert "".join(e.get("value", "") for e in events if e["type"] == "token").strip()


def test_empty_question_is_400(client):
    assert client.post("/api/hermes/chat", json={"question": "  "}).status_code == 400


def test_no_token_is_401():
    app.dependency_overrides.clear()
    r = TestClient(app).post("/api/hermes/chat", json={"question": "hi", "user_id": "x"})
    assert r.status_code == 401
