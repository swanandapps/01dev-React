import json

import pytest
from fastapi.testclient import TestClient

from app.auth import current_student
from app.main import app
from app.services import chat_pipeline


def _events(text):
    return [json.loads(l[5:].strip()) for l in text.splitlines() if l.startswith("data:")]


@pytest.fixture
def client():
    app.dependency_overrides[current_student] = lambda: "token-uid"
    yield TestClient(app)
    app.dependency_overrides.clear()


def _body(course_id="react-perf", messages=None):
    return {"user_id": "spoofed", "course_id": course_id, "lecture": "4.1 - React.memo and useCallback",
            "messages": messages or [{"role": "user", "content": "first q"},
                                     {"role": "assistant", "content": "first a"},
                                     {"role": "user", "content": "what does this mean?"}]}


def test_player_turn_uses_lecture_scope_client_history_and_token_identity(client, monkeypatch):
    seen = {}

    async def fake_turn(req, model=None):
        seen["req"] = req
        yield {"type": "token", "value": "Think about re-renders."}
        yield {"type": "done"}

    monkeypatch.setattr(chat_pipeline, "chat_turn", fake_turn)
    r = client.post("/api/ai/tutor/stream", json=_body())
    req = seen["req"]
    assert req.student_id == "token-uid"
    assert req.question == "what does this mean?"
    assert req.history == [{"role": "user", "content": "first q"}, {"role": "assistant", "content": "first a"}]
    assert req.scope.course_slug == "react-perf" and req.scope.lecture_title.startswith("4.1")
    assert req.memory_slug == "react-perf"
    assert [e["type"] for e in _events(r.text)] == ["token", "done"]


def test_course_without_transcripts_is_accepted(client, monkeypatch):
    async def fake_turn(req, model=None):
        yield {"type": "done"}
    monkeypatch.setattr(chat_pipeline, "chat_turn", fake_turn)
    r = client.post("/api/ai/tutor/stream", json=_body(course_id="state-management"))
    assert _events(r.text)[-1]["type"] == "done"


def test_unknown_course_and_no_user_message_are_sse_errors(client):
    r = client.post("/api/ai/tutor/stream", json=_body(course_id="nope"))
    assert _events(r.text) == [{"type": "error", "message": "Unknown course"}]
    r = client.post("/api/ai/tutor/stream", json=_body(messages=[{"role": "assistant", "content": "hi"}]))
    assert _events(r.text)[0]["type"] == "error"
