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
    assert "QuizMe" in tokens
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
    assert "QuizMe" not in tokens


def test_progress_intent_calls_journey_service_not_the_model(client, monkeypatch):
    from app.routing import progress_handoff
    from app.services import grounding

    async def _fail_if_called(*args, **kwargs):
        raise AssertionError("retrieval must not run for a PROGRESS_LOOKUP request")

    async def _fake_get_journey(user_id):
        assert user_id == "test-student"
        return {"ai": {"narrative": "You're making steady progress.", "insights": [], "focus": "Keep it up."}}

    monkeypatch.setattr(grounding, "retrieve", _fail_if_called)
    monkeypatch.setattr(progress_handoff, "get_journey", _fake_get_journey)

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
    assert "You're making steady progress." in tokens


def test_out_of_scope_intent_falls_through_to_normal_chat_logic(client, monkeypatch):
    # OUT_OF_SCOPE must NOT be diverted by the `if intent in (QUIZ_GENERATE,
    # PROGRESS_LOOKUP):` short-circuit — it should reach the same Hermes path
    # as an ordinary course question (there's no separate backend decline
    # path anymore; SOUL.md's own "don't answer outside the course material"
    # instruction is what Hermes uses to decline, not a code branch here).
    # Force the intent directly rather than relying on classify()'s gibberish
    # heuristics, for a cleaner, more direct test of the routing decision.
    from app import main as app_main
    from app.routing.intent import Intent
    from app.services import hermes_client

    monkeypatch.setattr(app_main, "classify", lambda question: Intent.OUT_OF_SCOPE)

    async def _fake_stream_chat(question, system=None, history=None):
        yield {"type": "token", "value": "not covered by this course"}
        yield {"type": "done"}

    monkeypatch.setattr(hermes_client, "stream_chat", _fake_stream_chat)

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
    # Reached the real Hermes path (our fake was actually called) — proof it
    # wasn't diverted to the quiz/progress hand-off branch.
    assert "not covered by this course" in tokens
    assert "QuizMe" not in tokens
    sources_event = next(e for e in events if e.get("type") == "sources")
    assert sources_event["insufficient_context"] is False
    assert any(e.get("type") == "done" for e in events)


def test_progress_lookup_failure_degrades_gracefully_instead_of_500(client, monkeypatch):
    # Finding 1 regression: a DB/LLM failure inside build_progress_message
    # (via journey_service.get_journey) must not become an unhandled 500 on
    # the whole chat endpoint — it should fall back to a plain message.
    from app.routing import progress_handoff

    async def _boom(user_id):
        raise RuntimeError("journey service is down")

    monkeypatch.setattr(progress_handoff, "get_journey", _boom)

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
    assert "Journey dashboard" in tokens
    assert any(e.get("type") == "done" for e in events)


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
