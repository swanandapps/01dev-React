from langchain_core.messages import AIMessage
from langchain_core.utils.function_calling import convert_to_openai_tool

from app.services import grounding, journey_service, tutor_agent
from tests.fakes import FakeToolModel


def test_no_tool_exposes_student_id_to_the_model():
    for t in tutor_agent.TOOLS:
        props = convert_to_openai_tool(t)["function"]["parameters"].get("properties", {})
        assert "student_id" not in props, t.name
        assert "runtime" not in props, t.name


async def _collect(gen):
    return [e async for e in gen]


async def test_tool_uses_context_student_not_model_supplied_id(monkeypatch):
    seen = []

    async def fake_progress(user_id, course_slug=None):
        seen.append(user_id)
        return {"scope": "all your courses", "metrics": {"quizzes": 3}, "recent_quizzes": []}

    monkeypatch.setattr(journey_service, "get_progress", fake_progress)
    model = FakeToolModel(messages=iter([
        AIMessage("", tool_calls=[{"name": "get_learning_metrics", "args": {"student_id": "victim"}, "id": "c1"}]),
        AIMessage("You have taken 3 quizzes."),
    ]))
    events = await _collect(tutor_agent.stream_answer(
        system_prompt="sys", history=[], question="how many quizzes?", student_id="alice", model=model))
    assert seen == ["alice"]
    assert "".join(e["value"] for e in events if e["type"] == "token") == "You have taken 3 quizzes."


def _stub(monkeypatch, graded=(), calls=None):
    """graded: [(chunk, grade, cosine)] as the reranked pipeline returns them (fused order)."""
    from app.retrieval import pipeline
    from app.retrieval.base import Candidate
    from app.retrieval.rerank import Graded, decide

    async def fake_graded(question, scope, **kw):
        if calls is not None:
            calls.append((question, tuple(scope), kw))
        gs = [Graded(Candidate(chunk=c, vec_score=s), g, "r") for c, g, s in graded if c.course_id in scope]
        outcome, ordered = decide(gs)
        return pipeline.RetrievalResult(outcome, ordered, intent=kw.get("intent", "explain"), search_query=question)

    monkeypatch.setattr(pipeline, "graded_search", fake_graded)


async def test_follow_up_search_yields_cards(monkeypatch):
    from app.models import TranscriptChunk
    chunk = TranscriptChunk(chunk_id="c", course_id="custom-library", course_title="Build a Custom Library",
                            lecture_id="custom-library-3-1", lecture_title="4.1 - React.memo and useCallback", text="memo",
                            start_time=30, end_time=60)

    _stub(monkeypatch, [(chunk, "answers", 0.7)])
    from app.services import enrollment_service

    async def enrolled_2(uid):
        return [{"id": 2, "title": "Build a Custom Library"}]  # F1: Ask cites only launched+enrolled

    monkeypatch.setattr(enrollment_service, "get_enrolled_courses", enrolled_2)
    model = FakeToolModel(messages=iter([
        AIMessage("", tool_calls=[{"name": "search_course_content", "args": {"query": "memo"}, "id": "c1"}]),
        AIMessage("Memo skips re-renders."),
    ]))
    events = await _collect(tutor_agent.stream_answer(
        system_prompt="sys", history=[{"role": "user", "content": "hi"}, {"role": "assistant", "content": "hello"}],
        question="memo?", student_id="alice", model=model))
    cards = [c for e in events if e["type"] == "cards" for c in e["cards"]]
    assert cards and cards[0]["lecture_title"] == "4.1 - React.memo and useCallback"


def _schema(name):
    t = next(t for t in tutor_agent.TOOLS if t.name == name)
    return convert_to_openai_tool(t)["function"]["parameters"]["properties"]


def test_record_skill_observation_schema_constrains_confidence_and_describes_args():
    props = _schema("record_skill_observation")
    assert props["confidence"]["enum"] == ["weak", "developing", "strong"]
    assert props["concept"].get("description")
    assert props["course_id"].get("description")
    assert props["note"].get("description")


def _ask_tool_setup(monkeypatch, enrolled_ids, rows, grade="answers"):
    """rows: [(slug, course_title, lecture_id, lecture_title, score)] the graded pipeline can return."""
    from types import SimpleNamespace

    from app.models import TranscriptChunk
    from app.services import enrollment_service

    chunks = [(TranscriptChunk(chunk_id=f"{s}-{i}", course_id=s, course_title=t, lecture_id=lid, lecture_title=lt,
                               text="body", start_time=87, end_time=117), grade, sc)
              for i, (s, t, lid, lt, sc) in enumerate(rows)]
    _stub(monkeypatch, chunks)

    async def fake_enrolled(student_id):
        assert student_id == "alice"
        return [{"id": i, "title": f"course {i}"} for i in enrolled_ids]

    monkeypatch.setattr(enrollment_service, "get_enrolled_courses", fake_enrolled)
    return SimpleNamespace(context=tutor_agent.ChatContext(student_id="alice"))


