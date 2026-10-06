import pytest

from app.models import TranscriptChunk
from app.services import course_lookup as cl
from app.services import enrollment_service
from app.services.catalog_index import CatalogEntry


def _chunk(slug, title, lecture, text="t", start=87):
    return TranscriptChunk(chunk_id=f"{slug}-x", course_id=slug, course_title=title, lecture_id=f"{slug}-l",
                           lecture_title=lecture, text=text, start_time=start, end_time=start + 30)


NPM_CHUNK = _chunk("custom-library", "Build a Custom Library", "8.1 - The npm link command", "npm link symlinks...")
MEMO_CHUNK = _chunk("react-perf", "React Performance Patterns", "4.1 - React.memo and useCallback")
NPM_MODULE = CatalogEntry(2, "custom-library", "Build a Custom Library", "NPM Package Development", "npm link")


@pytest.fixture
def patch_sources(monkeypatch):
    # Pin thresholds so these tests don't depend on Task 9's calibrated values.
    monkeypatch.setattr(cl, "TRANSCRIPT_THRESHOLD", 0.35)
    monkeypatch.setattr(cl, "CATALOG_THRESHOLD", 0.35)

    def apply(transcripts=(), catalog=(), enrolled_ids=(), enrollment_error=False):
        async def fake_transcripts(question, top_k=8):
            return list(transcripts)

        async def fake_catalog(query, top_k=5):
            return list(catalog)

        async def fake_enrolled(student_id):
            if enrollment_error:
                raise RuntimeError("db down")
            return [{"id": i, "title": f"course {i}", "purchased_at": "x"} for i in enrolled_ids]

        monkeypatch.setattr(cl, "_transcript_hits", fake_transcripts)
        monkeypatch.setattr(cl.catalog_index, "search", fake_catalog)
        monkeypatch.setattr(enrollment_service, "get_enrolled_courses", fake_enrolled)
    return apply


async def test_npm_question_for_student_not_in_custom_library_is_not_enrolled(patch_sources):
    # Demo fixture from the spec: enrolled in JS Deep Dive (9) + React Perf (11), not Custom Library (2).
    patch_sources(transcripts=[(NPM_CHUNK, 0.62)], catalog=[(NPM_MODULE, 0.58)], enrolled_ids=[9, 11])
    out = await cl.course_lookup("how do I publish an npm library", "demo")
    assert out.case == cl.LookupCase.NOT_ENROLLED_MATCH
    assert out.hits[0].course_title == "Build a Custom Library"
    assert all(not h.enrolled for h in out.hits)


async def test_enrolled_hit_wins_over_not_enrolled(patch_sources):
    patch_sources(transcripts=[(NPM_CHUNK, 0.70), (MEMO_CHUNK, 0.50)], enrolled_ids=[11])
    out = await cl.course_lookup("q", "s")
    assert out.case == cl.LookupCase.ENROLLED_MATCH
    assert out.hits[0].course_slug == "react-perf"


async def test_scores_below_threshold_mean_no_match(patch_sources):
    patch_sources(transcripts=[(NPM_CHUNK, cl.TRANSCRIPT_THRESHOLD - 0.01)],
                  catalog=[(NPM_MODULE, cl.CATALOG_THRESHOLD - 0.01)])
    out = await cl.course_lookup("how do I bake bread", "s")
    assert out.case == cl.LookupCase.NO_MATCH
    assert out.hits == []


async def test_enrollment_failure_still_answers_as_not_enrolled(patch_sources):
    patch_sources(transcripts=[(MEMO_CHUNK, 0.6)], enrollment_error=True)
    out = await cl.course_lookup("q", "s")
    assert out.case == cl.LookupCase.NOT_ENROLLED_MATCH
    assert out.enrolled_titles == []


