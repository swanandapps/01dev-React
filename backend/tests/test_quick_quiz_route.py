"""In-player 'Quiz me': 3 questions straight from what the student has watched of this lecture — no Lab
lesson, no objectives. Owners of the course only."""
import pytest
from fastapi.testclient import TestClient

from app.auth import current_student
from app.main import app
from app.models import TranscriptChunk
from app.services import enrollment_service, lecture_context
from app.services.lab import llm as lab_llm

L51 = "5.1 - Prototype, a Hero Turned Villain"
Q = {"question": "Why is extending String.prototype risky?", "options": ["a1", "a2", "a3", "a4"],
     "correctIndex": 2, "explanation": "Because…", "hint": "Think security", "concept": "prototype risk"}


def _c(n, start):
    return TranscriptChunk(chunk_id=f"cl-4-0-{n}", course_id="custom-library", course_title="Build a Custom Library",
                           lecture_id="custom-library-4-0", lecture_title=L51, text=f"raw {n}", text_clean=f"passage {n}",
                           start_time=start, end_time=start + 50)


@pytest.fixture
def client(monkeypatch):
    app.dependency_overrides[current_student] = lambda: "token-uid"
    seen = {}

    async def chunks(slug, title):
        return [_c(i, i * 50) for i in range(8)] if title == L51 else []

    def fake_gen(document, objective, n):
        seen["doc"], seen["n"] = document, n
        return [Q] * n

    async def owns(student_id):
        return [{"id": 2, "title": "Build a Custom Library"}]

    monkeypatch.setattr(lecture_context, "lecture_chunks", chunks)
    monkeypatch.setattr(lab_llm, "gen_quiz", fake_gen)
    monkeypatch.setattr(enrollment_service, "get_enrolled_courses", owns)
    yield TestClient(app), seen
    app.dependency_overrides.clear()


def test_three_questions_from_what_was_watched_so_far(client):
    c, seen = client
    r = c.post("/api/ai/quick-quiz", json={"course_id": "custom-library", "lecture": L51, "position": 160})
    assert r.status_code == 200
    qs = r.json()["questions"]
    assert len(qs) == 3 and set(qs[0]) == {"question", "options", "correctIndex", "explanation"}
    assert seen["n"] == 3 and "passage 3" in seen["doc"] and "passage 4" not in seen["doc"]


def test_early_in_the_video_still_uses_the_first_passages_and_no_position_uses_the_whole_lecture(client):
    c, seen = client
    c.post("/api/ai/quick-quiz", json={"course_id": "custom-library", "lecture": L51, "position": 5})
    assert "passage 2" in seen["doc"] and "passage 3" not in seen["doc"]
    c.post("/api/ai/quick-quiz", json={"course_id": "custom-library", "lecture": L51})
    assert "passage 7" in seen["doc"]


def test_not_owner_403_unknown_course_404_no_transcript_404(client, monkeypatch):
    c, _ = client

    async def none(student_id):
        return []

    assert c.post("/api/ai/quick-quiz", json={"course_id": "nope", "lecture": L51}).status_code == 404
    assert c.post("/api/ai/quick-quiz", json={"course_id": "custom-library", "lecture": "9.9 - x"}).status_code == 404
    monkeypatch.setattr(enrollment_service, "get_enrolled_courses", none)
    assert c.post("/api/ai/quick-quiz", json={"course_id": "custom-library", "lecture": L51}).status_code == 403
