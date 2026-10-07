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


from app.retrieval import rerank as rr
from app.retrieval.base import Candidate
from app.retrieval import titles


@pytest.fixture
def grader(monkeypatch):
    calls = []

    async def no_titles(*a, **kw):
        return {}

    monkeypatch.setattr(titles, "title_scores", no_titles)

    def set_reply(grades, why=None):
        async def fake(system, user):
            calls.append(user)
            return {"g": dict(grades), "why": why or {}}
        monkeypatch.setattr(rr, "_complete", fake)

    set_reply.calls = calls
    return set_reply


def fixed_retrieval(monkeypatch, cands):
    """Replace the retrieval step (embedding + vector/lexical lists) with a fixed, already ranked candidate list."""
    async def fake_gather(queries, scope, lecture_id, terms=(), *, vector=True):
        embs = [await embedding_service.embed(q) for q in queries] if vector else []
        for q, e in zip(queries, embs):
            pipeline._remember(q, e)
        return embs, [[(c.chunk, 0.9) for c in cands]] * len(embs), [[]] * len(queries)
    monkeypatch.setattr(pipeline, "_gather", fake_gather)


def _lectures(n, prefix="L"):
    """n candidates, each from its own lecture (RRF caps three per lecture)."""
    return [Candidate(chunk=CORPUS[0][0].model_copy(update={"chunk_id": f"{prefix}{i}", "lecture_id": f"{prefix}{i}"}))
            for i in range(n)]


async def test_graded_search_decides_from_grades(mem, grader):
    grader({"c1": "a"}, {"c1": "defines IIFE"})
    res = await pipeline.graded_search("what is an IIFE?", ["custom-library"])
    assert res.outcome == pipeline.Outcome.COVERED and not res.fallback
    assert res.best().candidate.chunk.chunk_id == "cl-5-2-0" and res.best().reason == "defines IIFE"
    assert [g.grade for g in res.cited()] == ["answers"]
    assert set(res.timings_ms) >= {"retrieve", "rerank", "total"}


async def test_graded_search_returns_the_question_embedding_it_computed(mem, grader):
    grader({"c1": "a"})
    res = await pipeline.graded_search("what is an IIFE?", ["custom-library"])
    assert res.question_embedding and res.question_embedding == pipeline._recent["what is an IIFE?"]
    assert (await pipeline.graded_search("x", [])).question_embedding is None


async def test_graded_search_partial_and_best(mem, grader):
    grader({"c2": "p"})
    res = await pipeline.graded_search("what is an IIFE?", ["custom-library"])
    assert res.outcome == pipeline.Outcome.PARTIAL
    assert res.best().grade == "partial" and res.best(allow_partial=False) is None


async def test_graded_search_empty_scope_never_embeds_or_reranks(mem, grader):
    res = await pipeline.graded_search("what is an IIFE?", [])
    assert res.outcome == pipeline.Outcome.NOT_COVERED and res.graded == []
    assert mem == [] and grader.calls == []


async def test_graded_search_tells_the_reranker_about_navigation(mem, grader):
    grader({"c1": "a"})
    await pipeline.graded_search("IIFE", ["custom-library"], intent="navigate")
    assert "Intent: navigate" in grader.calls[0]


async def test_graded_search_adds_title_matched_lectures_to_the_pool(mem, grader, monkeypatch):
    async def titled(*a, **kw):
        return {("custom-library", "11.1 - Publishing using `np`"): 0.9}   # lecture cl-10-0, absent from the fused list

    monkeypatch.setattr(titles, "title_scores", titled)
    fixed_retrieval(monkeypatch, [Candidate(chunk=CORPUS[0][0])])
    grader({"c2": "a"})
    res = await pipeline.graded_search("what is an IIFE?", ["custom-library"])
    assert "[c2] custom-library" in grader.calls[0] and "Publishing using np" in grader.calls[0]
    assert res.outcome == pipeline.Outcome.COVERED and res.best().candidate.chunk.lecture_id == "cl-10-0"


async def test_graded_search_pool_is_at_most_12(mem, grader, monkeypatch):
    async def titled(*a, **kw):
        return {("custom-library", "11.1 - Publishing using `np`"): 0.9}

    monkeypatch.setattr(titles, "title_scores", titled)
    fixed_retrieval(monkeypatch, _lectures(12))
    grader({"c1": "n"})
    res = await pipeline.graded_search("what is an IIFE?", ["custom-library"])
    assert len(res.graded) == 12 and any(g.candidate.chunk.lecture_id == "cl-10-0" for g in res.graded)


