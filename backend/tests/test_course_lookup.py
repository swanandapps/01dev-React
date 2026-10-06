import pytest

from app.models import TranscriptChunk
from app.retrieval import pipeline
from app.retrieval.base import Candidate
from app.retrieval.rerank import Graded, decide
from app.services import course_lookup as cl
from app.retrieval import titles as title_index
from app.services import enrollment_service
from app.services.catalog_index import CatalogEntry


def _chunk(slug, title, lecture, text="t", start=87):
    return TranscriptChunk(chunk_id=f"{slug}-x", course_id=slug, course_title=title, lecture_id=f"{slug}-l",
                           lecture_title=lecture, text=text, start_time=start, end_time=start + 30)


NPM_CHUNK = _chunk("custom-library", "Build a Custom Library", "8.1 - The npm link command", "npm link symlinks...")
NPM_CHUNK.lecture_id = "custom-library-7-0"   # 8.1 is chapter index 7, sub index 0
MEMO_CHUNK = _chunk("react-perf", "React Performance Patterns", "4.1 - React.memo and useCallback")
NPM_MODULE = CatalogEntry(2, "custom-library", "Build a Custom Library", "NPM Package Development", "npm link")


@pytest.fixture
def patch_sources(monkeypatch):
    monkeypatch.setattr(cl, "CATALOG_THRESHOLD", 0.35)
    from types import SimpleNamespace   # the transcripts the library holds: custom-library and react-perf
    monkeypatch.setattr(cl, "vector_store", SimpleNamespace(chunks=[NPM_CHUNK, MEMO_CHUNK]))
    seen: dict = {"scopes": [], "questions": [], "kw": []}

    def apply(transcripts=(), catalog=(), enrolled_ids=(), enrollment_error=False):
        async def fake_graded(question, scope, **kw):
            seen["scopes"].append(tuple(scope))
            seen["questions"].append(question)
            seen["kw"].append(kw)
            graded = [Graded(Candidate(chunk=c, vec_score=0.6), g, f"why {c.lecture_title}")
                      for c, g in transcripts if c.course_id in scope]
            outcome, ordered = decide(graded)
            return pipeline.RetrievalResult(outcome, ordered, search_query=question)

        async def fake_catalog(query, top_k=5):
            return list(catalog)

        async def fake_enrolled(student_id):
            if enrollment_error:
                raise RuntimeError("db down")
            return [{"id": i, "title": f"course {i}", "purchased_at": "x"} for i in enrolled_ids]

        monkeypatch.setattr(pipeline, "graded_search", fake_graded)
        monkeypatch.setattr(cl.catalog_index, "search", fake_catalog)
        monkeypatch.setattr(enrollment_service, "get_enrolled_courses", fake_enrolled)

    apply.scopes, apply.seen = seen["scopes"], seen
    return apply


async def test_npm_question_for_student_not_in_custom_library_is_no_match(patch_sources):
    # CHANGED (F1 policy): was NOT_ENROLLED_MATCH. Demo fixture: enrolled in JS Deep Dive (9) + React
    # Perf (11), not Custom Library (2). The Ask page never points at a course the student doesn't own.
    patch_sources(transcripts=[(NPM_CHUNK, "answers")], catalog=[(NPM_MODULE, 0.58)], enrolled_ids=[9, 11])
    out = await cl.course_lookup("how do I publish an npm library", "demo")
    assert out.case == cl.LookupCase.NO_MATCH
    assert out.hits == []
    facts = cl.render_facts(out, cl.ChatScope())
    assert "Custom Library" not in facts and "the01.dev/course" not in facts
    assert cl.to_cards(out) == []


async def test_enrolled_in_custom_library_gets_a_deep_link_to_the_exact_lecture_and_second(patch_sources):
    patch_sources(transcripts=[(NPM_CHUNK, "answers")], catalog=[(NPM_MODULE, 0.58)], enrolled_ids=[2])
    out = await cl.course_lookup("how do I publish an npm library", "demo")
    assert out.case == cl.LookupCase.ENROLLED_MATCH
    facts = cl.render_facts(out, cl.ChatScope())
    assert "the01.dev/course/2?chapter=7&sub=0&t=87" in facts
    assert "Student is enrolled in: Build a Custom Library" in facts
    card = cl.to_cards(out)[0]
    assert card["url"] == "/course/2?chapter=7&sub=0&t=87" and card["chapter"] == 7 and card["sub"] == 0


async def test_an_unlaunched_course_the_student_owns_is_never_cited(patch_sources):
    # React Perf (11) is enrolled but not launched: not cited, not listed as owned.
    patch_sources(transcripts=[(MEMO_CHUNK, "answers")], enrolled_ids=[11])
    out = await cl.course_lookup("does React.memo need useCallback", "s")
    assert out.case == cl.LookupCase.NO_MATCH and out.hits == []
    assert out.enrolled_titles == []
    assert "React Performance" not in cl.render_facts(out, cl.ChatScope())


