import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.services.lab.routes import AnswerResult, SubmitReq


@pytest.fixture
def client(monkeypatch):
    from app.services.lab import graph as lab_graph

    monkeypatch.setattr(lab_graph, "gen_objectives", lambda doc, title: [
        {"id": "o1", "title": "Closures", "difficulty": "beginner", "focus": "scope"}])
    monkeypatch.setattr(lab_graph, "gen_quiz", lambda doc, objective, *a, **kw: [
        {"question": "Q?", "options": ["a", "b", "c", "d"], "correctIndex": 0,
         "explanation": "e", "hint": "h", "concept": "closures"} for _ in range(2)])
    monkeypatch.setattr(lab_graph, "gen_summary", lambda doc, objectives, results: {
        "overall": "ok", "perObjective": [], "studyTips": []})
    return TestClient(app)


def test_submit_contract_shape():
    assert set(AnswerResult.model_fields) == {"question_index", "selected_index"}
    assert "answers" in SubmitReq.model_fields
    assert "student_id" not in SubmitReq.model_fields  # identity comes from the token
    assert SubmitReq(score=1, total=1).answers == []


def _start(client, per_quiz=2):
    doc = client.post("/api/lab/upload-text", json={"text": "Closures."}).json()["docId"]
    lesson = client.post("/api/lab/lessons", json={"docId": doc}).json()
    lid = lesson["id"]
    client.post(f"/api/lab/lessons/{lid}/approve",
                json={"objectives": lesson["plan"]["objectives"], "questionsPerQuiz": per_quiz})
    return lid


def test_submit_accepts_per_answer_results(client):
    lid = _start(client)
    r = client.post(f"/api/lab/lessons/{lid}/submit", json={
        "score": 1, "total": 2,
        "answers": [{"question_index": 0, "selected_index": 0},
                    {"question_index": 1, "selected_index": 2}]})
    assert r.status_code == 200
    assert r.json()["status"] == "complete"


def test_submit_without_answers_still_works(client):
    lid = _start(client, 1)
    assert client.post(f"/api/lab/lessons/{lid}/submit",
                       json={"score": 1, "total": 1}).status_code == 200


def test_submit_rejects_malformed_answers(client):
    lid = _start(client)
    r = client.post(f"/api/lab/lessons/{lid}/submit", json={
        "score": 1, "total": 2, "answers": [{"concept": "x", "correct": True}]})
    assert r.status_code == 422
