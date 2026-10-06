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
    if not scope:
        return []
    await _ensure_loaded()
    r = factory.get_retriever()
    queries = list(dict.fromkeys(q for q in (question, *extra_queries) if q and q.strip()))
    embeddings = await asyncio.gather(*(embedding_service.embed(q) for q in queries))
    terms = " ".join(extra_terms)
    lists = await asyncio.gather(
        *(_vector(r, e, scope, lecture_id) for e in embeddings),
        *(_lexical(r, tokenize(f"{q} {terms}"), scope, lecture_id) for q in queries))
    return rrf_fuse(lists[:len(queries)], lists[len(queries):], limit=limit,
                     per_lecture=None if lecture_id else per_lecture)
