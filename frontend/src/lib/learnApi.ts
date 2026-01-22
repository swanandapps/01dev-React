import type {
  Lecture, StudyGuideStatus, QuestionStatus, QuizSubmit, QuizSession, AdaptiveResponse,
} from "../types/learn";

const API_BASE = import.meta.env.VITE_RAG_API_URL || "http://localhost:8080";

async function getJson<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`${API_BASE}${path}`, init);
  if (!res.ok) {
    const text = await res.text().catch(() => "Unknown error");
    throw new Error(`Backend error ${res.status}: ${text}`);
  }
  return res.json();
}

export function getLectures(): Promise<Lecture[]> {
  return getJson<Lecture[]>("/api/lectures");
}

export function getStudyGuide(lectureId: string): Promise<StudyGuideStatus> {
  return getJson<StudyGuideStatus>(`/api/ai/study-guide/${lectureId}`);
}

export function generateStudyGuide(lectureId: string): Promise<StudyGuideStatus> {
  return getJson<StudyGuideStatus>(`/api/ai/study-guide/${lectureId}/generate`, { method: "POST" });
}

export function getQuestions(lectureId: string): Promise<QuestionStatus> {
  return getJson<QuestionStatus>(`/api/ai/questions/${lectureId}`);
}

export function generateQuestions(lectureId: string): Promise<QuestionStatus> {
  return getJson<QuestionStatus>(`/api/ai/questions/${lectureId}/generate`, { method: "POST" });
}

export function saveQuizSession(submit: QuizSubmit): Promise<QuizSession> {
  return getJson<QuizSession>("/api/ai/quiz-session", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(submit),
  });
}

export function listQuizSessions(userId: string): Promise<QuizSession[]> {
  return getJson<QuizSession[]>(`/api/ai/quiz-sessions?user_id=${encodeURIComponent(userId)}`);
}

export function startAdaptive(userId: string, lectureId: string): Promise<AdaptiveResponse> {
  return getJson<AdaptiveResponse>("/api/ai/adaptive/start", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ user_id: userId, lecture_id: lectureId }),
  });
}

// Feature 6 — knowledge graph is internal; we only trigger its build on access.
export function buildKnowledgeGraph(lectureId: string): Promise<{ status: string }> {
  return getJson<{ status: string }>(`/api/ai/knowledge-graph/${lectureId}/build`, { method: "POST" });
}

export function answerAdaptive(body: {
  session_id: string;
  question_id: string;
  concept: string;
  correct: boolean;
}): Promise<AdaptiveResponse> {
  return getJson<AdaptiveResponse>("/api/ai/adaptive/answer", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
}
