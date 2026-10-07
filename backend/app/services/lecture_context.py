"""What the student is looking at, for in-player "this" questions ("give an example for this", "explain this").

Layers, from the screen outwards:
  on_screen        the passage at the video position plus its neighbours — what "this" means
  so_far           one-line summaries of the lecture's earlier passages — the thread it is part of
  earlier_passages what the student already built earlier in the course (earlier lectures only: no spoilers),
                   found with the on-screen passages' keywords, not the vague question
No course-wide search and no reranker: the student is already where the answer is."""
import re
from typing import Optional, Sequence

from app.models import TranscriptChunk
from app.retrieval import pipeline
from app.retrieval.text import norm_title
from app.services.vector_store import vector_store

EARLIER_K = 2


async def lecture_chunks(slug: str, lecture_title: str) -> list[TranscriptChunk]:
    await pipeline._ensure_loaded()  # the store loads lazily outside the server's startup
    want = norm_title(lecture_title or "")
    return sorted((c for c in vector_store.chunks if c.course_id == slug and norm_title(c.lecture_title) == want),
                  key=lambda c: c.start_time)


def lecture_pos(lecture_id: str) -> Optional[tuple[int, int]]:
    m = re.search(r"-(\d+)-(\d+)$", lecture_id or "")
    return (int(m.group(1)), int(m.group(2))) if m else None


def on_screen(chunks: Sequence[TranscriptChunk], position: float) -> tuple[list[TranscriptChunk], int]:
    """The passage playing at `position` (seconds) with the one before and the one after, and the index of the
    playing one in that list."""
    if not chunks:
        return [], 0
    i = next((k for k, c in enumerate(chunks) if c.start_time <= position < c.end_time), None)
    if i is None:
        i = 0 if position < chunks[0].start_time else len(chunks) - 1
    lo = max(0, i - 1)
    return list(chunks[lo:i + 2]), i - lo


def so_far(chunks: Sequence[TranscriptChunk], before: float) -> list[TranscriptChunk]:
    return [c for c in chunks if c.start_time < before]


async def earlier_passages(slug: str, lecture_id: str, terms: Sequence[str], k: int = EARLIER_K) -> list[TranscriptChunk]:
    """Best passages from lectures BEFORE this one, one per lecture. Best-effort: never fails the turn."""
    here = lecture_pos(lecture_id)
    query = " ".join(dict.fromkeys(t for t in terms if t))
    if not here or not query:
        return []
    try:
        cands = await pipeline.search(query, [slug])
    except Exception as e:  # noqa: BLE001
        print(f"[lecture_context] earlier search failed: {e!r}")
        return []
    out, seen = [], set()
    for cand in cands:
        c = cand.chunk
        pos = lecture_pos(c.lecture_id)
        if c.course_id != slug or not pos or pos >= here or c.lecture_id in seen:
            continue
        seen.add(c.lecture_id)
        out.append(c)
        if len(out) == k:
            break
    return out
