import pytest

from app.services import concept_explain
from app.services.store import InMemoryStore


@pytest.fixture
def store(monkeypatch):
    s = InMemoryStore()
    monkeypatch.setattr(concept_explain, "store", s)
    return s


async def test_attributes_attempts_to_their_sources(store):
    await store.set("quiz_sessions", "course-1", {
        "user_id": "s1", "course_id": "react-perf",
        "course_title": "React Performance Patterns",
        "completed_at": "2026-09-01T00:00:00+00:00",
        "answers": [
            {"concept": "react-memo", "correct": True},
            {"concept": "react-memo", "correct": True},
            {"concept": "use-memo", "correct": False},
        ],
    })
    await store.set("quiz_sessions", "lab-1", {
        "user_id": "s1", "course_id": None, "course_title": "Your own material",
        "doc_title": "React Perf Notes", "source": "self_study",
        "completed_at": "2026-09-18T00:00:00+00:00",
        "answers": [
            {"concept": "react-memo", "raw_concept": "React.memo", "correct": True},
            {"concept": "react-memo", "raw_concept": "memo wrapper", "correct": False},
        ],
    })

    out = await concept_explain.explain_concept("s1", "react-memo")

    assert out["concept"] == "react-memo"
    assert (out["attempts"], out["correct"], out["accuracy"]) == (4, 3, 0.75)
    by_label = {s["label"]: s for s in out["sources"]}
    course = by_label["React Performance Patterns"]
    assert (course["attempts"], course["correct"], course["source"]) == (2, 2, "course")
    notes = by_label["React Perf Notes"]
    assert (notes["attempts"], notes["correct"], notes["source"]) == (2, 1, "self_study")
    assert notes["last_at"] == "2026-09-18T00:00:00+00:00"


async def test_matches_by_slug_so_loose_spellings_still_count(store):
    await store.set("quiz_sessions", "a", {
        "user_id": "s1", "course_title": "C", "completed_at": "2026-09-01T00:00:00+00:00",
        "answers": [{"concept": "React.memo", "correct": True}],
    })
    out = await concept_explain.explain_concept("s1", "react-memo")
    assert out["attempts"] == 1


async def test_merged_tags_come_from_this_students_raw_concepts(store):
    await store.set("quiz_sessions", "lab-1", {
        "user_id": "s1", "doc_title": "Notes", "source": "self_study",
        "completed_at": "2026-09-18T00:00:00+00:00",
        "answers": [
            {"concept": "use-callback", "raw_concept": "useCallback hook", "correct": True},
            {"concept": "use-callback", "raw_concept": "useCallback hook", "correct": False},
            {"concept": "use-callback", "raw_concept": "use-callback", "correct": True},
            {"concept": "use-callback", "correct": True},
        ],
    })
    out = await concept_explain.explain_concept("s1", "use-callback")
    # identical-slug raw tags and absent raw tags are not merges
    assert out["merged_tags"] == [{"candidate": "useCallback hook", "count": 2}]


async def test_another_students_sessions_and_resolutions_never_appear(store):
    await store.set("quiz_sessions", "theirs", {
        "user_id": "s2", "doc_title": "Their private notes", "source": "self_study",
        "completed_at": "2026-09-18T00:00:00+00:00",
        "answers": [{"concept": "react-memo", "raw_concept": "secret tag", "correct": True}],
    })
    await store.set("concept_resolutions", "r1", {
        "candidate": "secret tag", "resolved_to": "react-memo", "method": "embedding", "score": 0.7})

    out = await concept_explain.explain_concept("s1", "react-memo")

    assert out["attempts"] == 0
    assert out["sources"] == []
    assert out["merged_tags"] == []
    assert "secret" not in str(out)


async def test_unknown_concept_reports_no_attempts(store):
    out = await concept_explain.explain_concept("s1", "kubernetes")
    assert out["attempts"] == 0
    assert out["sources"] == []
    assert out["accuracy"] is None
    assert out["merged_tags"] == []


async def test_course_and_lab_doc_with_the_same_title_stay_separate_sources(store):
    await store.set("quiz_sessions", "course-1", {
        "user_id": "s1", "course_id": "react-perf", "course_title": "X",
        "completed_at": "2026-09-01T00:00:00+00:00",
        "answers": [{"concept": "react-memo", "correct": True}],
    })
    await store.set("quiz_sessions", "lab-1", {
        "user_id": "s1", "course_id": None, "course_title": "Your own material",
        "doc_id": "d1", "doc_title": "X", "source": "self_study",
        "completed_at": "2026-09-18T00:00:00+00:00",
        "answers": [{"concept": "react-memo", "correct": False}],
    })
    out = await concept_explain.explain_concept("s1", "react-memo")
    assert len(out["sources"]) == 2
    assert {(s["label"], s["source"]) for s in out["sources"]} == {("X", "course"), ("X", "self_study")}


async def test_lecture_session_is_labelled_as_a_lecture_source(store):
    await store.set("quiz_sessions", "lab-2", {
        "user_id": "s1", "course_id": None, "course_title": "4.1 - React.memo and useCallback",
        "doc_id": "d2", "doc_title": "4.1 - React.memo and useCallback", "source": "lecture",
        "completed_at": "2026-09-19T00:00:00+00:00",
        "answers": [{"concept": "react-memo", "correct": True}],
    })
    out = await concept_explain.explain_concept("s1", "react-memo")
    assert [(s["label"], s["source"]) for s in out["sources"]] == [("4.1 - React.memo and useCallback", "lecture")]


async def _lab_session(store, sid, answers):
    await store.set("quiz_sessions", sid, {
        "user_id": "s1", "course_id": None, "course_title": "Your own material",
        "doc_id": sid, "doc_title": f"Doc {sid}", "source": "self_study",
        "completed_at": "2026-10-05T00:00:00+00:00", "answers": answers,
    })


async def test_loose_name_counts_the_students_concepts_that_contain_it(store):
    # The model asks about "React.memo"; the resolver stored the student's
    # attempts under more specific canonical names. Exact-only matching said
    # "no attempts" — reproduced live against the real tutor.
    await _lab_session(store, "a", [
        {"concept": "react-memo-purpose", "correct": True},
        {"concept": "react-memo-behavior", "correct": False},
        {"concept": "use-callback-basics", "correct": True},
    ])

    out = await concept_explain.explain_concept("s1", "React.memo")

    assert (out["attempts"], out["correct"]) == (2, 1)
    assert out["matched_concepts"] == ["react-memo-behavior", "react-memo-purpose"]


async def test_exact_match_wins_over_containment(store):
    await _lab_session(store, "a", [
        {"concept": "react-memo", "correct": True},
        {"concept": "react-memo-purpose", "correct": False},
    ])

    out = await concept_explain.explain_concept("s1", "react-memo")

    assert (out["attempts"], out["correct"]) == (1, 1)
    assert out["matched_concepts"] == ["react-memo"]


async def test_no_match_returns_the_students_own_concept_names(store):
    await _lab_session(store, "a", [
        {"concept": "react-memo-purpose", "correct": True},
        {"concept": "react-memo-purpose", "correct": True},
        {"concept": "use-callback-basics", "correct": False},
    ])
    await store.set("quiz_sessions", "other", {
        "user_id": "s2", "answers": [{"concept": "secret-topic", "correct": True}]})

    out = await concept_explain.explain_concept("s1", "event loop")

    assert out["attempts"] == 0
    assert out["matched_concepts"] == []
    assert out["known_concepts"] == ["react-memo-purpose", "use-callback-basics"]