ROWS = [("custom-library", "Build a Custom Library", "custom-library-7-0", "8.1 - The npm link command", 0.8),
        ("react-perf", "React Performance Patterns", "react-perf-1-0", "2.1 - memo", 0.7),
        ("js-engine", "JavaScript Engine Internals", "js-engine-0-0", "1.1 - Intro", 0.6)]


async def test_ask_tool_for_an_unlaunched_only_student_returns_nothing(monkeypatch):
    # F1: enrolled in 9 and 11 (neither launched) -> no result text and no card, whatever retrieve finds.
    rt = _ask_tool_setup(monkeypatch, [9, 11], ROWS)
    content, cards = await tutor_agent.search_course_content.coroutine(query="memo", runtime=rt)
    assert content == "No matching course content." and cards == []


async def test_ask_tool_keeps_only_launched_owned_courses_with_deep_links(monkeypatch):
    rt = _ask_tool_setup(monkeypatch, [2, 11], ROWS)   # 2 launched+owned; 11 owned but unlaunched; js-engine unowned
    content, cards = await tutor_agent.search_course_content.coroutine(query="npm", runtime=rt)
    assert [c["course_id"] for c in cards] == ["custom-library"]
    assert cards[0]["url"] == "/course/2?chapter=7&sub=0&t=87" and (cards[0]["chapter"], cards[0]["sub"]) == (7, 0)
    assert "the01.dev/course/2?chapter=7&sub=0&t=87" in content
    assert "React Performance" not in content and "JavaScript Engine" not in content
    assert "ENROLLED" not in content


async def test_ask_tool_enrollment_failure_cites_nothing(monkeypatch):
    from app.services import enrollment_service

    rt = _ask_tool_setup(monkeypatch, [2], ROWS)

    async def broken(student_id):
        raise RuntimeError("db down")

    monkeypatch.setattr(enrollment_service, "get_enrolled_courses", broken)
    assert await tutor_agent.search_course_content.coroutine(query="npm", runtime=rt) == ("No matching course content.", [])


async def test_player_tool_path_is_unchanged_by_the_ask_policy(monkeypatch):
    from types import SimpleNamespace

    from app.models import TranscriptChunk

    chunk = TranscriptChunk(chunk_id="c", course_id="react-perf", course_title="React Performance Patterns",
                            lecture_id="react-perf-1-0", lecture_title="2.1 - memo", text="body",
                            start_time=87, end_time=117)

    _stub(monkeypatch, [(chunk, "answers", 0.8)])
    rt = SimpleNamespace(context=tutor_agent.ChatContext(student_id="alice", in_course="react-perf"))
    content, cards = await tutor_agent.search_course_content.coroutine(query="memo", runtime=rt)  # unlaunched, unowned: still answers
    assert content.startswith("[THIS COURSE] React Performance Patterns → 2.1 - memo @ 01:27")
    assert [c["course_id"] for c in cards] == ["react-perf"]


async def test_write_tool_uses_context_student_not_model_supplied_id(monkeypatch):
    from app.services import skill_graph_service
    seen = []

    async def fake_record(student_id, course_id, concept, confidence, note):
        seen.append(student_id)
        return {"ok": True}

    monkeypatch.setattr(skill_graph_service, "record_observation", fake_record)
    model = FakeToolModel(messages=iter([
        AIMessage("", tool_calls=[{"name": "record_skill_observation", "id": "c1", "args": {
            "student_id": "victim", "concept": "react-memo", "course_id": "react-perf",
            "confidence": "strong", "note": "Explained memo unprompted."}}]),
        AIMessage("Noted."),
    ]))
    await _collect(tutor_agent.stream_answer(
        system_prompt="sys", history=[], question="memo skips re-renders", student_id="alice", model=model))
    assert seen == ["alice"]


async def test_record_skill_observation_returns_error_json_instead_of_raising(monkeypatch):
    import json
    from types import SimpleNamespace

    from app.services import skill_graph_service

    async def rejecting(*args):
        raise ValueError("confidence must be one of weak/developing/strong")

    monkeypatch.setattr(skill_graph_service, "record_observation", rejecting)
    out = await tutor_agent.record_skill_observation.coroutine(
        concept="react-memo", course_id="react-perf", confidence="strong", note="n",
        runtime=SimpleNamespace(context=tutor_agent.ChatContext(student_id="alice")))
    assert json.loads(out) == {"error": "confidence must be one of weak/developing/strong"}


