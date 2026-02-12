"""
Per-course "How you're doing" insight.

One GPT call synthesizes several signals for a single course into a short,
honest progress report — what the student is doing well, where they need to
improve, and concrete next steps. Signals:

  - quiz/adaptive performance  (per-concept accuracy + recent session scores)
  - chat history               (topics the student has been asking about → confusion)
  - video rewatches            (lectures replayed → likely sticking points)

Performance/sessions are read from the store; chat questions and rewatch counts
are passed in from the client (chat history + rewatch tracking live there).
"""

from typing import List

from app.services.llm import llm
from app.services.store import store
from app.services.vector_store import vector_store

SYSTEM_PROMPT = """You are a candid, encouraging learning coach for the 0.1% Dev platform.
Given a student's signals for ONE course, write a short progress report. Be specific and
honest — name the concepts/lectures involved. If there's little data, say so and suggest a
starting point. Ground everything in the signals provided; do not invent performance.

Return a JSON object with EXACTLY this shape:
{
  "summary": "1-2 sentence honest overview of how they're doing in this course",
  "doing_well": ["short point", ...],     // 0-3 items
  "improve": ["concept or topic to focus on, with why", ...],   // 0-4 items
  "next_steps": ["a concrete action, e.g. rewatch a lecture / practice a concept / ask about X", ...]  // 1-3 items
}"""


async def generate(
    user_id: str,
    course_id: str,
    chat_questions: List[str],
    rewatched_lectures: List[str],
) -> dict:
    meta = vector_store.get_course_meta(course_id)
    if not meta:
        return {"summary": "This course isn't available.", "doing_well": [], "improve": [], "next_steps": []}

    qdoc = await store.get("questions", course_id)
    course_concepts = sorted({q["concept"] for q in qdoc["questions"]}) if qdoc else []
    course_lectures = [l["lecture_title"] for l in meta.get("lectures", [])]

    perf_all = await store.query("concept_performance", "user_id", user_id)
    perf = [p for p in perf_all if p["concept"] in course_concepts]

    sessions = [s for s in await store.query("quiz_sessions", "user_id", user_id) if s["course_id"] == course_id]

    # Build the signals summary for the model.
    lines = [f"Course: {meta['course_title']}", f"Lectures: {', '.join(course_lectures) or 'n/a'}"]

    if sessions:
        avg = sum(s["score"] / max(s["total"], 1) for s in sessions) / len(sessions)
        lines.append(f"Practice: {len(sessions)} adaptive session(s), average {round(avg * 100)}%.")
    else:
        lines.append("Practice: no practice sessions on this course yet.")

    if perf:
        strong = [p for p in perf if p["accuracy"] >= 0.8 and p["attempts"] > 0]
        weak = sorted([p for p in perf if p["accuracy"] < 0.8 and p["attempts"] > 0], key=lambda p: p["accuracy"])
        if strong:
            lines.append("Strong concepts: " + ", ".join(f"{p['concept']} ({round(p['accuracy']*100)}%)" for p in strong))
        if weak:
            lines.append("Weak concepts: " + ", ".join(f"{p['concept']} ({round(p['accuracy']*100)}%)" for p in weak))

    # Rewatched lectures relevant to this course (likely sticking points).
    rw = [l for l in rewatched_lectures if l in course_lectures]
    if rw:
        lines.append("Rewatched lectures (possible sticking points): " + ", ".join(rw))

    if chat_questions:
        lines.append("Recently asked the AI: " + " | ".join(chat_questions[:8]))

    data = await llm.generate_json(SYSTEM_PROMPT, "\n".join(lines), max_tokens=700)
    if not data:
        return {
            "summary": "Couldn't generate insights right now. Try a practice session to get started.",
            "doing_well": [],
            "improve": [],
            "next_steps": ["Run an adaptive practice session for this course."],
        }
    return {
        "summary": data.get("summary", ""),
        "doing_well": data.get("doing_well", []),
        "improve": data.get("improve", []),
        "next_steps": data.get("next_steps", []),
    }
