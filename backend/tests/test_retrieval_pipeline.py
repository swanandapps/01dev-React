import pytest

from app.retrieval import factory, pipeline
from app.retrieval.memory import MemoryRetriever
from app.services import catalog_service
from app.services.embeddings import embedding_service
from app.services.vector_store import InMemoryVectorStore
from tests.test_retriever_contract import CORPUS, vec


@pytest.fixture
def mem(monkeypatch):
    store = InMemoryVectorStore()
    store.chunks = [c for c, _ in CORPUS]
    store._embeddings = [e for _, e in CORPUS]
    monkeypatch.setattr(pipeline, "vector_store", store)
    monkeypatch.setattr(factory, "_retriever", MemoryRetriever(store))
    embedded = []
    table = {"what is an IIFE?": vec(1, 0, 0, 0), "publish with np": vec(0, 1, 0, 0)}

    async def fake_embed(text):
        embedded.append(text)
        return table.get(text, vec(0, 0, 0, 1))

    monkeypatch.setattr(embedding_service, "embed", fake_embed)
    return embedded


async def test_search_fuses_vector_and_lexical_inside_the_scope(mem):
    out = await pipeline.search("what is an IIFE?", ["custom-library"])
    assert out[0].chunk.chunk_id == "cl-5-2-0"
    assert (out[0].vec_rank, out[0].lex_rank) == (1, 1)
    assert {c.chunk.course_id for c in out} == {"custom-library"}


async def test_search_empty_scope_embeds_nothing(mem):
    assert await pipeline.search("what is an IIFE?", []) == []
    assert mem == []


async def test_search_lecture_filter_and_extra_queries(mem):
    out = await pipeline.search("publish with np", ["custom-library"], lecture_id="cl-10-0", per_lecture=None)
    assert {c.chunk.lecture_id for c in out} == {"cl-10-0"}
    await pipeline.search("publish with np", ["custom-library"], extra_queries=["what is an IIFE?"])
    assert mem[-2:] == ["publish with np", "what is an IIFE?"]


def test_ask_scope_is_launched_and_owned_only(monkeypatch):
    courses = [{"id": 2, "slug": "custom-library", "launched": True},
               {"id": 9, "slug": "javascript-deep-dive", "launched": False},
               {"id": 4, "slug": "product-engineering", "launched": True}]
    monkeypatch.setattr(catalog_service, "all_courses", lambda: courses)
    monkeypatch.setattr(catalog_service, "get", lambda i: next((c for c in courses if c["id"] == i), None))
    assert pipeline.ask_scope({2, 9}) == ("custom-library",)
    assert pipeline.ask_scope({9, 11}) == ()
    assert pipeline.ask_scope(set()) == ()


def test_lecture_id_for_matches_loosely(mem):
    assert pipeline.lecture_id_for("custom-library", "11.1 - Publishing using `np`") == "cl-10-0"
    assert pipeline.lecture_id_for("custom-library", "9.9 - Nope") is None


def test_ask_scope_uses_course_lookup_launched_predicate(monkeypatch):
    """The eval's ask_all patch (course_lookup._is_launched) must change ask_scope too."""
    from app.services import course_lookup as cl
    courses = [{"id": 2, "slug": "a", "launched": True}, {"id": 9, "slug": "b", "launched": False}]
    monkeypatch.setattr(catalog_service, "all_courses", lambda: courses)
    monkeypatch.setattr(cl, "_is_launched", lambda cid: True)
    assert pipeline.ask_scope({2, 9}) == ("a", "b")


async def test_lexical_candidates_are_capped_per_lecture_before_fusion(mem):
    from app.models import TranscriptChunk
    flood = [TranscriptChunk(chunk_id=f"fl-0-0-{i}", course_id="custom-library", course_title="c", lecture_id="fl-0-0",
                             lecture_title="zzword lecture", text="zzword", start_time=0, end_time=1) for i in range(8)]
    store = pipeline.vector_store
    store.chunks = store.chunks + flood
    store._embeddings = store._embeddings + [vec(0, 0, 0, 1)] * 8
    hits = await pipeline._lexical(factory.get_retriever(), ["zzword"], ["custom-library"], None)
    assert len(hits) == pipeline.LEX_PER_LECTURE
    in_lecture = await pipeline.search("zzword", ["custom-library"], lecture_id="fl-0-0")
    assert len([c for c in in_lecture if c.lex_rank]) == 8   # no caps inside one lecture


