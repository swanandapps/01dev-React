import type {
  Course, StudyGuideStatus, QuestionStatus, AdaptiveResponse,
  CourseInsight, Journey, EnrolledCourse,
} from "../types/learn";
import { authHeaders } from "./authHeaders";

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

export function generateQuestions(courseId: string): Promise<QuestionStatus> {
  return getJson<QuestionStatus>(`/api/ai/questions/${courseId}/generate`, { method: "POST" });
}

export function getJourney(userId: string): Promise<Journey> {
  return getJson<Journey>(`/api/ai/journey?user_id=${encodeURIComponent(userId)}`);
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

// Lectures this browser has opened (by title), for the player's course outline progress.
export function viewedLectures(): Set<string> {
  try {
    return new Set(Object.keys(JSON.parse(localStorage.getItem("lecture_views") || "{}")));
  } catch {
    return new Set();
  }
}

// Key moments under the player's video: each passage of the lecture with its one-line summary.
export interface LectureMoment {
  start_time: number;
  summary: string;
}

export async function getLectureMoments(courseSlug: string, lecture: string): Promise<LectureMoment[]> {
  const qs = `course_id=${encodeURIComponent(courseSlug)}&lecture=${encodeURIComponent(lecture)}`;
  const res = await fetch(`${API_BASE}/api/ai/lecture-moments?${qs}`, { headers: { ...(await authHeaders()) } });
  if (!res.ok) throw new Error(`Backend error ${res.status}`);
  return res.json();
}

// The player's "Quiz me": a few questions on what the student has watched of the lecture. The answer key stays
// on the server; submitting grades it and records the result like any course quiz.
export interface QuickQuestion {
  question: string;
  options: string[];
  lecture?: string;
}

export interface QuickQuizResult {
  score: number;
  total: number;
  results: { correct: boolean; correctIndex: number; explanation: string }[];
}

export async function getQuickQuiz(
  courseSlug: string, lecture: string, position?: number,
): Promise<{ quiz_id: string; questions: QuickQuestion[] }> {
  const res = await fetch(`${API_BASE}/api/ai/quick-quiz`, {
    method: "POST",
    headers: { "Content-Type": "application/json", ...(await authHeaders()) },
    body: JSON.stringify({ course_id: courseSlug, lecture, position }),
  });
  if (!res.ok) throw new Error(`Backend error ${res.status}`);
  return res.json();
}

export async function submitQuickQuiz(quizId: string, answers: number[]): Promise<QuickQuizResult> {
  const res = await fetch(`${API_BASE}/api/ai/quick-quiz/${encodeURIComponent(quizId)}/submit`, {
    method: "POST",
    headers: { "Content-Type": "application/json", ...(await authHeaders()) },
    body: JSON.stringify({ answers }),
  });
  if (!res.ok) throw new Error(`Backend error ${res.status}`);
  return res.json();
}

// Lab page side panel: recent quiz sessions and concepts worth revisiting (the student's own data).
export interface LabOverview {
  recent: { title: string; kind: string; score: number; total: number; completed_at: string }[];
  weak: { concept: string; accuracy: number; attempts: number }[];
}

export async function getLabOverview(): Promise<LabOverview> {
  const res = await fetch(`${API_BASE}/api/ai/lab/overview`, { headers: { ...(await authHeaders()) } });
  if (!res.ok) throw new Error(`Backend error ${res.status}`);
  return res.json();
}

// Lab topics: each chapter of the student's courses, its lectures solid / shaky / not tried from their quizzes.
export type LectureStatus = "solid" | "shaky" | "not_tried";

export interface TopicLecture {
  title: string;
  chapter: number;
  sub: number;
  status: LectureStatus;
  right: number;
  total: number;
}

export interface LabTopic {
  index: number;
  name: string;
  lectures: TopicLecture[];
  solid: number;
  shaky: number;
  untried: number;
  last_practised: string;
}

export interface LabTopicsResponse {
  courses: { slug: string; id: number; title: string; topics: LabTopic[] }[];
  start_here: { slug: string; topic: number; why: string } | null;
  keep_fresh: { slug: string; topic: number; why: string } | null;
}

export async function getLabTopics(): Promise<LabTopicsResponse> {
  const res = await fetch(`${API_BASE}/api/ai/lab/topics`, { headers: { ...(await authHeaders()) } });
  if (!res.ok) throw new Error(`Backend error ${res.status}`);
  return res.json();
}

export async function startTopicQuiz(courseSlug: string, chapter: number): Promise<{ quiz_id: string; questions: QuickQuestion[] }> {
  const res = await fetch(`${API_BASE}/api/ai/lab/topic-quiz`, {
    method: "POST",
    headers: { "Content-Type": "application/json", ...(await authHeaders()) },
    body: JSON.stringify({ course_id: courseSlug, chapter }),
  });
  if (!res.ok) throw new Error(`Backend error ${res.status}`);
  return res.json();
}

// Ask page chips: what the student might ask next (best-effort; [] on any problem).
export async function getFollowups(question: string, answer: string): Promise<string[]> {
  try {
    const res = await fetch(`${API_BASE}/api/ai/followups`, {
      method: "POST",
      headers: { "Content-Type": "application/json", ...(await authHeaders()) },
      body: JSON.stringify({ question, answer }),
    });
    if (!res.ok) return [];
    return (await res.json()).suggestions ?? [];
  } catch {
    return [];
  }
}

// The player tutor's "take me to …" (find_moment): sent once, right before "done".
export interface TutorNavigate {
  course_slug: string;
  lecture_title: string;
  start_time: number;
}

// Offered, never followed: sent instead of navigate when the course covers the question.
export interface TutorSuggest {
  course_slug: string;
  moments: { lecture_title: string; start_time: number }[];
}

// Stream a tutor reply over SSE. Resolves when the stream ends.
export async function streamTutor(
  body: {
    user_id: string;
    course_id: string;
    messages: { role: string; content: string }[];
    lecture?: string;
    /** Video position in seconds when the student asked, so "this" means what is on screen. */
    position?: number;
  },
  cb: {
    onToken: (t: string) => void;
    onDone: () => void;
    onError: (e: Error) => void;
    onNavigate?: (nav: TutorNavigate) => void;
    onSuggest?: (s: TutorSuggest) => void;
  },
): Promise<void> {
  const res = await fetch(`${API_BASE}/api/ai/tutor/stream`, {
    method: "POST",
    headers: { "Content-Type": "application/json", ...(await authHeaders()) },
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
        else if (msg.type === "navigate" && typeof msg.lecture_title === "string") {
          cb.onNavigate?.({
            course_slug: String(msg.course_slug ?? ""),
            lecture_title: msg.lecture_title,
            start_time: Number.isFinite(Number(msg.start_time)) ? Math.max(0, Number(msg.start_time)) : 0,
          });
        }
        else if (msg.type === "suggest" && Array.isArray(msg.moments)) {
          const moments = msg.moments
            .filter((m: any) => m && typeof m.lecture_title === "string" && m.lecture_title
              && Number.isFinite(Number(m.start_time)) && Number(m.start_time) >= 0)
            .map((m: any) => ({ lecture_title: m.lecture_title as string, start_time: Number(m.start_time) }));
          if (moments.length) cb.onSuggest?.({ course_slug: String(msg.course_slug ?? ""), moments });
        }
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
  time_taken_ms?: number;
}): Promise<AdaptiveResponse> {
  return getJson<AdaptiveResponse>("/api/ai/adaptive/answer", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
}

export function getEnrollment(userId: string): Promise<EnrolledCourse[]> {
  return getJson<EnrolledCourse[]>(`/api/enrollment/${userId}`);
}

export function enrollCourse(body: {
  student_id: string;
  course_id: number;
  course_title: string;
}): Promise<EnrolledCourse[]> {
  return getJson<EnrolledCourse[]>("/api/enrollment", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
}
