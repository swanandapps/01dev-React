"""
Transcript chunking utility for production ingestion.
Not used in MVP (seed JSON pre-chunked), but here for the pgvector path.
"""

from typing import List
from app.models import TranscriptChunk


def chunk_transcript(
    raw_text: str,
    course_id: str,
    course_title: str,
    lecture_id: str,
    lecture_title: str,
    chunk_size: int = 400,
    overlap: int = 50,
) -> List[TranscriptChunk]:
    words = raw_text.split()
    chunks = []
    start = 0

    while start < len(words):
        end = min(start + chunk_size, len(words))
        text = " ".join(words[start:end])
        chunk_id = f"{lecture_id}-chunk-{start}"
        chunks.append(
            TranscriptChunk(
                chunk_id=chunk_id,
                course_id=course_id,
                course_title=course_title,
                lecture_id=lecture_id,
                lecture_title=lecture_title,
                text=text,
                start_time=0,
                end_time=0,
            )
        )
        start += chunk_size - overlap

    return chunks
