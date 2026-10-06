"""app.retrieval.titles: the lecture-title signal (cache, prewarm, cooldown, word-overlap fallback).
Moved here from test_course_lookup when course_lookup's thin wrappers were deleted (Task 15)."""
from types import SimpleNamespace

import pytest

from app.retrieval import titles as title_index
from app.services import catalog_service
from app.services.embeddings import embedding_service

ES = "10.1 - What Are ES Modules"
LINK = "8.1 - The `npm link` command"


def _fake_embeddings_client(monkeypatch, behaviour):
    """Stub OpenAI client: behaviour(texts) -> vectors or raises. Returns the list of input batches."""
    batches = []

    async def create(model, input):
        batches.append(list(input))
        return SimpleNamespace(data=[SimpleNamespace(embedding=v) for v in behaviour(input)])

    monkeypatch.setattr(embedding_service, "use_openai", True)
    monkeypatch.setattr(embedding_service, "client", SimpleNamespace(embeddings=SimpleNamespace(create=create)))
    monkeypatch.setattr(title_index, "_cache", {})
    monkeypatch.setattr(title_index, "_failed_until", {})
    return batches


def _one_course(monkeypatch, titles):
    monkeypatch.setattr(catalog_service, "by_slug", lambda slug: {"chapters": [{"name": "c", "subchapters": titles}]})


async def test_title_scores_fall_back_to_word_overlap_without_embeddings(monkeypatch):
    monkeypatch.setattr(embedding_service, "use_openai", False)
    _one_course(monkeypatch, [ES, LINK])
    scores = await title_index.title_scores(None, ["custom-library"], question="what are ES modules")
    assert scores[("custom-library", ES)] >= title_index.TITLE_THRESHOLD
    assert scores[("custom-library", LINK)] < title_index.TITLE_THRESHOLD
    other = await title_index.title_scores(None, ["custom-library"], question="how does the event loop work")
    assert other[("custom-library", ES)] == 0.0


async def test_title_embedding_failure_falls_back_to_overlap_and_is_not_retried_in_the_cooldown(monkeypatch):
    calls = {"n": 0}

    class Boom:
        class embeddings:
            @staticmethod
            async def create(**kw):
                calls["n"] += 1
                raise RuntimeError("openai down")

    monkeypatch.setattr(embedding_service, "use_openai", True)
    monkeypatch.setattr(embedding_service, "client", Boom)
    monkeypatch.setattr(title_index, "_cache", {})
    monkeypatch.setattr(title_index, "_failed_until", {})
    _one_course(monkeypatch, [ES])
    first = await title_index.title_scores([1.0, 0.0], ["custom-library"], question="what are ES modules")
    second = await title_index.title_scores([1.0, 0.0], ["custom-library"], question="what are ES modules")
    assert first == second == {("custom-library", ES): 1.0}
    assert calls["n"] == 1
    title_index._failed_until["custom-library"] = 0.0  # cooldown over -> retries
    await title_index.title_scores([1.0, 0.0], ["custom-library"], question="what are ES modules")
    assert calls["n"] == 2


async def test_prewarm_embeds_every_course_in_one_call_and_fills_the_cache(monkeypatch):
    batches = _fake_embeddings_client(monkeypatch, lambda texts: [[1.0, float(i)] for i, _ in enumerate(texts)])
    n_titles, n_courses = await title_index.prewarm()
    expected = {c["slug"]: title_index.lecture_titles(c["slug"]) for c in catalog_service.all_courses()}
    expected = {k: v for k, v in expected.items() if v}
    assert len(batches) == 1 and n_courses == len(expected) and n_titles == sum(map(len, expected.values()))
    assert set(title_index._cache) == set(expected)
    for slug, titles in expected.items():
        assert title_index._cache[slug][0] == titles and len(title_index._cache[slug][1]) == len(titles)


async def test_prewarm_failure_raises_but_sets_no_cooldown(monkeypatch):
    def boom(texts):
        raise RuntimeError("openai down")

    _fake_embeddings_client(monkeypatch, boom)
    with pytest.raises(RuntimeError):
        await title_index.prewarm()
    assert title_index._failed_until == {} and title_index._cache == {}


async def test_scoring_never_embeds_the_question_and_uses_cached_cosines(monkeypatch):
    _fake_embeddings_client(monkeypatch, lambda texts: [[1.0, 0.0] for _ in texts])
    await title_index.prewarm()

    async def no_embed(text):
        raise AssertionError("title_scores must reuse the given question embedding")

    monkeypatch.setattr(embedding_service, "embed", no_embed)
    scores = await title_index.title_scores([1.0, 0.0], ["custom-library"], question="npm link")
    assert scores and set(scores.values()) == {1.0} and title_index._failed_until == {}


async def test_title_build_failure_still_sets_a_short_cooldown(monkeypatch):
    def boom(texts):
        raise RuntimeError("down")

    _fake_embeddings_client(monkeypatch, boom)
    await title_index.title_scores([1.0, 0.0], ["custom-library"], question="npm link")
    assert 0 < title_index._failed_until["custom-library"] - title_index.time.monotonic() <= 60.0
