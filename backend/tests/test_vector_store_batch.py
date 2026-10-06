"""Boot embedding is batched: stubbed embeddings client + stubbed pool, no real DB/OpenAI."""
import asyncio
from types import SimpleNamespace

import pytest

from app.models import TranscriptChunk
from app.services import vector_store as vs
from app.services.embeddings import embedding_service


class FakeClient:
    def __init__(self, fail_on_call=None):
        self.calls = []
        self.fail_on_call = fail_on_call
        self.embeddings = SimpleNamespace(create=self._create)

    async def _create(self, model, input):
        self.calls.append(list(input))
        if self.fail_on_call == len(self.calls):
            raise RuntimeError("boom")
        return SimpleNamespace(data=[SimpleNamespace(embedding=[float(len(t)), 1.0]) for t in input])


class FakePool:
    def __init__(self, cached=()):
        self.cached = list(cached)
        self.inserted = []

    async def fetch(self, sql, *a):
        return [{"chunk_id": c, "emb": "[0.5,0.5]"} for c in self.cached]

    async def executemany(self, sql, rows):
        self.inserted.extend(list(rows))

    async def execute(self, sql, *a):
        self.inserted.append(a)


def _chunks(n):
    return [
        TranscriptChunk(chunk_id=f"c-{i}", course_id="x", course_title="X", lecture_id="x-0-0",
                        lecture_title="L", text="t" * (i + 1), start_time=i, end_time=i + 1, embedding=[])
        for i in range(n)
    ]


def _setup(monkeypatch, n, client, pool):
    monkeypatch.setattr(embedding_service, "use_openai", True)
    monkeypatch.setattr(embedding_service, "client", client)

    async def get_pool():
        return pool

    monkeypatch.setattr("app.services.db.get_pool", get_pool)
    store = vs.InMemoryVectorStore()
    store.chunks = _chunks(n)
    return store


def test_250_missing_chunks_three_batches(monkeypatch):
    client, pool = FakeClient(), FakePool()
    store = _setup(monkeypatch, 250, client, pool)
    asyncio.run(store._init_with_pgvector())
    assert [len(c) for c in client.calls] == [100, 100, 50]
    flat = [t for c in client.calls for t in c]
    assert flat == [c.text for c in store.chunks]
    assert len(pool.inserted) == 250
    assert len(store._embeddings) == 250
    assert store._embeddings[0] == [1.0, 1.0]


def test_failure_on_batch_two_keeps_batch_one_and_falls_back(monkeypatch):
    client, pool = FakeClient(fail_on_call=2), FakePool()
    _setup(monkeypatch, 0, client, pool)
    monkeypatch.setenv("DATABASE_URL", "postgres://stub")
    store = vs.InMemoryVectorStore()
    asyncio.run(store.initialize())  # seed has >100 chunks: batch 2 fails, in-memory fallback runs
    assert len(pool.inserted) == 100
    assert len(store._embeddings) == len(store.chunks) > 100
    assert all(len(e) == 2 for e in store._embeddings)


def test_no_missing_chunks_no_embed_calls(monkeypatch):
    client = FakeClient()
    pool = FakePool(cached=[f"c-{i}" for i in range(5)])
    store = _setup(monkeypatch, 5, client, pool)
    asyncio.run(store._init_with_pgvector())
    assert client.calls == []
    assert pool.inserted == []
    assert len(store._embeddings) == 5


def test_inmemory_path_batches(monkeypatch):
    client = FakeClient()
    monkeypatch.setattr(embedding_service, "use_openai", True)
    monkeypatch.setattr(embedding_service, "client", client)
    monkeypatch.delenv("DATABASE_URL", raising=False)
    store = vs.InMemoryVectorStore()
    asyncio.run(store.initialize())
    n = len(store.chunks)
    assert sum(len(c) for c in client.calls) == n
    assert all(len(c) <= 100 for c in client.calls)
    assert len(store._embeddings) == n