async def test_only_the_launched_enrolled_hit_survives(patch_sources):
    # CHANGED (F1): was "enrolled hit wins over not enrolled"; now the unowned hit is dropped outright.
    patch_sources(transcripts=[(MEMO_CHUNK, "answers"), (NPM_CHUNK, "answers")], enrolled_ids=[2, 11])
    out = await cl.course_lookup("q", "s")
    assert out.case == cl.LookupCase.ENROLLED_MATCH
    assert [h.course_slug for h in out.hits] == ["custom-library"]


async def test_related_or_no_grades_mean_no_match(patch_sources):
    patch_sources(transcripts=[(NPM_CHUNK, "related")], catalog=[(NPM_MODULE, 0.58)], enrolled_ids=[2])
    out = await cl.course_lookup("q", "s")
    assert out.case == cl.LookupCase.NO_MATCH and out.hits == []      # custom-library has transcripts: no catalog


async def test_enrollment_failure_still_answers_with_no_course(patch_sources):
    # CHANGED (F1): was NOT_ENROLLED_MATCH; unknown enrollment now means no course is cited.
    patch_sources(transcripts=[(MEMO_CHUNK, "answers")], enrollment_error=True)
    out = await cl.course_lookup("q", "s")
    assert out.case == cl.LookupCase.NO_MATCH
    assert out.enrolled_titles == []


async def test_lecture_scope_ranks_current_lecture_first(patch_sources):
    # CHANGED (F1): react-perf is unlaunched, so the ranking property is shown inside custom-library.
    other = _chunk("custom-library", "Build a Custom Library", "7.2 - Publishing to npm")
    patch_sources(transcripts=[(other, "answers"), (NPM_CHUNK, "answers")], enrolled_ids=[2])
    scope = cl.ChatScope(course_slug="custom-library", lecture_title="8.1 - The npm link command")
    out = await cl.course_lookup("what does this mean", "s", scope)
    assert out.hits[0].title == "8.1 - The npm link command"


async def test_catalog_hit_for_same_course_as_transcript_hit_is_dropped(patch_sources):
    patch_sources(transcripts=[(NPM_CHUNK, "answers")], catalog=[(NPM_MODULE, 0.58)], enrolled_ids=[2])
    out = await cl.course_lookup("q", "s")
    assert [h.source for h in out.hits] == ["transcript"]


async def test_facts_and_cards(patch_sources):
    # CHANGED (F1): enrolled in the launched course instead of 9; was a NOT_ENROLLED facts block.
    patch_sources(transcripts=[(NPM_CHUNK, "answers")], enrolled_ids=[2])
    out = await cl.course_lookup("q", "s")
    facts = cl.render_facts(out, cl.ChatScope(), weak_concepts=None)
    assert "CASE: ENROLLED_MATCH" in facts
    assert "[ENROLLED] Build a Custom Library" in facts
    assert "the01.dev/course/2?chapter=7&sub=0&t=87" in facts
    card = cl.to_cards(out)[0]
    assert card["course_id"] == "custom-library" and card["timestamp"] == "01:27"


def test_lecture_mode_facts_include_lecture_and_weak_concepts():
    lookup = cl.CourseLookup(case=cl.LookupCase.NO_MATCH, hits=[], enrolled_titles=["React Performance Patterns"])
    scope = cl.ChatScope(course_slug="react-perf", lecture_title="4.1 - React.memo and useCallback")
    facts = cl.render_facts(lookup, scope, weak_concepts=["useCallback (40%)"])
    assert "MODE: in-lecture" in facts and "4.1 - React.memo and useCallback" in facts
    assert "useCallback (40%)" in facts


JS_CHUNK = _chunk("javascript-deep-dive", "JavaScript Deep Dive", "3.2 - Closures")


async def test_case_follows_top_ranked_hit_in_unowned_lecture(patch_sources):
    # Watching React Perf (11, not owned) while owning JS Deep Dive (9): the current
    # lecture ranks first and is NOT enrolled, so the case must not be ENROLLED_MATCH.
    patch_sources(transcripts=[(MEMO_CHUNK, "answers"), (JS_CHUNK, "answers")], enrolled_ids=[9])
    scope = cl.ChatScope(course_slug="react-perf", lecture_title="4.1 - React.memo and useCallback")
    out = await cl.course_lookup("what does this mean", "s", scope)
    # CHANGED (F1): the unowned current lecture is dropped; only the owned JS hit remains... but JS Deep
    # Dive is not launched, so nothing is cited at all.
    assert out.hits == []
    assert out.case == cl.LookupCase.NO_MATCH


async def test_same_lecture_title_in_another_course_gets_no_lecture_boost(patch_sources):
    # Generic title "1.1 - Introduction" exists in Custom Library too; scope is React Perf.
    other_intro = _chunk("custom-library", "Build a Custom Library", "1.1 - Introduction")
    patch_sources(transcripts=[(other_intro, "answers"), (MEMO_CHUNK, "answers")], enrolled_ids=[2, 11])
    scope = cl.ChatScope(course_slug="react-perf", lecture_title="1.1 - Introduction")
    out = await cl.course_lookup("q", "s", scope)
    # CHANGED (F1): react-perf (11) is not launched so only custom-library can appear; the boost
    # property is still covered by the in-course tests.
    assert [h.course_slug for h in out.hits] == ["custom-library"]


