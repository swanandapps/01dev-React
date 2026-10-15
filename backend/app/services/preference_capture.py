"""How a student likes to learn, captured from what they say (spec: learning preferences).

After every tutor turn, in the background (the student never waits on it), one small JSON call reads the
student's message and their current preferences note and decides whether the message said something LASTING
about how they learn ("explain with anime characters from now on", "in Hinglish", "I'm a backend dev"). If so
it returns the whole updated note, which replaces the old one: one short paragraph per student, in the tutor
memory record. Done in code rather than as a tutor tool because a live check showed the model rarely chose to
call a save tool mid-answer.
"""
import asyncio
import json
import logging

from app.services import memory_service

logger = logging.getLogger(__name__)
TIMEOUT_S = 10.0

SYSTEM = """You keep a short note on how ONE student likes to learn, for their tutor. You get the current note
(may be empty) and the student's latest message. Return JSON {"changed": true|false, "note": "..."}.

changed is true ONLY when the message states something LASTING about how they learn or who they are:
- analogies or examples they like ("explain with anime characters", "use real-life analogies")
- language ("in Hinglish", "explain in Hindi")
- length or depth ("keep answers short", "go deep")
- order ("examples first", "code before theory")
- background or goal ("I'm a backend dev", "preparing for interviews")
A one-off request about the current answer only ("explain it simpler", "give another example", "shorter")
is NOT lasting, unless they say it should always apply ("always", "from now on").

note: the complete updated note in the third person, at most three short sentences, keeping earlier points
unless the student changed them. Write only what the student actually said; never add anything.
If changed is false, return the current note unchanged."""


async def capture(student_id: str, message: str) -> None:
    """Update the student's learning-preferences note if `message` states a lasting preference. Never raises."""
    try:
        from app.services.llm import GEN_MODEL, llm
        if not llm.client or not (message or "").strip():
            return
        current = await memory_service.get_learning_preferences(student_id)
        resp = await llm.client.chat.completions.create(
            model=GEN_MODEL, temperature=0.0, max_tokens=200, response_format={"type": "json_object"},
            timeout=TIMEOUT_S,
            messages=[{"role": "system", "content": SYSTEM},
                      {"role": "user", "content": f"Current note: <note>{current or '(empty)'}</note>\n"
                                                  f"Latest message: <message>{message[:1000]}</message>"}])
        data = json.loads(resp.choices[0].message.content or "{}")
        note = (data.get("note") or "").strip() if isinstance(data, dict) else ""
        if data.get("changed") is True and note and note != current:
            await memory_service.set_learning_preferences(student_id, note)
    except Exception as e:  # noqa: BLE001 — best-effort: a failed capture must never affect the chat
        logger.warning("preference capture failed: %r", e)


_tasks: set[asyncio.Task] = set()


def capture_in_background(student_id: str, message: str) -> None:
    """Fire and forget, keeping a reference so the task isn't garbage-collected mid-flight."""
    task = asyncio.create_task(capture(student_id, message))
    _tasks.add(task)
    task.add_done_callback(_tasks.discard)
