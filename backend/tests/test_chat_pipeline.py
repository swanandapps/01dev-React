import pytest

from app.services import audit_service, chat_pipeline, course_lookup as cl, journey_service, memory_service, tutor_agent


@pytest.fixture
def wired(monkeypatch):
    calls = {"audit": [], "recorded": [], "lookup_q": [], "agent_q": []}

    async def log_event(**kw):
        calls["audit"].append(kw)
    async def memory_context(*a):
        return ""
    async def record_turn(student_id, slug, q, a):
        calls["recorded"].append((student_id, slug, q, a))
    async def weak(*a):
        return []
    async def lookup(question, student_id, scope=cl.ChatScope()):
        calls["lookup_q"].append(question)
        hit = cl.Hit(source="transcript", course_id=2, course_slug="custom-library",
                     course_title="Build a Custom Library", title="8.1 - The npm link command", score=0.6,
                     enrolled=False, text="npm link", lecture_id="custom-library-8-1", start_time=87, url="/course/2")
        return cl.CourseLookup(case=cl.LookupCase.NOT_ENROLLED_MATCH, hits=[hit], enrolled_titles=[])

    monkeypatch.setattr(audit_service, "log_event", log_event)
    monkeypatch.setattr(memory_service, "memory_context", memory_context)
    monkeypatch.setattr(memory_service, "record_turn", record_turn)
    monkeypatch.setattr(journey_service, "weak_concepts_for_course", weak)
    monkeypatch.setattr(chat_pipeline, "course_lookup", lookup)
    return calls


def _agent(monkeypatch, calls, events=None, raise_after_tokens=False):
    async def fake_stream(*, system_prompt, history, question, student_id, model=None):
        calls["agent_q"].append(question)
        calls["system"] = system_prompt
        for e in events or [{"type": "token", "value": "Short answer."}]:
            yield e
        if raise_after_tokens:
            raise RuntimeError("openai exploded: sk-secret")
    monkeypatch.setattr(tutor_agent, "stream_answer", fake_stream)


def _req(q="how do I publish an npm library"):
    return chat_pipeline.TurnRequest(question=q, student_id="alice", scope=cl.ChatScope(), history=[],
                                     memory_slug="all-courses")


async def test_order_sources_first_then_tokens_then_done(wired, monkeypatch):
    _agent(monkeypatch, wired)
    events = [e async for e in chat_pipeline.chat_turn(_req())]
    assert [e["type"] for e in events] == ["sources", "token", "done"]
    assert events[0]["sources"][0]["course_id"] == "custom-library"
    assert "CASE: NOT_ENROLLED_MATCH" in wired["system"]
    assert wired["recorded"] == [("alice", "all-courses", "how do I publish an npm library", "Short answer.")]


async def test_pii_is_scrubbed_everywhere(wired, monkeypatch):
    _agent(monkeypatch, wired)
    [e async for e in chat_pipeline.chat_turn(_req("email me at bob@example.com about npm"))]
    for q in (wired["lookup_q"][0], wired["agent_q"][0], wired["audit"][0]["question"], wired["recorded"][0][2]):
        assert "bob@example.com" not in q


async def test_agent_failure_sends_generic_error_and_saves_nothing(wired, monkeypatch):
    _agent(monkeypatch, wired, raise_after_tokens=True)
    events = [e async for e in chat_pipeline.chat_turn(_req())]
    assert events[-1]["type"] == "error"
    assert "sk-secret" not in events[-1]["message"]
    assert wired["recorded"] == []


async def test_duplicate_cards_from_follow_up_search_are_not_repeated(wired, monkeypatch):
    dup = {"course_id": "custom-library", "lecture_id": "custom-library-8-1", "start_time": 87}
    new = {"course_id": "react-perf", "lecture_id": "react-perf-4-1", "start_time": 30}
    _agent(monkeypatch, wired, events=[{"type": "token", "value": "x"}, {"type": "cards", "cards": [dup, new]}])
    events = [e async for e in chat_pipeline.chat_turn(_req())]
    later = [e for e in events if e["type"] == "sources"][1:]
    assert len(later) == 1 and later[0]["sources"] == [new]
