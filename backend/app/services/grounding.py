"""
Single source of truth for the "grounded answer" capability.

Retrieval + source-card building + a full grounded answer live here, ONCE.
Every path reuses these — the Hermes governance handler (`main.py`), the eval
harness (`eval/accuracy.py`), and the MCP tool (`answer_question`). No caller
re-embeds/re-searches/re-builds-material itself.
"""
from typing import List

from app.models import SearchResult, SourceCard
from app.services.embeddings import embedding_service
from app.services.vector_store import vector_store
from app.services.answer_generator import answer_generator

INSUFFICIENT_CONTEXT_ANSWER = (
    "The course content does not contain enough information to answer this question. "
    "This assistant only answers questions about the indexed course material."
)


def _fmt_time(seconds: int) -> str:
    m, s = divmod(seconds, 60)
    return f"{m:02d}:{s:02d}"


async def retrieve(question: str, top_k: int = 5) -> List[SearchResult]:
    """Embed the question and return the top-k matching transcript chunks.

    Emits `embed` + `vector_search` OTel child spans (no-op unless tracing is on).
    """
    from app.services.otel import get_tracer
    tracer = get_tracer()

    with tracer.start_as_current_span("embed") as sp:
        sp.set_attribute("query_chars", len(question))
        query_embedding = await embedding_service.embed(question)

    with tracer.start_as_current_span("vector_search") as sp:
        results = vector_store.search(query_embedding, top_k=top_k, query_text=question)
        sp.set_attribute("top_k", top_k)
        sp.set_attribute("n_results", len(results))
        sp.set_attribute("top_score", round(results[0].score, 3) if results else 0.0)
    return results


def build_material(results: List[SearchResult]) -> str:
    """The cited course-material block injected into a grounded prompt."""
    return "\n\n".join(
        f"[{r.chunk.course_title} — {r.chunk.lecture_title} @ {_fmt_time(r.chunk.start_time)}]\n{r.chunk.text}"
        for r in results
    )


def build_sources(results: List[SearchResult]) -> List[SourceCard]:
    """Citation cards (lecture, timestamp, snippet, score) for the UI / tools."""
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


async def answer_grounded(question: str, top_k: int = 5) -> dict:
    """The whole grounded-answer capability: retrieve → answer only from context → cite.

    Returns {answer, sources (list[SourceCard]), insufficient_context, model}.
    Non-streaming; the streaming tutor path composes `retrieve`/`build_material`
    itself but shares the same retrieval.
    """
    results = await retrieve(question, top_k)
    if not results:
        return {
            "answer": INSUFFICIENT_CONTEXT_ANSWER,
            "sources": [],
            "insufficient_context": True,
            "model": "retrieval-only",
        }
    answer, model = await answer_generator.generate(question, results)
    return {
        "answer": answer,
        "sources": build_sources(results),
        "insufficient_context": False,
        "model": model,
    }