async def test_lecture_scope_ranks_current_lecture_first(patch_sources):
    patch_sources(transcripts=[(NPM_CHUNK, 0.80), (MEMO_CHUNK, 0.50)], enrolled_ids=[2, 11])
    scope = cl.ChatScope(course_slug="react-perf", lecture_title="4.1 - React.memo and useCallback")
    out = await cl.course_lookup("what does this mean", "s", scope)
    assert out.hits[0].course_slug == "react-perf"


async def test_catalog_hit_for_same_course_as_transcript_hit_is_dropped(patch_sources):
    patch_sources(transcripts=[(NPM_CHUNK, 0.62)], catalog=[(NPM_MODULE, 0.58)])
    out = await cl.course_lookup("q", "s")
    assert [h.source for h in out.hits] == ["transcript"]


async def test_facts_and_cards(patch_sources):
    patch_sources(transcripts=[(NPM_CHUNK, 0.62)], enrolled_ids=[9])
    out = await cl.course_lookup("q", "s")
    facts = cl.render_facts(out, cl.ChatScope(), weak_concepts=None)
    assert "CASE: NOT_ENROLLED_MATCH" in facts
    assert "[NOT ENROLLED] Build a Custom Library" in facts
    assert "the01.dev/course/2" in facts
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
    patch_sources(transcripts=[(MEMO_CHUNK, 0.5), (JS_CHUNK, 0.8)], enrolled_ids=[9])
    scope = cl.ChatScope(course_slug="react-perf", lecture_title="4.1 - React.memo and useCallback")
    out = await cl.course_lookup("what does this mean", "s", scope)
    assert out.hits[0].course_slug == "react-perf"
    assert out.case == cl.LookupCase.NOT_ENROLLED_MATCH


async def test_same_lecture_title_in_another_course_gets_no_lecture_boost(patch_sources):
    # Generic title "1.1 - Introduction" exists in Custom Library too; scope is React Perf.
    other_intro = _chunk("custom-library", "Build a Custom Library", "1.1 - Introduction")
    patch_sources(transcripts=[(other_intro, 0.8), (MEMO_CHUNK, 0.5)])
    scope = cl.ChatScope(course_slug="react-perf", lecture_title="1.1 - Introduction")
    out = await cl.course_lookup("q", "s", scope)
    assert out.hits[0].course_slug == "react-perf"


async def test_malformed_enrollment_doc_does_not_fail_the_turn(patch_sources, monkeypatch):
    patch_sources(transcripts=[(MEMO_CHUNK, 0.6)])

    async def malformed(student_id):
        return [{"title": "no id"}]

    monkeypatch.setattr(enrollment_service, "get_enrolled_courses", malformed)
    out = await cl.course_lookup("q", "s")
    assert out.case == cl.LookupCase.NOT_ENROLLED_MATCH
    assert out.enrolled_titles == []


async def test_lecture_boost_survives_backticks_and_spacing_in_player_title(patch_sources):
    # tracks.ts names it "8.1 - The `npm link` command"; the transcript says "8.1 - The npm link command".
    other = _chunk("custom-library", "Build a Custom Library", "7.2 - Publishing to npm")
    patch_sources(transcripts=[(other, 0.8), (NPM_CHUNK, 0.5)])
    scope = cl.ChatScope(course_slug="custom-library", lecture_title="8.1 -  The `npm link` Command")
    out = await cl.course_lookup("what does this mean", "s", scope)
    assert out.hits[0].title == "8.1 - The npm link command"


