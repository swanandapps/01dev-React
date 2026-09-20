import pytest

from app.models import SearchResult, TranscriptChunk
from app.services.store import InMemoryStore


def _result(course_id="react-perf", start_time=73, score=0.9):
    return SearchResult(
        chunk=TranscriptChunk(
            chunk_id="c1", course_id=course_id, course_title="React Performance Patterns",
            lecture_id="l1", lecture_title="Lecture 4.1", text="React.memo prevents re-renders...",
            start_time=start_time, end_time=start_time + 60,
        ),
        score=score,
    )


@pytest.mark.asyncio
async def test_search_course_content_persists_citations_for_student(monkeypatch):
    from app.mcp import the01dev_tools
    from app.services import grounding

    real_store = InMemoryStore()
    monkeypatch.setattr(the01dev_tools, "store", real_store)

    async def fake_retrieve(query, top_k=5):
        return [_result()]

    async def fake_ensure_index():
        return None

    monkeypatch.setattr(grounding, "retrieve", fake_retrieve)
    monkeypatch.setattr(the01dev_tools, "_ensure_index", fake_ensure_index)

    await the01dev_tools.search_course_content(query="what is memo?", student_id="citations-student")

    saved = await real_store.get("chat_citations", "citations-student")
    assert saved is not None
    cards = saved["cards"]
    assert len(cards) == 1
    assert cards[0]["course_id"] == "react-perf"
    assert cards[0]["lecture_title"] == "Lecture 4.1"
    assert cards[0]["start_time"] == 73


@pytest.mark.asyncio
async def test_search_course_content_does_not_write_citations_on_no_match(monkeypatch):
    from app.mcp import the01dev_tools
    from app.services import grounding

    real_store = InMemoryStore()
    monkeypatch.setattr(the01dev_tools, "store", real_store)

    async def fake_retrieve(query, top_k=5):
        return []

    async def fake_ensure_index():
        return None

    monkeypatch.setattr(grounding, "retrieve", fake_retrieve)
    monkeypatch.setattr(the01dev_tools, "_ensure_index", fake_ensure_index)

    await the01dev_tools.search_course_content(query="unrelated", student_id="no-match-student")

    assert await real_store.get("chat_citations", "no-match-student") is None
