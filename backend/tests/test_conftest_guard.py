"""The leak guard must catch a direct embeddings.create call (not only EmbeddingService)."""
import pytest
from openai import AsyncOpenAI


@pytest.mark.asyncio
async def test_guard_blocks_direct_openai_embeddings_create(_no_real_db_or_embeddings):
    client = AsyncOpenAI(api_key="sk-test")
    with pytest.raises(AssertionError, match="real OpenAI embeddings client"):
        await client.embeddings.create(model="text-embedding-3-small", input=["x"])
    leaks = _no_real_db_or_embeddings
    assert len(leaks) == 1  # recorded, so a try/except in real code could not hide it
    leaks.clear()  # provoked on purpose: don't fail this test at teardown


@pytest.mark.asyncio
async def test_guard_blocks_direct_chat_completions_create(_no_real_db_or_embeddings):
    client = AsyncOpenAI(api_key="sk-test")
    with pytest.raises(AssertionError, match="real OpenAI chat completions"):
        await client.chat.completions.create(model="gpt-4.1-mini", messages=[{"role": "user", "content": "x"}])
    leaks = _no_real_db_or_embeddings
    assert len(leaks) == 1
    leaks.clear()


def test_guard_blocks_sync_chat_completions_create(_no_real_db_or_embeddings):
    from openai import OpenAI
    client = OpenAI(api_key="sk-test")
    with pytest.raises(AssertionError, match="chat completions \\(sync\\)"):
        client.chat.completions.create(model="gpt-4.1-mini", messages=[{"role": "user", "content": "x"}])
    leaks = _no_real_db_or_embeddings
    assert len(leaks) == 1
    leaks.clear()
