import pytest


@pytest.mark.asyncio
async def test_get_enrolled_courses_wraps_enrollment_service(monkeypatch):
    from app.mcp import the01dev_tools
    from app.services import enrollment_service

    async def fake_get_enrolled_courses(student_id):
        assert student_id == "student-1"
        return [{"id": 11, "title": "React Performance Patterns", "purchased_at": "2026-01-01T00:00:00"}]

    monkeypatch.setattr(enrollment_service, "get_enrolled_courses", fake_get_enrolled_courses)

    result = await the01dev_tools.get_enrolled_courses(student_id="student-1")

    assert result == [{"id": 11, "title": "React Performance Patterns", "purchased_at": "2026-01-01T00:00:00"}]
