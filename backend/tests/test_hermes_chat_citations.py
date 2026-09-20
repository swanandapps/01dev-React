import pytest
from fastapi.testclient import TestClient

import app.main as main_module
from app.main import app
from app.services import hermes_client
from app.services.store import InMemoryStore


@pytest.mark.asyncio
async def test_hermes_chat_emits_real_sources_when_mcp_tool_left_citations(monkeypatch):
    # The MCP tool (a separate process from Hermes's own point of view) writes
    # citations to the shared store keyed by student_id — simulate that having
    # already happened before this request's stream runs.
    from app.services import audit_service, memory_service

    real_store = InMemoryStore()
    monkeypatch.setattr(main_module, "store", real_store)

    async def _capture_stream_chat(question, system=None, history=None):
        # By the time Hermes starts emitting content tokens, its internal tool
        # loop (including any search_course_content call) has already resolved.
        await real_store.set("chat_citations", "citations-e2e-student", {
            "cards": [{
                "course_id": "react-perf", "course_title": "React Performance Patterns",
                "lecture_id": "l1", "lecture_title": "Lecture 4.1", "timestamp": "01:13",
                "start_time": 73, "end_time": 133, "snippet": "React.memo...", "score": 0.9,
            }],
        })
        yield {"type": "token", "value": "React.memo prevents re-renders."}
        yield {"type": "done"}

    async def _noop_log_event(**kwargs):
        return None

    async def _empty_memory_context(*args, **kwargs):
        return ""

    async def _empty_recent_turns(*args, **kwargs):
        return []

    async def _noop_record_turn(*args, **kwargs):
        return None

    monkeypatch.setattr(hermes_client, "stream_chat", _capture_stream_chat)
    monkeypatch.setattr(audit_service, "log_event", _noop_log_event)
    monkeypatch.setattr(memory_service, "memory_context", _empty_memory_context)
    monkeypatch.setattr(memory_service, "recent_turns", _empty_recent_turns)
    monkeypatch.setattr(memory_service, "record_turn", _noop_record_turn)

    client = TestClient(app)
    with client.stream(
        "POST",
        "/api/hermes/chat",
        json={
            "question": "How does React.memo work?",
            "user_id": "citations-e2e-student",
            "course_slug": "react-perf",
        },
    ) as resp:
        assert resp.status_code == 200
        body = "".join(resp.iter_text())

    assert body.count('"type": "sources"') == 2  # placeholder up front, real one after the stream
    assert "react-perf" in body
    assert "Lecture 4.1" in body


@pytest.mark.asyncio
async def test_hermes_chat_clears_stale_citations_from_a_prior_turn(monkeypatch):
    from app.services import audit_service, memory_service

    real_store = InMemoryStore()
    monkeypatch.setattr(main_module, "store", real_store)

    await real_store.set("chat_citations", "stale-citations-student", {
        "cards": [{"course_id": "stale-course", "course_title": "x", "lecture_id": "l",
                   "lecture_title": "x", "timestamp": "00:00", "start_time": 0, "end_time": 0,
                   "snippet": "x", "score": 0.1}],
    })

    async def _capture_stream_chat(question, system=None, history=None):
        # This turn's Hermes call never touches search_course_content — no new write.
        yield {"type": "token", "value": "I don't have course content for that."}
        yield {"type": "done"}

    async def _noop_log_event(**kwargs):
        return None

    async def _empty_memory_context(*args, **kwargs):
        return ""

    async def _empty_recent_turns(*args, **kwargs):
        return []

    async def _noop_record_turn(*args, **kwargs):
        return None

    monkeypatch.setattr(hermes_client, "stream_chat", _capture_stream_chat)
    monkeypatch.setattr(audit_service, "log_event", _noop_log_event)
    monkeypatch.setattr(memory_service, "memory_context", _empty_memory_context)
    monkeypatch.setattr(memory_service, "recent_turns", _empty_recent_turns)
    monkeypatch.setattr(memory_service, "record_turn", _noop_record_turn)

    client = TestClient(app)
    with client.stream(
        "POST",
        "/api/hermes/chat",
        json={
            "question": "unrelated question",
            "user_id": "stale-citations-student",
            "course_slug": "all-courses",
        },
    ) as resp:
        assert resp.status_code == 200
        body = "".join(resp.iter_text())

    assert "stale-course" not in body
    assert body.count('"type": "sources"') == 1  # only the empty placeholder — nothing to report
