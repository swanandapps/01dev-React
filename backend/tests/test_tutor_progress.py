"""The tutor's progress tool: platform-wide numbers or, in the player, this course only — always labelled with
its scope — plus the last few quizzes with scores (so 'what did I score last time?' has an answer)."""
import json

import pytest

from app.services import journey_service, tutor_agent
from app.services.store import InMemoryStore


@pytest.fixture
async def st(monkeypatch):
    s = InMemoryStore()
    monkeypatch.setattr(journey_service, "store", s)
    rows = [("a", "react-perf", "React Performance Patterns", 4, 5, "2026-10-01T10:00:00+00:00"),
            ("b", "custom-library", "Build a Custom Library", 2, 3, "2026-10-05T10:00:00+00:00"),
            ("c", "custom-library", "Build a Custom Library", 3, 3, "2026-10-06T10:00:00+00:00")]
    for sid, slug, title, score, total, at in rows:
        await s.set("quiz_sessions", sid, {"user_id": "me", "course_id": slug, "course_title": title,
                                           "score": score, "total": total, "answers": [], "completed_at": at})
    await s.set("concept_performance", "me__npm-link", {"user_id": "me", "concept": "npm-link", "course_id": "custom-library",
                                                       "attempts": 6, "correct": 5, "accuracy": 0.83})
    await s.set("concept_performance", "me__react-memo", {"user_id": "me", "concept": "react-memo", "course_id": "react-perf",
                                                         "attempts": 5, "correct": 2, "accuracy": 0.4})
    return s


async def test_all_courses_progress_is_labelled_and_lists_recent_quizzes_newest_first(st):
    p = await journey_service.get_progress("me")
    assert p["scope"] == "all your courses" and p["metrics"]["quizzes"] == 3
    assert [(q["course"], q["score"], q["total"]) for q in p["recent_quizzes"]] == [
        ("Build a Custom Library", 3, 3), ("Build a Custom Library", 2, 3), ("React Performance Patterns", 4, 5)]
    assert p["recent_quizzes"][0]["date"] == "2026-10-06"


async def test_this_course_only_filters_quizzes_and_concepts(st):
    p = await journey_service.get_progress("me", "custom-library")
    assert p["scope"] == "Build a Custom Library only"
    assert p["metrics"]["quizzes"] == 2 and p["metrics"]["questions_answered"] == 6
    assert p["metrics"]["concepts_practiced"] == 1
    assert {q["course"] for q in p["recent_quizzes"]} == {"Build a Custom Library"}


async def test_the_tool_uses_the_watched_course_only_when_asked(st):
    from types import SimpleNamespace
    rt = SimpleNamespace(context=tutor_agent.ChatContext(student_id="me", in_course="custom-library"))
    scoped = json.loads(await tutor_agent.get_learning_metrics.coroutine(this_course_only=True, runtime=rt))
    overall = json.loads(await tutor_agent.get_learning_metrics.coroutine(this_course_only=False, runtime=rt))
    assert scoped["scope"] == "Build a Custom Library only" and overall["scope"] == "all your courses"
    ask = SimpleNamespace(context=tutor_agent.ChatContext(student_id="me"))     # Ask page: no watched course
    assert json.loads(await tutor_agent.get_learning_metrics.coroutine(this_course_only=True, runtime=ask))["scope"] == "all your courses"


def test_prompt_keeps_the_running_project_inside_the_player():
    from app.grounding import loader
    assert "Only in the player" in loader.read_grounding_prompt()
