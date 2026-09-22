"""
QuizMe (app/services/lab, LangGraph, served at /api/lab/*) only builds a quiz
from uploaded notes — it has no "quiz me on <topic>" entry point. Until that
gap is closed, a chat request classified as QUIZ_GENERATE gets an honest
hand-off instead of a fake or silently-wrong answer.
"""


def build_handoff_message(course_slug: str) -> str:
    return (
        "I can't build a quiz straight from chat yet — QuizMe needs your "
        "notes first. Head to the QuizMe tab, upload the notes you want "
        f"quizzed on from '{course_slug}', and it'll generate questions "
        "from that material."
    )
