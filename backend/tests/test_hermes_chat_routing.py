import json

import pytest
from fastapi.testclient import TestClient

from app.main import app


@pytest.fixture
def client(monkeypatch):
    # Never touch Postgres/OpenAI/audit storage from this test — it's
    # asserting routing behavior, not the downstream services' correctness.
    from app.services import audit_service, memory_service

    async def _noop_log_event(**kwargs):
        return None

    async def _empty_memory_context(*args, **kwargs):
        return ""

    async def _empty_recent_turns(*args, **kwargs):
        return []

    async def _noop_record_turn(*args, **kwargs):
        return None

    monkeypatch.setattr(audit_service, "log_event", _noop_log_event)
    monkeypatch.setattr(memory_service, "memory_context", _empty_memory_context)
    monkeypatch.setattr(memory_service, "recent_turns", _empty_recent_turns)
    monkeypatch.setattr(memory_service, "record_turn", _noop_record_turn)
    return TestClient(app)


def _sse_events(raw_text: str) -> list[dict]:
    events = []
    for line in raw_text.splitlines():
        if line.startswith("data:"):
            events.append(json.loads(line[len("data:"):].strip()))
    return events


def test_quiz_intent_short_circuits_before_any_model_call(client, monkeypatch):
    # If routing is broken and this falls through to the real grounded/agentic
    # path, these would be hit and (without network) raise — the test fails
    # loudly instead of silently calling out to OpenAI/Hermes.
    from app.services import grounding, skill_graph_service

    async def _fail_if_called(*args, **kwargs):
        raise AssertionError("retrieval must not run for a QUIZ_GENERATE request")

    async def _fail_if_ensure_populated_called(*args, **kwargs):
        raise AssertionError(
            "ensure_populated must not run for QUIZ_GENERATE — it never touches the skill graph"
        )

    monkeypatch.setattr(grounding, "retrieve", _fail_if_called)
    monkeypatch.setattr(skill_graph_service, "ensure_populated", _fail_if_ensure_populated_called)

    resp = client.post(
        "/api/hermes/chat",
        json={
            "question": "Can you quiz me on closures?",
            "user_id": "test-student",
            "course_slug": "js-fundamentals",
        },
    )
    assert resp.status_code == 200
    events = _sse_events(resp.text)
    tokens = "".join(e["value"] for e in events if e.get("type") == "token")
    assert "Lab" in tokens
    assert any(e.get("type") == "done" for e in events)


def test_course_question_intent_is_unaffected(client, monkeypatch):
    # Not asserting the full Hermes answer here (that's hermes_client's own
    # concern, already covered by its own tests) — only that a normal
    # question reaches the real Hermes path, not the quiz/progress hand-off.
    from app.services import hermes_client

    async def _fake_stream_chat(question, system=None, history=None):
        yield {"type": "token", "value": "closures capture variables"}
        yield {"type": "done"}

    monkeypatch.setattr(hermes_client, "stream_chat", _fake_stream_chat)

    resp = client.post(
        "/api/hermes/chat",
        json={
            "question": "What is a closure?",
            "user_id": "test-student",
            "course_slug": "js-fundamentals",
        },
    )
    assert resp.status_code == 200
    events = _sse_events(resp.text)
    tokens = "".join(e["value"] for e in events if e.get("type") == "token")
    assert "closures capture variables" in tokens
    assert "Lab" not in tokens


def test_progress_question_reaches_real_hermes_path_not_a_handoff(client, monkeypatch):
    # "What's my progress" used to be a PROGRESS_LOOKUP short-circuit that
    # never reached Hermes at all — it's a plain COURSE_QUESTION now, and
    # Hermes answers it via the get_learning_strengths/get_learning_metrics
    # tools like any other question (those tools' own behavior is covered by
    # their dedicated tests; this just proves the routing decision).
    from app.services import hermes_client

    async def _fake_stream_chat(question, system=None, history=None):
        yield {"type": "token", "value": "you're making steady progress"}
        yield {"type": "done"}

    monkeypatch.setattr(hermes_client, "stream_chat", _fake_stream_chat)

    resp = client.post(
        "/api/hermes/chat",
        json={
            "question": "What's my progress so far?",
            "user_id": "test-student",
            "course_slug": "js-fundamentals",
        },
    )
    assert resp.status_code == 200
    events = _sse_events(resp.text)
    tokens = "".join(e["value"] for e in events if e.get("type") == "token")
    assert "you're making steady progress" in tokens
    assert "Lab" not in tokens