async def test_follow_up_search_cites_only_answers_and_partial(monkeypatch):
    rt = _ask_tool_setup(monkeypatch, [2], [])
    from app.models import TranscriptChunk

    def chunk(cid, lecture):
        return TranscriptChunk(chunk_id=cid, course_id="custom-library", course_title="Build a Custom Library",
                               lecture_id=f"custom-library-{cid}", lecture_title=lecture, text="body",
                               start_time=0, end_time=30)

    _stub(monkeypatch, [(chunk("1-0", "9.9 - Unrelated"), "related", 0.3), (chunk("2-0", "4.1 - Close"), "partial", 0.5),
                        (chunk("3-0", "5.1 - Exact"), "answers", 0.7)])
    content, cards = await tutor_agent.search_course_content.coroutine(query="memo", runtime=rt)
    assert [c["lecture_title"] for c in cards] == ["5.1 - Exact", "4.1 - Close"]
    assert "9.9 - Unrelated" not in content and "4.1 - Close @ 00:00 (touches on it)" in content
    _stub(monkeypatch, [(chunk("1-0", "9.9 - Unrelated"), "related", 0.3)])
    assert await tutor_agent.search_course_content.coroutine(query="memo", runtime=rt) == \
        ("No matching course content.", [])


async def test_vague_question_yields_no_citable_content_and_no_cards(monkeypatch):
    """Reranker grades everything n/related for "what does this mean?": the tool must cite nothing."""
    for runtime in (_ask_tool_setup(monkeypatch, [2], []), _player_runtime()):
        from app.models import TranscriptChunk
        c = TranscriptChunk(chunk_id="v", course_id="custom-library", course_title="Build a Custom Library",
                            lecture_id="custom-library-1-0", lecture_title="2.1 - Intro", text="body",
                            start_time=5, end_time=30)
        _stub(monkeypatch, [(c, "related", 0.5), (c, "no", 0.4)])
        assert await tutor_agent.search_course_content.coroutine(query="what does this mean?", runtime=runtime) == \
            ("No matching course content.", [])


async def test_text_before_and_after_a_tool_call_is_separated(monkeypatch):
    async def fake_metrics(user_id):
        return {"quizzes": 3}

    monkeypatch.setattr(journey_service, "get_metrics", fake_metrics)
    model = FakeToolModel(messages=iter([
        AIMessage("Let me check.", tool_calls=[{"name": "get_learning_metrics", "args": {}, "id": "c1"}]),
        AIMessage("You have taken 3 quizzes."),
    ]))
    events = await _collect(tutor_agent.stream_answer(
        system_prompt="sys", history=[], question="how many quizzes?", student_id="alice", model=model))
    assert "".join(e["value"] for e in events if e["type"] == "token") == "Let me check.\n\nYou have taken 3 quizzes."


def test_explain_concept_tool_hides_student_id_and_describes_concept():
    props = _schema("explain_concept")
    assert set(props) == {"concept"}
    assert props["concept"]["description"]


async def test_explain_concept_uses_context_student_not_model_supplied_id(monkeypatch):
    from app.services import concept_explain
    seen = []

    async def fake_explain(user_id, concept):
        seen.append((user_id, concept))
        return {"concept": concept, "attempts": 2, "correct": 1, "accuracy": 0.5,
                "sources": [], "merged_tags": []}

    monkeypatch.setattr(concept_explain, "explain_concept", fake_explain)
    model = FakeToolModel(messages=iter([
        AIMessage("", tool_calls=[{"name": "explain_concept", "id": "c1",
                                   "args": {"student_id": "victim", "concept": "react-memo"}}]),
        AIMessage("Because of two attempts."),
    ]))
    await _collect(tutor_agent.stream_answer(
        system_prompt="sys", history=[], question="why is memo my strong topic?",
        student_id="alice", model=model))
    assert seen == [("alice", "react-memo")]


async def test_explain_concept_tool_returns_json(monkeypatch):
    import json
    from types import SimpleNamespace

    from app.services import concept_explain

    async def fake_explain(user_id, concept):
        return {"concept": concept, "attempts": 0, "correct": 0, "accuracy": None,
                "sources": [], "merged_tags": []}

    monkeypatch.setattr(concept_explain, "explain_concept", fake_explain)
    out = await tutor_agent.explain_concept.coroutine(
        concept="react-memo",
        runtime=SimpleNamespace(context=tutor_agent.ChatContext(student_id="alice")))
    assert json.loads(out)["attempts"] == 0


