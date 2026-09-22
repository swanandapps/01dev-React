import pytest


@pytest.mark.asyncio
async def test_get_learning_metrics_wraps_journey_service(monkeypatch):
    from app.mcp import the01dev_tools
    from app.services import journey_service

    async def fake_get_metrics(student_id):
        assert student_id == "student-1"
        return {"quizzes": 3, "streak": 2, "avg_score": 0.75, "active_days": 3,
                "practice_minutes": 12.5, "questions_answered": 15,
                "courses_engaged": 1, "concepts_practiced": 4,
                "concepts_mastered": 2, "concepts_weak": 1, "avg_seconds_per_question": 10.0}

    monkeypatch.setattr(journey_service, "get_metrics", fake_get_metrics)

    result = await the01dev_tools.get_learning_metrics(student_id="student-1")

    assert result["quizzes"] == 3
    assert result["streak"] == 2
    assert result["avg_score"] == 0.75
