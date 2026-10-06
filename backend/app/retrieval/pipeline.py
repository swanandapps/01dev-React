"""The retrieval pipeline (spec §2): scope (code) → hybrid retrieval → [rerank + coverage, Task 13]
→ [query understanding, Task 18]. Every consumer (Ask lookup, player lookup, find_moment,
search_course_content) goes through here."""
import asyncio
from typing import Optional, Sequence

from app.retrieval import factory
from app.retrieval.base import Candidate, rrf_fuse
from app.retrieval.text import norm_title, tokenize
from app.services import catalog_service
from app.services.embeddings import embedding_service
from app.services.vector_store import vector_store

VEC_K = 30
LEX_K = 30
LIMIT = 12
PER_LECTURE = 3
LEX_PER_LECTURE = 5   # lexical candidates per lecture BEFORE fusion (one lecture's title-tied chunks can't flood the list)
LEX_OVERFETCH = 3     # fetch LEX_K * this, cap per lecture, keep LEX_K


def ask_scope(enrolled_ids: set[int]) -> tuple[str, ...]:
    """Ask citation policy F1, as a search scope: catalog courses that are launched AND owned."""
    from app.services import course_lookup as cl  # same predicates as cl.ask_citable (the eval patches them)
    owned = [c for c in catalog_service.all_courses() if c.get("slug") and c.get("id") in enrolled_ids]
    return tuple(c["slug"] for c in owned if cl._is_launched(c["id"]))  # all_courses() is lru_cached


def lecture_id_for(slug: str, lecture_title: str) -> Optional[str]:
    want = norm_title(lecture_title or "")
    for c in vector_store.chunks:
        if c.course_id == slug and norm_title(c.lecture_title) == want:
            return c.lecture_id
    return None


async def _ensure_loaded() -> None:
    if not vector_store.chunks:
        await vector_store.initialize()


def _cap(hits, k: int, per_lecture: Optional[int]):
    """Best-first hits, at most `per_lecture` per lecture (None = no cap), at most k in all."""
    out, per = [], {}
    for chunk, score in hits:
        if per_lecture is not None:
            if per.get(chunk.lecture_id, 0) >= per_lecture:
                continue
            per[chunk.lecture_id] = per.get(chunk.lecture_id, 0) + 1
        out.append((chunk, score))
        if len(out) == k:
            break
    return out


async def _lexical(r, tokens, scope, lecture_id):
    cap = None if lecture_id else LEX_PER_LECTURE   # inside one lecture the cap would cut recall to 5
    return _cap(await r.lexical_search(tokens, scope, LEX_K * LEX_OVERFETCH, lecture_id), LEX_K, cap)


async def _vector(r, embedding, scope, lecture_id):
    cap = None if lecture_id else PER_LECTURE       # over-fetch so the fused list can still reach `limit`
    return _cap(await r.vector_search(embedding, scope, VEC_K * LEX_OVERFETCH, lecture_id), VEC_K, cap)


async def search(question: str, scope: Sequence[str], *, lecture_id: Optional[str] = None, limit: int = LIMIT,
                 per_lecture: Optional[int] = PER_LECTURE, extra_queries: Sequence[str] = (),
                 extra_terms: Sequence[str] = ()) -> list[Candidate]:
    """Vector top VEC_K + lexical top LEX_K for every query (the question plus any rewrites), all
    inside `scope`, fused with RRF. extra_terms (keywords) join the lexical queries only."""
    scope = tuple(dict.fromkeys(s for s in scope if s))
    queries = list(dict.fromkeys(q for q in (question, *extra_queries) if q and q.strip()))
    if not scope or not queries:
        return []
    await _ensure_loaded()
    r = factory.get_retriever()
    embeddings = await asyncio.gather(*(embedding_service.embed(q) for q in queries))
    terms = " ".join(extra_terms)
    lists = await asyncio.gather(
        *(_vector(r, e, scope, lecture_id) for e in embeddings),
        *(_lexical(r, tokenize(f"{q} {terms}"), scope, lecture_id) for q in queries))
    _remember(queries[0], embeddings[0])
    out = rrf_fuse(lists[:len(queries)], lists[len(queries):], limit=limit,
                   per_lecture=None if lecture_id else per_lecture)
    _fill_cosines(out, embeddings[0])
    return out


_recent: dict[str, list[float]] = {}   # question -> its embedding, so callers can score more chunks without re-embedding


def _remember(question: str, embedding: list[float]) -> None:
    _recent.pop(question, None)
    _recent[question] = embedding
    while len(_recent) > 64:
        _recent.pop(next(iter(_recent)))


def _fill_cosines(cands: list[Candidate], question_embedding: list[float]) -> None:
    """RRF scores are not cosines, and the Phase 1-3 decision thresholds are calibrated on cosines. Every
    candidate carries its cosine to the question: the vector list's score when it has one, else (a
    lexical-only candidate) computed from the store's embedding of that chunk. Unknown -> None.
    NOTE: needs the in-memory store embeddings (vector_store._embeddings); a PgRetriever must keep them
    loaded or return cosines itself (Task 23)."""
    vector_store._ensure_index()
    embs = vector_store._embeddings
    for c in cands:
        if c.vec_score is not None:
            c.cosine = c.vec_score
            continue
        i = vector_store._pos_by_id.get(c.chunk.chunk_id)
        if question_embedding and i is not None and i < len(embs) and embs[i]:
            c.cosine = vector_store._cosine_sim(question_embedding, embs[i])


def lecture_ids_for_titles(slug: str, norm_titles) -> dict[str, str]:
    """{normalized lecture title: lecture_id} for the given titles of one course."""
    want = set(norm_titles)
    out = {}
    for c in vector_store.chunks:
        if c.course_id == slug:
            k = norm_title(c.lecture_title)
            if k in want:
                out.setdefault(k, c.lecture_id)
    return out


async def best_chunk_for_lectures(question: str, lecture_ids) -> dict[str, tuple]:
    """{lecture_id: (best chunk, cosine)} for the given lectures, scored against the SAME question
    embedding pipeline.search used (no extra embed call when it is still cached). Lets title-matched
    lectures whose chunks rank in neither top list still take part in a decision (and, in Phase 4, the
    rerank pool). {} when none of the lectures has an embedded chunk."""
    want = set(lecture_ids)
    vector_store._ensure_index()
    embs, norms = vector_store._embeddings, vector_store._norms
    pos = [i for i, c in enumerate(vector_store.chunks) if c.lecture_id in want and i < len(embs) and norms[i]]
    if not pos:
        return {}
    q = _recent.get(question)
    if q is None:
        q = await embedding_service.embed(question)
        _remember(question, q)
    qn = sum(x * x for x in q) ** 0.5
    if not qn:
        return {}
    best: dict[str, tuple] = {}
    for i in pos:
        cos = sum(x * y for x, y in zip(q, embs[i])) / (qn * norms[i])
        lid = vector_store.chunks[i].lecture_id
        if lid not in best or cos > best[lid][1]:
            best[lid] = (vector_store.chunks[i], cos)
    return best
