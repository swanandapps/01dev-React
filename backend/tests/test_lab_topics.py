"""Lab topics: every chapter of a course the student owns is a topic; its lectures are solid / shaky / not tried
from the student's quiz answers on that lecture (>= 80% right is solid). Plain rules pick 'Start here' and
'Keep it fresh'. 'Practise this topic' builds a quiz from the lectures that need work."""
import pytest
from fastapi.testclient import TestClient

from app.auth import current_student
from app.main import app
from app.models import TranscriptChunk
from app.services import enrollment_service, lab_topics, lecture_context
from app.services.lab import llm as lab_llm
from app.services.store import store

COURSE = {"id": 2, "slug": "custom-library", "title": "Build a Custom Library", "launched": True, "chapters": [
    {"name": "Chapter 1 - Introduction", "subchapters": ["1.1 - What is this course", "1.2 - What will we build"]},
    {"name": "Chapter 5 - Goodbye Prototype", "subchapters": ["5.1 - Prototype, a Hero Turned Villain",
                                                             "5.2 - When to Use Prototype and When To Not",
                                                             "5.3 - Summary So Far"]},
]}
OTHER = {"id": 9, "slug": "javascript-deep-dive", "title": "JavaScript Deep Dive", "launched": False,
         "chapters": [{"name": "Chapter 1 - Basics", "subchapters": ["1.1 - Values"]}]}


def _ans(lecture, correct):
    return {"question_id": "q", "concept": "c", "difficulty": "", "correct": correct, "lecture": lecture}


@pytest.fixture
def env(monkeypatch):
    who = {"uid": "topic-student"}
    app.dependency_overrides[current_student] = lambda: who["uid"]

    async def owns(student_id):
        return [{"id": 2, "title": "Build a Custom Library"}]

    async def chunks(slug, title):
        return [TranscriptChunk(chunk_id=f"{title}-0", course_id=slug, course_title="x", lecture_id="x-4-0",
                                lecture_title=title, text=f"text of {title}", start_time=0, end_time=50)]

    monkeypatch.setattr(lab_topics.catalog_service, "all_courses", lambda: [COURSE, OTHER])
    monkeypatch.setattr(lab_topics, "_has_transcripts", lambda slug: slug == "custom-library")
    monkeypatch.setattr(enrollment_service, "get_enrolled_courses", owns)
    monkeypatch.setattr(lecture_context, "lecture_chunks", chunks)
    yield TestClient(app), who
    app.dependency_overrides.clear()


async def _seed(uid, rows):
    for i, (when, answers) in enumerate(rows):
        await store.set("quiz_sessions", f"{uid}-{i}", {"session_id": f"{uid}-{i}", "user_id": uid,
                                                        "course_id": "custom-library", "completed_at": when,
                                                        "answers": answers})


async def test_lectures_are_solid_shaky_or_not_tried_from_quiz_answers(env):
    c, who = env
    await _seed(who["uid"], [
        ("2026-10-06T10:00:00+00:00", [_ans("5.1 - Prototype, a Hero Turned Villain", False),
                                       _ans("5.1 - Prototype, a Hero Turned Villain", True),
                                       _ans("5.1 - Prototype, a Hero Turned Villain", False),
                                       _ans("5.3 - Summary So Far", True)]),
    ])
    body = c.get("/api/ai/lab/topics").json()
    assert [co["slug"] for co in body["courses"]] == ["custom-library"]         # owned + has lectures only
    ch5 = body["courses"][0]["topics"][1]
    assert ch5["name"] == "Goodbye Prototype" and (ch5["solid"], ch5["shaky"], ch5["untried"]) == (1, 1, 1)
    lec = {l["title"]: l for l in ch5["lectures"]}
    assert (lec["5.1 - Prototype, a Hero Turned Villain"]["status"], lec["5.1 - Prototype, a Hero Turned Villain"]["right"],
            lec["5.1 - Prototype, a Hero Turned Villain"]["total"]) == ("shaky", 1, 3)
    assert lec["5.3 - Summary So Far"]["status"] == "solid" and lec["5.2 - When to Use Prototype and When To Not"]["status"] == "not_tried"
    assert (lec["5.1 - Prototype, a Hero Turned Villain"]["chapter"], lec["5.1 - Prototype, a Hero Turned Villain"]["sub"]) == (1, 0)


