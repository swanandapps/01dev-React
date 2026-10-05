import pytest

from app.services import (audit_service, chat_pipeline, context_builder, course_lookup as cl, journey_service,
                          memory_service, tutor_agent)


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
        calls["history"] = history
        for e in events or [{"type": "token", "value": "Short answer."}]:
            yield e
        if raise_after_tokens:
            raise RuntimeError("openai exploded: sk-secret")
    monkeypatch.setattr(tutor_agent, "stream_answer", fake_stream)


def _req(q="how do I publish an npm library", history=None):
    return chat_pipeline.TurnRequest(question=q, student_id="alice", scope=cl.ChatScope(), history=history or [],
                                     memory_slug="all-courses")


async def test_order_sources_first_then_tokens_then_done(wired, monkeypatch):
    answer = "Short answer. See the01.dev/course/2."
    _agent(monkeypatch, wired, events=[{"type": "token", "value": answer}])
    events = [e async for e in chat_pipeline.chat_turn(_req())]
    assert [e["type"] for e in events] == ["sources", "token", "done"]
    assert events[0]["sources"][0]["course_id"] == "custom-library"
    assert "CASE: NOT_ENROLLED_MATCH" in wired["system"]
    assert wired["recorded"] == [("alice", "all-courses", "how do I publish an npm library", answer)]


POINTER = ("\n\nThis is covered in depth in Build a Custom Library → 8.1 - The npm link command. "
           "You're not enrolled in it yet; you can find it at the01.dev/course/2.")


async def test_not_enrolled_answer_without_the_course_url_gets_the_pointer_appended(wired, monkeypatch):
    _agent(monkeypatch, wired)  # "Short answer." — no course url
    events = [e async for e in chat_pipeline.chat_turn(_req())]
    tokens = [e["value"] for e in events if e["type"] == "token"]
    assert tokens == ["Short answer.", POINTER]
    assert events[-1]["type"] == "done"
    assert wired["recorded"][0][3] == "Short answer." + POINTER


async def test_not_enrolled_answer_that_already_has_the_course_url_gets_no_pointer(wired, monkeypatch):
    _agent(monkeypatch, wired, events=[{"type": "token", "value": "Find it at the01."},
                                       {"type": "token", "value": "dev/course/2."}])
    events = [e async for e in chat_pipeline.chat_turn(_req())]
    assert [e["value"] for e in events if e["type"] == "token"] == ["Find it at the01.", "dev/course/2."]
    assert wired["recorded"][0][3] == "Find it at the01.dev/course/2."


@pytest.mark.parametrize("case,enrolled", [(cl.LookupCase.ENROLLED_MATCH, True), (cl.LookupCase.NO_MATCH, False)])
async def test_pointer_is_never_appended_outside_not_enrolled(wired, monkeypatch, case, enrolled):
    async def lookup(question, student_id, scope=cl.ChatScope()):
        hit = cl.Hit(source="transcript", course_id=2, course_slug="custom-library",
                     course_title="Build a Custom Library", title="8.1 - The npm link command", score=0.6,
                     enrolled=enrolled, text="npm link", url="/course/2")
        return cl.CourseLookup(case=case, hits=[hit] if case != cl.LookupCase.NO_MATCH else [], enrolled_titles=[])
    monkeypatch.setattr(chat_pipeline, "course_lookup", lookup)
    _agent(monkeypatch, wired)
    events = [e async for e in chat_pipeline.chat_turn(_req())]
    assert [e["value"] for e in events if e["type"] == "token"] == ["Short answer."]
    assert wired["recorded"][0][3] == "Short answer."


async def test_pii_is_scrubbed_everywhere(wired, monkeypatch):
    _agent(monkeypatch, wired)
    history = [{"role": "user", "content": "I'm carol@example.com"}, {"role": "assistant", "content": "Hi!"}]
    [e async for e in chat_pipeline.chat_turn(_req("email me at bob@example.com about npm", history=history))]
    for q in (wired["lookup_q"][0], wired["agent_q"][0], wired["audit"][0]["question"], wired["recorded"][0][2]):
        assert "bob@example.com" not in q
    assert wired["history"] and all("carol@example.com" not in t["content"] for t in wired["history"])


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
    sources = [e for e in events if e["type"] == "sources"]
    later = sources[1:]
    lookup_card = sources[0]["sources"][0]
    assert len(later) == 1 and later[0]["sources"] == [lookup_card, new]
    assert sum(1 for c in later[0]["sources"] if (c["course_id"], c["lecture_id"], c["start_time"])
               == (dup["course_id"], dup["lecture_id"], dup["start_time"])) == 1


async def test_lookup_failure_sends_only_a_generic_error(wired, monkeypatch):
    _agent(monkeypatch, wired)
    async def boom(*a, **kw):
        raise RuntimeError("embed down: sk-secret")
    monkeypatch.setattr(chat_pipeline, "course_lookup", boom)
    events = [e async for e in chat_pipeline.chat_turn(_req())]
    assert [e["type"] for e in events] == ["error"]
    assert "sk-secret" not in events[0]["message"]
    assert wired["recorded"] == [] and wired["agent_q"] == []


async def test_audit_failure_does_not_fail_the_turn(wired, monkeypatch):
    _agent(monkeypatch, wired, events=[{"type": "token", "value": "See the01.dev/course/2."}])
    async def boom(**kw):
        raise RuntimeError("audit store down")
    monkeypatch.setattr(audit_service, "log_event", boom)
    events = [e async for e in chat_pipeline.chat_turn(_req())]
    assert [e["type"] for e in events] == ["sources", "token", "done"]


