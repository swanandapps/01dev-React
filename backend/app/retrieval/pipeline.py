"""The retrieval pipeline (spec §2): scope (code) → hybrid retrieval → [rerank + coverage, Task 13]
→ [query understanding, Task 18]. Every consumer (Ask lookup, player lookup, find_moment,
search_course_content) goes through here."""
import asyncio
import re
import time
from dataclasses import dataclass, field
from typing import Optional, Sequence

from app.retrieval import factory, titles
from app.retrieval import understand as qu
from app.retrieval.base import Candidate, rrf_fuse
from app.retrieval.rerank import CITED, FALLBACK_MIN_COSINE, MAX_CANDIDATES, Graded, Outcome, decide, rerank
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


async def _gather(queries: Sequence[str], scope: tuple[str, ...], lecture_id: Optional[str],
                  terms: Sequence[str] = (), *, vector: bool = True) -> tuple[list[list[float]], list, list]:
    """(embeddings, vector lists, lexical lists): one embedding + vector list per query (none when vector=False)
    and one lexical list per query; `terms` (keywords) join the lexical queries only."""
    r = factory.get_retriever()
    joined = " ".join(terms)
    embeddings = list(await asyncio.gather(*(embedding_service.embed(q) for q in queries))) if vector else []
    lists = await asyncio.gather(
        *(_vector(r, e, scope, lecture_id) for e in embeddings),
        *(_lexical(r, tokenize(f"{q} {joined}"), scope, lecture_id) for q in queries))
    for q, e in zip(queries, embeddings):
        _remember(q, e)
    return embeddings, list(lists[:len(embeddings)]), list(lists[len(embeddings):])


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
    embeddings, vec, lex = await _gather(queries, scope, lecture_id, extra_terms)
    out = rrf_fuse(vec, lex, limit=limit, per_lecture=None if lecture_id else per_lecture)
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


MAX_TITLE_ADDED = 3   # title-matched lectures added to the rerank pool, at most


@dataclass
class RetrievalResult:
    outcome: Outcome
    graded: list[Graded]
    intent: str = "explain"
    search_query: str = ""
    fallback: bool = False
    question_embedding: Optional[list[float]] = None   # the embedding graded_search already computed for the question
    rerank_error: Optional[str] = None   # why the reranker fell back, or "salvaged: ..." when it was repaired
    timings_ms: dict = field(default_factory=dict)

    def cited(self) -> list[Graded]:
        return [g for g in self.graded if g.grade in CITED]

    def best(self, allow_partial: bool = True) -> Optional[Graded]:
        for wanted in ("answers", "partial") if allow_partial else ("answers",):
            for g in self.graded:
                if g.grade == wanted:
                    return g
        return None


def _ms(t0: float) -> float:
    return round((time.perf_counter() - t0) * 1000, 1)


async def _title_candidates(question: str, scope: Sequence[str], cands: list[Candidate]) -> tuple[list[Candidate], list[Candidate]]:
    """(kept fused candidates, title-matched additions). Lectures whose TITLE matches the question
    (titles.TITLE_THRESHOLD) but that the kept fused slice lacks are added to the rerank pool (best title score
    first, at most MAX_TITLE_ADDED, pool <= MAX_CANDIDATES) with their best chunk scored on the SAME question
    embedding search already computed: one embedding, one best_chunk_for_lectures call across every slug.
    Best-effort: any failure means no additions."""
    kept = cands[:MAX_CANDIDATES]
    try:
        scores = await titles.title_scores(_recent.get(question), scope, question=question)
        matched: dict[str, float] = {}   # lecture_id -> best title score
        for slug in scope:
            by_key = {norm_title(t): sc for (s, t), sc in scores.items() if s == slug and sc >= titles.TITLE_THRESHOLD}
            for key, lid in lecture_ids_for_titles(slug, by_key).items():
                matched[lid] = max(matched.get(lid, 0.0), by_key[key])
        order = sorted(matched, key=matched.get, reverse=True)
        for k in range(MAX_TITLE_ADDED + 1):   # smallest k whose backfilled additions fit in the k slots it frees
            kept = cands[:MAX_CANDIDATES - k]
            have = {c.chunk.lecture_id for c in kept}
            # drop lectures the kept slice already holds BEFORE taking the top MAX_TITLE_ADDED (backfill)
            missing = [lid for lid in order if lid not in have][:MAX_TITLE_ADDED]
            if len(missing) <= k:
                break
        if not missing:
            return kept, []
        found = await best_chunk_for_lectures(question, missing)
        return kept, [Candidate(chunk=found[lid][0], cosine=found[lid][1]) for lid in missing if lid in found]
    except Exception as e:  # noqa: BLE001 — the title signal is best-effort
        print(f"[pipeline] title candidates failed: {e!r}")
        return cands[:MAX_CANDIDATES], []