async def test_malformed_enrollment_doc_does_not_fail_the_turn(patch_sources, monkeypatch):
    patch_sources(transcripts=[(MEMO_CHUNK, "answers")])

    async def malformed(student_id):
        return [{"title": "no id"}]

    monkeypatch.setattr(enrollment_service, "get_enrolled_courses", malformed)
    out = await cl.course_lookup("q", "s")
    assert out.case == cl.LookupCase.NO_MATCH  # CHANGED (F1): was NOT_ENROLLED_MATCH
    assert out.enrolled_titles == []


async def test_lecture_boost_survives_backticks_and_spacing_in_player_title(patch_sources):
    # tracks.ts names it "8.1 - The `npm link` command"; the transcript says "8.1 - The npm link command".
    other = _chunk("custom-library", "Build a Custom Library", "7.2 - Publishing to npm")
    patch_sources(transcripts=[(other, "answers"), (NPM_CHUNK, "answers")], enrolled_ids=[2])
    scope = cl.ChatScope(course_slug="custom-library", lecture_title="8.1 -  The `npm link` Command")
    out = await cl.course_lookup("what does this mean", "s", scope)
    assert out.hits[0].title == "8.1 - The npm link command"


async def test_ask_searches_the_bare_question_and_passes_the_lecture_as_context(patch_sources):
    patch_sources(transcripts=[], enrolled_ids=[2])
    scope = cl.ChatScope(course_slug="custom-library", lecture_title="1.1 - What is this course")
    await cl.course_lookup("Give me an example", "s", scope, history=[{"role": "user", "content": "hi"}])
    assert patch_sources.seen["questions"] == ["Give me an example"]
    assert patch_sources.seen["kw"][0] == {"history": [{"role": "user", "content": "hi"}],
                                           "lecture_title": "1.1 - What is this course"}


def test_in_lecture_without_a_transcript_excerpt_gets_the_course_outline():
    # 1.1 of Build a Custom Library has no transcript; with nothing to ground on, the
    # tutor asked "what kind of example?" instead of answering. The catalog has the
    # course description and chapter outline — give the model those.
    scope = cl.ChatScope(course_slug="custom-library", lecture_title="1.1 - What is this course")
    facts = cl.render_facts(cl.CourseLookup(case=cl.LookupCase.NO_MATCH, hits=[], enrolled_titles=[]), scope)
    assert "No transcript excerpt for this lecture" in facts
    assert "closures, callbacks, and prototypes" in facts          # course description
    assert "Chapter 1 - Introduction" in facts                      # the lecture's chapter
    assert "1.2 - What will we build" in facts                      # its sibling lectures


def test_in_lecture_with_an_excerpt_from_that_lecture_skips_the_outline():
    hit = cl.Hit(source="transcript", course_id=11, course_slug="react-perf",
                 course_title="React Performance Patterns", title="4.1 - React.memo and useCallback",
                 score=0.7, enrolled=True, text="memo...", lecture_id="react-perf-4-1", start_time=0, end_time=30)
    scope = cl.ChatScope(course_slug="react-perf", lecture_title="4.1 - React.memo and useCallback")
    facts = cl.render_facts(cl.CourseLookup(case=cl.LookupCase.ENROLLED_MATCH, hits=[hit], enrolled_titles=[]), scope)
    assert "No transcript excerpt" not in facts


# ---- in-player (course-first) mode — spec §3.2 ---------------------------------

PUBLISH_CHUNK = _chunk("custom-library", "Build a Custom Library", "11.1 - Publishing using `np`",
                       "run np and pick the version", start=200)
PLAYER = cl.ChatScope(course_slug="custom-library", lecture_title="8.1 - The `npm link` command", in_player=True)


def test_chat_scope_in_player_defaults_off_and_positional_args_still_work():
    assert cl.ChatScope().in_player is False
    s = cl.ChatScope("react-perf", "4.1 - React.memo and useCallback")
    assert (s.course_slug, s.lecture_title, s.in_player) == ("react-perf", "4.1 - React.memo and useCallback", False)


