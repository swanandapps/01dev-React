from app.models import AskRequest, AskResponse, SourceCard
from app.services.vector_store import vector_store
from app.services.embeddings import embedding_service
from app.services.answer_generator import answer_generator


async def ask(request: AskRequest) -> AskResponse:
    query_embedding = await embedding_service.embed(request.question)
    results = vector_store.search(query_embedding, top_k=5, query_text=request.question)

    if not results:
        return AskResponse(
            answer=(
                "The course content does not contain enough information to answer this question. "
                "This assistant only answers questions about the indexed course material."
            ),
            sources=[],
            insufficient_context=True,
            model="retrieval-only",
        )

    answer, model_name = await answer_generator.generate(request.question, results)

    sources = [
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

    return AskResponse(
        answer=answer,
        sources=sources,
        insufficient_context=False,
        model=model_name,
    )


def _fmt_time(seconds: int) -> str:
    m, s = divmod(seconds, 60)
    return f"{m:02d}:{s:02d}"
