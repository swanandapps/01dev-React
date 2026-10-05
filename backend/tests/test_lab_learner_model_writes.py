import pytest
from fastapi.testclient import TestClient

from app.auth import optional_student
from app.main import app
from app.services import adaptive_service, concept_resolver, journey_service
from app.services.lab import routes as lab_routes
from app.services.store import InMemoryStore

# Server-side quiz: correctIndex is 0 for every question; concepts differ by case
# so the resolver stub's work is observable.
CONCEPTS = ["React.memo", "React.memo", "Closures"]


@pytest.fixture
def env(monkeypatch):
    from app.services.lab import graph as lab_graph

    s = InMemoryStore()
    monkeypatch.setattr(lab_routes, "store", s)
    monkeypatch.setattr(adaptive_service, "store", s)
    resolved = []

    async def fake_resolve(candidate, course_id=None):
        resolved.append((candidate, course_id))
        return concept_resolver.slugify(candidate)

    monkeypatch.setattr(concept_resolver, "resolve", fake_resolve)
    monkeypatch.setattr(lab_graph, "gen_objectives", lambda doc, title: [
        {"id": "o1", "title": "Memoization", "difficulty": "beginner", "focus": "memo"}])
    monkeypatch.setattr(lab_graph, "gen_quiz", lambda doc, objective, *a, **kw: [
        {"question": f"Q{i}?", "options": ["a", "b", "c", "d"], "correctIndex": 0,
         "explanation": "e", "hint": "h", "concept": CONCEPTS[i]} for i in range(3)])
    monkeypatch.setattr(lab_graph, "gen_summary", lambda doc, objectives, results: {
        "overall": "ok", "perObjective": [], "studyTips": []})
    app.dependency_overrides[optional_student] = lambda: "s1"
    yield TestClient(app), s, resolved
    app.dependency_overrides.clear()


def _start(c, headers=None):
    doc = c.post("/api/lab/upload-text", json={"text": "Memo.", "title": "My Notes"}).json()["docId"]
    lesson = c.post("/api/lab/lessons", json={"docId": doc}).json()
    lid = lesson["id"]
    c.post(f"/api/lab/lessons/{lid}/approve",
           json={"objectives": lesson["plan"]["objectives"], "questionsPerQuiz": 3})
    return lid


ANSWERS = [{"question_index": 0, "selected_index": 0},   # correct
           {"question_index": 1, "selected_index": 2},   # wrong
           {"question_index": 2, "selected_index": 0}]   # correct


async def test_writes_concept_performance_per_resolved_concept(env):
    c, s, resolved = env
    lid = _start(c)
    c.post(f"/api/lab/lessons/{lid}/submit", json={"score": 99, "total": 99, "answers": ANSWERS})
    memo = await s.get("concept_performance", "s1__react-memo")
    assert (memo["attempts"], memo["correct"], memo["accuracy"]) == (2, 1, 0.5)
    clo = await s.get("concept_performance", "s1__closures")
    assert (clo["attempts"], clo["correct"]) == (1, 1)
    # each distinct raw concept resolved once, with no course scope
    assert sorted(resolved) == [("Closures", None), ("React.memo", None)]


async def test_quiz_session_is_server_graded_with_provenance(env):
    c, s, _ = env
    lid = _start(c)
    # client lies about the aggregate; the session must use the server's grading
    c.post(f"/api/lab/lessons/{lid}/submit", json={"score": 99, "total": 99, "answers": ANSWERS})
    sessions = await s.query("quiz_sessions", "user_id", "s1")
    assert len(sessions) == 1
    sess = sessions[0]
    assert sess["session_id"] == f"lab-{lid}-o0"
    assert (sess["score"], sess["total"]) == (2, 3)
    assert sess["source"] == "self_study" and sess["course_id"] is None
    assert sess["doc_title"] == "My Notes" and sess["doc_id"]
    a1 = sess["answers"][1]
    assert a1["correct"] is False and a1["concept"] == "react-memo" and a1["raw_concept"] == "React.memo"


async def test_resubmit_is_idempotent(env):
    c, s, _ = env
    lid = _start(c)
    v = lab_routes._state_values(lid)  # state at the quiz, before the first submit
    answers = [lab_routes.AnswerResult(**a) for a in ANSWERS]
    await lab_routes._record_learner_model("s1", lid, v, answers)
    await lab_routes._record_learner_model("s1", lid, v, answers)  # retry / double-click
    assert (await s.get("concept_performance", "s1__react-memo"))["attempts"] == 2
    assert len(await s.query("quiz_sessions", "user_id", "s1")) == 1


async def test_body_student_id_is_ignored(env):
    c, s, _ = env
    lid = _start(c)
    c.post(f"/api/lab/lessons/{lid}/submit",
           json={"score": 2, "total": 3, "answers": ANSWERS, "student_id": "victim"})
    assert await s.query("quiz_sessions", "user_id", "victim") == []
    assert len(await s.query("quiz_sessions", "user_id", "s1")) == 1


