"""Boot embedding is batched: stubbed embeddings client + stubbed pool, no real DB/OpenAI."""
import asyncio
from types import SimpleNamespace

import pytest

from app.models import TranscriptChunk
from app.services import vector_store as vs
from app.services.embeddings import embedding_service


class FakeClient:
    def __init__(self, fail_on_call=None, short=False):
        self.short = short
        self.calls = []
        self.fail_on_call = fail_on_call
        self.embeddings = SimpleNamespace(create=self._create)

    async def _create(self, model, input):
        self.calls.append(list(input))
        if self.fail_on_call == len(self.calls):
            raise RuntimeError("boom")
        # reversed order + explicit index: embed_many must sort by index
        items = [SimpleNamespace(index=i, embedding=[float(len(t)), 1.0]) for i, t in enumerate(input)]
        data = items[::-1]
        if self.short:
            data = data[:-1]
        return SimpleNamespace(data=data)


class FakePool:
    def __init__(self, cached=(), hashes=None):
        # list of ids (stored text == seed text "t"*(i+1)) or dict id -> stored text
        if not isinstance(cached, dict):
            cached = {c: "t" * (int(c.split("-")[1]) + 1) for c in cached}
        self.cached = dict(cached)
        self.hashes = dict(hashes or {})
        self.inserted = []

    async def fetch(self, sql, *a):
        return [{"chunk_id": c, "text": t, "h": self.hashes.get(c), "emb": "[0.5,0.5]"}
                for c, t in self.cached.items()]

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
    seed = [c.model_dump() for c in _chunks(250)]
    monkeypatch.setattr(vs, "json", SimpleNamespace(load=lambda f: seed))
    store = vs.InMemoryVectorStore()
    asyncio.run(store.initialize())  # batch 2 fails, in-memory fallback runs
    assert len(pool.inserted) == 100
    assert len(store._embeddings) == len(store.chunks) == 250
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
    monkeypatch.delenv("RAG_EMBED_CACHE", raising=False)
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


def test_changed_text_is_reembedded_and_upserted(monkeypatch):
    client = FakeClient()
    pool = FakePool(cached={"c-0": "t", "c-1": "OLD TEXT", "c-2": "ttt"})
    store = _setup(monkeypatch, 3, client, pool)
    asyncio.run(store._init_with_pgvector())
    assert client.calls == [["tt"]]
    assert [r[0] for r in pool.inserted] == ["c-1"]
    assert pool.inserted[0][1] == "tt"
    assert store._embeddings[1] == [2.0, 1.0]
    assert store._embeddings[0] == [0.5, 0.5]


def test_identical_text_not_reembedded(monkeypatch):
    client = FakeClient()
    pool = FakePool(cached=["c-0", "c-1"])
    store = _setup(monkeypatch, 2, client, pool)
    asyncio.run(store._init_with_pgvector())
    assert client.calls == [] and pool.inserted == []


def test_logged_counts_new_vs_changed(monkeypatch, capsys):
    client = FakeClient()
    pool = FakePool(cached={"c-0": "t", "c-1": "stale", "c-2": "stale"})
    store = _setup(monkeypatch, 5, client, pool)  # c-3, c-4 are new
    asyncio.run(store._init_with_pgvector())
    out = capsys.readouterr().out
    assert "2 new" in out and "2 changed" in out and "1 from pgvector cache" in out


def test_embed_many_orders_by_index(monkeypatch):
    monkeypatch.setattr(embedding_service, "use_openai", True)
    monkeypatch.setattr(embedding_service, "client", FakeClient())
    out = asyncio.run(embedding_service.embed_many(["a", "bb", "ccc"]))
    assert out == [[1.0, 1.0], [2.0, 1.0], [3.0, 1.0]]


def test_embed_many_raises_on_length_mismatch(monkeypatch):
    monkeypatch.setattr(embedding_service, "use_openai", True)
    monkeypatch.setattr(embedding_service, "client", FakeClient(short=True))
    with pytest.raises(RuntimeError):
        asyncio.run(embedding_service.embed_many(["a", "bb", "ccc"]))


def _seed_two():
    return [dict(chunk_id=f"custom-library-5-2-{i}", course_id="custom-library", course_title="Build a Custom Library",
                 lecture_id="custom-library-5-2", lecture_title="6.5 - IIFE, To The Rescue", text=t,
                 start_time=60 * i, end_time=60 * i + 60, embedding=[])
            for i, t in enumerate(["We wrap it.", "Then call it."])]


def test_initialize_enriches_and_embeds_embed_text(monkeypatch):
    client = FakeClient()
    monkeypatch.setattr(embedding_service, "use_openai", True)
    monkeypatch.setattr(embedding_service, "client", client)
    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.delenv("RAG_EMBED_CACHE", raising=False)
    monkeypatch.setattr(vs, "json", SimpleNamespace(load=lambda f: _seed_two()))
    store = vs.InMemoryVectorStore()
    asyncio.run(store.initialize())
    assert store.chunks[1].embed_text.startswith("Build a Custom Library › ")
    assert "Previously: We wrap it." in store.chunks[1].embed_text
    assert [t for c in client.calls for t in c] == [c.embed_text for c in store.chunks]
    assert store.chunks[1].text == "Then call it."          # raw text unchanged


def test_embed_cache_skips_openai_on_the_second_boot(monkeypatch, tmp_path):
    client = FakeClient()
    monkeypatch.setattr(embedding_service, "use_openai", True)
    monkeypatch.setattr(embedding_service, "client", client)
    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.setenv("RAG_EMBED_CACHE", str(tmp_path))
    monkeypatch.setattr(vs, "json", SimpleNamespace(load=lambda f: _seed_two()))
    first = vs.InMemoryVectorStore()
    asyncio.run(first.initialize())
    n_calls = len(client.calls)
    second = vs.InMemoryVectorStore()
    asyncio.run(second.initialize())
    assert n_calls == 1 and len(client.calls) == 1          # second boot: all from the cache
    assert second._embeddings == first._embeddings


def test_pg_path_reembeds_when_the_content_hash_changes(monkeypatch):
    client = FakeClient()
    store = _setup(monkeypatch, 2, client, FakePool(cached=["c-0", "c-1"], hashes={"c-0": "same", "c-1": "old"}))
    store.chunks[0].content_hash, store.chunks[0].embed_text = "same", "E0"
    store.chunks[1].content_hash, store.chunks[1].embed_text = "new", "E1"
    asyncio.run(store._init_with_pgvector())
    assert client.calls == [["E1"]]
