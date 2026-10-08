"""The tutor's memory of a student lists what they worked on, not their raw words: the lecture for a player
question, the cited lecture for an Ask answer, the question itself only when it says something, and never
filler like "yes" or "Explain this" on its own."""
import pytest

from app.services import memory_service as ms
from app.services.store import store


def test_a_player_question_is_remembered_as_its_lecture():
    assert ms.topic_label("Explain this", lecture_title="5.2 - Writing an Event Loop Simulator") \
        == "5.2 - Writing an Event Loop Simulator"
    assert ms.topic_label("tell me about the commands with example", lecture_title="11.2 - npm publish") \
        == "11.2 - npm publish"


def test_an_ask_answer_is_remembered_as_the_lecture_it_cited():
    card = {"lecture_title": "8.1 - The npm link command", "course_title": "Build a Custom Library"}
    assert ms.topic_label("how do I test my package locally", cited=card) \
        == "8.1 - The npm link command (Build a Custom Library)"


def test_without_a_lecture_a_real_question_is_kept_and_filler_is_dropped():
    assert ms.topic_label("what is a closure in javascript") == "what is a closure in javascript"
    for filler in ("yes", "ok thanks", "Sure!", "no", "Explain this", "I'm confused about this part", "  "):
        assert ms.topic_label(filler) is None, filler


@pytest.mark.asyncio
async def test_record_turn_keeps_topics_useful():
    uid = "topics-test-uid"
    await ms.record_turn(uid, "javascript-deep-dive", "Explain this", "…", topic="5.2 - Event Loop")
    await ms.record_turn(uid, "javascript-deep-dive", "and this?", "…", topic="5.2 - Event Loop")   # same lecture
    await ms.record_turn(uid, "all-courses", "yes", "…")                                          # filler
    await ms.record_turn(uid, "all-courses", "what is a closure in javascript", "…")
    prof = await store.get("student_profile", uid)
    assert prof["turn_count"] == 4                      # every exchange still counts
    assert prof["topics"] == ["5.2 - Event Loop", "what is a closure in javascript"]
