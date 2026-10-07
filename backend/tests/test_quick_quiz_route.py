"""In-player 'Quiz me': 3 questions on what the student has watched of this lecture — no Lab lesson, no
objectives. The answer key stays on the server; Submit grades, records the result in the learner model (the
same quiz_sessions + concept performance a course or Lab quiz writes) and only then reveals answers."""
import pytest
from fastapi.testclient import TestClient

from app.auth import current_student
from app.main import app
from app.models import TranscriptChunk
from app.services import adaptive_service, concept_resolver, enrollment_service, lecture_context, recommendation_service
from app.services.lab import llm as lab_llm
from app.services.store import store

L51 = "5.1 - Prototype, a Hero Turned Villain"


def _q(i):
    return {"question": f"Question {i}?", "options": ["o0", "o1", "o2", "o3"], "correctIndex": i % 4,
            "explanation": f"because {i}", "hint": "h", "concept": f"concept {i}"}


def _c(n, start):
    return TranscriptChunk(chunk_id=f"cl-4-0-{n}", course_id="custom-library", course_title="Build a Custom Library",
                           lecture_id="custom-library-4-0", lecture_title=L51, text=f"raw {n}", text_clean=f"passage {n}",
                           start_time=start, end_time=start + 50)


@pytest.fixture
def client(monkeypatch):
    who = {"uid": "token-uid"}
    app.dependency_overrides[current_student] = lambda: who["uid"]
    seen = {"perf": [], "invalidated": 0}

    async def chunks(slug, title):
        return [_c(i, i * 50) for i in range(8)] if title == L51 else []

    def fake_gen(document, objective, n):
        seen["doc"], seen["n"] = document, n
        return [_q(i) for i in range(n)]

    async def owns(student_id):
        return [{"id": 2, "title": "Build a Custom Library"}]

    async def resolve(raw, course_id=None):
        return raw.title()

    async def perf(user_id, concept, correct):
        seen["perf"].append((user_id, concept, correct))

    async def invalidate(user_id):
        seen["invalidated"] += 1

    monkeypatch.setattr(lecture_context, "lecture_chunks", chunks)
    monkeypatch.setattr(lab_llm, "gen_quiz", fake_gen)
    monkeypatch.setattr(enrollment_service, "get_enrolled_courses", owns)
    monkeypatch.setattr(concept_resolver, "resolve", resolve)
    monkeypatch.setattr(adaptive_service, "_update_perf", perf)
    monkeypatch.setattr(recommendation_service, "invalidate", invalidate)
    yield TestClient(app), seen, who
    app.dependency_overrides.clear()


def _start(c, **kw):
    return c.post("/api/ai/quick-quiz", json={"course_id": "custom-library", "lecture": L51, **kw})


def test_questions_come_from_what_was_watched_and_carry_no_answer_key(client):
    c, seen, _ = client
    r = _start(c, position=160)
    assert r.status_code == 200
    body = r.json()
    assert body["quiz_id"] and len(body["questions"]) == 3
    assert set(body["questions"][0]) == {"question", "options", "lecture"}   # no correctIndex, no explanation
    assert body["questions"][0]["lecture"] == L51
    assert seen["n"] == 3 and "passage 3" in seen["doc"] and "passage 4" not in seen["doc"]


def test_early_in_the_video_uses_the_first_passages_and_no_position_uses_the_whole_lecture(client):
    c, seen, _ = client
    _start(c, position=5)
    assert "passage 2" in seen["doc"] and "passage 3" not in seen["doc"]
    _start(c)
    assert "passage 7" in seen["doc"]


def test_submit_grades_on_the_server_records_the_session_and_reveals_answers(client):
    c, seen, _ = client
    quiz_id = _start(c, position=160).json()["quiz_id"]
    r = c.post(f"/api/ai/quick-quiz/{quiz_id}/submit", json={"answers": [0, 0, 2]})   # keys are 0, 1, 2
    assert r.status_code == 200
    res = r.json()
    assert (res["score"], res["total"]) == (2, 3)
    assert [x["correct"] for x in res["results"]] == [True, False, True]
    assert [x["correctIndex"] for x in res["results"]] == [0, 1, 2] and res["results"][1]["explanation"] == "because 1"
    assert seen["perf"] == [("token-uid", "Concept 0", True), ("token-uid", "Concept 1", False),
                            ("token-uid", "Concept 2", True)] and seen["invalidated"] == 1


async def test_the_session_row_is_a_course_quiz_session_with_the_lecture(client):
    c, _, _ = client
    quiz_id = _start(c, position=160).json()["quiz_id"]
    c.post(f"/api/ai/quick-quiz/{quiz_id}/submit", json={"answers": [0, 1, 2]})
    row = await store.get("quiz_sessions", f"quick-{quiz_id}")
    assert row["user_id"] == "token-uid" and row["course_id"] == "custom-library" and row["score"] == 3
    assert row["source"] == "player_quick_quiz" and {a["lecture"] for a in row["answers"]} == {L51}


def test_submitting_twice_counts_once(client):
    c, seen, _ = client
    quiz_id = _start(c).json()["quiz_id"]
    a = c.post(f"/api/ai/quick-quiz/{quiz_id}/submit", json={"answers": [0, 1, 2]}).json()
    b = c.post(f"/api/ai/quick-quiz/{quiz_id}/submit", json={"answers": [3, 3, 3]}).json()
    assert a == b and len(seen["perf"]) == 3


def test_only_the_student_who_got_the_quiz_can_submit_and_answers_must_be_complete(client):
    c, _, who = client
    quiz_id = _start(c).json()["quiz_id"]
    assert c.post(f"/api/ai/quick-quiz/{quiz_id}/submit", json={"answers": [0, 1]}).status_code == 400
    assert c.post(f"/api/ai/quick-quiz/{quiz_id}/submit", json={"answers": [0, 1, 9]}).status_code == 400
    assert c.post("/api/ai/quick-quiz/nope/submit", json={"answers": [0, 1, 2]}).status_code == 404
    who["uid"] = "someone-else"
    assert c.post(f"/api/ai/quick-quiz/{quiz_id}/submit", json={"answers": [0, 1, 2]}).status_code == 404


def test_not_owner_403_unknown_course_404_no_transcript_404(client, monkeypatch):
    c, _, _ = client

    async def none(student_id):
        return []

    assert c.post("/api/ai/quick-quiz", json={"course_id": "nope", "lecture": L51}).status_code == 404
    assert c.post("/api/ai/quick-quiz", json={"course_id": "custom-library", "lecture": "9.9 - x"}).status_code == 404
    monkeypatch.setattr(enrollment_service, "get_enrolled_courses", none)
    assert _start(c).status_code == 403
