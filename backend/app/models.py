from pydantic import BaseModel
from typing import List


class TranscriptChunk(BaseModel):
    chunk_id: str
    course_id: str
    course_title: str
    lecture_id: str
    lecture_title: str
    text: str
    start_time: int
    end_time: int
    embedding: List[float] = []


class SearchResult(BaseModel):
    chunk: TranscriptChunk
    score: float


class SourceCard(BaseModel):
    course_id: str
    course_title: str
    lecture_id: str
    lecture_title: str
    timestamp: str
    start_time: int
    end_time: int
    snippet: str
    score: float


class AskRequest(BaseModel):
    question: str


class AskResponse(BaseModel):
    answer: str
    sources: List[SourceCard]
    insufficient_context: bool
    model: str


class Course(BaseModel):
    course_id: str
    title: str
    lecture_count: int