# ---- find_moment (player only) — spec §3.3 + amendment-relevance.md item 7 ------

LECTURE = "11.1 - Publishing using `np`"


def _moment_chunk(course="custom-library", lecture=LECTURE, start=200):
    from app.models import TranscriptChunk
    return TranscriptChunk(chunk_id=f"{course}-10-0-3", course_id=course, course_title="Build a Custom Library",
                           lecture_id=f"{course}-10-0", lecture_title=lecture, text="now run np " * 60,
                           start_time=start, end_time=start + 55)


def _player_runtime(slug="custom-library"):
    from types import SimpleNamespace
    return SimpleNamespace(context=tutor_agent.ChatContext(student_id="alice", in_course=slug))


def test_find_moment_is_bound_only_in_the_player():
    assert tutor_agent.find_moment not in tutor_agent.TOOLS
    assert tutor_agent.tools_for(None) == tutor_agent.TOOLS
    assert tutor_agent.tools_for("custom-library") == tutor_agent.TOOLS                  # not gated open: no find_moment
    assert tutor_agent.tools_for("custom-library", allow_moment=True) == tutor_agent.TOOLS + [tutor_agent.find_moment]
    assert tutor_agent.tools_for(None, allow_moment=True) == tutor_agent.TOOLS


def test_find_moment_schema_takes_only_what():
    props = convert_to_openai_tool(tutor_agent.find_moment)["function"]["parameters"]["properties"]
    assert list(props) == ["what"]


async def test_find_moment_returns_the_best_answers_chunk_and_says_it_is_navigation(monkeypatch):
    import json
    calls = []
    _stub(monkeypatch, [(_moment_chunk(start=50), "partial", 0.5), (_moment_chunk(), "answers", 0.66)], calls)
    content, artifact = await tutor_agent.find_moment.coroutine(what="publish with np", runtime=_player_runtime())
    body = json.loads(content)
    assert (body["lecture_title"], body["start_time"], body["end_time"], body["score"]) == (LECTURE, 200, 255, 0.66)
    assert 0 < len(body["excerpt"]) <= 400
    assert artifact == {"course_slug": "custom-library", "lecture_title": LECTURE, "start_time": 200}
    assert calls[0][:2] == ("publish with np", ("custom-library",)) and calls[0][2]["intent"] == "navigate"


async def test_find_moment_falls_back_to_the_best_partial_chunk(monkeypatch):
    _stub(monkeypatch, [(_moment_chunk(start=50), "related", 0.6), (_moment_chunk(start=90), "partial", 0.42)])
    _, artifact = await tutor_agent.find_moment.coroutine(what="virtualize the table", runtime=_player_runtime())
    assert artifact["start_time"] == 90


async def test_find_moment_among_answers_prefers_the_lecture_whose_title_matches_the_phrase(monkeypatch):
    other = _moment_chunk(lecture="8.2 - Testing Our NPM Package", start=184)
    _stub(monkeypatch, [(other, "answers", 0.60), (_moment_chunk(start=45), "answers", 0.52)])
    _, artifact = await tutor_agent.find_moment.coroutine(what="publishing", runtime=_player_runtime())
    assert (artifact["lecture_title"], artifact["start_time"]) == (LECTURE, 45)


async def test_find_moment_title_matched_partial_never_beats_a_non_title_answers(monkeypatch):
    other = _moment_chunk(lecture="8.2 - Testing Our NPM Package", start=184)
    _stub(monkeypatch, [(_moment_chunk(start=45), "partial", 0.7), (other, "answers", 0.4)])
    _, artifact = await tutor_agent.find_moment.coroutine(what="publishing", runtime=_player_runtime())
    assert (artifact["lecture_title"], artifact["start_time"]) == ("8.2 - Testing Our NPM Package", 184)


async def test_find_moment_title_match_beats_cosine_and_non_title_chunks_order_by_cosine(monkeypatch):
    a = _moment_chunk(lecture="8.2 - Testing Our NPM Package", start=184)
    b = _moment_chunk(lecture="6.5 - IIFE, To The Rescue", start=9)
    _stub(monkeypatch, [(a, "answers", 0.60), (b, "answers", 0.65), (_moment_chunk(start=45), "answers", 0.50)])
    _, artifact = await tutor_agent.find_moment.coroutine(what="publishing", runtime=_player_runtime())
    assert artifact["start_time"] == 45                      # title-matched, though lowest cosine
    _stub(monkeypatch, [(a, "answers", 0.60), (b, "answers", 0.65)])
    _, artifact = await tutor_agent.find_moment.coroutine(what="publishing", runtime=_player_runtime())
    assert artifact["lecture_title"] == "6.5 - IIFE, To The Rescue"   # neither matches: highest cosine


