import type { Lecture, StudyGuideStatus, QuestionStatus } from "../types/learn";

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
