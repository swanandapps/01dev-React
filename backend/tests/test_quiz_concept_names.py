"""Quizzes built from a course tag each question with the course's own concept names (the ones its question bank
uses, which the tutor's weak-concept list and the dashboard read), so results land on existing concepts instead
of near-duplicates like "event-loop-role" next to "event-loop"."""
from types import SimpleNamespace

import pytest

from app.services import lab_topics, lecture_context, quick_quiz_service as qq
from app.services.lab import llm
from app.services.store import store

BANK = ["event-loop", "microtask-queue", "promise-chaining"]


def _q(i):
    return {"question": f"Q{i}?", "options": ["one two three four five", "six seven eight nine ten",
                                              "aa bb cc dd ee", "ff gg hh ii jj"],
            "correctIndex": 0, "explanation": "e", "hint": "h", "concept": "event-loop"}


def test_the_generator_is_given_the_course_concept_names(monkeypatch):
    prompts = []
    monkeypatch.setattr(llm, "_chat_json", lambda system, user, max_tokens=900: prompts.append(user) or
                        {"questions": [_q(i) for i in range(3)]})
    llm.gen_quiz("material", {"title": "The event loop"}, 3, concepts=BANK)
    assert "event-loop, microtask-queue, promise-chaining" in prompts[0]

    prompts.clear()
    llm.gen_quiz("material", {"title": "The event loop"}, 3)
    assert "CONCEPT NAMES" not in prompts[0]          # no course list (notes, PDFs): free naming as before


@pytest.fixture
def course_with_bank(monkeypatch):
    seen = {}

    def gen(document, objective, n, concepts=None):
        seen.setdefault("concepts", []).append(concepts)
        return [_q(i) for i in range(n)]

    async def chunks(slug, title):
        return [SimpleNamespace(text=f"{title} passage {i}", text_clean=None, start_time=i * 45.0) for i in range(4)]

    async def to_practise(student_id, course, chapter, limit):
        return ["6.1 - The Event Loop", "6.2 - Microtasks"]

    monkeypatch.setattr(llm, "gen_quiz", gen)
    monkeypatch.setattr(lecture_context, "lecture_chunks", chunks)
    monkeypatch.setattr(lab_topics, "lectures_to_practise", to_practise)
    return seen


@pytest.mark.asyncio
async def test_player_and_topic_quizzes_pass_the_course_bank(course_with_bank):
    await store.set("questions", "concept-names-course", {"questions": [{"concept": c} for c in BANK + ["event-loop"]]})
    course = {"slug": "concept-names-course", "title": "JS", "chapters": [
        {"name": "Concurrency", "subchapters": [{"name": "6.1 - The Event Loop"}, {"name": "6.2 - Microtasks"}]}]}

    await qq.create("concept-names-uid", course, "6.1 - The Event Loop", position=None)
    await qq.create_for_topic("concept-names-uid", course, 0)
    assert course_with_bank["concepts"] == [BANK, BANK, BANK]     # sorted, deduped; one call per topic lecture


@pytest.mark.asyncio
async def test_a_course_without_a_bank_names_freely(course_with_bank):
    course = {"slug": "no-bank-course", "title": "X", "chapters": []}
    await qq.create("concept-names-uid", course, "1.1 - Intro", position=None)
    assert course_with_bank["concepts"] == [None]
