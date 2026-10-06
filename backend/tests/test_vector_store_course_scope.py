"""pipeline.search / vector_store.search: precomputed norms and per-course scoping must
not change a single ranking or score versus the old score-everything-then-filter path."""
import asyncio
import math
import random

from app.models import TranscriptChunk
from app.services.embeddings import embedding_service
from app.services.vector_store import InMemoryVectorStore

DIM = 24
COURSES = ["custom-library", "js-engine", "product-engineering"]


def _store(n=90):
    rng = random.Random(7)
    st = InMemoryVectorStore()
    st.chunks = [
        TranscriptChunk(chunk_id=f"c{i}", course_id=COURSES[i % 3], course_title=COURSES[i % 3],
                        lecture_id=f"l{i // 10}", lecture_title=f"{i // 10}.1 - L", start_time=i, end_time=i + 1,
                        text=f"chunk {i}")
        for i in range(n)
    ]
    st._embeddings = [[rng.uniform(-1, 1) for _ in range(DIM)] for _ in range(n)]
    st._embeddings[5] = [0.0] * DIM  # zero vector scores 0.0, as before
    return st


def _old_search(st, q, top_k, threshold):
    scores = sorted(((i, st._cosine_sim(q, e)) for i, e in enumerate(st._embeddings)),
                    key=lambda x: x[1], reverse=True)
    out = []
    for i, s in scores[:top_k]:
        if s < threshold:
            break
        out.append((st.chunks[i].chunk_id, s))
    return out


def test_scores_and_ranking_identical_to_the_old_full_cosine(monkeypatch):
    monkeypatch.setattr(embedding_service, "use_openai", True)
    st = _store()
    q = [random.Random(3).uniform(-1, 1) for _ in range(DIM)]
    for top_k, th in [(5, 0.25), (90, 0.0), (10, -1.0)]:
        new = [(r.chunk.chunk_id, r.score) for r in st.search(q, top_k=top_k, threshold=th)]
        old = _old_search(st, q, top_k, th)
        assert [a for a, _ in new] == [a for a, _ in old]
        assert all(abs(a - b) < 1e-9 for (_, a), (_, b) in zip(new, old))


def test_course_scoped_search_equals_filtering_the_full_ranking(monkeypatch):
    monkeypatch.setattr(embedding_service, "use_openai", True)
    st = _store()
    q = [random.Random(4).uniform(-1, 1) for _ in range(DIM)]
    for course in COURSES:
        full = [(r.chunk.chunk_id, r.score) for r in st.search(q, top_k=90, threshold=0.0)
                if r.chunk.course_id == course]
        scoped = [(r.chunk.chunk_id, r.score) for r in st.search(q, top_k=90, threshold=0.0, course_id=course)]
        assert [a for a, _ in scoped] == [a for a, _ in full]
        assert all(abs(a - b) < 1e-9 for (_, a), (_, b) in zip(scoped, full))
    assert st.search(q, top_k=5, threshold=0.0, course_id="nope") == []


def test_norms_follow_replaced_embeddings(monkeypatch):
    monkeypatch.setattr(embedding_service, "use_openai", True)
    st = _store(6)
    q = [1.0] * DIM
    st.search(q, top_k=1, threshold=0.0)
    st._embeddings = [[1.0] * DIM for _ in range(6)]
    assert abs(st.search(q, top_k=1, threshold=0.0)[0].score - 1.0) < 1e-9


def test_pipeline_search_never_touches_other_courses_chunks(monkeypatch):
    from app.retrieval import factory, pipeline
    from app.retrieval.memory import MemoryRetriever
    monkeypatch.setattr(embedding_service, "use_openai", True)
    st = _store()
    q = [0.5] * DIM
    seen = []

    class Spy(list):
        def __getitem__(self, i):
            seen.append(i)
            return list.__getitem__(self, i)

    st._embeddings = Spy(st._embeddings)
    st._ensure_index()
    seen.clear()

    async def fake_embed(_):
        return q

    monkeypatch.setattr(pipeline, "vector_store", st)
    monkeypatch.setattr(factory, "_retriever", MemoryRetriever(st))
    monkeypatch.setattr(embedding_service, "embed", fake_embed)
    cands = asyncio.run(pipeline.search("x", ["js-engine"], limit=pipeline.VEC_K + pipeline.LEX_K, per_lecture=None))
    out = [(c.chunk, c.vec_score) for c in cands]
    assert out and all(c.course_id == "js-engine" for c, _ in out)
    assert seen and all(st.chunks[i].course_id == "js-engine" for i in seen)
    # js-engine has 30 chunks, 3 or 4 per lecture; the vector list keeps the best 3 per lecture (Task 9's
    # over-fetch + cap), so 3 lectures lose one chunk: 27. Never another course's chunk.
    assert len(out) == 27


def test_partially_initialised_store_returns_empty_not_indexerror(monkeypatch):
    monkeypatch.setattr(embedding_service, "use_openai", True)
    st = _store(9)
    st._embeddings = []
    q = [1.0] * DIM
    assert st.search(q, top_k=5, threshold=0.0) == []
    assert st.search(q, top_k=5, threshold=0.0, course_id="js-engine") == []
    st._embeddings = _store(9)._embeddings[:4]  # shorter than chunks: partial results only
    assert all(st.chunks.index(r.chunk) < 4 for r in st.search(q, top_k=9, threshold=-1.0))
