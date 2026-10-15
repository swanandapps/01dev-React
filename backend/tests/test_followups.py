"""Ask page follow-up chips: up to 3 short next questions the student might ask, from one small model call after
the answer has finished. Never blocks or fails a turn: any problem -> no chips."""
import pytest
from fastapi.testclient import TestClient

from app.auth import current_student
from app.main import app
from app.services import followups


@pytest.fixture
def client():
    app.dependency_overrides[current_student] = lambda: "me"
    yield TestClient(app)
    app.dependency_overrides.clear()


def _model(monkeypatch, reply):
    seen = {}

    async def fake(system, user, temperature=0.3, max_tokens=1500):
        seen["user"] = user
        return reply

    monkeypatch.setattr(followups.llm, "generate_json", fake)
    return seen


def test_three_short_distinct_questions(client, monkeypatch):
    seen = _model(monkeypatch, {"suggestions": ["What does np check before publishing?", "How do I test it locally first?",
                                                "what does np check before publishing?", "x" * 200, "", 7, "Quiz me?"]})
    r = client.post("/api/ai/followups", json={"question": "how do I publish to npm?", "answer": "Use np..."})
    assert r.status_code == 200
    assert r.json() == {"suggestions": ["What does np check before publishing?", "How do I test it locally first?", "Quiz me?"]}
    assert "how do I publish to npm?" in seen["user"] and "Use np..." in seen["user"]


@pytest.mark.parametrize("reply", [None, {}, {"suggestions": "nope"}])
def test_a_bad_reply_means_no_chips(client, monkeypatch, reply):
    _model(monkeypatch, reply)
    assert client.post("/api/ai/followups", json={"question": "q", "answer": "a"}).json() == {"suggestions": []}


def test_a_model_error_means_no_chips(client, monkeypatch):
    async def boom(*a, **k):
        raise RuntimeError("down")

    monkeypatch.setattr(followups.llm, "generate_json", boom)
    assert client.post("/api/ai/followups", json={"question": "q", "answer": "a"}).json() == {"suggestions": []}


def test_needs_login():
    app.dependency_overrides.clear()
    assert TestClient(app).post("/api/ai/followups", json={"question": "q", "answer": "a"}).status_code == 401
