from app.services import hermes_client
from fastapi.testclient import TestClient

from app.main import app


def test_system_prompt_includes_student_and_course_ids(monkeypatch):
    from app.services import audit_service, memory_service

    captured = {}

    async def _capture_stream_chat(question, system=None, history=None):
        captured["system"] = system
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
    resp = client.post(
        "/api/hermes/chat",
        json={
            "question": "What is a closure?",
            "user_id": "identity-test-student",
            "course_slug": "js-fundamentals",
        },
    )
    assert resp.status_code == 200
    assert "identity-test-student" in captured["system"]
    assert "js-fundamentals" in captured["system"]


def test_all_courses_sentinel_does_not_read_as_a_real_course_name(monkeypatch):
    # Regression: the global Ask page (no course selector) sends
    # course_slug="all-courses" as a sentinel for "no specific course chosen".
    # The old phrasing ("You are tutoring the 'all-courses' course") made the
    # model answer "you're enrolled in the course called all-courses" when
    # asked what courses the student is enrolled in — it must not read as a
    # real course name. (Enrollment now has real data via the
    # get_enrolled_courses tool — see test_enrollment_endpoint.py /
    # test_mcp_get_enrolled_courses.py; this test only checks the sentinel.)
    from app.services import audit_service, memory_service

    captured = {}

    async def _capture_stream_chat(question, system=None, history=None):
        captured["system"] = system
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
    resp = client.post(
        "/api/hermes/chat",
        json={
            "question": "What courses am I enrolled in?",
            "user_id": "identity-test-student",
            "course_slug": "all-courses",
        },
    )
    assert resp.status_code == 200
    system = captured["system"]
    assert "tutoring the 'all-courses' course" not in system
    assert "get_enrolled_courses" in system
