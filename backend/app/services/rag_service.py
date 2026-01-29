import json
from typing import AsyncIterator

from app.models import AskRequest, AskResponse, SourceCard
from app.services.vector_store import vector_store
from app.services.embeddings import embedding_service
from app.services.answer_generator import answer_generator
from app.services import knowledge_graph_service

INSUFFICIENT_CONTEXT_ANSWER = (
    "The course content does not contain enough information to answer this question. "
    "This assistant only answers questions about the indexed course material."
)


async def ask(request: AskRequest) -> AskResponse:
    query_embedding = await embedding_service.embed(request.question)
    results = vector_store.search(query_embedding, top_k=5, query_text=request.question)

    if not results:
        return AskResponse(
            answer=INSUFFICIENT_CONTEXT_ANSWER,
            sources=[],
            insufficient_context=True,
            model="retrieval-only",
        )

    answer, model_name = await answer_generator.generate(
        request.question, results, await _graph_context(results)
    )

    return AskResponse(
        answer=answer,
        sources=_build_sources(results),
        insufficient_context=False,
        model=model_name,
    )


async def ask_stream(request: AskRequest) -> AsyncIterator[str]:
    """Server-Sent Events stream: a `sources` event, then `token` events, then `done`."""
    query_embedding = await embedding_service.embed(request.question)
    results = vector_store.search(query_embedding, top_k=5, query_text=request.question)

    if not results:
        yield _sse({"type": "sources", "sources": [], "insufficient_context": True, "model": "retrieval-only"})
        for word in INSUFFICIENT_CONTEXT_ANSWER.split(" "):
            yield _sse({"type": "token", "value": word + " "})
        yield _sse({"type": "done"})
        return

    sources = [s.model_dump() for s in _build_sources(results)]
    yield _sse({
        "type": "sources",
        "sources": sources,
        "insufficient_context": False,
        "model": answer_generator.model_name,
    })

    try:
        extra = await _graph_context(results)
        async for token in answer_generator.generate_stream(request.question, results, extra):
            yield _sse({"type": "token", "value": token})
    except Exception as e:  # noqa: BLE001 — surface generation errors to the client
        yield _sse({"type": "error", "message": str(e)})
        return

    yield _sse({"type": "done"})


def _build_sources(results) -> list[SourceCard]:
    return [
        SourceCard(
            course_id=r.chunk.course_id,
            course_title=r.chunk.course_title,
            lecture_id=r.chunk.lecture_id,
            lecture_title=r.chunk.lecture_title,
            timestamp=_fmt_time(r.chunk.start_time),
            start_time=r.chunk.start_time,
            end_time=r.chunk.end_time,
            snippet=r.chunk.text[:220] + "…",
            score=round(r.score, 3),
        )
        for r in results
    ]


async def _graph_context(results) -> str:
    """
    Feature 6 integration: enrich the answer with the knowledge graph of the
    top-matched lecture — its concepts (with descriptions) and prerequisite
    edges. No-op (empty string) when no graph has been built yet, so the live
    RAG behaviour is unchanged until graphs exist.
    """
    try:
        course_id = results[0].chunk.course_id
        graph = await knowledge_graph_service.get_graph(course_id)
        concepts = [c for c in graph["concepts"] if c.get("description")]
        if not concepts:
            return ""

        lines = ["\n\n--- Concept map for this lecture (for grounding) ---"]
        for c in concepts:
            lines.append(f"• {c['name']}: {c['description']}")
        prereqs = [r for r in graph["relationships"] if r.get("type") == "prerequisite_of"]
        if prereqs:
            lines.append("Prerequisites: " + "; ".join(f"{r['source']} → {r['target']}" for r in prereqs))
        return "\n".join(lines)
    except Exception:  # noqa: BLE001 — graph context is best-effort, never block answers
        return ""


def _sse(payload: dict) -> str:
    return f"data: {json.dumps(payload)}\n\n"


def _fmt_time(seconds: int) -> str:
    m, s = divmod(seconds, 60)
    return f"{m:02d}:{s:02d}"
