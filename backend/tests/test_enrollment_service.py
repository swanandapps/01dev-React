import pytest

from app.services import enrollment_service
from app.services.store import InMemoryStore


@pytest.mark.asyncio
async def test_enroll_then_get(monkeypatch):
    real_store = InMemoryStore()
    monkeypatch.setattr(enrollment_service, "store", real_store)

    courses = await enrollment_service.enroll("s1", 11, "React Performance Patterns")

    assert courses == [{"id": 11, "title": "React Performance Patterns", "purchased_at": courses[0]["purchased_at"]}]
    assert await enrollment_service.get_enrolled_courses("s1") == courses


@pytest.mark.asyncio
async def test_enroll_is_idempotent(monkeypatch):
    real_store = InMemoryStore()
    monkeypatch.setattr(enrollment_service, "store", real_store)

    await enrollment_service.enroll("s1", 11, "React Performance Patterns")
    courses = await enrollment_service.enroll("s1", 11, "React Performance Patterns")

    assert len(courses) == 1


@pytest.mark.asyncio
async def test_enroll_multiple_courses(monkeypatch):
    real_store = InMemoryStore()
    monkeypatch.setattr(enrollment_service, "store", real_store)

    await enrollment_service.enroll("s1", 11, "React Performance Patterns")
    courses = await enrollment_service.enroll("s1", 9, "JavaScript Deep Dive")

    assert {c["id"] for c in courses} == {11, 9}


@pytest.mark.asyncio
async def test_get_enrolled_courses_empty_for_unknown_student(monkeypatch):
    real_store = InMemoryStore()
    monkeypatch.setattr(enrollment_service, "store", real_store)

    assert await enrollment_service.get_enrolled_courses("nobody") == []
