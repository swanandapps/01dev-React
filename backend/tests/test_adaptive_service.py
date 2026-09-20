import pytest

from app.services import adaptive_service, skill_graph_service, question_service


@pytest.mark.asyncio
async def test_start_calls_ensure_populated(monkeypatch):
    """Nothing else in the suite would fail if adaptive_service.start()
    stopped calling skill_graph_service.ensure_populated — this pins the
    wiring directly so a future refactor can't silently drop it."""
    calls = []

    async def fake_ensure_populated(user_id, course_id):
        calls.append((user_id, course_id))
        return 0

    async def fake_question_bank(course_id):
        # Keep start() on the short "preparing" path so we don't need to
        # stand up a full question bank / session store for this test.
        return []

    async def fake_ensure_generated(course_id):
        return {}

    monkeypatch.setattr(skill_graph_service, "ensure_populated", fake_ensure_populated)
    monkeypatch.setattr(adaptive_service, "_question_bank", fake_question_bank)
    monkeypatch.setattr(question_service, "ensure_generated", fake_ensure_generated)

    result = await adaptive_service.start("student-1", "js-fundamentals")

    assert calls == [("student-1", "js-fundamentals")]
    assert result == {"status": "preparing"}


@pytest.mark.asyncio
async def test_start_survives_ensure_populated_failure(monkeypatch):
    """A transient store error during the (non-essential) back-fill must not
    take down session start — ensure_populated's own docstring calls it a
    silent no-op, and start() must honor that even when it raises."""
    async def failing_ensure_populated(user_id, course_id):
        raise RuntimeError("store unavailable")

    async def fake_question_bank(course_id):
        return []

    async def fake_ensure_generated(course_id):
        return {}

    monkeypatch.setattr(skill_graph_service, "ensure_populated", failing_ensure_populated)
    monkeypatch.setattr(adaptive_service, "_question_bank", fake_question_bank)
    monkeypatch.setattr(question_service, "ensure_generated", fake_ensure_generated)

    result = await adaptive_service.start("student-1", "js-fundamentals")

    assert result == {"status": "preparing"}