async def test_lecture_title_steers_the_transcript_search_but_not_the_catalog(patch_sources, monkeypatch):
    # Live bug: in "1.1 - What is this course" of Build a Custom Library, "Give me an example"
    # searched the catalog as "1.1 - What is this course Give me an example" and matched
    # Product Engineering Essentials' overview (0.37) → a not-enrolled pointer to an unrelated course.
    patch_sources()
    seen = {}

    async def fake_transcripts(question, top_k=8):
        seen["transcript"] = question
        return []

    async def fake_catalog(query, top_k=5):
        seen["catalog"] = query
        return []

    monkeypatch.setattr(cl, "_transcript_hits", fake_transcripts)
    monkeypatch.setattr(cl.catalog_index, "search", fake_catalog)
    scope = cl.ChatScope(course_slug="custom-library", lecture_title="1.1 - What is this course")

    await cl.course_lookup("Give me an example", "s", scope)

    assert seen == {"transcript": "1.1 - What is this course Give me an example",
                    "catalog": "Give me an example"}


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
    monkeypatch.setattr(cl, "TRANSCRIPT_THRESHOLD", 0.54)
    monkeypatch.setattr(cl, "RELATED_THRESHOLD", 0.40)
    seen = {}

    def apply(results=(), enrolled_ids=()):
        patch_sources(enrolled_ids=enrolled_ids)

        async def fake_search(query, course_slug, top_k=8):
            seen["query"], seen["slug"] = query, course_slug
            return list(results)

        async def no_catalog(query, top_k=5):
            raise AssertionError("the player tutor must not search the catalog")

        async def no_global_transcripts(question, top_k=8):
            raise AssertionError("the player tutor must not search other courses' transcripts")

        monkeypatch.setattr(cl, "search_in_course", fake_search)
        monkeypatch.setattr(cl.catalog_index, "search", no_catalog)
        monkeypatch.setattr(cl, "_transcript_hits", no_global_transcripts)
        return seen
    return apply


async def test_player_searches_only_this_course_with_the_lecture_title_and_skips_the_catalog(patch_in_course):
    seen = patch_in_course(results=[(PUBLISH_CHUNK, 0.61)])
    out = await cl.course_lookup("how do I publish", "s", PLAYER)
    assert seen == {"query": "8.1 - The `npm link` command how do I publish", "slug": "custom-library"}
    assert out.case == cl.LookupCase.IN_COURSE_MATCH
    assert [h.course_slug for h in out.hits] == ["custom-library"]
    assert out.hits[0].title == "11.1 - Publishing using `np`" and out.hits[0].start_time == 200


@pytest.mark.parametrize("score,case,n_hits", [
    (0.60, "IN_COURSE_MATCH", 1), (0.54, "IN_COURSE_MATCH", 1),
    (0.47, "IN_COURSE_RELATED", 1), (0.40, "IN_COURSE_RELATED", 1),
    (0.39, "IN_COURSE_NONE", 0), (0.10, "IN_COURSE_NONE", 0),
])
async def test_player_outcome_follows_the_best_in_course_score(patch_in_course, score, case, n_hits):
    patch_in_course(results=[(PUBLISH_CHUNK, score)])
    out = await cl.course_lookup("q", "s", PLAYER)
    assert out.case == cl.LookupCase[case]
    assert len(out.hits) == n_hits


async def test_player_with_no_results_is_in_course_none(patch_in_course):
    patch_in_course(results=[])
    out = await cl.course_lookup("how do I bake bread", "s", PLAYER)
    assert out.case == cl.LookupCase.IN_COURSE_NONE and out.hits == []


async def test_player_match_keeps_only_match_strength_hits(patch_in_course):
    weak = _chunk("custom-library", "Build a Custom Library", "8.2 - Testing Our NPM Package", "symlink", start=10)
    patch_in_course(results=[(PUBLISH_CHUNK, 0.62), (weak, 0.45)])
    out = await cl.course_lookup("q", "s", PLAYER)
    assert out.case == cl.LookupCase.IN_COURSE_MATCH
    assert [h.score for h in out.hits] == [0.62]


async def test_player_drops_any_other_course_chunk_even_if_search_returns_one(patch_in_course):
    patch_in_course(results=[(MEMO_CHUNK, 0.90), (PUBLISH_CHUNK, 0.45)])
    out = await cl.course_lookup("q", "s", PLAYER)
    assert [h.course_slug for h in out.hits] == ["custom-library"]
    assert out.case == cl.LookupCase.IN_COURSE_RELATED


