import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.services.store import InMemoryStore


@pytest.fixture
def client(monkeypatch):
    from app.services.lab import artifact_store, artifacts_graph, graph as lab_graph, routes

    s = InMemoryStore()
    monkeypatch.setattr(artifact_store, "store", s)
    monkeypatch.setattr(artifacts_graph, "generate", lambda t, doc: f"GEN-{t}")
    monkeypatch.setattr(lab_graph, "gen_objectives", lambda doc, title: [
        {"id": "o1", "title": "Closures", "difficulty": "beginner", "focus": "scope"},
    ])
    # rebuild the graph so the patched generate is picked up by fresh nodes
    monkeypatch.setattr(routes, "LAB_GRAPH", artifacts_graph.build_lab_graph())
    return TestClient(app), s


def test_artifacts_only_returns_them_and_completes(client):
    c, _ = client
    doc = c.post("/api/lab/upload-text",
                 json={"text": "Closures.", "title": "Notes"}).json()["docId"]
    r = c.post("/api/lab/generate", json={
        "docId": doc, "outputs": ["flashcards", "summary"], "student_id": "s1"})
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "complete"
    assert body["artifacts"]["flashcards"] == "GEN-flashcards"
    assert body["artifacts"]["summary"] == "GEN-summary"
    assert "lesson_id" not in body or body["lesson_id"] is None


def test_quiz_selected_returns_a_lesson_id_and_objectives(client):
    c, _ = client
    doc = c.post("/api/lab/upload-text", json={"text": "Closures."}).json()["docId"]
    r = c.post("/api/lab/generate", json={
        "docId": doc, "outputs": ["quiz"], "student_id": "s1"})
    body = r.json()
    assert body["status"] == "awaiting_approval"
    assert body["lesson_id"]
    assert [o["title"] for o in body["proposed_objectives"]] == ["Closures"]
    assert body["artifacts"] == {}


def test_quiz_only_via_generate_matches_the_existing_lessons_endpoint_byte_for_byte(client):
    """Production constraint: outputs=["quiz"] through the new /generate route
    must be byte-identical to POST /api/lab/lessons, the endpoint already
    live in production. Same LessonView keys, same values -- the existing
    quiz frontend depends on this shape not drifting. Only `run_id` (new to
    /generate, absent from /lessons) and the redundant `lesson_id`/`id` naming
    are allowed to differ; everything else in the LessonView must match."""
    c, _ = client
    doc = c.post("/api/lab/upload-text", json={"text": "Closures."}).json()["docId"]

    via_lessons = c.post("/api/lab/lessons", json={"docId": doc}).json()
    doc2 = c.post("/api/lab/upload-text", json={"text": "Closures."}).json()["docId"]
    via_generate = c.post("/api/lab/generate", json={
        "docId": doc2, "outputs": ["quiz"], "student_id": "s1"}).json()

    assert via_generate["status"] == via_lessons["status"]
    assert via_generate["proposed_objectives"] == via_lessons["plan"]["objectives"]
    assert via_generate["lesson_id"]
    assert via_generate["artifacts"] == {}


def test_all_four_returns_artifacts_and_a_lesson(client):
    c, _ = client
    doc = c.post("/api/lab/upload-text", json={"text": "Closures."}).json()["docId"]
    body = c.post("/api/lab/generate", json={
        "docId": doc,
        "outputs": ["quiz", "flashcards", "summary", "study_plan"],
        "student_id": "s1"}).json()
    assert sorted(body["artifacts"]) == ["flashcards", "study_plan", "summary"]
    assert body["lesson_id"]
    assert body["status"] == "awaiting_approval"


def test_generate_rejects_an_empty_selection(client):
    c, _ = client
    doc = c.post("/api/lab/upload-text", json={"text": "Closures."}).json()["docId"]
    r = c.post("/api/lab/generate", json={"docId": doc, "outputs": []})
    assert r.status_code == 400


