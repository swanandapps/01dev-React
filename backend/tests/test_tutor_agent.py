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

    async def fake_metrics(user_id):
        seen.append(user_id)
        return {"quizzes": 3}

    monkeypatch.setattr(journey_service, "get_metrics", fake_metrics)
    model = FakeToolModel(messages=iter([
        AIMessage("", tool_calls=[{"name": "get_learning_metrics", "args": {"student_id": "victim"}, "id": "c1"}]),
        AIMessage("You have taken 3 quizzes."),
    ]))
    events = await _collect(tutor_agent.stream_answer(
        system_prompt="sys", history=[], question="how many quizzes?", student_id="alice", model=model))
    assert seen == ["alice"]
    assert "".join(e["value"] for e in events if e["type"] == "token") == "You have taken 3 quizzes."


async def test_follow_up_search_yields_cards(monkeypatch):
    from app.models import SearchResult, TranscriptChunk
    chunk = TranscriptChunk(chunk_id="c", course_id="react-perf", course_title="React Performance Patterns",
                            lecture_id="l", lecture_title="4.1 - React.memo and useCallback", text="memo",
                            start_time=30, end_time=60)

    async def fake_retrieve(q, top_k=5):
        return [SearchResult(chunk=chunk, score=0.7)]

    monkeypatch.setattr(grounding, "retrieve", fake_retrieve)
    from app.services import enrollment_service

    async def no_enrollments(uid):
        return []

    monkeypatch.setattr(enrollment_service, "get_enrolled_courses", no_enrollments)  # else a real DB read
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


async def test_follow_up_search_labels_each_excerpt_by_enrollment(monkeypatch):
    from types import SimpleNamespace

    from app.models import SearchResult, TranscriptChunk
    from app.services import catalog_service, enrollment_service

    def chunk(slug, title):
        return TranscriptChunk(chunk_id=slug, course_id=slug, course_title=title, lecture_id="l",
                               lecture_title="1.1 - Intro", text="body", start_time=0, end_time=30)

    async def fake_retrieve(q, top_k=5):
        return [SearchResult(chunk=chunk("react-perf", "React Performance Patterns"), score=0.8),
                SearchResult(chunk=chunk("js-engine", "JavaScript Engine Internals"), score=0.6)]

    async def fake_enrolled(student_id):
        assert student_id == "alice"
        return [{"id": 3, "title": "React Performance Patterns"}]

    monkeypatch.setattr(grounding, "retrieve", fake_retrieve)
    monkeypatch.setattr(enrollment_service, "get_enrolled_courses", fake_enrolled)
    monkeypatch.setattr(catalog_service, "by_slug", lambda s: {"react-perf": {"id": 3}, "js-engine": {"id": 7}}.get(s))

    content, cards = await tutor_agent.search_course_content.coroutine(
        query="memo", runtime=SimpleNamespace(context=tutor_agent.ChatContext(student_id="alice")))
    lines = content.splitlines()
    assert lines[0].startswith("[ENROLLED] React Performance Patterns")
    assert lines[1].startswith("[NOT ENROLLED] JavaScript Engine Internals")
    assert [c["course_id"] for c in cards] == ["react-perf", "js-engine"]
    assert "student_id" not in _schema("search_course_content")


async def test_follow_up_search_enrollment_failure_labels_all_not_enrolled(monkeypatch):
    from types import SimpleNamespace

    from app.models import SearchResult, TranscriptChunk
    from app.services import enrollment_service

    c = TranscriptChunk(chunk_id="c", course_id="react-perf", course_title="React Performance Patterns",
                        lecture_id="l", lecture_title="1.1 - Intro", text="body", start_time=0, end_time=30)

    async def fake_retrieve(q, top_k=5):
        return [SearchResult(chunk=c, score=0.8)]

    async def broken(student_id):
        raise RuntimeError("db down")

    monkeypatch.setattr(grounding, "retrieve", fake_retrieve)
    monkeypatch.setattr(enrollment_service, "get_enrolled_courses", broken)
    content, _ = await tutor_agent.search_course_content.coroutine(
        query="memo", runtime=SimpleNamespace(context=tutor_agent.ChatContext(student_id="alice")))
    assert content.startswith("[NOT ENROLLED] ")


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


