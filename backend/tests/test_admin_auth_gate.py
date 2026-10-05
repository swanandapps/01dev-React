import pytest
from fastapi.testclient import TestClient

from app import deps as app_deps
from app import main as app_main


@pytest.fixture
def client(monkeypatch):
    from app.services import audit_service

    async def _fake_recent(limit=20):
        return [{"student_id": "x"}]

    monkeypatch.setattr(audit_service, "recent", _fake_recent)
    return TestClient(app_main.app)


def test_admin_routes_open_when_no_key_configured(client, monkeypatch):
    monkeypatch.setattr(app_deps, "_ADMIN_API_KEY", "")
    resp = client.get("/api/hermes/audit")
    assert resp.status_code == 200


def test_admin_routes_reject_missing_key_when_configured(client, monkeypatch):
    monkeypatch.setattr(app_deps, "_ADMIN_API_KEY", "secret-123")
    resp = client.get("/api/hermes/audit")
    assert resp.status_code == 401


def test_admin_routes_reject_wrong_key_when_configured(client, monkeypatch):
    monkeypatch.setattr(app_deps, "_ADMIN_API_KEY", "secret-123")
    resp = client.get("/api/hermes/audit", headers={"X-Admin-Key": "wrong"})
    assert resp.status_code == 401


def test_admin_routes_accept_correct_key_when_configured(client, monkeypatch):
    monkeypatch.setattr(app_deps, "_ADMIN_API_KEY", "secret-123")
    resp = client.get("/api/hermes/audit", headers={"X-Admin-Key": "secret-123"})
    assert resp.status_code == 200


def test_lab_audit_route_gated_the_same_way(client, monkeypatch):
    # /api/lab/audit follows the same require_admin_key convention as the
    # Hermes audit route above, not left open on its own.
    monkeypatch.setattr(app_deps, "_ADMIN_API_KEY", "secret-123")
    assert client.get("/api/lab/audit").status_code == 401
    assert client.get("/api/lab/audit", headers={"X-Admin-Key": "wrong"}).status_code == 401
    resp = client.get("/api/lab/audit", headers={"X-Admin-Key": "secret-123"})
    assert resp.status_code == 200


def test_chat_route_unaffected_by_admin_key(monkeypatch):
    # /api/hermes/chat must NOT require the admin key — it's a student-facing
    # route, not an admin one. Guard against accidentally gating it too.
    monkeypatch.setattr(app_deps, "_ADMIN_API_KEY", "secret-123")
    from app.auth import current_student
    from app.services import audit_service, chat_pipeline, memory_service, skill_graph_service

    async def _fake_chat_turn(req, model=None):
        yield {"type": "done"}

    async def _noop(*args, **kwargs):
        return None

    async def _empty_recent_turns(*args, **kwargs):
        return []

    monkeypatch.setattr(chat_pipeline, "chat_turn", _fake_chat_turn)
    monkeypatch.setattr(audit_service, "log_event", _noop)
    monkeypatch.setattr(memory_service, "recent_turns", _empty_recent_turns)
    monkeypatch.setattr(skill_graph_service, "ensure_populated", _noop)
    # Student auth is the login token, not the admin key — stub it so this test
    # isolates the admin-key question.
    monkeypatch.setitem(app_main.app.dependency_overrides, current_student, lambda: "x")

    client = TestClient(app_main.app)
    resp = client.post(
        "/api/hermes/chat",
        json={"question": "hi", "user_id": "x", "course_slug": "js-fundamentals"},
    )
    assert resp.status_code == 200
