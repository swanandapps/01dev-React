from app.services import hermes_client
from fastapi.testclient import TestClient

from app.main import app


def test_system_prompt_includes_student_and_course_ids(monkeypatch):
    from app.services import audit_service, memory_service

    captured = {}

    async def _capture_stream_chat(question, system=None, history=None):
        captured["system"] = system
        yield {"type": "done"}

    async def _noop_log_event(**kwargs):
        return None

    async def _empty_memory_context(*args, **kwargs):
        return ""

    async def _empty_recent_turns(*args, **kwargs):
        return []

    async def _noop_record_turn(*args, **kwargs):
        return None

    monkeypatch.setattr(hermes_client, "stream_chat", _capture_stream_chat)
    monkeypatch.setattr(audit_service, "log_event", _noop_log_event)
    monkeypatch.setattr(memory_service, "memory_context", _empty_memory_context)
    monkeypatch.setattr(memory_service, "recent_turns", _empty_recent_turns)
    monkeypatch.setattr(memory_service, "record_turn", _noop_record_turn)

    client = TestClient(app)
    resp = client.post(
        "/api/hermes/chat",
        json={
            "question": "What is a closure?",
            "user_id": "identity-test-student",
            "course_slug": "js-fundamentals",
        },
    )
    assert resp.status_code == 200
    assert "identity-test-student" in captured["system"]
    assert "js-fundamentals" in captured["system"]
