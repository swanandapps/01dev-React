"""One chat turn, shared by both chats (Ask page and the video-player tutor).

PII scrub → audit → course_lookup (always, in code) → tutor agent → save to memory.
The endpoints differ only in ChatScope and where history comes from.
"""
import contextlib
import json
import os
import re
from dataclasses import dataclass
from typing import AsyncIterator, Optional

from app.grounding.loader import read_grounding_prompt
from app.services import audit_service, context_builder, journey_service, memory_service, pii, tutor_agent
from app.services.course_lookup import ChatScope, CourseLookup, LookupCase, course_lookup, render_facts, to_cards
from app.services.llm import GEN_MODEL

CONTEXT_LIMIT = int(os.getenv("MODEL_CONTEXT_LIMIT", "8192"))
PROVIDER = "langchain-agent"
_ERROR = "The tutor hit a problem answering that. Please try again."


@dataclass
class TurnRequest:
    question: str          # raw; scrubbed here
    student_id: str        # verified server-side (app.auth)
    scope: ChatScope
    history: list[dict]    # prior [{"role", "content"}], oldest first
    memory_slug: str       # memory_service course key: "all-courses" or the course slug


def sse(event: dict) -> str:
    return f"data: {json.dumps(event)}\n\n"


def _sources(cards: list[dict]) -> dict:
    return {"type": "sources", "sources": cards, "insufficient_context": False, "offer_general": False}


def _card_key(card: dict) -> tuple:
    return (card.get("course_id"), card.get("lecture_id"), card.get("start_time"))


def _missing_pointer(lookup: CourseLookup, answer: str, scope: ChatScope) -> Optional[str]:
    """The not-enrolled course pointer, if the model left it out (prompt alone isn't reliable)."""
    if lookup.case != LookupCase.NOT_ENROLLED_MATCH:
        return None
    if "not enrolled" in answer.lower() and "the01.dev/course/" in answer:
        return None
    linked = [h for h in lookup.hits if not h.enrolled and h.url]
    if not linked or any(re.search(re.escape(f"the01.dev{h.url}") + r"(?!\d)", answer) for h in linked):
        return None
    hit = linked[0]
    if scope.course_slug and hit.course_slug == scope.course_slug:
        return None  # watching that course's preview — don't point at the page they're on
    return (f"\n\nThis is covered in depth in {hit.course_title} → {hit.title}. "
            f"You're not enrolled in it yet; you can find it at the01.dev{hit.url}.")


async def chat_turn(req: TurnRequest, *, model: Optional[object] = None) -> AsyncIterator[dict]:
    question, _ = pii.scrub(req.question)
    history_in = [{**t, "content": pii.scrub(t.get("content", ""))[0]} for t in req.history]
    try:
        await audit_service.log_event(student_id=req.student_id, course_slug=req.memory_slug,
                                      question=question, model=GEN_MODEL, provider=PROVIDER)
    except Exception as e:  # noqa: BLE001 — audit is best-effort; never fail the turn over it
        print(f"[chat_turn] audit failed: {e!r}")

    try:
        # In the player, vague questions ("Give me an example") only find the right
        # transcript when the lecture title rides along; agent/audit/memory keep the bare question.
        lookup_q = f"{req.scope.lecture_title} {question}" if req.scope.lecture_title else question
        lookup = await course_lookup(lookup_q, req.student_id, req.scope)
        weak = (await journey_service.weak_concepts_for_course(req.student_id, req.scope.course_slug)
                if req.scope.course_slug else None)
        memory = await memory_service.memory_context(req.student_id, req.memory_slug)
        system = "\n\n".join(p for p in (read_grounding_prompt(), render_facts(lookup, req.scope, weak), memory) if p)
        history, _fit = context_builder.build(system, history_in, question, CONTEXT_LIMIT)
        cards = to_cards(lookup)
    except Exception as e:  # noqa: BLE001 — never leak internal errors to the student
        print(f"[chat_turn] preparing the turn failed: {e!r}")
        yield {"type": "error", "message": _ERROR}
        return
    if _fit["fill_pct"] >= 80 or _fit["dropped_turns"]:
        print(f"[chat_turn] context {_fit['fill_pct']}% "
              f"({_fit['prompt_tokens_est']}/{_fit['limit']} tok), dropped {_fit['dropped_turns']} old turn(s)"
              f"{' — essentials OVER limit' if _fit['over_limit'] else ''}")

    yield _sources(cards)
    seen = {_card_key(c) for c in cards}
    extra: list[dict] = []
    answer: list[str] = []
    try:
        async with contextlib.aclosing(tutor_agent.stream_answer(
                system_prompt=system, history=history, question=question,
                student_id=req.student_id, model=model)) as stream:
            async for event in stream:
                if event["type"] == "token":
                    answer.append(event["value"])
                    yield event
                elif event["type"] == "cards":
                    for c in event["cards"]:
                        if _card_key(c) not in seen:
                            seen.add(_card_key(c))
                            extra.append(c)
    except Exception as e:  # noqa: BLE001 — never leak provider errors to the student
        print(f"[chat_turn] agent failed: {e!r}")
        yield {"type": "error", "message": _ERROR}
        return

    pointer = _missing_pointer(lookup, "".join(answer), req.scope)
    if pointer:
        answer.append(pointer)
        yield {"type": "token", "value": pointer}
    if extra:
        # The client replaces its card list on each sources event, so send the full deduped list.
        yield _sources(cards + extra)
    try:
        await memory_service.record_turn(req.student_id, req.memory_slug, question, "".join(answer))
    except Exception as e:  # noqa: BLE001 — never fail the answer over memory persistence
        print(f"[chat_turn] record_turn failed: {e!r}")
    yield {"type": "done"}