def test_out_of_scope_intent_short_circuits_before_any_model_call(client, monkeypatch):
    # OUT_OF_SCOPE (gibberish/empty) short-circuits with a canned decline —
    # it must NOT reach Hermes at all, same as QUIZ_GENERATE. This used to
    # fall through to the real Hermes path (a latent gap: classifying
    # something OUT_OF_SCOPE didn't actually skip the expensive call) —
    # fixed alongside wiring up the smalltalk classifier's short-circuit.
    from app.services import hermes_client

    async def _fail_if_called(*args, **kwargs):
        raise AssertionError("Hermes must not be called for an OUT_OF_SCOPE request")

    monkeypatch.setattr(hermes_client, "stream_chat", _fail_if_called)

    resp = client.post(
        "/api/hermes/chat",
        json={
            "question": "asdkjaslkdj",
            "user_id": "test-student",
            "course_slug": "js-fundamentals",
        },
    )
    assert resp.status_code == 200
    events = _sse_events(resp.text)
    tokens = "".join(e["value"] for e in events if e.get("type") == "token")
    assert "ask me about a course" in tokens
    assert "Lab" not in tokens
    sources_event = next(e for e in events if e.get("type") == "sources")
    assert sources_event["insufficient_context"] is False
    assert any(e.get("type") == "done" for e in events)


def test_smalltalk_check_does_not_block_by_default(client, monkeypatch):
    # SMALLTALK_BLOCK_ENABLED defaults to false — even a short greeting-like
    # message must still reach Hermes while this ships in observe-only mode.
    from app.routing import smalltalk_classifier
    from app.services import hermes_client

    async def _fake_check(question):
        return {"checked": True, "similarity": 0.99, "should_block": False}

    async def _fake_stream_chat(question, system=None, history=None):
        yield {"type": "token", "value": "hey there!"}
        yield {"type": "done"}

    monkeypatch.setattr(smalltalk_classifier, "check", _fake_check)
    monkeypatch.setattr(hermes_client, "stream_chat", _fake_stream_chat)

    resp = client.post(
        "/api/hermes/chat",
        json={"question": "hi", "user_id": "test-student", "course_slug": "js-fundamentals"},
    )
    assert resp.status_code == 200
    events = _sse_events(resp.text)
    tokens = "".join(e["value"] for e in events if e.get("type") == "token")
    assert "hey there!" in tokens


def test_smalltalk_block_enabled_short_circuits_to_out_of_scope(client, monkeypatch):
    # With SMALLTALK_BLOCK_ENABLED explicitly on (simulated via the check's
    # own return value, not the env var — see smalltalk_classifier's own
    # tests for the threshold/env-var logic itself), a should_block=True
    # result upgrades COURSE_QUESTION to the OUT_OF_SCOPE short-circuit.
    from app.routing import smalltalk_classifier
    from app.services import hermes_client

    async def _fake_check(question):
        return {"checked": True, "similarity": 0.95, "should_block": True}

    async def _fail_if_called(*args, **kwargs):
        raise AssertionError("Hermes must not be called when smalltalk blocking fires")

    monkeypatch.setattr(smalltalk_classifier, "check", _fake_check)
    monkeypatch.setattr(hermes_client, "stream_chat", _fail_if_called)

    resp = client.post(
        "/api/hermes/chat",
        json={"question": "hi", "user_id": "test-student", "course_slug": "js-fundamentals"},
    )
    assert resp.status_code == 200
    events = _sse_events(resp.text)
    tokens = "".join(e["value"] for e in events if e.get("type") == "token")
    assert "ask me about a course" in tokens


def test_course_question_backfills_skill_graph(client, monkeypatch):
    from app.services import hermes_client, skill_graph_service

    calls = []

    async def fake_ensure_populated(user_id, course_id):
        calls.append((user_id, course_id))
        return 0

    async def _fake_stream_chat(question, system=None, history=None):
        yield {"type": "token", "value": "ok"}
        yield {"type": "done"}

    monkeypatch.setattr(skill_graph_service, "ensure_populated", fake_ensure_populated)
    monkeypatch.setattr(hermes_client, "stream_chat", _fake_stream_chat)

    resp = client.post(
        "/api/hermes/chat",
        json={"question": "What is a closure?", "user_id": "backfill-test", "course_slug": "js-fundamentals"},
    )
    assert resp.status_code == 200
    assert ("backfill-test", "js-fundamentals") in calls


def test_backfill_failure_does_not_break_chat(client, monkeypatch):
    from app.services import hermes_client, skill_graph_service

    async def fake_ensure_populated(user_id, course_id):
        raise RuntimeError("skill graph service is down")

    async def _fake_stream_chat(question, system=None, history=None):
        yield {"type": "token", "value": "ok"}
        yield {"type": "done"}

    monkeypatch.setattr(skill_graph_service, "ensure_populated", fake_ensure_populated)
    monkeypatch.setattr(hermes_client, "stream_chat", _fake_stream_chat)

    resp = client.post(
        "/api/hermes/chat",
        json={"question": "What is a closure?", "user_id": "backfill-fail-test", "course_slug": "js-fundamentals"},
    )
    assert resp.status_code == 200
