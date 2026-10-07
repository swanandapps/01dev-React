"""Key moments under the video: each transcript passage of the lecture, at its start time, with its one-line
summary. Only for a logged-in student who owns the course."""
import pytest
from fastapi.testclient import TestClient

from app.auth import current_student
from app.main import app
from app.models import TranscriptChunk
from app.services import enrollment_service
from app.services import lecture_context

L51 = "5.1 - Prototype, a Hero Turned Villain"


def _c(n, start, summary, text="raw words"):
    return TranscriptChunk(chunk_id=f"custom-library-4-0-{n}", course_id="custom-library", course_title="Build a Custom Library",
                           lecture_id="custom-library-4-0", lecture_title=L51, text=text, start_time=start,
                           end_time=start + 48, summary=summary)


@pytest.fixture
def client(monkeypatch):
    app.dependency_overrides[current_student] = lambda: "token-uid"

    async def chunks(slug, title):
        return [_c(0, 0, "Prototype extends built-ins."), _c(1, 49, ""), _c(2, 97, "Security risk.")] \
            if (slug, title) == ("custom-library", L51) else []

    monkeypatch.setattr(lecture_context, "lecture_chunks", chunks)
    yield TestClient(app)
    app.dependency_overrides.clear()


def _owns(monkeypatch, ids):
    async def enrolled(student_id):
        assert student_id == "token-uid"
        return [{"id": i, "title": "x"} for i in ids]
    monkeypatch.setattr(enrollment_service, "get_enrolled_courses", enrolled)


def test_owner_gets_every_passage_with_its_summary_in_time_order(client, monkeypatch):
    _owns(monkeypatch, [2])
    r = client.get("/api/ai/lecture-moments", params={"course_id": "custom-library", "lecture": L51})
    assert r.status_code == 200
    assert r.json() == [{"start_time": 0, "summary": "Prototype extends built-ins."},
                        {"start_time": 49, "summary": "raw words"},
                        {"start_time": 97, "summary": "Security risk."}]


def test_a_student_who_does_not_own_the_course_gets_403(client, monkeypatch):
    _owns(monkeypatch, [9])
    r = client.get("/api/ai/lecture-moments", params={"course_id": "custom-library", "lecture": L51})
    assert r.status_code == 403


def test_unknown_course_is_404_and_a_lecture_without_transcript_is_empty(client, monkeypatch):
    _owns(monkeypatch, [2])
    assert client.get("/api/ai/lecture-moments", params={"course_id": "nope", "lecture": L51}).status_code == 404
    r = client.get("/api/ai/lecture-moments", params={"course_id": "custom-library", "lecture": "9.9 - Nothing"})
    assert r.status_code == 200 and r.json() == []