async def test_no_token_means_no_writes(env):
    c, s, _ = env
    app.dependency_overrides[optional_student] = lambda: None
    lid = _start(c)
    r = c.post(f"/api/lab/lessons/{lid}/submit", json={"score": 2, "total": 3, "answers": ANSWERS})
    assert r.status_code == 200
    assert await s.list_all("concept_performance") == []
    assert await s.list_all("quiz_sessions") == []


async def test_another_students_lesson_is_not_written_for_me(env):
    c, s, _ = env
    app.dependency_overrides[optional_student] = lambda: "owner"
    lid = _start(c)
    app.dependency_overrides[optional_student] = lambda: "intruder"
    r = c.post(f"/api/lab/lessons/{lid}/submit", json={"score": 2, "total": 3, "answers": ANSWERS})
    assert r.status_code == 200
    assert await s.list_all("quiz_sessions") == []


async def test_out_of_range_and_duplicate_answers_are_skipped(env):
    c, s, _ = env
    lid = _start(c)
    answers = [{"question_index": 0, "selected_index": 0}, {"question_index": 0, "selected_index": 1},
               {"question_index": 9, "selected_index": 0}, {"question_index": -1, "selected_index": 0}]
    c.post(f"/api/lab/lessons/{lid}/submit", json={"score": 1, "total": 1, "answers": answers})
    sess = (await s.query("quiz_sessions", "user_id", "s1"))[0]
    assert (sess["score"], sess["total"]) == (1, 1)


async def test_write_failure_never_fails_the_quiz(env, monkeypatch):
    c, s, _ = env

    async def boom(*a, **k):
        raise RuntimeError("db down")

    monkeypatch.setattr(adaptive_service, "_update_perf", boom)
    lid = _start(c)
    r = c.post(f"/api/lab/lessons/{lid}/submit", json={"score": 2, "total": 3, "answers": ANSWERS})
    assert r.status_code == 200 and r.json()["status"] == "complete"


async def test_lesson_started_with_a_token_carries_the_student_id(env):
    c, _, _ = env
    lid = _start(c)
    assert lab_routes._state_values(lid)["student_id"] == "s1"
    assert lab_routes._state_values(lid)["doc_id"]


def test_courses_engaged_ignores_courseless_sessions():
    base = {"score": 1, "total": 1, "answers": [], "completed_at": "2026-10-01T00:00:00+00:00"}
    out = journey_service._compute_metrics(
        [{**base, "course_id": None}, {**base, "course_id": "c1"}], [])
    metrics = out[0] if isinstance(out, tuple) else out
    assert metrics["courses_engaged"] == 1


async def test_stale_resubmit_is_409_and_the_next_objective_still_records(env, monkeypatch):
    from app.services.lab import graph as lab_graph
    c, s, _ = env
    monkeypatch.setattr(lab_graph, "gen_objectives", lambda doc, title: [
        {"id": "o1", "title": "A", "difficulty": "beginner", "focus": "a"},
        {"id": "o2", "title": "B", "difficulty": "beginner", "focus": "b"}])
    doc = c.post("/api/lab/upload-text", json={"text": "x", "title": "T"}).json()["docId"]
    lesson = c.post("/api/lab/lessons", json={"docId": doc}).json()
    lid = lesson["id"]
    c.post(f"/api/lab/lessons/{lid}/approve",
           json={"objectives": lesson["plan"]["objectives"], "questionsPerQuiz": 3})
    body = {"score": 2, "total": 3, "answers": ANSWERS, "objective_index": 0}
    assert c.post(f"/api/lab/lessons/{lid}/submit", json=body).status_code == 200
    perf_before = await s.get("concept_performance", "s1__react-memo")
    assert c.post(f"/api/lab/lessons/{lid}/submit", json=body).status_code == 409
    assert await s.get("concept_performance", "s1__react-memo") == perf_before
    assert len(await s.query("quiz_sessions", "user_id", "s1")) == 1
    assert lab_routes._state_values(lid)["objective_index"] == 1  # graph not advanced again
    r = c.post(f"/api/lab/lessons/{lid}/submit", json={**body, "objective_index": 1})
    assert r.status_code == 200
    ids = sorted(x["session_id"] for x in await s.query("quiz_sessions", "user_id", "s1"))
    assert ids == [f"lab-{lid}-o0", f"lab-{lid}-o1"]


async def test_partial_perf_failure_leaves_the_claim_and_retry_adds_nothing(env, monkeypatch):
    c, s, _ = env
    lid = _start(c)
    v = lab_routes._state_values(lid)
    answers = [lab_routes.AnswerResult(**a) for a in ANSWERS]
    real = adaptive_service._update_perf
    calls = []

    async def flaky(uid, concept, correct):
        calls.append(concept)
        if len(calls) == 2:
            raise RuntimeError("db blip")
        await real(uid, concept, correct)

    monkeypatch.setattr(adaptive_service, "_update_perf", flaky)
    with pytest.raises(RuntimeError):
        await lab_routes._record_learner_model("s1", lid, v, answers)
    assert len(await s.query("quiz_sessions", "user_id", "s1")) == 1  # claim exists
    n = len(calls)
    await lab_routes._record_learner_model("s1", lid, v, answers)  # retry
    assert len(calls) == n  # no further perf writes
