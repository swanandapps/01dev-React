"""
Lab (app/services/lab, LangGraph, served at /api/lab/*) only builds a quiz
from material the student brings — it has no "quiz me on <topic>" entry point.
Until that gap is closed, a chat request classified as QUIZ_GENERATE gets an
honest hand-off instead of a fake or silently-wrong answer.

The tab name in the message below must match the nav label in
frontend/src/components/Home/Header.tsx — it is directions to a real place.
"""


def build_handoff_message(course_slug: str) -> str:
    return (
        "I can't build a quiz straight from chat yet — Lab needs your "
        "notes first. Head to the Lab tab, upload the notes you want "
        f"quizzed on from '{course_slug}', and it'll generate questions "
        "from that material."
    )