async def _enable_titles(monkeypatch):
    from app.retrieval import titles as t
    outline = {"custom-library": ["6.5 - IIFE, To The Rescue", "11.1 - Publishing using `np`"],
               "react-perf": ["5.1 - Virtualizing the Table"]}
    monkeypatch.setattr(catalog_service, "by_slug",
                        lambda slug: {"chapters": [{"name": "c", "subchapters": outline[slug]}]} if slug in outline else None)
    monkeypatch.setattr(embedding_service, "use_openai", True)
    monkeypatch.setattr(embedding_service, "client", object())
    monkeypatch.setattr(t, "_cache", {slug: (ts, [vec(1, 0, 0, 0)] * len(ts)) for slug, ts in outline.items()})
    monkeypatch.setattr(t, "_failed_until", {})


def _fused_only_first(monkeypatch):
    fixed_retrieval(monkeypatch, [Candidate(chunk=CORPUS[0][0])])


async def test_title_signal_embeds_the_question_once_across_slugs(mem, monkeypatch):
    calls = []

    async def real_grader(system, user):
        calls.append(user)
        return {"g": {"c1": "n"}}

    monkeypatch.setattr(rr, "_complete", real_grader)
    await _enable_titles(monkeypatch)
    _fused_only_first(monkeypatch)
    once = []
    orig = pipeline.best_chunk_for_lectures

    async def counting(question, ids):
        once.append(sorted(ids))
        return await orig(question, ids)

    monkeypatch.setattr(pipeline, "best_chunk_for_lectures", counting)
    res = await pipeline.graded_search("what is an IIFE?", ["custom-library", "react-perf"])
    assert mem == ["what is an IIFE?"]            # the question was embedded exactly once
    assert len(once) == 1                          # one best_chunk_for_lectures call for ALL slugs
    lectures = {g.candidate.chunk.lecture_id for g in res.graded}
    assert {"cl-10-0", "rp-4-0"} <= lectures       # title-only lectures of both slugs reached the pool


async def test_title_additions_never_come_from_outside_the_scope(mem, grader, monkeypatch):
    await _enable_titles(monkeypatch)
    res = await pipeline.graded_search("what is an IIFE?", ["custom-library"])
    assert {g.candidate.chunk.course_id for g in res.graded} == {"custom-library"}


async def test_lecture_id_disables_title_additions(mem, grader, monkeypatch):
    async def boom(*a, **kw):
        raise AssertionError("title scoring must not run for a lecture-scoped search")

    monkeypatch.setattr(titles, "title_scores", boom)
    res = await pipeline.graded_search("publish with np", ["custom-library"], lecture_id="cl-10-0")
    assert {g.candidate.chunk.lecture_id for g in res.graded} == {"cl-10-0"}


async def test_title_failure_means_no_additions_and_no_exception(mem, grader, monkeypatch):
    async def boom(*a, **kw):
        raise RuntimeError("titles down")

    monkeypatch.setattr(titles, "title_scores", boom)
    _fused_only_first(monkeypatch)
    grader({"c1": "a"})
    res = await pipeline.graded_search("what is an IIFE?", ["custom-library"])
    assert res.outcome == pipeline.Outcome.COVERED and len(res.graded) == 1


async def test_pool_edge_counts_only_the_kept_slice(mem, grader, monkeypatch):
    """The title lecture sits at fused position 12 (the one the pool drops to make room): it is still 'missing'."""
    async def titled(*a, **kw):
        return {("custom-library", "11.1 - Publishing using `np`"): 0.9}

    monkeypatch.setattr(titles, "title_scores", titled)
    fixed_retrieval(monkeypatch, _lectures(11, "x") + [Candidate(chunk=CORPUS[1][0])])   # cl-10-0 is the 12th fused candidate
    grader({"c1": "n"})
    res = await pipeline.graded_search("what is an IIFE?", ["custom-library"])
    assert len(res.graded) == 12 and sum(g.candidate.chunk.lecture_id == "cl-10-0" for g in res.graded) == 1