async def test_start_here_is_the_weakest_topic_with_a_reason_from_the_numbers(env):
    c, who = env
    who["uid"] = "weak-student"
    await _seed("weak-student", [("2026-10-06T10:00:00+00:00", [
        _ans("1.1 - What is this course", True), _ans("1.1 - What is this course", False),
        _ans("5.1 - Prototype, a Hero Turned Villain", False), _ans("5.1 - Prototype, a Hero Turned Villain", False)])])
    start = c.get("/api/ai/lab/topics").json()["start_here"]
    assert (start["slug"], start["topic"]) == ("custom-library", 1)
    assert start["why"] == "You got 0 of 2 right on 5.1 - Prototype, a Hero Turned Villain."


async def test_keep_it_fresh_is_an_all_solid_topic_not_practised_for_a_week(env):
    c, who = env
    who["uid"] = "fresh-student"
    await _seed("fresh-student", [("2026-09-01T10:00:00+00:00", [
        _ans("1.1 - What is this course", True), _ans("1.2 - What will we build", True)])])
    body = c.get("/api/ai/lab/topics").json()
    assert body["start_here"] is None
    assert (body["keep_fresh"]["topic"], body["keep_fresh"]["why"].startswith("Last practised")) == (0, True)


def test_a_new_student_sees_topics_but_no_suggestions_yet(env):
    c, who = env
    who["uid"] = "brand-new"
    body = c.get("/api/ai/lab/topics").json()
    assert body["courses"][0]["topics"][0]["untried"] == 2 and body["start_here"] is None and body["keep_fresh"] is None


async def test_practise_this_topic_asks_about_the_lectures_that_need_work_and_tags_each_question(env, monkeypatch):
    c, who = env
    who["uid"] = "quiz-student"
    await _seed("quiz-student", [("2026-10-06T10:00:00+00:00", [
        _ans("5.3 - Summary So Far", True), _ans("5.1 - Prototype, a Hero Turned Villain", False)])])
    asked = []

    def gen(document, objective, n, concepts=None):
        asked.append(document)
        return [{"question": f"Q on {document}?", "options": ["a", "b", "c", "d"], "correctIndex": 0,
                 "explanation": "e", "hint": "h", "concept": "k"} for _ in range(n)]

    monkeypatch.setattr(lab_llm, "gen_quiz", gen)
    r = c.post("/api/ai/lab/topic-quiz", json={"course_id": "custom-library", "chapter": 1})
    assert r.status_code == 200
    body = r.json()
    lectures = [q["lecture"] for q in body["questions"]]
    assert lectures[:2] == ["5.1 - Prototype, a Hero Turned Villain"] * 2       # shaky first
    assert lectures[2:4] == ["5.2 - When to Use Prototype and When To Not"] * 2  # then not tried
    assert "5.3 - Summary So Far" in lectures                                   # solid last
    res = c.post(f"/api/ai/quick-quiz/{body['quiz_id']}/submit", json={"answers": [0] * len(lectures)}).json()
    assert res["score"] == len(lectures)
    row = await store.get("quiz_sessions", f"quick-{body['quiz_id']}")
    assert [a["lecture"] for a in row["answers"]] == lectures and row["source"] == "lab_topic"


def test_topic_quiz_needs_an_owned_course_and_a_real_chapter(env, monkeypatch):
    c, _ = env

    async def none(student_id):
        return []

    assert c.post("/api/ai/lab/topic-quiz", json={"course_id": "custom-library", "chapter": 9}).status_code == 404
    monkeypatch.setattr(enrollment_service, "get_enrolled_courses", none)
    assert c.post("/api/ai/lab/topic-quiz", json={"course_id": "custom-library", "chapter": 1}).status_code == 403