async def test_follow_up_search_drops_results_below_the_transcript_threshold(monkeypatch):
    from types import SimpleNamespace

    from app.models import SearchResult, TranscriptChunk
    from app.services import course_lookup, enrollment_service

    def chunk(cid, lecture):
        return TranscriptChunk(chunk_id=cid, course_id="react-perf", course_title="React Performance Patterns",
                               lecture_id=cid, lecture_title=lecture, text="body", start_time=0, end_time=30)

    async def fake_retrieve(q, top_k=5):
        return [SearchResult(chunk=chunk("weak", "9.9 - Unrelated"), score=0.30),
                SearchResult(chunk=chunk("good", "4.1 - React.memo"), score=0.70)]

    async def no_enrollments(student_id):
        return []

    assert 0.30 < course_lookup.TRANSCRIPT_THRESHOLD <= 0.70
    monkeypatch.setattr(grounding, "retrieve", fake_retrieve)
    monkeypatch.setattr(enrollment_service, "get_enrolled_courses", no_enrollments)
    runtime = SimpleNamespace(context=tutor_agent.ChatContext(student_id="alice"))
    content, cards = await tutor_agent.search_course_content.coroutine(query="memo", runtime=runtime)
    assert [c["lecture_title"] for c in cards] == ["4.1 - React.memo"]
    assert "9.9 - Unrelated" not in content and "4.1 - React.memo" in content

    async def only_weak(q, top_k=5):
        return [SearchResult(chunk=chunk("weak", "9.9 - Unrelated"), score=0.30)]
    monkeypatch.setattr(grounding, "retrieve", only_weak)
    assert await tutor_agent.search_course_content.coroutine(query="memo", runtime=runtime) == \
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


def _stub(monkeypatch, *, titles=None, course=None):
    from app.services import course_lookup

    async def fake_titles(q, slug):
        return titles or {}

    async def fake_course(q, slug, top_k=8):
        return course or []

    monkeypatch.setattr(course_lookup, "_title_scores", fake_titles)
    monkeypatch.setattr(course_lookup, "search_in_course", fake_course)


def test_find_moment_is_bound_only_in_the_player():
    assert tutor_agent.find_moment not in tutor_agent.TOOLS
    assert tutor_agent.tools_for(None) == tutor_agent.TOOLS
    assert tutor_agent.tools_for("custom-library") == tutor_agent.TOOLS + [tutor_agent.find_moment]


def test_find_moment_schema_takes_only_what():
    props = convert_to_openai_tool(tutor_agent.find_moment)["function"]["parameters"]["properties"]
    assert list(props) == ["what"]


async def test_find_moment_returns_the_best_in_course_chunk_above_the_moment_threshold(monkeypatch):
    import json
    _stub(monkeypatch, titles={LECTURE: 0.3}, course=[(_moment_chunk(), 0.66)])
    content, artifact = await tutor_agent.find_moment.coroutine(what="publish with np", runtime=_player_runtime())
    body = json.loads(content)
    assert (body["lecture_title"], body["start_time"], body["end_time"], body["score"]) == (LECTURE, 200, 255, 0.66)
    assert 0 < len(body["excerpt"]) <= 400
    assert artifact == {"course_slug": "custom-library", "lecture_title": LECTURE, "start_time": 200}


async def test_find_moment_between_related_and_moment_threshold_is_not_found(monkeypatch):
    _stub(monkeypatch, titles={LECTURE: 0.3}, course=[(_moment_chunk(), 0.406)])  # "event loop" case
    assert await tutor_agent.find_moment.coroutine(what="x", runtime=_player_runtime()) == ('{"found": false}', None)


async def test_find_moment_ranks_lectures_by_chunk_or_title_minus_offset(monkeypatch):
    A = "8.1 - The `npm link` command"
    _stub(monkeypatch, titles={A: 0.68, LECTURE: 0.44},
          course=[(_moment_chunk(lecture=A, start=484), 0.60), (_moment_chunk(start=92), 0.685)])
    content, artifact = await tutor_agent.find_moment.coroutine(what="npm publish", runtime=_player_runtime())
    assert artifact == {"course_slug": "custom-library", "lecture_title": LECTURE, "start_time": 92}


