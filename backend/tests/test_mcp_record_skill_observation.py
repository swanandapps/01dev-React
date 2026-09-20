import pytest


@pytest.mark.asyncio
async def test_record_skill_observation_wraps_record_observation(monkeypatch):
    from app.mcp import the01dev_tools

    async def fake_record_observation(user_id, course_id, concept, confidence, note):
        assert (user_id, course_id, concept, confidence, note) == (
            "student-1", "js-fundamentals", "closures", "weak", "some note",
        )
        return {"concept": "closures", "chat_confidence": "weak"}

    monkeypatch.setattr(the01dev_tools, "record_observation", fake_record_observation)

    result = await the01dev_tools.record_skill_observation(
        concept="closures", course_id="js-fundamentals", student_id="student-1",
        confidence="weak", note="some note",
    )

    assert result == {"concept": "closures", "chat_confidence": "weak"}


@pytest.mark.asyncio
async def test_record_skill_observation_rejects_bad_confidence_without_crashing():
    from app.mcp import the01dev_tools

    result = await the01dev_tools.record_skill_observation(
        concept="closures", course_id="js-fundamentals", student_id="student-1",
        confidence="super-duper-good", note="x",
    )
    assert "error" in result
