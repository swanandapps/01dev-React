"""In-lecture "this" questions: answer from what is on screen at the student's video position, the lecture so far,
and what the student already built earlier in the course — no course-wide search, no cards, no links elsewhere."""
import pytest

from app.models import TranscriptChunk
from app.retrieval import pipeline
from app.retrieval import understand as un
from app.services import course_lookup as cl
from app.services import lecture_context as lc
from app.services import tutor_agent

SLUG, COURSE = "custom-library", "Build a Custom Library"
L51 = "5.1 - Prototype, a Hero Turned Villain"


def _c(lid, title, n, start, end, text, summary="", keywords=(), slug=SLUG):
    return TranscriptChunk(chunk_id=f"{lid}-{n}", course_id=slug, course_title=COURSE, lecture_id=lid,
                           lecture_title=title, text=text, text_clean=text, start_time=start, end_time=end,
                           summary=summary, keywords=list(keywords))


V51 = [_c("custom-library-4-0", L51, i, s, s + 50, f"passage {i} of 5.1", summary=f"summary {i}",
          keywords=["prototype", f"kw{i}"]) for i, s in enumerate(range(0, 500, 50))]
EARLIER = _c("custom-library-2-5", "3.6 - Hacking Javascript's Prototype", 3, 240, 300,
             "we add String.prototype.s1 to every string", keywords=["String.prototype"])
LATER = _c("custom-library-10-0", "11.1 - Publishing using `np`", 1, 45, 100, "np publish")
OTHER = _c("react-perf-3-0", "4.1 - React.memo", 0, 0, 60, "memo", slug="react-perf")


# ---- which questions are about the screen ---------------------------------------------------
@pytest.mark.parametrize("q", ["give an example for this", "give me an example", "explain this",
                               "what does this mean?", "can you explain that again", "I don't get this part",
                               "what is he talking about here?"])
def test_screen_questions(q):
    assert un.about_the_screen(q)


@pytest.mark.parametrize("q", ["what is an IIFE?", "take me to ES modules", "what am I weak at?", "explain closures",
                               "give me an example of debounce", "how do I publish with np", ""])
def test_questions_with_their_own_topic_or_route_are_not_about_the_screen(q):
    assert not un.about_the_screen(q)


# ---- pure assembly -----------------------------------------------------------------------------
def test_on_screen_is_the_passage_at_the_position_plus_its_neighbours():
    got, now = lc.on_screen(V51, 160)
    assert [c.start_time for c in got] == [100, 150, 200] and now == 1


def test_on_screen_at_the_edges_and_past_the_end():
    got, now = lc.on_screen(V51, 0)
    assert [c.start_time for c in got] == [0, 50] and now == 0
    got, now = lc.on_screen(V51, 9999)
    assert [c.start_time for c in got] == [400, 450] and now == 1


def test_so_far_lists_summaries_of_earlier_passages_only():
    assert [c.start_time for c in lc.so_far(V51, before=150)] == [0, 50, 100]


def test_lecture_position_parses_position_ids():
    assert lc.lecture_pos("custom-library-4-0") == (4, 0) and lc.lecture_pos("weird") is None


async def test_earlier_passages_come_only_from_earlier_lectures_of_this_course(monkeypatch):
    seen = {}

    async def fake_search(q, scope, **kw):
        seen["q"], seen["scope"] = q, tuple(scope)
        return [pipeline.Candidate(chunk=c) for c in (LATER, OTHER, V51[2], EARLIER)]

    monkeypatch.setattr(pipeline, "search", fake_search)
    got = await lc.earlier_passages(SLUG, "custom-library-4-0", ["prototype", "security"])
    assert [c.chunk_id for c in got] == [EARLIER.chunk_id]
    assert seen["scope"] == (SLUG,) and "prototype" in seen["q"]


async def test_earlier_passages_never_fail_the_turn(monkeypatch):
    async def down(*a, **kw):
        raise RuntimeError("embeddings down")

    monkeypatch.setattr(pipeline, "search", down)
    assert await lc.earlier_passages(SLUG, "custom-library-4-0", ["prototype"]) == []