def _same(a: str, b: str) -> bool:
    """Equal ignoring case, whitespace and punctuation: a dropped "?" or a recapitalisation is not a rewrite."""
    def norm(x: str) -> str:
        return " ".join(re.sub(r"[^\w\s]", " ", x.lower()).split())
    return norm(a) == norm(b)


def _discard(task: "asyncio.Task") -> None:
    """Cancel a background task nobody will await, and retrieve its outcome so asyncio never logs
    'Task exception was never retrieved'."""
    task.add_done_callback(lambda t: t.cancelled() or t.exception())
    task.cancel()


async def graded_search(question: str, scope: Sequence[str], *, intent: str = "explain",
                        lecture_id: Optional[str] = None, history: Sequence[dict] = (),
                        lecture_title: Optional[str] = None) -> RetrievalResult:
    """understand || raw retrieval -> (+ the rewrite's retrieval) -> RRF over every list -> rerank pool (fused
    list plus title-matched lectures, at most MAX_CANDIDATES) -> rerank the standalone query -> decision.
    account questions, and off_topic ones whose best raw hit is weak, return NOT_COVERED without a rerank call;
    the caller's navigate always wins."""
    t0 = time.perf_counter()
    scope = tuple(dict.fromkeys(s for s in scope if s))
    if not scope:
        return RetrievalResult(Outcome.NOT_COVERED, [], intent=intent, search_query=question)
    await _ensure_loaded()
    timings: dict = {}
    raw_queries = [question] if question and question.strip() else []
    per = None if lecture_id else PER_LECTURE
    if qu.needs_rewrite(question, history, lecture_title):
        raw = asyncio.create_task(_gather(raw_queries, scope, lecture_id))   # starts now, runs alongside
        try:
            u = await qu.understand(question, history, lecture_title)
        except BaseException:
            _discard(raw)
            raise
        timings["understand"] = _ms(t0)
        rewritten = not _same(u.search_query, question)
        sq = u.search_query if rewritten else question      # a case/punctuation-only change reuses the raw embedding
        second = None
        if intent != "navigate" and u.intent == "account":
            _discard(raw)
            timings["total"] = _ms(t0)
            return RetrievalResult(Outcome.NOT_COVERED, [], intent=u.intent, search_query=u.search_query,
                                   timings_ms=timings)
        if intent != "navigate" and u.intent == "off_topic":
            pass
        elif rewritten or u.keywords:
            second = asyncio.create_task(_gather([sq], scope, lecture_id, u.keywords, vector=rewritten))
        try:
            embeddings, vec, lex = await raw
        except BaseException:
            if second:
                _discard(second)
            raise
        if intent != "navigate" and u.intent == "off_topic":
            weak = not vec or not vec[0] or vec[0][0][1] < FALLBACK_MIN_COSINE
            if weak:
                timings["total"] = _ms(t0)
                return RetrievalResult(Outcome.NOT_COVERED, [], intent=u.intent, search_query=u.search_query,
                                       timings_ms=timings)
            u.intent = "explain"       # an off-topic guess with a strong raw hit: let the reranker judge
        if second:
            try:
                _, v2, l2 = await second
                vec, lex = vec + v2, lex + l2
            except Exception as e:  # noqa: BLE001 — the rewrite is an optimisation: keep the raw lists
                print(f"[pipeline] rewrite retrieval failed, using the raw lists only: {e!r}")
        u = qu.Understanding(sq, u.keywords, u.intent, fallback=u.fallback)
    else:
        u = qu.Understanding(question, [], "explain", skipped=True)
        embeddings, vec, lex = await _gather(raw_queries, scope, lecture_id)
    cands = rrf_fuse(vec, lex, limit=LIMIT, per_lecture=per)
    if embeddings:
        _fill_cosines(cands, embeddings[0])
    effective = intent if intent != "explain" else u.intent
    kept, extra = (cands[:MAX_CANDIDATES], []) if lecture_id else await _title_candidates(u.search_query, scope, cands)
    pool = kept + extra
    timings["retrieve"] = _ms(t0)   # wall time from the start (understanding runs inside it)
    t1 = time.perf_counter()
    rr = await rerank(u.search_query, pool, intent=effective)
    outcome, ordered = decide(rr.graded)
    timings["rerank"], timings["total"] = _ms(t1), _ms(t0)
    return RetrievalResult(outcome, ordered, intent=effective, search_query=u.search_query, fallback=rr.fallback,
                           question_embedding=_recent.get(question), rerank_error=rr.error, timings_ms=timings)
