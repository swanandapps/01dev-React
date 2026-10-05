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
