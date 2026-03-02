import type {
  Course, StudyGuideStatus, QuestionStatus, QuizSubmit, QuizSession, AdaptiveResponse,
  RecommendationsResponse, CourseInsight,
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

export function getCourseInsight(body: {
  user_id: string;
  course_id: string;
  chat_questions: string[];
  rewatched_lectures: string[];
}): Promise<CourseInsight> {
  return getJson<CourseInsight>("/api/ai/course-insight", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
}

// Read recent user questions from the saved RAG chat history (localStorage).
export function readChatQuestions(limit = 8): string[] {
  try {
    const raw = localStorage.getItem("rag_chat_history");
    if (!raw) return [];
    return (JSON.parse(raw) as { role: string; content: string }[])
      .filter((m) => m.role === "user" && m.content)
      .map((m) => m.content)
      .slice(-limit);
  } catch {
    return [];
  }
}

// Read which lectures the student has replayed (view count >= 2) from localStorage.
export function readRewatchedLectures(): string[] {
  try {
    const raw = localStorage.getItem("lecture_views");
    if (!raw) return [];
    const views = JSON.parse(raw) as Record<string, number>;
    return Object.entries(views).filter(([, n]) => n >= 2).map(([title]) => title);
  } catch {
    return [];
  }
}

// Increment a lecture's view count (used by the course player to detect rewatches).
export function recordLectureView(lectureTitle: string): void {
  if (!lectureTitle) return;
  try {
    const views = JSON.parse(localStorage.getItem("lecture_views") || "{}") as Record<string, number>;
    views[lectureTitle] = (views[lectureTitle] || 0) + 1;
    localStorage.setItem("lecture_views", JSON.stringify(views));
  } catch {
    /* ignore */
  }
}

// Knowledge graph is internal; we only trigger its build on access.
export function buildKnowledgeGraph(courseId: string): Promise<{ status: string }> {
  return getJson<{ status: string }>(`/api/ai/knowledge-graph/${courseId}/build`, { method: "POST" });
}

// Stream a tutor reply over SSE. Resolves when the stream ends.
export async function streamTutor(
  body: {
    user_id: string;
    course_id: string;
    messages: { role: string; content: string }[];
    lecture?: string;
  },
  cb: { onToken: (t: string) => void; onDone: () => void; onError: (e: Error) => void },
): Promise<void> {
  const res = await fetch(`${API_BASE}/api/ai/tutor/stream`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  if (!res.ok || !res.body) {
    throw new Error(`Backend error ${res.status}`);
  }
  const reader = res.body.getReader();
  const decoder = new TextDecoder();
  let buf = "";
  try {
    while (true) {
      const { done, value } = await reader.read();
      if (done) break;
      buf += decoder.decode(value, { stream: true });
      const parts = buf.split("\n\n");
      buf = parts.pop() ?? "";
      for (const part of parts) {
        const line = part.trim();
        if (!line.startsWith("data:")) continue;
        const msg = JSON.parse(line.slice(5).trim());
        if (msg.type === "token") cb.onToken(msg.value);
        else if (msg.type === "done") cb.onDone();
        else if (msg.type === "error") cb.onError(new Error(msg.message));
      }
    }
  } finally {
    reader.releaseLock();
  }
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