async def test_player_ranks_the_current_lecture_first_among_matches(patch_in_course):
    here = _chunk("custom-library", "Build a Custom Library", "8.1 - The npm link command", "npm link", start=30)
    patch_in_course(results=[(PUBLISH_CHUNK, 0.70), (here, 0.58)])
    out = await cl.course_lookup("what does this mean", "s", PLAYER)
    assert out.hits[0].title == "8.1 - The npm link command"
    assert out.case == cl.LookupCase.IN_COURSE_MATCH


async def test_player_with_no_lecture_selected_searches_the_bare_question_in_this_course(patch_in_course):
    # CoursePlayerPage sends the course title as `lecture` before a lecture is picked; the
    # route blanks it, so the scope has no lecture_title — still course-only.
    seen = patch_in_course(results=[(PUBLISH_CHUNK, 0.47)])
    scope = cl.ChatScope(course_slug="custom-library", in_player=True)
    out = await cl.course_lookup("how do I publish", "s", scope)
    assert seen == {"query": "how do I publish", "slug": "custom-library"}
    assert out.case == cl.LookupCase.IN_COURSE_RELATED
    assert "MODE: in-lecture" not in cl.render_facts(out, scope)


async def test_ask_with_a_course_filter_is_unchanged(patch_sources):
    # The Ask page's course filter also sets course_slug: it must keep cross-course
    # search, the catalog and the enrolled / not-enrolled cases.
    patch_sources(transcripts=[(MEMO_CHUNK, 0.6)], catalog=[(NPM_MODULE, 0.58)], enrolled_ids=[11])
    out = await cl.course_lookup("q", "s", cl.ChatScope(course_slug="custom-library"))
    assert out.case == cl.LookupCase.NOT_ENROLLED_MATCH
    assert {h.course_slug for h in out.hits} == {"react-perf", "custom-library"}
    assert {h.source for h in out.hits} == {"transcript", "catalog"}


async def test_search_in_course_keeps_only_that_course_best_first(monkeypatch):
    from app.models import SearchResult
    results = [SearchResult(chunk=MEMO_CHUNK, score=0.9), SearchResult(chunk=PUBLISH_CHUNK, score=0.6),
               SearchResult(chunk=NPM_CHUNK, score=0.5)]

    class FakeStore:
        chunks = [r.chunk for r in results]
        calls: list = []

        def search(self, emb, top_k=5, threshold=0.25, query_text=""):
            self.calls.append((top_k, threshold, query_text))
            return results[:top_k]

    async def fake_embed(text):
        return [1.0, 0.0]

    fake = FakeStore()
    monkeypatch.setattr(cl, "vector_store", fake)
    monkeypatch.setattr(cl.embedding_service, "embed", fake_embed)
    assert await cl.search_in_course("publish", "custom-library", top_k=1) == [(PUBLISH_CHUNK, 0.6)]
    assert await cl.search_in_course("publish", "custom-library") == [(PUBLISH_CHUNK, 0.6), (NPM_CHUNK, 0.5)]
    assert await cl.search_in_course("publish", "nope") == []
    assert fake.calls[0] == (3, 0.0, "publish")  # whole store ranked, then filtered


def test_player_facts_name_only_this_course():
    hit = cl.Hit(source="transcript", course_id=2, course_slug="custom-library", course_title="Build a Custom Library",
                 title="11.1 - Publishing using `np`", score=0.47, enrolled=False, text="run np",
                 lecture_id="custom-library-10-0", start_time=200, end_time=250, url="/course/2")
    lookup = cl.CourseLookup(case=cl.LookupCase.IN_COURSE_RELATED, hits=[hit],
                             enrolled_titles=["JavaScript Deep Dive", "React Performance Patterns"])
    facts = cl.render_facts(lookup, PLAYER)
    assert "CASE: IN_COURSE_RELATED" in facts
    assert "[THIS COURSE] 11.1 - Publishing using `np` @ 03:20" in facts
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
