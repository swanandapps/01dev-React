import pytest
from fastapi.testclient import TestClient

from app.auth import current_student
from app.main import app
from app.services import enrollment_service


class FakeVectorStore:
    def get_course_lectures(self, course_id):
        if course_id != "react-perf":
            return []
        return [
            {"lecture_id": "react-perf-3-2", "lecture_title": "3.2 - Memoization"},
            {"lecture_id": "react-perf-4-1", "lecture_title": "4.1 - React.memo"},
        ]

    def get_lecture_transcript(self, lecture_id):
        return "React.memo skips a re-render when props are shallowly equal." \
            if lecture_id == "react-perf-4-1" else ""

    def get_lecture_meta(self, lecture_id):
        if lecture_id == "react-perf-4-1":
            return {"lecture_id": lecture_id, "lecture_title": "4.1 - React.memo",
                    "course_id": "react-perf", "course_title": "React Performance Patterns"}
        if lecture_id == "empty-1":
            return {"lecture_id": lecture_id, "lecture_title": "T", "course_id": "react-perf"}
        return None


@pytest.fixture
def client(monkeypatch):
    from app.services import catalog_service
    from app.services.lab import routes as lab_routes

    monkeypatch.setattr(lab_routes, "vector_store", FakeVectorStore())
    # slug (transcript chunks) <-> numeric id (enrollments)
    monkeypatch.setattr(catalog_service, "by_slug",
                        lambda slug: {"id": 7, "slug": slug} if slug == "react-perf" else None)
    state = {"courses": [{"id": 7, "title": "React Performance Patterns"}]}

    async def enrolled(uid):
        return state["courses"] if uid == "s1" else []

    monkeypatch.setattr(enrollment_service, "get_enrolled_courses", enrolled)
    app.dependency_overrides[current_student] = lambda: "s1"
    c = TestClient(app)
    c.state = state
    yield c
    app.dependency_overrides.clear()


def test_lists_lectures_for_a_course(client):
    r = client.get("/api/lab/lectures?course_id=react-perf")
    assert r.status_code == 200
    assert [l["lecture_id"] for l in r.json()] == ["react-perf-3-2", "react-perf-4-1"]


def test_lists_nothing_for_a_course_without_transcripts(client):
    assert client.get("/api/lab/lectures?course_id=nope").json() == []


def test_upload_lecture_creates_a_doc_from_the_transcript(client):
    r = client.post("/api/lab/upload-lecture", json={"lecture_id": "react-perf-4-1"})
    assert r.status_code == 200
    body = r.json()
    assert body["docId"]
    assert body["title"] == "4.1 - React.memo"
    assert body["course_id"] == "react-perf"


def test_uploaded_lecture_drives_generation(client):
    doc = client.post("/api/lab/upload-lecture",
                      json={"lecture_id": "react-perf-4-1"}).json()["docId"]
    from app.services.lab import routes as lab_routes
    assert lab_routes.DOCS[doc]["text"].startswith("React.memo skips")
    assert lab_routes.DOCS[doc]["course_id"] == "react-perf"


def test_generate_passes_course_id_into_the_lesson_graph(client, monkeypatch):
    from app.services.lab import routes as lab_routes
    doc = client.post("/api/lab/upload-lecture",
                      json={"lecture_id": "react-perf-4-1"}).json()["docId"]
    seen = {}

    class FakeGraph:
        def invoke(self, state, cfg):
            seen.update(state)
            return {"status": "awaiting_approval", "proposed_objectives": []}

    class FakeLab:
        def invoke(self, state, cfg):
            return {"artifacts": {}}

    monkeypatch.setattr(lab_routes, "GRAPH", FakeGraph())
    monkeypatch.setattr(lab_routes, "LAB_GRAPH", FakeLab())
    client.post("/api/lab/generate", json={"docId": doc, "outputs": ["quiz"]})
    assert seen["course_id"] == "react-perf"


def test_unknown_lecture_is_403_same_as_not_enrolled(client):
    r = client.post("/api/lab/upload-lecture", json={"lecture_id": "does-not-exist"})
    assert r.status_code == 403


def test_course_missing_from_catalog_is_403(client, monkeypatch):
    from app.services import catalog_service
    monkeypatch.setattr(catalog_service, "by_slug", lambda slug: None)
    r = client.post("/api/lab/upload-lecture", json={"lecture_id": "react-perf-4-1"})
    assert r.status_code == 403


def test_lecture_with_no_extractable_transcript_is_400(client):
    r = client.post("/api/lab/upload-lecture", json={"lecture_id": "empty-1"})
    assert r.status_code == 400


def test_not_enrolled_is_403(client):
    client.state["courses"] = [{"id": 99, "title": "Other"}]
    r = client.post("/api/lab/upload-lecture", json={"lecture_id": "react-perf-4-1"})
    assert r.status_code == 403


def test_no_token_is_401(client):
    app.dependency_overrides.clear()
    r = client.post("/api/lab/upload-lecture", json={"lecture_id": "react-perf-4-1"})
    assert r.status_code == 401
