"""Leak guard: no test may reach the real database or the real OpenAI embeddings.

backend/.env points at a remote Postgres, so a test that forgets to stub the
`store` singleton would otherwise read or DELETE real rows. The guards below
raise at the call AND record the attempt, then fail the test at teardown, so a
leak cannot be hidden by a try/except in the code under test.
"""
import pytest


@pytest.fixture(autouse=True)
def _no_real_db_or_embeddings(monkeypatch):
    from app.services import db, embeddings

    leaks: list[str] = []

    async def _blocked_pool(*a, **k):
        leaks.append("app.services.db.get_pool (real Postgres)")
        raise AssertionError("test reached the real database: stub the store it uses")

    async def _blocked_openai(self, *a, **k):
        leaks.append("EmbeddingService._openai_embed (real OpenAI)")
        raise AssertionError("test reached the real OpenAI embeddings: stub embedding_service.embed")

    async def _blocked_embeddings_create(self, *a, **k):
        leaks.append("openai AsyncEmbeddings.create (real OpenAI, e.g. course_lookup._embed_titles)")
        raise AssertionError("test reached the real OpenAI embeddings client: stub it")

    monkeypatch.setattr(db, "get_pool", _blocked_pool)
    monkeypatch.setattr("openai.resources.embeddings.AsyncEmbeddings.create", _blocked_embeddings_create)
    monkeypatch.setattr(type(embeddings.embedding_service), "_openai_embed", _blocked_openai)
    yield leaks
    assert not leaks, f"test leaked to a real backend: {leaks}"
