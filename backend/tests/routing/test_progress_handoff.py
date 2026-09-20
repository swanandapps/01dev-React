import pytest

from app.routing.progress_handoff import build_progress_message


@pytest.mark.asyncio
async def test_progress_message_surfaces_the_existing_narrative(monkeypatch):
    from app.routing import progress_handoff

    async def fake_get_journey(user_id):
        assert user_id == "student-42"
        return {
            "metrics": {"quizzes": 3, "avg_score": 0.75},
            "heatmap": [],
            "strengths": [{"concept": "closures", "accuracy": 0.9, "attempts": 4}],
            "weaknesses": [{"concept": "async/await", "accuracy": 0.4, "attempts": 3}],
            "ai": {
                "narrative": "You've been consistent this week.",
                "insights": ["You do best in the mornings."],
                "focus": "Review async/await next.",
            },
        }

    monkeypatch.setattr(progress_handoff, "get_journey", fake_get_journey)
    msg = await build_progress_message("student-42")
    assert "You've been consistent this week." in msg
    assert "Review async/await next." in msg


@pytest.mark.asyncio
async def test_progress_message_handles_no_activity_yet(monkeypatch):
    from app.routing import progress_handoff

    async def fake_get_journey(user_id):
        return {
            "metrics": {"quizzes": 0, "avg_score": 0.0},
            "heatmap": [],
            "strengths": [],
            "weaknesses": [],
            "ai": {"narrative": "No activity yet.", "insights": [], "focus": "Take your first quiz to start tracking."},
        }

    monkeypatch.setattr(progress_handoff, "get_journey", fake_get_journey)
    msg = await build_progress_message("new-student")
    assert "No activity yet." in msg
