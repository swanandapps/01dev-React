"""
Conversational AI tutor with memory.

A per-course Socratic tutor that (1) knows the student's performance — it injects
their weak concepts so it can target them, (2) is grounded in the course material
via RAG, and (3) remembers the conversation (the client sends the running message
list each turn). Streams tokens over SSE, same shape as the RAG assistant.
"""

import json
from typing import AsyncIterator, List

from app.services.llm import llm, GEN_MODEL
from app.services.store import store
from app.services.embeddings import embedding_service
from app.services.vector_store import vector_store


def _sse(payload: dict) -> str:
    return f"data: {json.dumps(payload)}\n\n"


async def _weak_concepts(user_id: str, course_id: str) -> List[str]:
    qdoc = await store.get("questions", course_id)
    if not qdoc:
        return []
    course_concepts = {q["concept"] for q in qdoc["questions"]}
    perf = await store.query("concept_performance", "user_id", user_id)
    weak = sorted(
        [p for p in perf if p["concept"] in course_concepts and p["attempts"] > 0 and p["accuracy"] < 0.7],
        key=lambda p: p["accuracy"],
    )
    return [f"{p['concept']} ({round(p['accuracy']*100)}%)" for p in weak[:5]]


async def _course_context(course_id: str, query: str) -> str:
    """Top transcript snippets from THIS course relevant to the student's message."""
    emb = await embedding_service.embed(query)
    results = vector_store.search(emb, top_k=8, query_text=query)
    course_results = [r for r in results if r.chunk.course_id == course_id][:3]
    if not course_results:
        # Fall back to the start of the course transcript.
        return vector_store.get_course_transcript(course_id)[:1500]
    return "\n\n---\n\n".join(
        f"[{r.chunk.lecture_title}] {r.chunk.text}" for r in course_results
    )


def _system_prompt(course_title: str, weak: List[str], context: str, lecture: str) -> str:
    weak_line = (
        f"This student is currently weak on: {', '.join(weak)}. Gently steer toward these when relevant."
        if weak
        else "You don't have performance data for this student yet."
    )
    watching_line = (
        f'The student is RIGHT NOW watching the lecture "{lecture}". If their question seems to be about '
        f"what they're watching (e.g. \"what does this mean\", \"I'm confused here\"), assume it's about this lecture."
        if lecture
        else ""
    )
    return f"""You are a patient, encouraging Socratic AI tutor for the course "{course_title}" on the 0.1% Dev platform.

{weak_line}
{watching_line}

Teaching style:
- Prefer guiding questions over handing over answers. When the student is stuck, give a small hint first, then explain.
- Be concise and conversational (2-5 sentences). Use concrete examples from the course material.
- If they get something wrong, correct it kindly and check understanding with a follow-up question.
- Stay grounded in the course material below; if something isn't covered, say so briefly.

Course material (for grounding):
{context}"""


async def tutor_stream(
    user_id: str, course_id: str, messages: List[dict], lecture: str = ""
) -> AsyncIterator[str]:
    meta = vector_store.get_course_meta(course_id)
    if not meta:
        yield _sse({"type": "error", "message": "Unknown course"})
        return

    last_user = next((m["content"] for m in reversed(messages) if m.get("role") == "user"), "")
    weak = await _weak_concepts(user_id, course_id)
    # Bias retrieval toward the lecture they're watching.
    context = await _course_context(course_id, f"{lecture} {last_user}".strip())
    system = _system_prompt(meta["course_title"], weak, context, lecture)

    if not llm.client:
        for w in "The AI tutor needs an OpenAI API key to chat. ".split(" "):
            yield _sse({"type": "token", "value": w + " "})
        yield _sse({"type": "done"})
        return

    # Keep the running conversation as memory (cap to recent turns for token budget).
    convo = [{"role": m["role"], "content": m["content"]} for m in messages if m.get("role") in ("user", "assistant")][-12:]

    try:
        stream = await llm.client.chat.completions.create(
            model=GEN_MODEL,
            messages=[{"role": "system", "content": system}, *convo],
            temperature=0.4,
            max_tokens=600,
            stream=True,
        )
        async for chunk in stream:
            delta = chunk.choices[0].delta.content
            if delta:
                yield _sse({"type": "token", "value": delta})
    except Exception as e:  # noqa: BLE001
        yield _sse({"type": "error", "message": str(e)})
        return

    yield _sse({"type": "done"})
