"""How a student likes to learn ("explain with anime analogies", "Hinglish", "short answers"): one short paragraph
per student, captured from what they say by a background step after each turn, and added to EVERY tutor prompt
(and to the current message) by the backend itself, so using it never depends on the model."""
import json
from types import SimpleNamespace

import pytest

from app.services import chat_pipeline, preference_capture, tutor_agent
from app.services import course_lookup as cl
from app.services import memory_service as ms


@pytest.mark.asyncio
async def test_preferences_are_one_paragraph_that_each_write_replaces():
    uid = "prefs-replace-uid"
    assert await ms.get_learning_preferences(uid) == ""
    await ms.set_learning_preferences(uid, "Prefers anime-character analogies.")
    await ms.set_learning_preferences(uid, "Prefers anime-character analogies. Wants short answers.")
    assert await ms.get_learning_preferences(uid) == "Prefers anime-character analogies. Wants short answers."


@pytest.mark.asyncio
async def test_preferences_are_capped_scrubbed_and_keep_the_rest_of_the_profile():
    uid = "prefs-safety-uid"
    await ms.record_turn(uid, "all-courses", "what is a closure in javascript", "…")
    await ms.set_learning_preferences(uid, "Reach me at someone@example.com. " + "Likes analogies. " * 60)
    saved = await ms.get_learning_preferences(uid)
    assert len(saved) <= ms.MAX_PREFERENCES_CHARS
    assert "someone@example.com" not in saved
    prof = await ms.get_profile(uid)
    assert prof["turn_count"] == 1 and prof["topics"] == ["what is a closure in javascript"]


@pytest.mark.asyncio
async def test_every_prompt_carries_the_preferences_even_for_a_first_time_student():
    uid = "prefs-prompt-uid"
    assert "LIKES TO LEARN" not in await ms.memory_context(uid, "all-courses")
    await ms.set_learning_preferences(uid, "Prefers anime-character analogies.")
    block = await ms.memory_context(uid, "all-courses")                 # no conversations yet
    assert "HOW THIS STUDENT LIKES TO LEARN" in block and "anime-character analogies" in block


def _fake_llm(monkeypatch, reply):
    """Patch the shared OpenAI client so capture() gets `reply` (a dict, or an Exception to raise)."""
    from app.services import llm as llm_mod
    seen = {}

    async def create(**kw):
        seen["user"] = kw["messages"][1]["content"]
        if isinstance(reply, Exception):
            raise reply
        return SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content=json.dumps(reply)))])

    client = SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=create)))
    monkeypatch.setattr(llm_mod.llm, "client", client, raising=False)
    return seen


@pytest.mark.asyncio
async def test_a_lasting_preference_is_saved_and_a_one_off_is_not(monkeypatch):
    uid = "prefs-capture-uid"
    _fake_llm(monkeypatch, {"changed": True, "note": "Prefers anime-character analogies."})
    await preference_capture.capture(uid, "explain things with anime characters from now on")
    assert await ms.get_learning_preferences(uid) == "Prefers anime-character analogies."

    seen = _fake_llm(monkeypatch, {"changed": False, "note": "Prefers anime-character analogies."})
    await preference_capture.capture(uid, "explain it simpler")
    assert "Prefers anime-character analogies." in seen["user"]          # the current note is shown to the model
    assert await ms.get_learning_preferences(uid) == "Prefers anime-character analogies."


@pytest.mark.asyncio
async def test_a_failed_capture_changes_nothing_and_never_raises(monkeypatch):
    uid = "prefs-capture-fail-uid"
    await ms.set_learning_preferences(uid, "Prefers Hinglish.")
    _fake_llm(monkeypatch, TimeoutError("slow"))
    await preference_capture.capture(uid, "from now on use anime")        # must not raise
    assert await ms.get_learning_preferences(uid) == "Prefers Hinglish."


@pytest.mark.asyncio
async def test_the_saved_preference_rides_on_the_message_to_the_tutor_not_on_the_stored_question(monkeypatch):
    uid = "prefs-pipeline-uid"
    await ms.set_learning_preferences(uid, "Prefers anime-character analogies.")
    seen = {}

    async def fake_stream(*, system_prompt, history, question, student_id, model=None, **kw):
        seen["q"], seen["system"] = question, system_prompt
        yield {"type": "token", "value": "Like Naruto's scroll..."}

    async def lookup(question, student_id, scope, history=()):
        return cl.CourseLookup(case=cl.LookupCase.NO_MATCH, hits=[], enrolled_titles=[])

    monkeypatch.setattr(tutor_agent, "stream_answer", fake_stream)
    monkeypatch.setattr(chat_pipeline, "course_lookup", lookup)
    monkeypatch.setattr(preference_capture, "capture_in_background", lambda *a: None)
    req = chat_pipeline.TurnRequest(question="what is a closure", student_id=uid, scope=cl.ChatScope(),
                                    history=[], memory_slug="all-courses")
    [e async for e in chat_pipeline.chat_turn(req)]
    assert seen["q"].startswith("what is a closure") and "Prefers anime-character analogies." in seen["q"]
    assert "HOW THIS STUDENT LIKES TO LEARN" in seen["system"]
    turns = await ms.recent_turns(uid, "all-courses")
    assert turns[-1]["question"] == "what is a closure"                     # stored as the student typed it
