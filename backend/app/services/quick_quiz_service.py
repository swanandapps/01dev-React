"""The player's 'Quiz me': a few multiple-choice questions on what the student has watched of a lecture.

create() makes the questions and keeps the answer key on the server; submit() grades, records the result in the
learner model — one quiz_sessions row plus concept performance, exactly what a course or Lab quiz writes, so the
dashboard and recommendations move — and only then reveals the answers. Submitting twice counts once."""
import asyncio
import uuid
from datetime import datetime, timezone
from typing import Optional, Sequence

from app.services import adaptive_service, concept_resolver, lecture_context, recommendation_service
from app.services.lab import llm as lab_llm
from app.services.store import store

QUESTIONS = 3
MIN_PASSAGES = 3   # early in the video there is little watched yet: still ask about the opening
COLLECTION = "quick_quizzes"
TOPIC_LECTURES = 3      # Lab 'Practise this topic': the lectures that need the most work ...
PER_LECTURE = 2         # ... two questions each


class QuizNotFound(Exception):
    pass


class BadAnswers(Exception):
    pass


def _objective(lecture: str) -> dict:
    return {"title": f"Key ideas of {lecture}", "difficulty": "beginner",
            "focus": "what the instructor explained in this part of the lecture"}


async def _save(student_id: str, course: dict, lecture: str, questions: list[dict], source: str) -> dict:
    quiz_id = uuid.uuid4().hex
    await store.set(COLLECTION, quiz_id, {
        "quiz_id": quiz_id, "student_id": student_id, "course_slug": course["slug"],
        "course_title": course.get("title", ""), "lecture": lecture, "questions": questions, "source": source,
        "created_at": datetime.now(timezone.utc).isoformat(),
    })
    return {"quiz_id": quiz_id,
            "questions": [{"question": q["question"], "options": q["options"], "lecture": q.get("lecture", lecture)}
                          for q in questions]}


async def create_for_topic(student_id: str, course: dict, chapter: int) -> Optional[dict]:
    """Lab 'Practise this topic': PER_LECTURE questions from each of the TOPIC_LECTURES lectures of the chapter that
    need the most work (shaky, then not tried, then solid), each question tagged with its lecture."""
    from app.services import lab_topics  # local: lab_topics imports nothing from here, keep it one-way
    titles = await lab_topics.lectures_to_practise(student_id, course, chapter, limit=len(course["chapters"][chapter]["subchapters"]))
    picked = []
    for title in titles:
        chunks = await lecture_context.lecture_chunks(course["slug"], title)
        if chunks:
            picked.append((title, "\n\n".join(c.text_clean or c.text for c in chunks)))
        if len(picked) == TOPIC_LECTURES:
            break
    if not picked:
        return None
    batches = await asyncio.gather(*(asyncio.to_thread(lab_llm.gen_quiz, doc, _objective(title), PER_LECTURE)
                                     for title, doc in picked))
    questions = [{**q, "lecture": title} for (title, _), batch in zip(picked, batches) for q in batch]
    return await _save(student_id, course, course["chapters"][chapter]["name"], questions, "lab_topic")


async def create(student_id: str, course: dict, lecture: str, position: Optional[float]) -> Optional[dict]:
    """None when the lecture has no transcript."""
    chunks = await lecture_context.lecture_chunks(course["slug"], lecture)
    if not chunks:
        return None
    watched = chunks if position is None else [c for c in chunks if c.start_time <= position]
    watched = watched if len(watched) >= MIN_PASSAGES else chunks[:MIN_PASSAGES]
    document = "\n\n".join(c.text_clean or c.text for c in watched)
    objective = _objective(lecture)
    questions = await asyncio.to_thread(lab_llm.gen_quiz, document, objective, QUESTIONS)
    return await _save(student_id, course, lecture, questions, "player_quick_quiz")


async def submit(student_id: str, quiz_id: str, answers: Sequence[int]) -> dict:
    doc = await store.get(COLLECTION, quiz_id)
    if not doc or doc.get("student_id") != student_id:
        raise QuizNotFound(quiz_id)  # another student's quiz looks the same as a missing one
    if doc.get("result"):
        return doc["result"]
    qs = doc["questions"]
    if len(answers) != len(qs) or any(not isinstance(a, int) or not 0 <= a < len(q["options"])
                                      for a, q in zip(answers, qs)):
        raise BadAnswers(quiz_id)

    graded = [(q, a == q["correctIndex"]) for q, a in zip(qs, answers)]
    concepts = {}
    for q, _ in graded:
        raw = (q.get("concept") or "").strip() or doc["lecture"]
        if raw not in concepts:
            concepts[raw] = await concept_resolver.resolve(raw, doc["course_slug"])
    concept_of = [concepts[(q.get("concept") or "").strip() or doc["lecture"]] for q, _ in graded]
    score = sum(1 for _, ok in graded if ok)
    result = {
        "score": score, "total": len(graded),
        "results": [{"correct": ok, "correctIndex": q["correctIndex"], "explanation": q.get("explanation", "")}
                    for q, ok in graded],
    }

    # The result is the idempotency marker, written before the performance updates (as Lab does): a failure
    # partway under-counts rather than double-counts on a retry.
    await store.set(COLLECTION, quiz_id, {**doc, "result": result})
    breakdown: dict[str, dict] = {}
    for c, (_, ok) in zip(concept_of, graded):
        row = breakdown.setdefault(c, {"concept": c, "attempts": 0, "correct": 0})
        row["attempts"] += 1
        row["correct"] += 1 if ok else 0
    await store.set("quiz_sessions", f"quick-{quiz_id}", {
        "session_id": f"quick-{quiz_id}", "user_id": student_id, "course_id": doc["course_slug"],
        "course_title": doc["course_title"], "source": doc.get("source", "player_quick_quiz"), "score": score,
        "total": len(graded),
        "answers": [{"question_id": f"{quiz_id}-{i}", "concept": c, "difficulty": "", "correct": ok,
                     "time_taken_ms": 0, "lecture": q.get("lecture", doc["lecture"])}
                    for i, (c, (q, ok)) in enumerate(zip(concept_of, graded))],
        "concept_breakdown": sorted(({**r, "accuracy": round(r["correct"] / r["attempts"], 3)}
                                     for r in breakdown.values()), key=lambda r: r["accuracy"]),
        "completed_at": datetime.now(timezone.utc).isoformat(),
    })
    for c, (_, ok) in zip(concept_of, graded):
        await adaptive_service._update_perf(student_id, c, ok)
    await recommendation_service.invalidate(student_id)
    return result
