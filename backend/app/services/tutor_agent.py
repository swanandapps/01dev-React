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

from app.services import (catalog_service, concept_explain, enrollment_service, grounding, journey_service, memory_service,
                          skill_graph_service)
from app.models import SearchResult
from app.services import course_lookup as cl
from app.services.course_lookup import TRANSCRIPT_THRESHOLD
from app.services import tool_descriptions as D
from app.services.llm import GEN_MODEL


@dataclass(frozen=True)
class ChatContext:
    student_id: str
    in_course: Optional[str] = None  # player only: the course being watched (spec §3.2, §3.3)


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
    in_course = runtime.context.in_course
    if in_course:  # player: this course only (spec §3.2)
        pairs = await cl.search_in_course(query, in_course, top_k=5)
        results = [SearchResult(chunk=c, score=s) for c, s in pairs
                   if c.course_id == in_course and s >= TRANSCRIPT_THRESHOLD]
    else:
        results = [r for r in await grounding.retrieve(query, top_k=5) if r.score >= TRANSCRIPT_THRESHOLD]
    if not results:
        return "No matching course content.", []
    enrolled_ids = set() if in_course else await _enrolled_ids(runtime.context.student_id)
    cards = [c.model_dump() for c in grounding.build_sources(results)]
    text = "\n".join(
        f"[{'THIS COURSE' if in_course else _enrollment_label(r.chunk.course_id, enrolled_ids)}] "
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


@tool("explain_concept", description=D.EXPLAIN_CONCEPT)
async def explain_concept(
    concept: Annotated[str, "Concept name as reported by get_learning_strengths, e.g. 'react-memo'."],
    runtime: ToolRuntime[ChatContext],
) -> str:
    return _dump(await concept_explain.explain_concept(runtime.context.student_id, concept))


_NOT_FOUND = '{"found": false}'


async def _locate_moment(what: str, slug: str):
    """(chunk, chunk_score) of a real chunk of the course, or None. Lectures are ranked by
    max(best chunk, title - TITLE_OFFSET); the winner counts as found when its title clears
    TITLE_THRESHOLD or its best chunk clears MOMENT_THRESHOLD."""
    rows = [(c, s) for c, s in await cl.search_in_course(what, slug, top_k=1000) if c.course_id == slug]
    titles = {cl._norm(t): sc for t, sc in (await cl._title_scores(what, slug)).items()}
    best: dict = {}
    for c, s in rows:
        k = cl._norm(c.lecture_title)
        if k not in best or s > best[k][1]:
            best[k] = (c, s)
    if not best:
        return None
    key = max(best, key=lambda k: max(best[k][1], titles.get(k, 0.0) - cl.TITLE_OFFSET))
    chunk, score = best[key]
    if titles.get(key, 0.0) < cl.TITLE_THRESHOLD and score < cl.MOMENT_THRESHOLD:
        return None
    if score < cl.MOMENT_LECTURE_FLOOR:
        chunk = chunk.model_copy(update={"start_time": 0})
    return chunk, score


@tool("find_moment", description=D.FIND_MOMENT, response_format="content_and_artifact")
async def find_moment(
    what: Annotated[str, "The specific thing to find, in the instructor's on-screen words: the command, tool, "
                         "function or term (e.g. 'npm publish command', 'npm link', 'IIFE syntax'), no request filler."],
    runtime: ToolRuntime[ChatContext],
) -> tuple[str, Optional[dict]]:
    """Only ever returns a real chunk of the watched course — the model cannot invent a time."""
    slug = runtime.context.in_course
    if not slug:
        return _NOT_FOUND, None
    hit = await _locate_moment(what, slug)
    if not hit:
        return _NOT_FOUND, None
    chunk, score = hit
    found = {"lecture_title": chunk.lecture_title, "start_time": chunk.start_time, "end_time": chunk.end_time,
             "excerpt": chunk.text[:400], "score": round(score, 3)}
    return _dump(found), {"course_slug": slug, "lecture_title": chunk.lecture_title, "start_time": chunk.start_time}


TOOLS = [search_course_content, get_enrolled_courses, get_learning_strengths, get_learning_metrics,
         get_concept_confidence, search_history, record_skill_observation, explain_concept]


def tools_for(in_course: Optional[str]) -> list:
    """The tool list is chosen per turn: find_moment exists only inside the player."""
    return TOOLS + [find_moment] if in_course else TOOLS


@lru_cache(maxsize=1)
def _default_model() -> ChatOpenAI:
    return ChatOpenAI(model=GEN_MODEL, temperature=0.4, streaming=True, timeout=60, max_retries=2)


async def stream_answer(*, system_prompt: str, history: list[dict], question: str, student_id: str,
                        model: Optional[object] = None, in_course: Optional[str] = None) -> AsyncIterator[dict]:
    agent = create_agent(model or _default_model(), tools=tools_for(in_course), system_prompt=system_prompt,
                         context_schema=ChatContext)
    messages = [HumanMessage(t["content"]) if t["role"] == "user" else AIMessage(t["content"])
                for t in history if t.get("role") in ("user", "assistant")]
    messages.append(HumanMessage(question))
    spoke = after_tool = False
    async for chunk, meta in agent.astream({"messages": messages}, context=ChatContext(student_id=student_id, in_course=in_course),
                                           stream_mode="messages"):
        if isinstance(chunk, AIMessageChunk) and meta.get("langgraph_node") == "model" and chunk.text:
            if spoke and after_tool:
                # "Let me check." + tool call, then the answer: keep them from running together.
                yield {"type": "token", "value": "\n\n"}
            spoke, after_tool = True, False
            yield {"type": "token", "value": chunk.text}
        elif isinstance(chunk, ToolMessage):
            after_tool = True
            if chunk.name == "find_moment":
                if chunk.artifact:
                    yield {"type": "moment", "moment": dict(chunk.artifact)}
            elif chunk.artifact:
                yield {"type": "cards", "cards": list(chunk.artifact)}