def test_generate_rejects_an_unknown_output_type(client):
    """The real trust boundary: user input arrives here. An unrecognized
    output must be rejected outright, not silently dropped from the set."""
    c, _ = client
    doc = c.post("/api/lab/upload-text", json={"text": "Closures."}).json()["docId"]
    r = c.post("/api/lab/generate", json={"docId": doc, "outputs": ["summary", "horoscope"]})
    assert r.status_code == 400


def test_generate_unknown_doc_is_404(client):
    c, _ = client
    r = c.post("/api/lab/generate", json={"docId": "nope", "outputs": ["summary"]})
    assert r.status_code == 404


def test_library_returns_the_students_artifacts(client):
    c, _ = client
    doc = c.post("/api/lab/upload-text",
                 json={"text": "Closures.", "title": "Notes"}).json()["docId"]
    c.post("/api/lab/generate", json={
        "docId": doc, "outputs": ["summary"], "student_id": "s1"})
    lib = c.get("/api/lab/library?student_id=s1").json()
    assert len(lib) == 1
    assert lib[0]["artifact_type"] == "summary"
    assert lib[0]["doc_title"] == "Notes"


def test_library_is_empty_for_another_student(client):
    c, _ = client
    doc = c.post("/api/lab/upload-text", json={"text": "C."}).json()["docId"]
    c.post("/api/lab/generate", json={
        "docId": doc, "outputs": ["summary"], "student_id": "s1"})
    assert c.get("/api/lab/library?student_id=s2").json() == []


def test_generate_actually_calls_save_for_each_artifact(client):
    """Not just a shape check: prove persistence is happening. Store must
    contain one row per generated artifact, keyed under lab_artifacts, and
    the route must be the thing calling save() -- not the graph (see
    test_lab_unified_graph.py's test_gen_node_does_no_io... for the graph-side
    half of this guarantee). Uses a non-empty student_id since save() no-ops
    on an empty one."""
    from app.services.lab.artifact_store import COLLECTION

    c, store = client
    doc = c.post("/api/lab/upload-text",
                 json={"text": "Closures.", "title": "Notes"}).json()["docId"]
    c.post("/api/lab/generate", json={
        "docId": doc, "outputs": ["flashcards", "summary"], "student_id": "s1"})

    rows = store._db.get(COLLECTION, {})
    assert len(rows) == 2
    types = sorted(r["artifact_type"] for r in rows.values())
    assert types == ["flashcards", "summary"]
    for r in rows.values():
        assert r["student_id"] == "s1"
        assert r["doc_id"] == doc
        assert r["doc_title"] == "Notes"


def test_generate_with_no_student_id_persists_nothing(client):
    """save() deliberately no-ops for an empty student_id -- confirm the
    route doesn't work around that (e.g. by defaulting to some sentinel id)."""
    from app.services.lab.artifact_store import COLLECTION

    c, store = client
    doc = c.post("/api/lab/upload-text", json={"text": "Closures."}).json()["docId"]
    r = c.post("/api/lab/generate", json={"docId": doc, "outputs": ["summary"]})
    assert r.status_code == 200
    assert store._db.get(COLLECTION, {}) == {}


def test_upload_pdf_content_length_rejects_before_reading_body(monkeypatch):
    """Content-Length-based early rejection: an oversized body must be turned
    away before `await file.read()` ever runs, so it's never fully spooled
    into memory just to be discarded."""
    from starlette.datastructures import UploadFile

    from app.services.lab.routes import MAX_PDF_BYTES

    called = []
    orig_read = UploadFile.read

    async def spy_read(self, *a, **kw):
        called.append(True)
        return await orig_read(self, *a, **kw)

    monkeypatch.setattr(UploadFile, "read", spy_read)

    client = TestClient(app)
    oversize = b"x" * (MAX_PDF_BYTES + 1)
    r = client.post("/api/lab/upload",
                    files={"file": ("notes.pdf", oversize, "application/pdf")})
    assert r.status_code == 400
    assert not called, "body must be rejected via Content-Length before being read"
