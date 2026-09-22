import pytest
from fastapi.testclient import TestClient

from app.main import app


@pytest.fixture
def client(monkeypatch):
    """Drive the real graph with a fake LLM so shapes are real but no network.

    IMPORTANT — patch `app.services.lab.graph`, NOT `app.services.lab.llm`.
    graph.py does `from .llm import gen_objectives, gen_quiz, gen_summary`, so
    those names are bound in graph.py's own module namespace. Its node functions
    look them up there at call time, which means patching the llm module has no
    effect at all. (Patching works despite the graph being compiled at import,
    because the lookup happens inside the node function body, not at compile.)
    """
    from app.services.lab import graph as lab_graph

    def fake_gen_objectives(doc, title):
        return [
            {"id": "o1", "title": "Closures", "difficulty": "beginner", "focus": "scope"},
            {"id": "o2", "title": "Hoisting", "difficulty": "beginner", "focus": "declarations"},
        ]

    def fake_gen_quiz(doc, objective, n):
        return [
            {"question": f"Q about {objective['title']}?", "options": ["a", "b", "c", "d"],
             "correctIndex": 1, "explanation": "because b", "hint": "think about b"}
            for _ in range(n)
        ]

    def fake_gen_summary(doc, objectives, results):
        return {"overall": "Good work.", "perObjective": [], "studyTips": ["Review closures."]}

    monkeypatch.setattr(lab_graph, "gen_objectives", fake_gen_objectives)
    monkeypatch.setattr(lab_graph, "gen_quiz", fake_gen_quiz)
    monkeypatch.setattr(lab_graph, "gen_summary", fake_gen_summary)
    return TestClient(app)


def test_upload_text_returns_a_doc_id(client):
    r = client.post("/api/lab/upload-text", json={"text": "Closures capture variables.",
                                                  "title": "My notes"})
    assert r.status_code == 200
    assert r.json()["docId"]


def test_upload_text_rejects_empty(client):
    r = client.post("/api/lab/upload-text", json={"text": "   "})
    assert r.status_code == 400


def test_upload_text_rejects_oversize(client):
    from app.services.lab.routes import MAX_TEXT_CHARS

    r = client.post("/api/lab/upload-text",
                    json={"text": "x" * (MAX_TEXT_CHARS + 1)})
    assert r.status_code == 400
    assert "too long" in r.json()["detail"]


def test_upload_text_accepts_up_to_the_limit(client):
    from app.services.lab.routes import MAX_TEXT_CHARS

    r = client.post("/api/lab/upload-text",
                    json={"text": "x" * MAX_TEXT_CHARS})
    assert r.status_code == 200
    assert r.json()["docId"]


def test_upload_pdf_rejects_oversize_before_parsing(client):
    from app.services.lab.routes import MAX_PDF_BYTES

    # Garbage bytes, not a real PDF — the size check must reject this on byte
    # count alone, before ever handing it to PdfReader.
    oversize = b"x" * (MAX_PDF_BYTES + 1)
    r = client.post("/api/lab/upload",
                    files={"file": ("notes.pdf", oversize, "application/pdf")})
    assert r.status_code == 400
    assert "too large" in r.json()["detail"]


def test_start_lesson_returns_awaiting_approval_lessonview(client):
    doc_id = client.post("/api/lab/upload-text", json={"text": "Closures."}).json()["docId"]
    r = client.post("/api/lab/lessons", json={"docId": doc_id})
    assert r.status_code == 200
    v = r.json()
    # exact LessonView shape the frontend expects — do not change these keys
    assert v["status"] == "awaiting_approval"
    assert v["id"]
    assert [o["title"] for o in v["plan"]["objectives"]] == ["Closures", "Hoisting"]


def test_start_lesson_unknown_doc_is_404(client):
    r = client.post("/api/lab/lessons", json={"docId": "nope"})
    assert r.status_code == 404


