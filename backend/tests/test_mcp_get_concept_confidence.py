import pytest


@pytest.mark.asyncio
async def test_get_concept_confidence_wraps_get_prerequisite_view(monkeypatch):
    from app.mcp import the01dev_tools
    from app.services import skill_graph_service

    async def fake_get_prerequisite_view(user_id, course_id, concept):
        assert (user_id, course_id, concept) == ("student-1", "js-fundamentals", "closures")
        return {
            "concept": "closures", "accuracy": 0.6, "attempts": 5, "attempted": True,
            "prerequisites": [
                {"concept": "scope", "accuracy": 0.3, "attempts": 2, "attempted": True},
            ],
            "weakest_prerequisite": {"concept": "scope", "accuracy": 0.3, "attempts": 2, "attempted": True},
        }

    monkeypatch.setattr(skill_graph_service, "get_prerequisite_view", fake_get_prerequisite_view)

    result = await the01dev_tools.get_concept_confidence(
        concept="closures", course_id="js-fundamentals", student_id="student-1",
    )

    assert result["concept"] == "closures"
    assert result["weakest_prerequisite"]["concept"] == "scope"
