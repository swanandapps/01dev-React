import json
from typing import AsyncIterator

from app.models import AskRequest, AskResponse, SourceCard
from app.services.vector_store import vector_store
from app.services.embeddings import embedding_service
from app.services.answer_generator import answer_generator

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

    answer, model_name = await answer_generator.generate(request.question, results)

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
        async for token in answer_generator.generate_stream(request.question, results):
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


def _sse(payload: dict) -> str:
    return f"data: {json.dumps(payload)}\n\n"


def _fmt_time(seconds: int) -> str:
    m, s = divmod(seconds, 60)
    return f"{m:02d}:{s:02d}"
