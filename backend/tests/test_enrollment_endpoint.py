import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.services.store import InMemoryStore


@pytest.mark.asyncio
async def test_post_then_get_enrollment(monkeypatch):
    from app.services import enrollment_service

    real_store = InMemoryStore()
    monkeypatch.setattr(enrollment_service, "store", real_store)

    client = TestClient(app)
    resp = client.post("/api/enrollment", json={
        "student_id": "s1", "course_id": 11, "course_title": "React Performance Patterns",
    })
    assert resp.status_code == 200
    assert resp.json() == [{"id": 11, "title": "React Performance Patterns",
                             "purchased_at": resp.json()[0]["purchased_at"]}]

    resp2 = client.get("/api/enrollment/s1")
    assert resp2.status_code == 200
    assert resp2.json() == resp.json()


@pytest.mark.asyncio
async def test_get_enrollment_empty_for_unknown_student(monkeypatch):
    from app.services import enrollment_service

    real_store = InMemoryStore()
    monkeypatch.setattr(enrollment_service, "store", real_store)

    client = TestClient(app)
    resp = client.get("/api/enrollment/nobody")
    assert resp.status_code == 200
    assert resp.json() == []