async def test_title_additions_backfill_past_lectures_the_kept_slice_already_holds(mem, grader, monkeypatch):
    """Task 13 review: lectures already in the kept slice are dropped BEFORE the top 3 is taken."""
    chunks = [CORPUS[0][0].model_copy(update={"chunk_id": f"x{i}", "lecture_id": f"L{i}"}) for i in range(12)]
    cands = [Candidate(chunk=c) for c in chunks]
    titles_scored = {("custom-library", f"T{i}"): 0.95 - n * 0.05 for n, i in enumerate((0, 20, 21, 22))}   # L0 best, then 3 absent

    async def scored(*a, **kw):
        return titles_scored

    ids = {"t0": "L0", "t20": "L20", "t21": "L21", "t22": "L22"}
    monkeypatch.setattr(titles, "title_scores", scored)
    monkeypatch.setattr(pipeline, "norm_title", lambda t: t.lower())
    monkeypatch.setattr(pipeline, "lecture_ids_for_titles", lambda slug, keys: {k: ids[k] for k in keys})

    async def found(question, lids):
        return {l: (CORPUS[0][0].model_copy(update={"chunk_id": f"y{l}", "lecture_id": l}), 0.5) for l in lids}

    monkeypatch.setattr(pipeline, "best_chunk_for_lectures", found)
    kept, extra = await pipeline._title_candidates("q", ["custom-library"], cands)
    assert {c.chunk.lecture_id for c in extra} == {"L20", "L21", "L22"}     # L0 held already: three others backfill
    assert len(kept) + len(extra) == 12


# ---- query understanding inside graded_search (Task 18) ------------------------
import asyncio

from app.retrieval import understand as un

HIST = [{"role": "user", "content": "what is the np package?"}]


def _understood(query, intent="explain", keywords=()):
    async def fake(system, user):
        return {"search_query": query, "keywords": list(keywords), "intent": intent}
    return fake


async def test_rewrite_is_fused_with_the_raw_retrieval_and_judged(mem, grader, monkeypatch):
    monkeypatch.setattr(un, "_complete", _understood("publish with np", keywords=["np"]))
    grader({"c1": "a"})
    res = await pipeline.graded_search("how do I use it?", ["custom-library"], history=HIST)
    assert mem == ["how do I use it?", "publish with np"]          # raw first, then the rewrite
    assert grader.calls[0].startswith("Question: publish with np")
    assert res.search_query == "publish with np" and res.best().candidate.chunk.lecture_id == "cl-10-0"
    assert "understand" in res.timings_ms
    assert res.question_embedding == pipeline._recent["how do I use it?"]   # the RAW question's embedding


async def test_raw_retrieval_starts_while_understanding_runs(mem, grader, monkeypatch):
    saw_raw = []

    async def waits_for_raw(system, user):
        for _ in range(200):
            if "what does this mean?" in mem:
                break
            await asyncio.sleep(0.001)
        saw_raw.append("what does this mean?" in mem)
        return {"search_query": "what does this mean?", "keywords": [], "intent": "explain"}

    monkeypatch.setattr(un, "_complete", waits_for_raw)
    grader({"c1": "p"})
    await pipeline.graded_search("what does this mean?", ["custom-library"], lecture_title="6.5 - IIFE, To The Rescue")
    assert saw_raw == [True]
    assert mem == ["what does this mean?"]                         # unchanged rewrite: no second embedding


@pytest.mark.parametrize("intent", ["account", "off_topic"])
async def test_account_and_off_topic_bypass_rerank(mem, grader, monkeypatch, intent):
    monkeypatch.setattr(un, "_complete", _understood("what courses do I own", intent=intent))
    res = await pipeline.graded_search("what courses do I own?", ["custom-library"], history=HIST)
    assert (res.outcome, res.intent, res.graded) == (pipeline.Outcome.NOT_COVERED, intent, [])
    assert grader.calls == []


async def test_forced_navigate_beats_an_off_topic_guess(mem, grader, monkeypatch):
    monkeypatch.setattr(un, "_complete", _understood("IIFE", intent="off_topic"))
    grader({"c1": "a"})
    res = await pipeline.graded_search("take me to it", ["custom-library"], intent="navigate", history=HIST)
    assert res.intent == "navigate" and res.outcome == pipeline.Outcome.COVERED
    assert "Intent: navigate" in grader.calls[0]


async def test_models_navigate_intent_reaches_the_reranker(mem, grader, monkeypatch):
    monkeypatch.setattr(un, "_complete", _understood("IIFE", intent="navigate"))
    grader({"c1": "a"})
    res = await pipeline.graded_search("take me to it", ["custom-library"], history=HIST)
    assert res.intent == "navigate" and "Intent: navigate" in grader.calls[0]