async def test_search_course_content_text_uses_the_clean_transcript(monkeypatch):
    c = _moment_chunk()
    c.text, c.text_clean = "raw uh text", "clean text"
    _stub(monkeypatch, [(c, "answers", 0.7)])
    content, _ = await tutor_agent.search_course_content.coroutine(query="np", runtime=_player_runtime())
    assert "clean text" in content and "raw uh text" not in content


async def test_find_moment_related_only_is_not_found(monkeypatch):
    _stub(monkeypatch, [(_moment_chunk(), "related", 0.5)])
    assert await tutor_agent.find_moment.coroutine(what="x", runtime=_player_runtime()) == ('{"found": false}', None)


async def test_find_moment_never_returns_another_course(monkeypatch):
    other = _moment_chunk(course="react-perf", lecture="4.1 - React.memo")

    async def leaky(question, scope, **kw):        # even if a backend leaked another course's chunk
        from app.retrieval import pipeline
        from app.retrieval.base import Candidate
        from app.retrieval.rerank import Graded, Outcome
        return pipeline.RetrievalResult(Outcome.COVERED, [Graded(Candidate(chunk=other, vec_score=0.9), "answers", "r")])

    from app.retrieval import pipeline
    monkeypatch.setattr(pipeline, "graded_search", leaky)
    assert await tutor_agent.find_moment.coroutine(what="x", runtime=_player_runtime()) == ('{"found": false}', None)


async def test_find_moment_without_a_course_in_context_is_not_found(monkeypatch):
    from types import SimpleNamespace
    from app.retrieval import pipeline

    async def boom(*a, **k):
        raise AssertionError("no course → no search")

    monkeypatch.setattr(pipeline, "graded_search", boom)
    runtime = SimpleNamespace(context=tutor_agent.ChatContext(student_id="alice"))
    assert await tutor_agent.find_moment.coroutine(what="x", runtime=runtime) == ('{"found": false}', None)


async def test_player_stream_yields_a_moment_event_from_find_moment(monkeypatch):
    _stub(monkeypatch, [(_moment_chunk(), "answers", 0.7)])
    model = FakeToolModel(messages=iter([
        AIMessage("", tool_calls=[{"name": "find_moment", "args": {"what": "publish with np"}, "id": "c1"}]),
        AIMessage("It's at 03:20 in 11.1."),
    ]))
    events = await _collect(tutor_agent.stream_answer(
        system_prompt="sys", history=[], question="take me to where you publish", student_id="alice",
        model=model, in_course="custom-library", allow_moment=True))
    assert [e for e in events if e["type"] == "moment"] == [{"type": "moment", "moment": {
        "course_slug": "custom-library", "lecture_title": LECTURE, "start_time": 200}}]
    assert not [e for e in events if e["type"] == "cards"]
    assert "".join(e["value"] for e in events if e["type"] == "token").endswith("It's at 03:20 in 11.1.")


async def test_ask_stream_has_no_find_moment(monkeypatch):
    from app.retrieval import pipeline

    async def boom(*a, **k):
        raise AssertionError("find_moment must not run outside the player")

    monkeypatch.setattr(pipeline, "graded_search", boom)
    model = FakeToolModel(messages=iter([
        AIMessage("", tool_calls=[{"name": "find_moment", "args": {"what": "publish"}, "id": "c1"}]),
        AIMessage("ok"),
    ]))
    events = await _collect(tutor_agent.stream_answer(
        system_prompt="sys", history=[], question="take me there", student_id="alice", model=model))
    assert not [e for e in events if e["type"] == "moment"]


async def test_follow_up_search_in_the_player_stays_in_this_course(monkeypatch):
    calls = []
    _stub(monkeypatch, [(_moment_chunk(), "answers", 0.7),
                        (_moment_chunk(lecture="8.1 - The `npm link` command", start=10), "related", 0.3)], calls)
    content, cards = await tutor_agent.search_course_content.coroutine(query="np", runtime=_player_runtime())
    assert calls[0][1] == ("custom-library",)
    assert [c["lecture_title"] for c in cards] == [LECTURE]
    assert "[THIS COURSE]" in content and "ENROLLED" not in content