@pytest.fixture
def patch_in_course(monkeypatch, patch_sources):
    seen = {"graded": [], "lecture": []}

    def apply(graded=(), context=None, enrolled_ids=()):
        """graded: [(chunk, grade)] in fused order, as the reranked pipeline returns them.
        context: [(chunk, score)] the current-lecture search can return (default: the graded chunks)."""
        patch_sources(enrolled_ids=enrolled_ids)

        async def fake_graded(question, scope, **kw):
            seen["graded"].append((question, tuple(scope), kw))
            gs = [Graded(Candidate(chunk=c, vec_score=0.5), g, f"why {g}") for c, g in graded]
            outcome, ordered = decide(gs)
            return pipeline.RetrievalResult(outcome, ordered, search_query=question)

        async def fake_lecture(query, course_slug, lecture_title):
            seen["lecture"].append(query)
            rows = context if context is not None else [(c, 0.5) for c, _ in graded]
            rows = [(c, s) for c, s in rows if cl._norm(c.lecture_title) == cl._norm(lecture_title)]
            return sorted(rows, key=lambda t: t[1], reverse=True)

        async def no_catalog(query, top_k=5):
            raise AssertionError("the player tutor must not search the catalog")

        monkeypatch.setattr(pipeline, "graded_search", fake_graded)
        monkeypatch.setattr(cl, "search_in_lecture", fake_lecture)
        monkeypatch.setattr(cl.catalog_index, "search", no_catalog)
        return seen
    return apply


async def test_player_searches_only_this_course_with_the_lecture_title_and_skips_the_catalog(patch_in_course):
    seen = patch_in_course(graded=[(PUBLISH_CHUNK, "answers")])
    out = await cl.course_lookup("how do I publish", "s", PLAYER)
    assert seen["graded"][0][:2] == ("how do I publish", ("custom-library",))
    assert seen["graded"][0][2]["lecture_title"] == "8.1 - The `npm link` command"
    assert seen["lecture"] == ["8.1 - The `npm link` command how do I publish"]
    assert out.case == cl.LookupCase.IN_COURSE_MATCH
    assert [h.course_slug for h in out.hits] == ["custom-library"]
    assert out.hits[0].title == "11.1 - Publishing using `np`" and out.hits[0].start_time == 200


@pytest.mark.parametrize("grade,case,n_hits", [
    ("answers", "IN_COURSE_MATCH", 1), ("partial", "IN_COURSE_RELATED", 1),
    ("related", "IN_COURSE_NONE", 0), ("no", "IN_COURSE_NONE", 0),
])
async def test_player_outcome_follows_the_grade(patch_in_course, grade, case, n_hits):
    patch_in_course(graded=[(PUBLISH_CHUNK, grade)])
    out = await cl.course_lookup("q", "s", PLAYER)
    assert out.case == cl.LookupCase[case]
    assert len(out.hits) == n_hits


async def test_player_with_no_results_is_in_course_none(patch_in_course):
    patch_in_course(graded=[])
    out = await cl.course_lookup("how do I bake bread", "s", PLAYER)
    assert out.case == cl.LookupCase.IN_COURSE_NONE and out.hits == []


async def test_player_match_keeps_only_match_strength_hits(patch_in_course):
    weak = _chunk("custom-library", "Build a Custom Library", "8.2 - Testing Our NPM Package", "symlink", start=10)
    patch_in_course(graded=[(PUBLISH_CHUNK, "answers"), (weak, "partial")])
    out = await cl.course_lookup("q", "s", PLAYER)
    assert out.case == cl.LookupCase.IN_COURSE_MATCH
    assert [h.grade for h in out.hits] == ["answers"]


async def test_player_drops_any_other_course_chunk_even_if_search_returns_one(patch_in_course):
    patch_in_course(graded=[(MEMO_CHUNK, "answers"), (PUBLISH_CHUNK, "partial")])
    out = await cl.course_lookup("q", "s", PLAYER)
    assert [h.course_slug for h in out.hits] == ["custom-library"]
    assert out.case == cl.LookupCase.IN_COURSE_RELATED


async def test_player_does_not_sort_the_current_lecture_first(patch_in_course):
    here = _chunk("custom-library", "Build a Custom Library", "8.1 - The npm link command", "npm link", start=30)
    patch_in_course(graded=[(PUBLISH_CHUNK, "answers"), (here, "answers")])
    out = await cl.course_lookup("what does this mean", "s", PLAYER)
    assert [h.title for h in out.hits] == ["11.1 - Publishing using `np`", "8.1 - The npm link command"]
    assert out.case == cl.LookupCase.IN_COURSE_MATCH


async def test_player_match_facts_show_band_and_reason_without_scores(patch_in_course):
    es = _chunk("custom-library", "Build a Custom Library", "10.1 - What Are ES Modules", "ECMAScript modules", start=251)
    patch_in_course(graded=[(es, "answers")])
    out = await cl.course_lookup("what are ES modules", "s", PLAYER)
    facts = cl.render_facts(out, PLAYER)
    assert "1. [THIS COURSE · STRONG] 10.1 - What Are ES Modules @ 04:11\n   why: why answers" in facts
    assert "score" not in facts.split("Matches:")[1]


async def test_off_topic_is_none_and_keeps_the_current_lecture_context(patch_in_course):
    here = _chunk("custom-library", "Build a Custom Library", "8.1 - The `npm link` command", "npm link", start=30)
    seen = patch_in_course(graded=[], context=[(here, 0.61)])
    out = await cl.course_lookup("how does the event loop work", "s", PLAYER)
    assert out.case == cl.LookupCase.IN_COURSE_NONE and out.hits == []
    assert out.current_excerpt is not None and out.current_excerpt.title == "8.1 - The `npm link` command"
    facts = cl.render_facts(out, PLAYER)
    assert 'CURRENT LECTURE excerpt (context for "this"/"here" questions' in facts and "npm link" in facts
    assert "Matches:" not in facts
    assert seen["graded"][0][0] == "how does the event loop work"


