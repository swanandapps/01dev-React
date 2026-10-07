"""Lab page side panel: the student's recent quiz sessions and the concepts worth revisiting — read straight
from quiz_sessions and concept_performance, no model call. Only the logged-in student's own data."""
import pytest
from fastapi.testclient import TestClient

from app.auth import current_student
from app.main import app
from app.services.store import store


@pytest.fixture
def client():
    app.dependency_overrides[current_student] = lambda: "me"
    yield TestClient(app)
    app.dependency_overrides.clear()


async def _seed():
    rows = [
        ("s1", "me", "2026-10-01T10:00:00+00:00", {"source": "lecture", "doc_title": "Lecture: 6.5 - IIFE, To The Rescue", "score": 2, "total": 3}),
        ("s2", "me", "2026-10-03T10:00:00+00:00", {"source": "player_quick_quiz", "course_title": "Build a Custom Library",
                                                     "answers": [{"lecture": "5.1 - Prototype, a Hero Turned Villain"}], "score": 3, "total": 3}),
        ("s3", "me", "2026-10-02T10:00:00+00:00", {"source": "self_study", "doc_title": "React hooks", "score": 4, "total": 6}),
        ("x1", "other", "2026-10-04T10:00:00+00:00", {"source": "self_study", "doc_title": "Not mine", "score": 1, "total": 1}),
    ]
    for sid, uid, at, extra in rows:
        await store.set("quiz_sessions", sid, {"session_id": sid, "user_id": uid, "completed_at": at, **extra})
    for concept, acc, n in (("Prototype Pollution", 0.33, 3), ("IIFE", 0.9, 10), ("Module Pattern", 0.5, 4)):
        await store.set("concept_performance", f"me::{concept}",
                        {"user_id": "me", "concept": concept, "accuracy": acc, "attempts": n,
                         "correct": round(acc * n), "last_seen": "2026-10-03"})


async def test_recent_sessions_newest_first_with_readable_titles_and_only_mine(client):
    await _seed()
    body = client.get("/api/ai/lab/overview").json()
    assert [r["title"] for r in body["recent"]] == ["5.1 - Prototype, a Hero Turned Villain", "React hooks",
                                                   "6.5 - IIFE, To The Rescue"]
    assert body["recent"][0] == {"title": "5.1 - Prototype, a Hero Turned Villain", "kind": "Quick check",
                                 "score": 3, "total": 3, "completed_at": "2026-10-03T10:00:00+00:00"}


async def test_worth_revisiting_lists_weak_concepts_worst_first(client):
    await _seed()
    weak = client.get("/api/ai/lab/overview").json()["weak"]
    assert [w["concept"] for w in weak][:2] == ["Prototype Pollution", "Module Pattern"]
    assert "IIFE" not in [w["concept"] for w in weak]


def test_a_new_student_gets_empty_lists(client):
    app.dependency_overrides[current_student] = lambda: "brand-new-student"
    assert client.get("/api/ai/lab/overview").json() == {"recent": [], "weak": []}