async def test_fused_list_reaches_limit_when_one_lecture_dominates_vectors(mem):
    from app.models import TranscriptChunk
    store = pipeline.vector_store
    many = [TranscriptChunk(chunk_id=f"d-0-0-{i}", course_id="custom-library", course_title="c", lecture_id="d-0-0",
                            lecture_title="dominant", text="x", start_time=0, end_time=1) for i in range(40)]
    others = [TranscriptChunk(chunk_id=f"o-{j}-0-0", course_id="custom-library", course_title="c", lecture_id=f"o-{j}-0",
                              lecture_title=f"other {j}", text="y", start_time=0, end_time=1) for j in range(6)]
    store.chunks = store.chunks + many + others
    store._embeddings = store._embeddings + [vec(0, 0, 0, 1, 0.01 * i) for i in range(40)] + [vec(0, 0, 0, 0.5) for _ in range(6)]
    out = await pipeline.search("unrelated", ["custom-library"])
    assert len(out) == pipeline.LIMIT


async def test_memory_vector_scores_match_vector_store_search(monkeypatch):
    from app.services import vector_store as vs
    store = InMemoryVectorStore()
    store.chunks = [c for c, _ in CORPUS]
    store._embeddings = [e for _, e in CORPUS]
    q = vec(0.3, 0.5, 0.1, 0.7)
    monkeypatch.setattr(vs.embedding_service, "use_openai", True)
    want = {r.chunk.chunk_id: r.score for r in store.search(q, top_k=10, threshold=-1.0, course_id="custom-library")}
    got = dict((c.chunk_id, s) for c, s in await MemoryRetriever(store).vector_search(q, ["custom-library"], 10))
    assert want.keys() == got.keys()
    assert all(abs(want[k] - got[k]) < 1e-9 for k in want)


async def test_bm25_index_rebuilds_when_the_store_reloads(mem):
    r = factory.get_retriever()
    assert await r.lexical_search(["brandnewword"], ["custom-library"], 5) == []
    from app.models import TranscriptChunk
    store = r.store
    store.chunks = store.chunks + [TranscriptChunk(chunk_id="n-0-0-0", course_id="custom-library", course_title="c",
                                                   lecture_id="n-0-0", lecture_title="t", text="brandnewword",
                                                   start_time=0, end_time=1)]
    store._embeddings = store._embeddings + [vec(0, 0, 0, 1)]
    assert [c.chunk_id for c, _ in await r.lexical_search(["brandnewword"], ["custom-library"], 5)] == ["n-0-0-0"]


async def test_every_candidate_carries_its_cosine_including_lexical_only_ones(mem):
    # "np" matches cl-10-0 lexically; vec top-30 over a 5-chunk corpus covers everything, so force a
    # lexical-only candidate by making the vector list miss it.
    store = pipeline.vector_store
    out = await pipeline.search("publish with np", ["custom-library"])
    assert out and all(c.cosine is not None for c in out)
    lex_only = pipeline.Candidate(chunk=store.chunks[0], lex_rank=1)
    pipeline._fill_cosines([lex_only], vec(1, 0, 0, 0))
    assert lex_only.cosine == pytest.approx(store._cosine_sim(vec(1, 0, 0, 0), store._embeddings[0]))
    with_vec = pipeline.Candidate(chunk=store.chunks[0], vec_rank=1, vec_score=0.42)
    pipeline._fill_cosines([with_vec], vec(1, 0, 0, 0))
    assert with_vec.cosine == 0.42


async def test_blank_question_returns_nothing_without_embedding(mem):
    assert await pipeline.search("   ", ["custom-library"]) == []
    assert await pipeline.search("", ["custom-library"]) == []
    assert mem == []


async def test_best_chunk_for_lectures_scores_the_same_question_embedding_without_re_embedding(mem):
    await pipeline.search("what is an IIFE?", ["custom-library"])
    n = len(mem)
    out = await pipeline.best_chunk_for_lectures("what is an IIFE?", ["cl-5-2", "nope"])
    assert len(mem) == n                       # served from the cached embedding
    chunk, cos = out["cl-5-2"]
    assert chunk.lecture_id == "cl-5-2" and cos == pytest.approx(1.0) and "nope" not in out
    assert await pipeline.best_chunk_for_lectures("x", ["nope"]) == {} and len(mem) == n   # no chunks: no embed