async def test_weak_band_is_related_with_a_weak_label(patch_in_course):
    patch_in_course(graded=[(PUBLISH_CHUNK, "partial")])
    scope = cl.ChatScope(course_slug="custom-library", in_player=True)
    out = await cl.course_lookup("q", "s", scope)
    assert out.case == cl.LookupCase.IN_COURSE_RELATED
    assert "[THIS COURSE · WEAK] 11.1 - Publishing using `np` @ 03:20" in cl.render_facts(out, scope)


async def test_one_best_chunk_per_lecture_and_at_most_three(patch_in_course):
    rows = [(_chunk("custom-library", "B", f"{i}.1 - L{i}", "t", start=i), "answers") for i in range(5)]
    rows.append((_chunk("custom-library", "B", "0.1 - L0", "dup", start=999), "answers"))
    patch_in_course(graded=rows)
    out = await cl.course_lookup("q", "s", cl.ChatScope(course_slug="custom-library", in_player=True))
    assert [h.title for h in out.hits] == ["0.1 - L0", "1.1 - L1", "2.1 - L2"] and out.hits[0].start_time == 0


async def test_title_scores_fall_back_to_word_overlap_without_embeddings(monkeypatch):
    monkeypatch.setattr(cl.embedding_service, "use_openai", False)
    monkeypatch.setattr(cl.catalog_service, "by_slug", lambda slug: {"chapters": [
        {"name": "c", "subchapters": ["10.1 - What Are ES Modules", "8.1 - The `npm link` command"]}]})
    scores = await cl._title_scores("what are ES modules", "custom-library")
    assert scores["10.1 - What Are ES Modules"] >= cl.TITLE_THRESHOLD
    assert scores["8.1 - The `npm link` command"] < cl.TITLE_THRESHOLD
    assert (await cl._title_scores("how does the event loop work", "custom-library"))["10.1 - What Are ES Modules"] == 0.0


async def test_player_with_no_lecture_selected_searches_the_bare_question_in_this_course(patch_in_course):
    # CoursePlayerPage sends the course title as `lecture` before a lecture is picked; the
    # route blanks it, so the scope has no lecture_title — still course-only.
    seen = patch_in_course(graded=[(PUBLISH_CHUNK, "partial")])
    scope = cl.ChatScope(course_slug="custom-library", in_player=True)
    out = await cl.course_lookup("how do I publish", "s", scope)
    assert seen["graded"][0][:2] == ("how do I publish", ("custom-library",))
    assert seen["graded"][0][2]["lecture_title"] is None and seen["lecture"] == []
    assert out.case == cl.LookupCase.IN_COURSE_RELATED
    assert "MODE: in-lecture" not in cl.render_facts(out, scope)


async def test_ask_with_a_course_filter_is_unchanged(patch_sources):
    # The Ask page's course filter also sets course_slug: it must keep cross-course
    # search, the catalog and the enrolled / not-enrolled cases.
    # CHANGED (F1): still cross-course search, but only launched+enrolled hits are kept.
    patch_sources(transcripts=[(MEMO_CHUNK, "answers"), (NPM_CHUNK, "answers")], catalog=[(NPM_MODULE, 0.58)],
                  enrolled_ids=[2, 11])
    out = await cl.course_lookup("q", "s", cl.ChatScope(course_slug="custom-library"))
    assert out.case == cl.LookupCase.ENROLLED_MATCH
    assert {h.course_slug for h in out.hits} == {"custom-library"}


async def test_ask_scope_is_launched_and_owned_before_searching(patch_sources):
    patch_sources(transcripts=[(NPM_CHUNK, "answers"), (MEMO_CHUNK, "answers")], enrolled_ids=[2, 11])
    out = await cl.course_lookup("npm link", "demo")
    assert patch_sources.scopes == [("custom-library",)]      # 11 is owned but unlaunched: not searched
    assert {h.course_slug for h in out.hits} == {"custom-library"}


async def test_ask_empty_scope_never_searches_or_reranks(patch_sources, monkeypatch):
    from app.retrieval import rerank as rr
    from app.services.embeddings import embedding_service
    patch_sources(transcripts=[(NPM_CHUNK, "answers")], enrolled_ids=[9, 11])   # the demo account

    async def boom(*a, **k):
        raise AssertionError("an empty Ask scope must not embed, search, rerank or read the catalog")

    monkeypatch.setattr(embedding_service, "embed", boom)
    monkeypatch.setattr(rr, "_complete", boom)
    monkeypatch.setattr(cl.catalog_index, "search", boom)
    out = await cl.course_lookup("how do I publish an npm library", "demo")
    assert out.case == cl.LookupCase.NO_MATCH and out.hits == [] and patch_sources.scopes == []