def test_approve_then_submit_walks_the_quiz_to_completion(client):
    doc_id = client.post("/api/lab/upload-text", json={"text": "Closures."}).json()["docId"]
    lesson = client.post("/api/lab/lessons", json={"docId": doc_id}).json()
    lid = lesson["id"]
    objectives = lesson["plan"]["objectives"]

    r = client.post(f"/api/lab/lessons/{lid}/approve",
                    json={"objectives": objectives, "questionsPerQuiz": 2})
    assert r.status_code == 200
    v = r.json()
    assert v["status"] == "quizzing"
    assert v["objectivesCount"] == 2
    assert v["objectiveIndex"] == 0
    assert len(v["quiz"]["questions"]) == 2
    assert v["quiz"]["questions"][0]["hint"], "interactive UI needs hint"
    assert v["quiz"]["questions"][0]["explanation"], "interactive UI needs explanation"

    # finish objective 1 → still quizzing, now on objective 2
    v = client.post(f"/api/lab/lessons/{lid}/submit", json={"score": 2, "total": 2}).json()
    assert v["status"] == "quizzing"
    assert v["objectiveIndex"] == 1

    # finish objective 2 → complete, with a summary
    v = client.post(f"/api/lab/lessons/{lid}/submit", json={"score": 2, "total": 2}).json()
    assert v["status"] == "complete"
    assert v["summary"]["overall"] == "Good work."


def test_get_lesson_resumes_state(client):
    doc_id = client.post("/api/lab/upload-text", json={"text": "Closures."}).json()["docId"]
    lid = client.post("/api/lab/lessons", json={"docId": doc_id}).json()["id"]
    r = client.get(f"/api/lab/lessons/{lid}")
    assert r.status_code == 200
    assert r.json()["status"] == "awaiting_approval"


def test_get_unknown_lesson_is_404(client):
    assert client.get("/api/lab/lessons/nope").status_code == 404


def test_ask_returns_a_tutor_answer(client, monkeypatch):
    from app.services.lab import routes as lab_routes

    monkeypatch.setattr(lab_routes, "tutor_answer",
                        lambda doc, objective, question: "Think about scope.")
    doc_id = client.post("/api/lab/upload-text", json={"text": "Closures."}).json()["docId"]
    lid = client.post("/api/lab/lessons", json={"docId": doc_id}).json()["id"]
    r = client.post(f"/api/lab/lessons/{lid}/ask", json={"question": "I'm stuck"})
    assert r.status_code == 200
    assert r.json()["answer"] == "Think about scope."


def test_artifacts_endpoints_are_not_exposed_in_phase_1(client):
    # artifacts_graph.py ships with the package but is deliberately unwired
    # until Phase 3, when it is reshaped into the unified sequenced graph.
    assert client.post("/api/lab/artifacts/start", json={"docId": "x"}).status_code == 404


def test_phase_1_writes_nothing_to_the_learner_model(client, monkeypatch):
    # HARD CONSTRAINT: Mastra (the external service this replaces) writes
    # nothing to our learner model, so this parity migration must not either.
    # concept_performance / quiz_sessions coupling lands in Phase 2, together
    # with the concept resolver — writing them before the resolver exists
    # would start fragmenting concepts immediately.
    from app.services import store as store_mod

    writes: list[tuple] = []

    async def spy_set(collection, doc_id, data):
        writes.append((collection, doc_id))

    async def spy_update(collection, doc_id, changes):
        writes.append((collection, doc_id))

    monkeypatch.setattr(store_mod.store, "set", spy_set)
    monkeypatch.setattr(store_mod.store, "update", spy_update)

    doc_id = client.post("/api/lab/upload-text", json={"text": "Closures."}).json()["docId"]
    lesson = client.post("/api/lab/lessons", json={"docId": doc_id}).json()
    lid = lesson["id"]
    client.post(f"/api/lab/lessons/{lid}/approve",
                json={"objectives": lesson["plan"]["objectives"], "questionsPerQuiz": 1})
    client.post(f"/api/lab/lessons/{lid}/submit", json={"score": 1, "total": 1})
    client.post(f"/api/lab/lessons/{lid}/submit", json={"score": 1, "total": 1})

    touched = {c for c, _ in writes}
    assert "concept_performance" not in touched, f"Phase 1 must not write concepts: {writes}"
    assert "quiz_sessions" not in touched, f"Phase 1 must not write sessions: {writes}"