async def test_find_moment_title_only_lecture_starts_at_zero(monkeypatch):
    import json
    _stub(monkeypatch, titles={LECTURE: 0.7}, course=[(_moment_chunk(start=120), 0.2), (_moment_chunk(start=15), 0.1)])
    content, artifact = await tutor_agent.find_moment.coroutine(what="np", runtime=_player_runtime())
    assert artifact == {"course_slug": "custom-library", "lecture_title": LECTURE, "start_time": 0}
    assert json.loads(content)["score"] == 0.2  # chunk score, not the title's
    # the jump starts at 0, so the range ends where the lecture's opening chunk ends (15 + 55), not the matched chunk's
    assert json.loads(content)["start_time"] == 0 and json.loads(content)["end_time"] == 70


async def test_find_moment_weak_title_and_weak_chunk_is_not_found(monkeypatch):
    _stub(monkeypatch, titles={LECTURE: 0.55}, course=[(_moment_chunk(), 0.44)])
    assert await tutor_agent.find_moment.coroutine(what="x", runtime=_player_runtime()) == ('{"found": false}', None)


async def test_find_moment_never_returns_another_course(monkeypatch):
    _stub(monkeypatch, course=[(_moment_chunk(course="react-perf", lecture="4.1 - React.memo"), 0.9)])
    assert await tutor_agent.find_moment.coroutine(what="x", runtime=_player_runtime()) == ('{"found": false}', None)


async def test_find_moment_without_a_course_in_context_is_not_found(monkeypatch):
    from types import SimpleNamespace
    from app.services import course_lookup

    async def boom(*a, **k):
        raise AssertionError("no course → no search")

    monkeypatch.setattr(course_lookup, "search_in_course", boom)
    monkeypatch.setattr(course_lookup, "_title_scores", boom)
    runtime = SimpleNamespace(context=tutor_agent.ChatContext(student_id="alice"))
    assert await tutor_agent.find_moment.coroutine(what="x", runtime=runtime) == ('{"found": false}', None)


async def test_player_stream_yields_a_moment_event_from_find_moment(monkeypatch):
    _stub(monkeypatch, course=[(_moment_chunk(), 0.7)])
    model = FakeToolModel(messages=iter([
        AIMessage("", tool_calls=[{"name": "find_moment", "args": {"what": "publish with np"}, "id": "c1"}]),
        AIMessage("It's at 03:20 in 11.1."),
    ]))
    events = await _collect(tutor_agent.stream_answer(
        system_prompt="sys", history=[], question="take me to where you publish", student_id="alice",
        model=model, in_course="custom-library"))
    assert [e for e in events if e["type"] == "moment"] == [{"type": "moment", "moment": {
        "course_slug": "custom-library", "lecture_title": LECTURE, "start_time": 200}}]
    assert not [e for e in events if e["type"] == "cards"]
    assert "".join(e["value"] for e in events if e["type"] == "token").endswith("It's at 03:20 in 11.1.")


async def test_ask_stream_has_no_find_moment(monkeypatch):
    from app.services import course_lookup

    async def boom(*a, **k):
        raise AssertionError("find_moment must not run outside the player")

    monkeypatch.setattr(course_lookup, "search_in_course", boom)
    model = FakeToolModel(messages=iter([
        AIMessage("", tool_calls=[{"name": "find_moment", "args": {"what": "publish"}, "id": "c1"}]),
        AIMessage("ok"),
    ]))
    events = await _collect(tutor_agent.stream_answer(
        system_prompt="sys", history=[], question="take me there", student_id="alice", model=model))
    assert not [e for e in events if e["type"] == "moment"]


async def test_follow_up_search_in_the_player_stays_in_this_course(monkeypatch):
    from app.services import course_lookup

    async def all_courses(q, top_k=5):
        raise AssertionError("the player's follow-up search must not search every course")

    async def fake_search(query, course_slug, top_k=8):
        assert course_slug == "custom-library"
        return [(_moment_chunk(), 0.7), (_moment_chunk(lecture="8.1 - The `npm link` command", start=10), 0.30)]

    monkeypatch.setattr(grounding, "retrieve", all_courses)
    monkeypatch.setattr(course_lookup, "search_in_course", fake_search)
    content, cards = await tutor_agent.search_course_content.coroutine(query="np", runtime=_player_runtime())
    assert [c["lecture_title"] for c in cards] == [LECTURE]
    assert "[THIS COURSE]" in content and "ENROLLED" not in content
