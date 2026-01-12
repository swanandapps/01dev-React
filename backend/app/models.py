from pydantic import BaseModel
from typing import List, Optional


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


class LectureInfo(BaseModel):
    lecture_id: str
    lecture_title: str
    course_id: str
    course_title: str


# ---- Feature 2: Study guides ----

class KeyConcept(BaseModel):
    name: str
    description: str


class PracticeQA(BaseModel):
    question: str
    answer: str


class StudyGuide(BaseModel):
    lecture_id: str
    course_id: str
    lecture_title: str
    course_title: str
    key_concepts: List[KeyConcept]
    summary: str
    practice_questions: List[PracticeQA]
    misconceptions: List[str]
    model: str
    generated_at: str


class StudyGuideStatus(BaseModel):
    lecture_id: str
    status: str  # "ready" | "generating" | "none"
    guide: Optional[StudyGuide] = None


# ---- Feature 3: MCQ questions ----

class MCQQuestion(BaseModel):
    id: str
    question: str
    options: List[str]
    correct_index: int
    explanation: str
    concept: str
    difficulty: str  # "easy" | "medium" | "hard"


class QuestionSet(BaseModel):
    lecture_id: str
    course_id: str
    lecture_title: str
    course_title: str
    questions: List[MCQQuestion]
    model: str
    generated_at: str
