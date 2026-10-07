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
from app.retrieval import pipeline, titles
from app.retrieval.text import norm_title
from app.services import course_lookup as cl
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


@tool("search_course_content", description=D.SEARCH_COURSE_CONTENT, response_format="content_and_artifact")
async def search_course_content(
    query: Annotated[str, "What to look up — the student's follow-up question or the concept."],
    runtime: ToolRuntime[ChatContext],
) -> tuple[str, list[dict]]:
    # Same bar as course_lookup: only reranker-graded answers/partial hits are citable; a vague question
    # ("what does this mean?") grades nothing and so yields no text and no cards.
    in_course = runtime.context.in_course
    if in_course:  # player: this course only (spec §3.2), whoever owns it
        enrolled_ids, scope = set(), (in_course,)
    else:          # Ask: launched AND owned courses only (F1, scope computed before searching), exact-lecture deep links
        enrolled_ids = await _enrolled_ids(runtime.context.student_id)
        scope = pipeline.ask_scope(enrolled_ids)
    result = await pipeline.graded_search(query, scope)   # empty scope: NOT_COVERED, nothing searched
    # cited() is already answers first, then partial, fused order within a grade
    cited = [g for g in result.cited() if g.candidate.chunk.course_id in scope]
    if in_course:
        kept = cited[:5]
        results = [SearchResult(chunk=g.candidate.chunk, score=_cos(g)) for g in kept]
        cards = [c.model_dump() for c in grounding.build_sources(results)]
    else:
        # ask_citable stays as the same-policy backstop to the scope
        pairs = [(g, h) for g in cited if cl.ask_citable(h := cl.graded_hit(g, enrolled_ids))][:5]
        kept = [g for g, _ in pairs]
        cards = cl.to_cards(cl.CourseLookup(case=cl.LookupCase.ENROLLED_MATCH, hits=[h for _, h in pairs],
                                            enrolled_titles=[]))
    if not kept:
        return "No matching course content.", []
    text = "\n".join(
        f"{'[THIS COURSE] ' if in_course else ''}"
        f"{g.candidate.chunk.course_title} → {g.candidate.chunk.lecture_title} @ {c['timestamp']}"
        f"{' (touches on it)' if g.grade == 'partial' else ''}: {g.candidate.chunk.text_clean or g.candidate.chunk.text}"
        + (f" — link: the01.dev{c['url']}" if not in_course and c.get("url") else "")
        for g, c in zip(kept, cards)
    )
    return text, cards


@tool("get_enrolled_courses", description=D.GET_ENROLLED_COURSES)
async def get_enrolled_courses(runtime: ToolRuntime[ChatContext]) -> str:
    return _dump(await enrollment_service.get_enrolled_courses(runtime.context.student_id))


@tool("get_learning_strengths", description=D.GET_LEARNING_STRENGTHS)
async def get_learning_strengths(runtime: ToolRuntime[ChatContext]) -> str:
    return _dump(await journey_service.get_strengths_report(runtime.context.student_id))


@tool("get_learning_metrics", description=D.GET_LEARNING_METRICS)
async def get_learning_metrics(runtime: ToolRuntime[ChatContext],
                               this_course_only: Annotated[bool, "True when the student asks about THIS course (the "
                                                                 "one being watched); false for overall progress."] = False) -> str:
    course = runtime.context.in_course if this_course_only else None
    return _dump(await journey_service.get_progress(runtime.context.student_id, course))


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


def _cos(g) -> float:
    c = g.candidate
    return c.cosine if c.cosine is not None else (c.vec_score or 0.0)


async def _locate_moment(what: str, slug: str):
    """(chunk, cosine) of the moment that shows `what` in the watched course, or None. find_moment only
    runs on an explicit "take me to ..." request, so the best `answers` chunk wins, else the best
    `partial` one (spec §2.5); a lower grade never loses to a higher one. Only a real chunk of THIS course
    is ever returned. Within a grade, a chunk of a lecture whose TITLE matches the phrase
    (titles.TITLE_THRESHOLD) comes first, then the highest cosine."""
    result = await pipeline.graded_search(what, [slug], intent="navigate")
    for grade in ("answers", "partial"):
        tier = [g for g in result.graded if g.grade == grade and g.candidate.chunk.course_id == slug]
        if tier:
            matched = await _title_matched(what, slug, result.question_embedding)
            best = max(tier, key=lambda g: (norm_title(g.candidate.chunk.lecture_title) in matched, _cos(g)))
            return best.candidate.chunk, _cos(best)
    return None


async def _title_matched(what: str, slug: str, question_embedding) -> set[str]:
    """Normalized titles of the course's lectures whose title matches the phrase, best effort."""
    try:
        scores = await titles.title_scores(question_embedding, [slug], question=what)
    except Exception as e:  # noqa: BLE001 — the title signal is only an ordering hint
        print(f"[tutor_agent] title match failed: {e!r}")
        return set()
    return {norm_title(t) for (_, t), sc in scores.items() if sc >= titles.TITLE_THRESHOLD}


@tool("find_moment", description=D.FIND_MOMENT, response_format="content_and_artifact")
async def find_moment(
    what: Annotated[str, "The specific thing to find, in the instructor's on-screen words: the command, tool, "
                         "function or term (e.g. 'npm publish command', 'npm link', 'IIFE syntax'), no request filler."],
    runtime: ToolRuntime[ChatContext],
) -> tuple[str, Optional[dict]]:
    """Navigation only: call when the student explicitly asks to be taken/jumped/shown to a place in the
    video, never to look something up (use search_course_content for that). Only ever returns a real
    chunk of the watched course — the model cannot invent a time."""
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


def tools_for(in_course: Optional[str], allow_moment: bool = False, allow_search: bool = True) -> list:
    """The tool list is chosen per turn: find_moment exists only inside the player AND only when the caller's code
    gate found an explicit "take me to ..." request (the model alone never decides to jump the player).
    allow_search=False (a player "this" question) withholds search_course_content: the answer is on screen."""
    tools = TOOLS if allow_search else [t for t in TOOLS if t is not search_course_content]
    return tools + [find_moment] if in_course and allow_moment else tools


@lru_cache(maxsize=1)
def _default_model() -> ChatOpenAI:
    return ChatOpenAI(model=GEN_MODEL, temperature=0.4, streaming=True, timeout=60, max_retries=2)


async def stream_answer(*, system_prompt: str, history: list[dict], question: str, student_id: str,
                        model: Optional[object] = None, in_course: Optional[str] = None,
                        allow_moment: bool = False, allow_search: bool = True) -> AsyncIterator[dict]:
    agent = create_agent(model or _default_model(), tools=tools_for(in_course, allow_moment, allow_search),
                         system_prompt=system_prompt,
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
