import pytest

from app.services import journey_service
from app.services.store import InMemoryStore


@pytest.mark.asyncio
async def test_get_metrics_computes_quiz_and_streak_numbers(monkeypatch):
    real_store = InMemoryStore()
    monkeypatch.setattr(journey_service, "store", real_store)

    from datetime import datetime, timezone
    today = datetime.now(timezone.utc).isoformat()

    await real_store.set("quiz_sessions", "s1", {
        "user_id": "s1", "course_id": "react-perf", "score": 4, "total": 5,
        "answers": [{"time_taken_ms": 1000}] * 5, "completed_at": today,
    })
    await real_store.set("concept_performance", "s1__react-memo", {
        "user_id": "s1", "concept": "react-memo", "attempts": 5, "correct": 4, "accuracy": 0.8,
    })

    metrics = await journey_service.get_metrics("s1")

    assert metrics["quizzes"] == 1
    assert metrics["questions_answered"] == 5
    assert metrics["avg_score"] == 0.8
    assert metrics["streak"] == 1
    assert metrics["concepts_mastered"] == 1


@pytest.mark.asyncio
async def test_get_metrics_empty_for_new_student(monkeypatch):
    real_store = InMemoryStore()
    monkeypatch.setattr(journey_service, "store", real_store)

    metrics = await journey_service.get_metrics("brand-new-student")

    assert metrics["quizzes"] == 0
    assert metrics["streak"] == 0
    assert metrics["avg_score"] == 0.0


@pytest.mark.asyncio
async def test_get_metrics_matches_get_journeys_metrics(monkeypatch):
    # get_journey's own metrics computation must stay in sync with the
    # extracted get_metrics — both read the same underlying data.
    real_store = InMemoryStore()
    monkeypatch.setattr(journey_service, "store", real_store)

    async def fake_generate_json(*args, **kwargs):
        return {"narrative": "x", "insights": [], "focus": "y"}

    monkeypatch.setattr(journey_service.llm, "generate_json", fake_generate_json)

    await real_store.set("quiz_sessions", "s1", {
        "user_id": "s1", "course_id": "react-perf", "score": 3, "total": 4,
        "answers": [], "completed_at": "2026-01-01T00:00:00+00:00",
    })

    metrics_only = await journey_service.get_metrics("s1")
    full_journey = await journey_service.get_journey("s1")

    assert metrics_only == full_journey["metrics"]
