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
