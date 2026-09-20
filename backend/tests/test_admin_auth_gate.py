import pytest
from fastapi.testclient import TestClient

from app import main as app_main


@pytest.fixture
def client(monkeypatch):
    from app.services import audit_service

    async def _fake_recent(limit=20):
        return [{"student_id": "x"}]

    monkeypatch.setattr(audit_service, "recent", _fake_recent)
    return TestClient(app_main.app)


def test_admin_routes_open_when_no_key_configured(client, monkeypatch):
    monkeypatch.setattr(app_main, "_ADMIN_API_KEY", "")
    resp = client.get("/api/hermes/audit")
    assert resp.status_code == 200


def test_admin_routes_reject_missing_key_when_configured(client, monkeypatch):
    monkeypatch.setattr(app_main, "_ADMIN_API_KEY", "secret-123")
    resp = client.get("/api/hermes/audit")
    assert resp.status_code == 401


def test_admin_routes_reject_wrong_key_when_configured(client, monkeypatch):
    monkeypatch.setattr(app_main, "_ADMIN_API_KEY", "secret-123")
    resp = client.get("/api/hermes/audit", headers={"X-Admin-Key": "wrong"})
    assert resp.status_code == 401


def test_admin_routes_accept_correct_key_when_configured(client, monkeypatch):
    monkeypatch.setattr(app_main, "_ADMIN_API_KEY", "secret-123")
    resp = client.get("/api/hermes/audit", headers={"X-Admin-Key": "secret-123"})
    assert resp.status_code == 200


def test_chat_route_unaffected_by_admin_key(monkeypatch):
    # /api/hermes/chat must NOT require the admin key — it's a student-facing
    # route, not an admin one. Guard against accidentally gating it too.
    monkeypatch.setattr(app_main, "_ADMIN_API_KEY", "secret-123")
    from app.services import audit_service, hermes_client, memory_service

    async def _fake_stream_chat(question, system=None, history=None):
        yield {"type": "done"}

    async def _noop_log_event(**kwargs):
        return None

    async def _empty_memory_context(*args, **kwargs):
        return ""

    async def _empty_recent_turns(*args, **kwargs):
        return []

    async def _noop_record_turn(*args, **kwargs):
        return None

    monkeypatch.setattr(hermes_client, "stream_chat", _fake_stream_chat)
    monkeypatch.setattr(audit_service, "log_event", _noop_log_event)
    monkeypatch.setattr(memory_service, "memory_context", _empty_memory_context)
    monkeypatch.setattr(memory_service, "recent_turns", _empty_recent_turns)
    monkeypatch.setattr(memory_service, "record_turn", _noop_record_turn)

    client = TestClient(app_main.app)
    resp = client.post(
        "/api/hermes/chat",
        json={"question": "hi", "user_id": "x", "course_slug": "js-fundamentals"},
    )
    assert resp.status_code == 200
