"""One chat turn, shared by both chats (Ask page and the video-player tutor).

PII scrub → audit → course_lookup (always, in code) → tutor agent → save to memory.
The endpoints differ only in ChatScope and where history comes from.
"""
import json
import os
from dataclasses import dataclass
from typing import AsyncIterator, Optional

from app.grounding.loader import read_grounding_prompt
from app.services import audit_service, context_builder, journey_service, memory_service, pii, tutor_agent
from app.services.course_lookup import ChatScope, course_lookup, render_facts, to_cards
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


async def chat_turn(req: TurnRequest, *, model: Optional[object] = None) -> AsyncIterator[dict]:
    question, _ = pii.scrub(req.question)
    await audit_service.log_event(student_id=req.student_id, course_slug=req.memory_slug,
                                  question=question, model=GEN_MODEL, provider=PROVIDER)

    lookup = await course_lookup(question, req.student_id, req.scope)
    weak = (await journey_service.weak_concepts_for_course(req.student_id, req.scope.course_slug)
            if req.scope.course_slug else None)
    memory = await memory_service.memory_context(req.student_id, req.memory_slug)
    system = "\n\n".join(p for p in (read_grounding_prompt(), render_facts(lookup, req.scope, weak), memory) if p)
    history, _fit = context_builder.build(system, req.history, question, CONTEXT_LIMIT)

    cards = to_cards(lookup)
    yield _sources(cards)
    seen = {_card_key(c) for c in cards}
    extra: list[dict] = []
    answer: list[str] = []
    try:
        async for event in tutor_agent.stream_answer(system_prompt=system, history=history, question=question,
                                                     student_id=req.student_id, model=model):
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

    if extra:
        yield _sources(extra)
    try:
        await memory_service.record_turn(req.student_id, req.memory_slug, question, "".join(answer))
    except Exception as e:  # noqa: BLE001 — never fail the answer over memory persistence
        print(f"[chat_turn] record_turn failed: {e!r}")
    yield {"type": "done"}
