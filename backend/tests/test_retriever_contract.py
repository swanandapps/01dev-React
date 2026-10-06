"""One contract, every Retriever backend: scope filtering, lecture filtering, ranking, empty scope."""
import pytest

from app.models import TranscriptChunk
from app.retrieval.memory import MemoryRetriever
from app.retrieval.text import tokenize
from app.services.vector_store import InMemoryVectorStore

DIM = 1536
BACKENDS = ["memory"]


def vec(*weights):
    """Sparse test vector: weights for dims 0..3, the rest 0."""
    v = [0.0] * DIM
    for i, w in enumerate(weights):
        v[i] = w
    return v


def chunk(cid, slug, lecture_id, title, text):
    return TranscriptChunk(chunk_id=cid, course_id=slug, course_title=slug, lecture_id=lecture_id,
                           lecture_title=title, text=text, start_time=0, end_time=60)


CORPUS = [
    (chunk("cl-5-2-0", "custom-library", "cl-5-2", "6.5 - IIFE, To The Rescue",
           "the IIFE pattern gives a function its own scope"), vec(1, 0, 0, 0)),
    (chunk("cl-10-0-0", "custom-library", "cl-10-0", "11.1 - Publishing using np",
           "np runs the checks and publishes the package to npm"), vec(0, 1, 0, 0)),
    (chunk("cl-10-0-1", "custom-library", "cl-10-0", "11.1 - Publishing using np",
           "after np finishes the version is tagged"), vec(0, 0.9, 0.1, 0)),
    (chunk("rp-4-0-0", "react-perf", "rp-4-0", "5.1 - Virtualizing the Table",
           "virtualizing the table renders only visible rows"), vec(0, 0, 1, 0)),
    (chunk("rp-0-1-0", "react-perf", "rp-0-1", "1.2 - Render vs Commit",
           "React reconciliation compares the trees"), vec(0, 0, 0, 1)),
    (chunk("je-1-0-0", "js-engine", "je-1-0", "2.1 - Tokenization in V8",
           "the IIFE is parsed lazily by V8"), vec(0.8, 0, 0, 0.2)),
]


async def make_retriever(kind: str, corpus=CORPUS, request=None):
    if kind == "memory":
        store = InMemoryVectorStore()
        store.chunks = [c for c, _ in corpus]
        store._embeddings = [e for _, e in corpus]
        return MemoryRetriever(store)
    raise ValueError(kind)


@pytest.fixture(params=BACKENDS)
async def retriever(request):
    return await make_retriever(request.param, request=request)


def ids(pairs):
    return [c.chunk_id for c, _ in pairs]


async def test_vector_search_is_scoped_and_best_first(retriever):
    out = await retriever.vector_search(vec(1, 0, 0, 0), ["custom-library", "js-engine"], 10)
    assert ids(out)[:2] == ["cl-5-2-0", "je-1-0-0"]
    assert all(c.course_id in ("custom-library", "js-engine") for c, _ in out)
    assert out[0][1] == pytest.approx(1.0, abs=1e-6)
    assert ids(await retriever.vector_search(vec(1, 0, 0, 0), ["js-engine"], 10)) == ["je-1-0-0"]
    assert len(await retriever.vector_search(vec(0, 1, 0, 0), ["custom-library"], 1)) == 1


async def test_lexical_search_finds_acronyms_scoped(retriever):
    out = await retriever.lexical_search(tokenize("what is an IIFE?"), ["custom-library", "js-engine"], 10)
    assert ids(out) == ["cl-5-2-0", "je-1-0-0"]        # title (weight A) outranks body-only
    assert ids(await retriever.lexical_search(tokenize("IIFE"), ["react-perf"], 10)) == []
    assert set(ids(await retriever.lexical_search(tokenize("np"), ["custom-library"], 10))) == {"cl-10-0-0",
                                                                                                  "cl-10-0-1"}


async def test_lecture_filter(retriever):
    out = await retriever.lexical_search(tokenize("np"), ["custom-library"], 10, lecture_id="cl-10-0")
    assert set(ids(out)) == {"cl-10-0-0", "cl-10-0-1"}
    vout = await retriever.vector_search(vec(0, 1, 0, 0), ["custom-library"], 10, lecture_id="cl-10-0")
    assert set(ids(vout)) == {"cl-10-0-0", "cl-10-0-1"}


async def test_empty_scope_returns_nothing(retriever):
    assert await retriever.vector_search(vec(1, 0, 0, 0), [], 10) == []
    assert await retriever.lexical_search(["iife"], [], 10) == []
    assert await retriever.lexical_search([], ["custom-library"], 10) == []