async def test_partial_grades_are_enrolled_related_with_partial_labels(patch_sources):
    patch_sources(transcripts=[(NPM_CHUNK, "partial")], enrolled_ids=[2])
    out = await cl.course_lookup("q", "s")
    assert out.case == cl.LookupCase.ENROLLED_RELATED and [h.grade for h in out.hits] == ["partial"]
    facts = cl.render_facts(out, cl.ChatScope())
    assert "CASE: ENROLLED_RELATED" in facts and "[ENROLLED · PARTIAL] Build a Custom Library" in facts
    assert "   why: why 8.1 - The npm link command" in facts
    assert "the01.dev/course/2?chapter=7&sub=0&t=87" in facts


async def test_answers_rank_before_partial(patch_sources):
    other = _chunk("custom-library", "Build a Custom Library", "7.2 - Publishing to npm")
    patch_sources(transcripts=[(other, "partial"), (NPM_CHUNK, "answers")], enrolled_ids=[2])
    out = await cl.course_lookup("q", "s")
    assert out.case == cl.LookupCase.ENROLLED_MATCH and [h.grade for h in out.hits] == ["answers", "partial"]


async def test_catalog_is_used_only_for_in_scope_courses_without_transcripts(patch_sources, monkeypatch):
    from types import SimpleNamespace
    patch_sources(transcripts=[], catalog=[(NPM_MODULE, 0.58)], enrolled_ids=[2])
    monkeypatch.setattr(cl, "vector_store", SimpleNamespace(chunks=[NPM_CHUNK]))
    assert (await cl.course_lookup("q", "s")).hits == []                     # custom-library has transcripts
    monkeypatch.setattr(cl, "vector_store", SimpleNamespace(chunks=[MEMO_CHUNK]))
    out = await cl.course_lookup("q", "s")
    assert out.case == cl.LookupCase.ENROLLED_MATCH and [h.source for h in out.hits] == ["catalog"]


async def test_search_in_course_goes_through_the_scoped_pipeline(monkeypatch):
    from app.retrieval import pipeline
    from app.retrieval.base import Candidate
    calls = []

    async def fake_search(q, scope, **kw):
        calls.append((q, tuple(scope), kw))
        return [Candidate(chunk=PUBLISH_CHUNK, vec_rank=1, vec_score=0.6), Candidate(chunk=NPM_CHUNK, lex_rank=1)]

    monkeypatch.setattr(pipeline, "search", fake_search)
    assert await cl.search_in_course("publish", "custom-library", top_k=1) == [(PUBLISH_CHUNK, 0.6), (NPM_CHUNK, 0.0)]
    assert calls[0] == ("publish", ("custom-library",), {"limit": 1, "per_lecture": None})
    await cl.search_in_course("publish", "custom-library", top_k=None)
    assert calls[1][2]["limit"] == pipeline.VEC_K + pipeline.LEX_K


async def test_decisions_read_the_cosine_not_the_fused_score(monkeypatch):
    # A lexical-only candidate carries a COMPUTED cosine (pipeline.search fills it); the thresholds see that.
    from app.retrieval import pipeline
    from app.retrieval.base import Candidate

    async def fake_search(q, scope, **kw):
        return [Candidate(chunk=NPM_CHUNK, lex_rank=1, fused=0.0164, cosine=0.57),
                Candidate(chunk=PUBLISH_CHUNK, vec_rank=1, vec_score=0.61, fused=0.0163, cosine=0.61)]

    monkeypatch.setattr(pipeline, "search", fake_search)
    assert await cl.search_in_course("q", "custom-library") == [(NPM_CHUNK, 0.57), (PUBLISH_CHUNK, 0.61)]


async def test_search_in_lecture_filters_by_the_resolved_lecture(monkeypatch):
    from app.retrieval import pipeline
    from app.retrieval.base import Candidate
    calls = []

    async def fake_search(q, scope, **kw):
        calls.append(kw)
        return [Candidate(chunk=NPM_CHUNK, vec_rank=1, vec_score=0.7)]

    monkeypatch.setattr(pipeline, "search", fake_search)
    monkeypatch.setattr(pipeline, "lecture_id_for",
                        lambda slug, title: "custom-library-7-0" if "npm link" in title else None)
    out = await cl.search_in_lecture("q", "custom-library", "8.1 - The `npm link` command")
    assert out == [(NPM_CHUNK, 0.7)] and calls[0]["lecture_id"] == "custom-library-7-0"
    assert await cl.search_in_lecture("q", "custom-library", "9.9 - No transcript") == []
    assert len(calls) == 1


