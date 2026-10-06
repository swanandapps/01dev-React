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