async def test_trimmed_history_reaches_the_agent(wired, monkeypatch):
    _agent(monkeypatch, wired)
    sentinel = [{"role": "user", "content": "TRIMMED"}]
    def build(system, history, question, limit):
        return sentinel, {"limit": limit, "prompt_tokens_est": 1, "fill_pct": 0.0, "dropped_turns": 0, "over_limit": False}
    monkeypatch.setattr(context_builder, "build", build)
    raw = [{"role": "user", "content": "old"}, {"role": "assistant", "content": "older"}]
    [e async for e in chat_pipeline.chat_turn(_req(history=raw))]
    assert wired["history"] is sentinel


async def test_memory_block_reaches_the_system_prompt(wired, monkeypatch):
    _agent(monkeypatch, wired)
    async def memory_context(*a):
        return "STUDENT MEMORY: likes analogies"
    monkeypatch.setattr(memory_service, "memory_context", memory_context)
    [e async for e in chat_pipeline.chat_turn(_req())]
    assert "STUDENT MEMORY: likes analogies" in wired["system"]


async def test_lecture_scope_grounds_lookup_in_lecture_title_but_agent_gets_bare_question(wired, monkeypatch):
    _agent(monkeypatch, wired)
    scope = cl.ChatScope(course_slug="react-perf", lecture_title="4.1 - React.memo and useCallback")
    req = chat_pipeline.TurnRequest(question="Give me an example", student_id="alice", scope=scope,
                                    history=[], memory_slug="react-perf")
    [e async for e in chat_pipeline.chat_turn(req)]
    assert wired["lookup_q"] == ["4.1 - React.memo and useCallback Give me an example"]
    assert wired["agent_q"] == ["Give me an example"]
    assert wired["audit"][0]["question"] == "Give me an example"
    assert wired["recorded"][0][2] == "Give me an example"


async def test_ask_scope_lookup_uses_the_bare_question(wired, monkeypatch):
    _agent(monkeypatch, wired)
    [e async for e in chat_pipeline.chat_turn(_req("how do I publish an npm library"))]
    assert wired["lookup_q"] == ["how do I publish an npm library"]


def _not_enrolled(*hits):
    async def lookup(question, student_id, scope=cl.ChatScope()):
        return cl.CourseLookup(case=cl.LookupCase.NOT_ENROLLED_MATCH, hits=list(hits), enrolled_titles=[])
    return lookup


def _hit(course_id, title, url, enrolled=False):
    return cl.Hit(source="catalog", course_id=course_id, course_slug=None, course_title=title, title=title,
                  score=0.5, enrolled=enrolled, url=url)


async def _tokens(monkeypatch, wired, answer, *hits):
    monkeypatch.setattr(chat_pipeline, "course_lookup", _not_enrolled(*hits))
    _agent(monkeypatch, wired, events=[{"type": "token", "value": answer}])
    events = [e async for e in chat_pipeline.chat_turn(_req())]
    return [e["value"] for e in events if e["type"] == "token"]


async def test_pointer_to_another_not_enrolled_hit_counts(wired, monkeypatch):
    toks = await _tokens(monkeypatch, wired, "See the01.dev/course/1.",
                         _hit(2, "Build a Custom Library", "/course/2"), _hit(1, "Build a Programming Language", "/course/1"))
    assert toks == ["See the01.dev/course/1."]


async def test_url_check_is_boundary_aware(wired, monkeypatch):
    toks = await _tokens(monkeypatch, wired, "See the01.dev/course/20.", _hit(2, "Build a Custom Library", "/course/2"))
    assert len(toks) == 2 and toks[1].endswith("the01.dev/course/2.")


async def test_not_enrolled_wording_without_any_course_url_still_gets_the_pointer(wired, monkeypatch):
    toks = await _tokens(monkeypatch, wired, "You're Not Enrolled in Build a Custom Library yet.",
                         _hit(2, "Build a Custom Library", "/course/2"))
    assert len(toks) == 2 and toks[1].endswith("the01.dev/course/2.")


async def test_not_enrolled_wording_with_some_course_url_gets_no_pointer(wired, monkeypatch):
    answer = "You're not enrolled in that one yet; see the01.dev/course/7."
    toks = await _tokens(monkeypatch, wired, answer, _hit(2, "Build a Custom Library", "/course/2"))
    assert toks == [answer]


async def test_no_pointer_to_the_course_the_student_is_watching(wired, monkeypatch):
    # Player on a not-enrolled preview: the pointer would name the page they're already on.
    _agent(monkeypatch, wired)  # "Short answer." — no url
    req = chat_pipeline.TurnRequest(question="what is npm link", student_id="alice",
                                    scope=cl.ChatScope(course_slug="custom-library", lecture_title="8.1 - npm link"),
                                    history=[], memory_slug="custom-library")
    events = [e async for e in chat_pipeline.chat_turn(req)]
    assert [e["value"] for e in events if e["type"] == "token"] == ["Short answer."]


async def test_no_pointer_when_the_not_enrolled_hit_has_no_url(wired, monkeypatch):
    toks = await _tokens(monkeypatch, wired, "Short answer.", _hit(2, "Build a Custom Library", None))
    assert toks == ["Short answer."]


async def test_memory_block_lists_topics_without_a_greeting_instruction(monkeypatch):
    from app.services import memory_service as ms

    async def get(collection, doc_id):
        return {"turn_count": 4, "topics": ["npm link", "react memo"]}
    monkeypatch.setattr(ms.store, "get", get)
    block = await ms.memory_context("alice", "all-courses")
    assert "4 prior exchange(s)" in block and "- npm link" in block and "- react memo" in block
    assert "greet" not in block.lower()