async def test_self_contained_question_without_context_skips_understanding(mem, grader, monkeypatch):
    async def boom(system, user):
        raise AssertionError("no understanding call expected")

    monkeypatch.setattr(un, "_complete", boom)
    grader({"c1": "a"})
    res = await pipeline.graded_search("what is an IIFE?", ["custom-library"])
    assert res.outcome == pipeline.Outcome.COVERED and "understand" not in res.timings_ms


async def test_understanding_failure_falls_back_to_the_raw_question(mem, grader, monkeypatch):
    async def down(system, user):
        raise RuntimeError("openai down")

    monkeypatch.setattr(un, "_complete", down)
    grader({"c1": "a"})
    res = await pipeline.graded_search("what is an IIFE?", ["custom-library"], history=HIST)
    assert res.search_query == "what is an IIFE?" and res.outcome == pipeline.Outcome.COVERED
    assert mem == ["what is an IIFE?"]


# ---- Task 18 fix round 1 -------------------------------------------------------
async def test_off_topic_with_a_strong_raw_hit_is_still_reranked(mem, grader, monkeypatch):
    monkeypatch.setattr(un, "_complete", _understood("what is an IIFE?", intent="off_topic"))
    grader({"c1": "a"})
    res = await pipeline.graded_search("what is an IIFE?", ["custom-library"], history=HIST)
    assert res.outcome == pipeline.Outcome.COVERED and len(grader.calls) == 1 and res.intent == "explain"


async def test_off_topic_with_a_weak_raw_hit_bypasses_rerank(mem, grader, monkeypatch):
    monkeypatch.setattr(un, "_complete", _understood("bake bread", intent="off_topic"))
    res = await pipeline.graded_search("how do I bake bread?", ["custom-library"], history=HIST)
    assert (res.outcome, res.intent) == (pipeline.Outcome.NOT_COVERED, "off_topic") and grader.calls == []


async def test_callers_navigate_beats_a_model_account_guess(mem, grader, monkeypatch):
    monkeypatch.setattr(un, "_complete", _understood("IIFE", intent="account"))
    grader({"c1": "a"})
    res = await pipeline.graded_search("take me to it", ["custom-library"], intent="navigate", history=HIST)
    assert res.intent == "navigate" and res.outcome == pipeline.Outcome.COVERED and len(grader.calls) == 1


async def test_rewrite_retrieval_failure_keeps_the_raw_lists(mem, grader, monkeypatch):
    monkeypatch.setattr(un, "_complete", _understood("what is an IIFE?", keywords=["IIFE"]))
    real = pipeline._gather

    async def flaky(queries, scope, lecture_id, terms=(), *, vector=True):
        if terms:
            raise RuntimeError("embedding down")
        return await real(queries, scope, lecture_id, terms, vector=vector)

    monkeypatch.setattr(pipeline, "_gather", flaky)
    grader({"c1": "a"})
    res = await pipeline.graded_search("it?", ["custom-library"], history=HIST)
    assert res.outcome == pipeline.Outcome.COVERED and len(grader.calls) == 1


async def test_case_and_punctuation_only_changes_are_not_rewrites(mem, grader, monkeypatch):
    monkeypatch.setattr(un, "_complete", _understood("what is an  iife"))
    grader({"c1": "a"})
    res = await pipeline.graded_search("what is an IIFE?", ["custom-library"], history=HIST)
    assert mem == ["what is an IIFE?"] and res.search_query == "what is an IIFE?"
    assert pipeline._same("Does it?", "does it") and not pipeline._same("np", "npm")


async def test_cancellation_during_understanding_leaves_no_orphaned_task(mem, grader, monkeypatch):
    started = asyncio.Event()

    async def hangs(system, user):
        started.set()
        await asyncio.sleep(30)

    monkeypatch.setattr(un, "_complete", hangs)
    errors = []
    asyncio.get_running_loop().set_exception_handler(lambda loop, ctx: errors.append(ctx))
    task = asyncio.create_task(pipeline.graded_search("what is an IIFE?", ["custom-library"], history=HIST))
    await started.wait()
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    await asyncio.sleep(0.05)
    import gc
    gc.collect()
    assert errors == [] and grader.calls == []
