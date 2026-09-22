import pytest

from app.routing import smalltalk_classifier
from app.services.embeddings import embedding_service


@pytest.mark.asyncio
async def test_length_gate_skips_the_embedding_call_entirely(monkeypatch):
    async def _fail_if_called(text):
        raise AssertionError("embed() must not be called for a message over the word limit")

    monkeypatch.setattr(embedding_service, "embed", _fail_if_called)
    monkeypatch.setattr(smalltalk_classifier, "_example_embeddings", None)

    result = await smalltalk_classifier.check("why does my component re-render every single time it updates")

    assert result == {"checked": False, "similarity": 0.0, "should_block": False}


@pytest.mark.asyncio
async def test_high_similarity_greeting_is_flagged_but_not_blocked_by_default(monkeypatch):
    # Deterministic fake embeddings: examples and "hello there" all map to
    # the identical vector -> similarity 1.0 -> would clear any real
    # threshold, but SMALLTALK_BLOCK_ENABLED defaults to false.
    async def _fake_embed(text):
        return [1.0, 0.0]

    monkeypatch.setattr(embedding_service, "embed", _fake_embed)
    monkeypatch.setattr(smalltalk_classifier, "_example_embeddings", None)
    monkeypatch.setattr(smalltalk_classifier, "_BLOCK_ENABLED", False)
    monkeypatch.setattr(smalltalk_classifier, "_THRESHOLD", 0.85)

    result = await smalltalk_classifier.check("hello there")

    assert result["checked"] is True
    assert result["similarity"] == 1.0
    assert result["should_block"] is False


@pytest.mark.asyncio
async def test_should_block_only_when_flag_enabled_and_above_threshold(monkeypatch):
    async def _fake_embed(text):
        return [1.0, 0.0] if text != "a real technical question" else [0.0, 1.0]

    monkeypatch.setattr(embedding_service, "embed", _fake_embed)
    monkeypatch.setattr(smalltalk_classifier, "_example_embeddings", None)
    monkeypatch.setattr(smalltalk_classifier, "_BLOCK_ENABLED", True)
    monkeypatch.setattr(smalltalk_classifier, "_THRESHOLD", 0.85)

    greeting_result = await smalltalk_classifier.check("hey there")
    assert greeting_result["should_block"] is True

    monkeypatch.setattr(smalltalk_classifier, "_example_embeddings", None)
    unrelated_result = await smalltalk_classifier.check("a real technical question")
    assert unrelated_result["similarity"] == 0.0
    assert unrelated_result["should_block"] is False


@pytest.mark.asyncio
async def test_example_embeddings_are_cached_across_calls(monkeypatch):
    calls = []

    async def _counting_embed(text):
        calls.append(text)
        return [1.0, 0.0]

    monkeypatch.setattr(embedding_service, "embed", _counting_embed)
    monkeypatch.setattr(smalltalk_classifier, "_example_embeddings", None)

    await smalltalk_classifier.check("hi")
    first_call_count = len(calls)
    await smalltalk_classifier.check("hey")

    # Second call only embeds the new question — the example set isn't re-embedded.
    assert len(calls) == first_call_count + 1
