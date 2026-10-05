"""The tutor: a LangChain create_agent over thin wrappers of app/services.

Identity is bound server-side: tools read student_id from the run's ChatContext
(ToolRuntime), which the model can neither see nor set — no tool schema has a
student_id parameter. The flow is linear (lookup → agent → save), so this is a
plain create_agent, not a custom LangGraph graph; Lab keeps its graph because it
branches and pauses for approval.
"""
import json
from dataclasses import dataclass
from functools import lru_cache
from typing import Annotated, AsyncIterator, Literal, Optional

from langchain.agents import create_agent
from langchain.tools import ToolRuntime, tool
from langchain_core.messages import AIMessage, AIMessageChunk, HumanMessage, ToolMessage
from langchain_openai import ChatOpenAI

from app.services import (catalog_service, enrollment_service, grounding, journey_service, memory_service,
                          skill_graph_service)
from app.services.course_lookup import TRANSCRIPT_THRESHOLD
from app.services import tool_descriptions as D
from app.services.llm import GEN_MODEL


@dataclass(frozen=True)
class ChatContext:
    student_id: str


def _dump(data) -> str:
    return json.dumps(data, default=str)


# Argument descriptions: @tool(description=...) doesn't parse an Args section,
# so each argument's guidance rides on its type.
Concept = Annotated[str, "Concept tag as used in that course, e.g. 'react-memo'."]
CourseId = Annotated[str, "Course slug, e.g. 'react-perf'."]


async def _enrolled_ids(student_id: str) -> set:
    try:
        return {c["id"] for c in await enrollment_service.get_enrolled_courses(student_id)}
    except Exception as e:  # noqa: BLE001 — unknown enrollment = not enrolled; never fail the turn
        print(f"[tutor_agent] enrollment lookup failed: {e!r}")
        return set()


def _enrollment_label(course_slug: str, enrolled_ids: set) -> str:
    course = catalog_service.by_slug(course_slug)
    return "ENROLLED" if course and course["id"] in enrolled_ids else "NOT ENROLLED"


@tool("search_course_content", description=D.SEARCH_COURSE_CONTENT, response_format="content_and_artifact")
async def search_course_content(
    query: Annotated[str, "What to look up — the student's follow-up question or the concept."],
    runtime: ToolRuntime[ChatContext],
) -> tuple[str, list[dict]]:
    # Same bar as course_lookup: weak matches would surface as citation cards for unrelated lectures.
    results = [r for r in await grounding.retrieve(query, top_k=5) if r.score >= TRANSCRIPT_THRESHOLD]
    if not results:
        return "No matching course content.", []
    enrolled_ids = await _enrolled_ids(runtime.context.student_id)
    cards = [c.model_dump() for c in grounding.build_sources(results)]
    text = "\n".join(
        f"[{_enrollment_label(r.chunk.course_id, enrolled_ids)}] "
        f"{r.chunk.course_title} → {r.chunk.lecture_title} @ {c['timestamp']}: {r.chunk.text}"
        for r, c in zip(results, cards)
    )
    return text, cards


@tool("get_enrolled_courses", description=D.GET_ENROLLED_COURSES)
async def get_enrolled_courses(runtime: ToolRuntime[ChatContext]) -> str:
    return _dump(await enrollment_service.get_enrolled_courses(runtime.context.student_id))


@tool("get_learning_strengths", description=D.GET_LEARNING_STRENGTHS)
async def get_learning_strengths(runtime: ToolRuntime[ChatContext]) -> str:
    return _dump(await journey_service.get_strengths_report(runtime.context.student_id))


@tool("get_learning_metrics", description=D.GET_LEARNING_METRICS)
async def get_learning_metrics(runtime: ToolRuntime[ChatContext]) -> str:
    return _dump(await journey_service.get_metrics(runtime.context.student_id))


@tool("get_concept_confidence", description=D.GET_CONCEPT_CONFIDENCE)
async def get_concept_confidence(concept: Concept, course_id: CourseId, runtime: ToolRuntime[ChatContext]) -> str:
    return _dump(await skill_graph_service.get_prerequisite_view(runtime.context.student_id, course_id, concept))


@tool("search_history", description=D.SEARCH_HISTORY)
async def search_history(query: Annotated[str, "What to look for in the student's past exchanges, e.g. 'did we cover promises?'."],
                         runtime: ToolRuntime[ChatContext]) -> str:
    rows = await memory_service.search_history(runtime.context.student_id, query, 3)
    return _dump([
        {"date": str(r.get("created_at", ""))[:10], "course": r.get("course_slug"),
         "snippet": f"Q: {r.get('question', '')}\nA: {r.get('answer', '')}"[:300]}
        for r in rows
    ])


@tool("record_skill_observation", description=D.RECORD_SKILL_OBSERVATION)
async def record_skill_observation(
    concept: Concept,
    course_id: CourseId,
    confidence: Literal["weak", "developing", "strong"],
    note: Annotated[str, "One sentence: what you actually observed, in plain language."],
    runtime: ToolRuntime[ChatContext],
) -> str:
    try:
        return _dump(await skill_graph_service.record_observation(
            runtime.context.student_id, course_id, concept, confidence, note))
    except ValueError as e:
        return _dump({"error": str(e)})


TOOLS = [search_course_content, get_enrolled_courses, get_learning_strengths, get_learning_metrics,
         get_concept_confidence, search_history, record_skill_observation]


@lru_cache(maxsize=1)
def _default_model() -> ChatOpenAI:
    return ChatOpenAI(model=GEN_MODEL, temperature=0.4, streaming=True, timeout=60, max_retries=2)


async def stream_answer(*, system_prompt: str, history: list[dict], question: str, student_id: str,
                        model: Optional[object] = None) -> AsyncIterator[dict]:
    agent = create_agent(model or _default_model(), tools=TOOLS, system_prompt=system_prompt,
                         context_schema=ChatContext)
    messages = [HumanMessage(t["content"]) if t["role"] == "user" else AIMessage(t["content"])
                for t in history if t.get("role") in ("user", "assistant")]
    messages.append(HumanMessage(question))
    spoke = after_tool = False
    async for chunk, meta in agent.astream({"messages": messages}, context=ChatContext(student_id=student_id),
                                           stream_mode="messages"):
        if isinstance(chunk, AIMessageChunk) and meta.get("langgraph_node") == "model" and chunk.text:
            if spoke and after_tool:
                # "Let me check." + tool call, then the answer: keep them from running together.
                yield {"type": "token", "value": "\n\n"}
            spoke, after_tool = True, False
            yield {"type": "token", "value": chunk.text}
        elif isinstance(chunk, ToolMessage):
            after_tool = True
            if chunk.artifact:
                yield {"type": "cards", "cards": list(chunk.artifact)}