def test_player_facts_name_only_this_course():
    hit = cl.Hit(source="transcript", course_id=2, course_slug="custom-library", course_title="Build a Custom Library",
                 title="11.1 - Publishing using `np`", score=0.47, enrolled=False, text="run np",
                 lecture_id="custom-library-10-0", start_time=200, end_time=250, url="/course/2")
    lookup = cl.CourseLookup(case=cl.LookupCase.IN_COURSE_RELATED, hits=[hit],
                             enrolled_titles=["JavaScript Deep Dive", "React Performance Patterns"])
    facts = cl.render_facts(lookup, PLAYER)
    assert "CASE: IN_COURSE_RELATED" in facts
    assert "[THIS COURSE · WEAK] 11.1 - Publishing using `np` @ 03:20" in facts
    assert "JavaScript Deep Dive" not in facts and "React Performance Patterns" not in facts
    assert "NOT ENROLLED" not in facts and "enrolled in" not in facts.lower()
    assert "never name, recommend or link another course" in facts
    assert "the01.dev/course/" not in facts
    assert "MODE: in-lecture" in facts


def test_player_none_in_a_lecture_still_gets_the_outline():
    scope = cl.ChatScope(course_slug="custom-library", lecture_title="1.1 - What is this course", in_player=True)
    facts = cl.render_facts(cl.CourseLookup(case=cl.LookupCase.IN_COURSE_NONE, hits=[], enrolled_titles=["X"]), scope)
    assert "CASE: IN_COURSE_NONE" in facts
    assert "No transcript excerpt for this lecture" in facts and "Chapter 1 - Introduction" in facts


async def test_current_lecture_excerpt_is_not_listed_under_matches_unless_it_is_a_hit(patch_in_course):
    here = _chunk("custom-library", "Build a Custom Library", "8.1 - The `npm link` command", "SYMLINK-EXCERPT", start=30)
    patch_in_course(graded=[(PUBLISH_CHUNK, "answers")], context=[(PUBLISH_CHUNK, 0.7), (here, 0.2)])
    out = await cl.course_lookup("how do I publish", "s", PLAYER)
    facts = cl.render_facts(out, PLAYER)
    matches = facts.split("Matches:")[1]
    assert "SYMLINK-EXCERPT" not in matches and "SYMLINK-EXCERPT" in facts.split("Matches:")[0]


async def test_title_embedding_failure_falls_back_to_overlap_and_is_not_retried_in_the_cooldown(monkeypatch):
    calls = {"n": 0}

    class Boom:
        class embeddings:
            @staticmethod
            async def create(**kw):
                calls["n"] += 1
                raise RuntimeError("openai down")

    async def fake_embed(text):
        return [1.0, 0.0]

    monkeypatch.setattr(cl.embedding_service, "use_openai", True)
    monkeypatch.setattr(cl.embedding_service, "client", Boom)
    monkeypatch.setattr(cl.embedding_service, "embed", fake_embed)
    monkeypatch.setattr(title_index, "_cache", {})
    monkeypatch.setattr(title_index, "_failed_until", {})
    monkeypatch.setattr(cl.catalog_service, "by_slug", lambda slug: {"chapters": [
        {"name": "c", "subchapters": ["10.1 - What Are ES Modules"]}]})
    first = await cl._title_scores("what are ES modules", "custom-library")
    second = await cl._title_scores("what are ES modules", "custom-library")
    assert first == second == {"10.1 - What Are ES Modules": 1.0}
    assert calls["n"] == 1
    title_index._failed_until["custom-library"] = 0.0  # cooldown over -> retries
    await cl._title_scores("what are ES modules", "custom-library")
    assert calls["n"] == 2


def test_no_launched_enrolled_course_means_no_enrolled_line_in_the_facts():
    lookup = cl.CourseLookup(case=cl.LookupCase.NO_MATCH, hits=[], enrolled_titles=[])
    facts = cl.render_facts(lookup, cl.ChatScope())
    assert "Student is enrolled in" not in facts and "no courses yet" not in facts


# ---- F5: richer CURRENT LECTURE context ---------------------------------------------

async def test_current_lecture_context_holds_top_three_passages_in_time_order(patch_in_course):
    L = "5.1 - Virtualizing the 5,000-Row Table"
    rows = [(_chunk("react-perf", "React Performance Patterns", L, f"passage at {t}", start=t), sc)
            for t, sc in ((300, 0.30), (60, 0.55), (180, 0.50), (120, 0.45), (240, 0.20))]
    patch_in_course(graded=[], context=rows)
    scope = cl.ChatScope(course_slug="react-perf", lecture_title=L, in_player=True)
    out = await cl.course_lookup("give me an example", "s", scope)
    assert [h.start_time for h in out.current_passages] == [60, 120, 180]  # top 3 by score, shown in time order
    assert out.current_excerpt.start_time == 60                            # best one stays the excerpt
    facts = cl.render_facts(out, scope)
    line = next(l for l in facts.splitlines() if l.startswith("CURRENT LECTURE"))
    assert line.index("passage at 60") < line.index("passage at 120") < line.index("passage at 180")
    assert "passage at 240" not in line and "passage at 300" not in line
    assert "@ 01:00" in line and "@ 03:00" in line


