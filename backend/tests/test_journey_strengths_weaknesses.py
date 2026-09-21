import pytest

from app.services import journey_service
from app.services.store import InMemoryStore


@pytest.mark.asyncio
async def test_get_strengths_weaknesses_is_course_agnostic(monkeypatch):
    real_store = InMemoryStore()
    monkeypatch.setattr(journey_service, "store", real_store)

    await real_store.set("concept_performance", "s1__react-memo", {
        "user_id": "s1", "concept": "react-memo", "attempts": 5, "correct": 4, "accuracy": 0.8,
    })
    await real_store.set("concept_performance", "s1__event-loop", {
        "user_id": "s1", "concept": "event-loop", "attempts": 5, "correct": 2, "accuracy": 0.4,
    })
    await real_store.set("concept_performance", "s1__untouched", {
        "user_id": "s1", "concept": "untouched", "attempts": 0, "correct": 0, "accuracy": 0.0,
    })

    result = await journey_service.get_strengths_weaknesses("s1")

    assert [s["concept"] for s in result["strengths"]] == ["react-memo"]
    assert [w["concept"] for w in result["weaknesses"]] == ["event-loop"]
    assert result["concepts_attempted"] == 2  # the untouched row (attempts=0) doesn't count


@pytest.mark.asyncio
async def test_get_strengths_weaknesses_empty_for_new_student(monkeypatch):
    real_store = InMemoryStore()
    monkeypatch.setattr(journey_service, "store", real_store)

    result = await journey_service.get_strengths_weaknesses("brand-new-student")

    assert result == {"strengths": [], "weaknesses": [], "concepts_attempted": 0}
