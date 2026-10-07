from pydantic import BaseModel
from typing import List, Optional


class TranscriptChunk(BaseModel):
    chunk_id: str
    course_id: str
    course_title: str
    lecture_id: str
    lecture_title: str
    text: str                      # the raw transcript ("text_raw" in the retrieval spec) — never rewritten
    start_time: int
    end_time: int
    embedding: List[float] = []
    # Retrieval v2 (derived at load by app.retrieval.enrichment; empty for un-enriched chunks)
    chapter: str = ""
    text_clean: str = ""           # glossary-fixed, whitespace-normalised text (shown to the model and on cards)
    summary: str = ""
    keywords: List[str] = []
    questions: List[str] = []
    embed_text: str = ""           # what is embedded: header + summary + key terms + overlap + text_clean
    embed_model: str = ""
    content_hash: str = ""         # sha256(embed_model + embed_text)


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
    course_id: str
    course_title: str
    key_concepts: List[KeyConcept]
    summary: str
    practice_questions: List[PracticeQA]
    misconceptions: List[str]
    model: str
    generated_at: str


class StudyGuideStatus(BaseModel):
    course_id: str
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
    lecture: str = ""  # lecture title this question came from (precision under a course)


class QuestionSet(BaseModel):
    course_id: str
    course_title: str
    questions: List[MCQQuestion]
    model: str
    generated_at: str


# ---- Feature 4: Quiz sessions ----

class QuizAnswer(BaseModel):
    question_id: str
    concept: str
    difficulty: str
    correct: bool
    time_taken_ms: int = 0
    lecture: str = ""  # which lecture in the course (precision)


class QuizSubmit(BaseModel):
    user_id: str = "anonymous"
    course_id: str
    answers: List[QuizAnswer]


class ConceptScore(BaseModel):
    concept: str
    attempts: int
    correct: int
    accuracy: float


class QuizSession(BaseModel):
    session_id: str
    user_id: str
    course_id: str
    course_title: str
    score: int
    total: int
    answers: List[QuizAnswer]
    concept_breakdown: List[ConceptScore]
    completed_at: str


# ---- Feature 5: Adaptive practice ----

class AdaptiveStartRequest(BaseModel):
    user_id: str = "anonymous"
    course_id: str


class AdaptiveAnswerRequest(BaseModel):
    session_id: str
    question_id: str
    concept: str
    correct: bool
    time_taken_ms: int = 0


class CourseInsightRequest(BaseModel):
    user_id: str = "anonymous"
    course_id: str
    chat_questions: List[str] = []
    rewatched_lectures: List[str] = []


class TutorTurn(BaseModel):
    role: str  # "user" | "assistant"
    content: str


class TutorRequest(BaseModel):
    user_id: str = "anonymous"  # ignored by the server; identity comes from the login token
    course_id: str
    messages: List[TutorTurn]
    lecture: str = ""  # the lecture the student is currently watching, if any
    position: Optional[float] = None  # video position (seconds) when the student asked, if the player has a video


# ---- Enrollment (Postgres system of record; Firebase stays auth + storage only) ----

class EnrolledCourse(BaseModel):
    id: int
    title: str
    purchased_at: str


class EnrollRequest(BaseModel):
    student_id: str
    course_id: int
    course_title: str