async def test_current_lecture_context_is_capped(patch_in_course):
    L = "5.1 - Virtualizing the 5,000-Row Table"
    rows = [(_chunk("react-perf", "React Performance Patterns", L, "x" * 2000, start=t * 60), 0.5 - t / 100)
            for t in range(3)]
    patch_in_course(graded=[], context=rows)
    scope = cl.ChatScope(course_slug="react-perf", lecture_title=L, in_player=True)
    out = await cl.course_lookup("explain this", "s", scope)
    line = next(l for l in cl.render_facts(out, scope).splitlines() if l.startswith("CURRENT LECTURE"))
    assert line.count("x") <= 1500 and line.count("x") > 900


def test_player_facts_carry_the_course_description_line():
    scope = cl.ChatScope(course_slug="programming-language", lecture_title="6.2 - Writing the Tokenizer Loop",
                         in_player=True)
    facts = cl.render_facts(cl.CourseLookup(case=cl.LookupCase.IN_COURSE_NONE, hits=[], enrolled_titles=[]), scope)
    desc = next(l for l in facts.splitlines() if l.startswith("COURSE DESCRIPTION"))
    assert "Ember" in desc and len(desc) <= cl.DESCRIPTION_CHARS + 80


def test_ask_facts_have_no_course_description_line():
    scope = cl.ChatScope(course_slug="programming-language")
    facts = cl.render_facts(cl.CourseLookup(case=cl.LookupCase.NO_MATCH, hits=[], enrolled_titles=[]), scope)
    assert "COURSE DESCRIPTION" not in facts


# ---- title-embedding prewarm (I1) ----
def _fake_embeddings_client(monkeypatch, behaviour):
    """Stub OpenAI client: behaviour(texts) -> vectors or raises. Returns the list of input batches."""
    from types import SimpleNamespace

    batches = []

    async def create(model, input):
        batches.append(list(input))
        return SimpleNamespace(data=[SimpleNamespace(embedding=v) for v in behaviour(input)])

    monkeypatch.setattr(cl.embedding_service, "use_openai", True)
    monkeypatch.setattr(cl.embedding_service, "client", SimpleNamespace(embeddings=SimpleNamespace(create=create)))
    monkeypatch.setattr(title_index, "_cache", {})
    monkeypatch.setattr(title_index, "_failed_until", {})
    return batches


async def test_prewarm_titles_embeds_every_course_in_one_call_and_fills_the_cache(monkeypatch):
    batches = _fake_embeddings_client(monkeypatch, lambda texts: [[1.0, float(i)] for i, _ in enumerate(texts)])
    n_titles, n_courses = await cl.prewarm_titles()
    expected = {c["slug"]: cl._lecture_titles(c["slug"]) for c in cl.catalog_service.all_courses()}
    expected = {k: v for k, v in expected.items() if v}
    assert len(batches) == 1 and n_courses == len(expected) and n_titles == sum(map(len, expected.values()))
    assert set(title_index._cache) == set(expected)
    for slug, titles in expected.items():
        assert title_index._cache[slug][0] == titles and len(title_index._cache[slug][1]) == len(titles)


async def test_prewarm_failure_raises_but_sets_no_cooldown(monkeypatch):
    def boom(texts):
        raise RuntimeError("openai down")

    _fake_embeddings_client(monkeypatch, boom)
    with pytest.raises(RuntimeError):
        await cl.prewarm_titles()
    assert title_index._failed_until == {} and title_index._cache == {}


async def test_question_embed_failure_does_not_trigger_the_title_cooldown(monkeypatch):
    _fake_embeddings_client(monkeypatch, lambda texts: [[1.0, 0.0] for _ in texts])
    await cl.prewarm_titles()

    async def flaky(text):
        raise RuntimeError("transient")

    monkeypatch.setattr(cl.embedding_service, "embed", flaky)
    scores = await cl._title_scores("npm link", "custom-library")  # falls back for this turn only
    assert scores and title_index._failed_until == {}

    async def ok(text):
        return [1.0, 0.0]

    monkeypatch.setattr(cl.embedding_service, "embed", ok)
    assert set((await cl._title_scores("npm link", "custom-library")).values()) == {1.0}  # real cosines again


async def test_title_build_failure_still_sets_a_short_cooldown(monkeypatch):
    def boom(texts):
        raise RuntimeError("down")

    _fake_embeddings_client(monkeypatch, boom)
    await cl._title_scores("npm link", "custom-library")
    assert 0 < title_index._failed_until["custom-library"] - cl.time.monotonic() <= 60.0


def test_description_cap_keeps_product_engineerings_project():
    course = cl.catalog_service.by_slug("product-engineering")
    desc = " ".join(course["description"].split())
    assert len(desc) <= cl.DESCRIPTION_CHARS


def test_player_outline_does_not_repeat_the_description():
    course = cl.catalog_service.by_slug("custom-library")
    scope = cl.ChatScope(course_slug="custom-library", lecture_title="1.1 - Introduction", in_player=True)
    facts = cl.render_facts(cl.CourseLookup(case=cl.LookupCase.IN_COURSE_NONE, hits=[], enrolled_titles=[]), scope)
    snippet = " ".join(course["description"].split())[:60]
    assert facts.count(snippet) == 1