# ---- course_lookup ------------------------------------------------------------------------------
@pytest.fixture
def screen(monkeypatch):
    async def no_graded(*a, **kw):
        raise AssertionError("a 'this' question must not search the whole course")

    async def fake_earlier(slug, lecture_id, terms, k=2):
        return [EARLIER]

    async def no_enrollments(student_id):
        return set(), []

    monkeypatch.setattr(pipeline, "graded_search", no_graded)
    async def chunks(slug, title):
        return V51 if title == L51 else []

    monkeypatch.setattr(lc, "lecture_chunks", chunks)
    monkeypatch.setattr(lc, "earlier_passages", fake_earlier)
    monkeypatch.setattr(cl, "_enrollments", no_enrollments)


async def test_this_question_at_a_position_is_answered_from_the_screen(screen):
    scope = cl.ChatScope(course_slug=SLUG, lecture_title=L51, in_player=True, position=160)
    lk = await cl.course_lookup("give an example for this", "s1", scope)
    assert lk.case == cl.LookupCase.IN_LECTURE and lk.hits == []
    assert [h.start_time for h in lk.on_screen] == [100, 150, 200]
    assert [h.start_time for h in lk.lecture_so_far] == [0, 50]
    assert [h.title for h in lk.earlier] == ["3.6 - Hacking Javascript's Prototype"]
    assert cl.to_cards(lk) == []


async def test_this_question_without_a_position_uses_the_lecture_start(screen):
    scope = cl.ChatScope(course_slug=SLUG, lecture_title=L51, in_player=True)
    lk = await cl.course_lookup("explain this", "s1", scope)
    assert lk.case == cl.LookupCase.IN_LECTURE and [h.start_time for h in lk.on_screen] == [0, 50]


async def test_a_lecture_without_a_transcript_falls_back_to_the_normal_player_lookup(screen, monkeypatch):
    called = []

    async def graded(question, scope, **kw):
        called.append(question)
        return pipeline.RetrievalResult(pipeline.Outcome.NOT_COVERED, [], search_query=question)

    async def no_lecture(*a, **kw):
        return []

    monkeypatch.setattr(pipeline, "graded_search", graded)
    monkeypatch.setattr(cl, "search_in_lecture", no_lecture)
    scope = cl.ChatScope(course_slug=SLUG, lecture_title="9.9 - No transcript", in_player=True, position=30)
    lk = await cl.course_lookup("explain this", "s1", scope)
    assert lk.case == cl.LookupCase.IN_COURSE_NONE and called == ["explain this"]


async def test_a_topic_question_in_the_player_still_uses_the_course_search(screen, monkeypatch):
    called = []

    async def graded(question, scope, **kw):
        called.append(question)
        return pipeline.RetrievalResult(pipeline.Outcome.NOT_COVERED, [], search_query=question)

    async def no_lecture(*a, **kw):
        return []

    monkeypatch.setattr(pipeline, "graded_search", graded)
    monkeypatch.setattr(cl, "search_in_lecture", no_lecture)
    scope = cl.ChatScope(course_slug=SLUG, lecture_title=L51, in_player=True, position=160)
    await cl.course_lookup("what is an IIFE?", "s1", scope)
    assert called == ["what is an IIFE?"]


async def test_facts_lay_out_screen_lecture_so_far_and_earlier_work(screen):
    scope = cl.ChatScope(course_slug=SLUG, lecture_title=L51, in_player=True, position=160)
    lk = await cl.course_lookup("give an example for this", "s1", scope)
    facts = cl.render_facts(lk, scope, ["closures"])
    assert "CASE: IN_LECTURE" in facts and "Matches:" not in facts
    assert "ON SCREEN NOW" in facts and '[PLAYING] @ 02:30 "passage 3 of 5.1"' in facts
    assert '[just before] @ 01:40' in facts and '[just after] @ 03:20' in facts
    assert "THIS LECTURE SO FAR" in facts and "00:00 summary 0" in facts
    assert "EARLIER IN THE COURSE" in facts and "3.6 - Hacking Javascript's Prototype @ 04:00" in facts
    assert "String.prototype.s1" in facts and "Weak concepts in this course: closures" in facts
    assert "CURRENT LECTURE excerpt" not in facts


# ---- tools ------------------------------------------------------------------------------------------
def test_search_tool_is_withheld_on_screen_turns():
    names = {t.name for t in tutor_agent.tools_for(SLUG, allow_moment=False, allow_search=False)}
    assert "search_course_content" not in names and "find_moment" not in names
    assert "search_course_content" in {t.name for t in tutor_agent.tools_for(SLUG)}
