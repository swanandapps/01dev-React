import pytest


@pytest.mark.asyncio
async def test_get_learning_strengths_enriches_weaknesses_with_prerequisites(monkeypatch):
    from app.mcp import the01dev_tools
    from app.services import journey_service, knowledge_graph_service, skill_graph_service

    async def fake_get_strengths_weaknesses(student_id):
        assert student_id == "student-1"
        return {
            "strengths": [{"concept": "react-memo", "accuracy": 0.9, "attempts": 5}],
            "weaknesses": [{"concept": "class-syntax-sugar", "accuracy": 0.4, "attempts": 4}],
            "concepts_attempted": 2,
        }

    async def fake_find_course_for_concept(concept, student_id=None):
        assert concept == "class-syntax-sugar"
        return "javascript-deep-dive"

    async def fake_get_prerequisite_view(student_id, course_id, concept):
        assert (student_id, course_id, concept) == ("student-1", "javascript-deep-dive", "class-syntax-sugar")
        return {
            "concept": concept, "accuracy": 0.4, "attempts": 4, "attempted": True,
            "prerequisites": [{"concept": "prototype-inheritance", "accuracy": 0.83, "attempts": 6, "attempted": True}],
            "weakest_prerequisite": None,
        }

    monkeypatch.setattr(journey_service, "get_strengths_weaknesses", fake_get_strengths_weaknesses)
    monkeypatch.setattr(knowledge_graph_service, "find_course_for_concept", fake_find_course_for_concept)
    monkeypatch.setattr(skill_graph_service, "get_prerequisite_view", fake_get_prerequisite_view)

    result = await the01dev_tools.get_learning_strengths(student_id="student-1")

    assert result["strengths"] == [{"concept": "react-memo", "accuracy": 0.9, "attempts": 5}]
    assert len(result["weaknesses"]) == 1
    weak = result["weaknesses"][0]
    assert weak["concept"] == "class-syntax-sugar"
    assert weak["course_id"] == "javascript-deep-dive"
    assert weak["prerequisites"] == [{"concept": "prototype-inheritance", "accuracy": 0.83, "attempts": 6, "attempted": True}]
    assert result["concepts_attempted"] == 2


@pytest.mark.asyncio
async def test_get_learning_strengths_skips_prereq_lookup_when_concept_has_no_course(monkeypatch):
    from app.mcp import the01dev_tools
    from app.services import journey_service, knowledge_graph_service

    async def fake_get_strengths_weaknesses(student_id):
        return {
            "strengths": [],
            "weaknesses": [{"concept": "orphan-concept", "accuracy": 0.3, "attempts": 2}],
            "concepts_attempted": 1,
        }

    async def fake_find_course_for_concept(concept, student_id=None):
        return None

    monkeypatch.setattr(journey_service, "get_strengths_weaknesses", fake_get_strengths_weaknesses)
    monkeypatch.setattr(knowledge_graph_service, "find_course_for_concept", fake_find_course_for_concept)

    result = await the01dev_tools.get_learning_strengths(student_id="student-2")

    assert result["weaknesses"][0]["course_id"] is None
    assert result["weaknesses"][0]["prerequisites"] == []
