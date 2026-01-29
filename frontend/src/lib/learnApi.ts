import type {
  Course, StudyGuideStatus, QuestionStatus, QuizSubmit, QuizSession, AdaptiveResponse,
  RecommendationsResponse,
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

export function getCourses(): Promise<Course[]> {
  return getJson<Course[]>("/api/courses");
}

export function getStudyGuide(courseId: string): Promise<StudyGuideStatus> {
  return getJson<StudyGuideStatus>(`/api/ai/study-guide/${courseId}`);
}

export function generateStudyGuide(courseId: string): Promise<StudyGuideStatus> {
  return getJson<StudyGuideStatus>(`/api/ai/study-guide/${courseId}/generate`, { method: "POST" });
}

export function getQuestions(courseId: string): Promise<QuestionStatus> {
  return getJson<QuestionStatus>(`/api/ai/questions/${courseId}`);
}

export function generateQuestions(courseId: string): Promise<QuestionStatus> {
  return getJson<QuestionStatus>(`/api/ai/questions/${courseId}/generate`, { method: "POST" });
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

export function getRecommendations(userId: string): Promise<RecommendationsResponse> {
  return getJson<RecommendationsResponse>(`/api/ai/recommendations?user_id=${encodeURIComponent(userId)}`);
}

// Knowledge graph is internal; we only trigger its build on access.
export function buildKnowledgeGraph(courseId: string): Promise<{ status: string }> {
  return getJson<{ status: string }>(`/api/ai/knowledge-graph/${courseId}/build`, { method: "POST" });
}

export function startAdaptive(userId: string, courseId: string): Promise<AdaptiveResponse> {
  return getJson<AdaptiveResponse>("/api/ai/adaptive/start", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ user_id: userId, course_id: courseId }),
  });
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
