// Lab quiz client for the backend's LangGraph flow at /api/lab (backend/app/services/lab/routes.py).

import type { LessonView, Objective } from "../types/lab";
export type { Difficulty, Objective, Question, Quiz, Result, Summary, LessonStatus, LessonView } from "../types/lab";

// Lab is served by the main backend now, not a standalone :8090 service.
// VITE_QUIZME_LANG_URL is retained as an override for pointing at a local
// backend during development. Strip any trailing slash so a `.../` env value
// can't turn this into `.../ /api/lab` (a `//api/lab` that 404s everywhere).
const RAG_API_URL = (import.meta.env.VITE_RAG_API_URL || "http://localhost:8080").replace(/\/+$/, "");
const BASE = import.meta.env.VITE_QUIZME_LANG_URL || `${RAG_API_URL}/api/lab`;

async function post<T>(path: string, body: unknown): Promise<T> {
  const res = await fetch(`${BASE}${path}`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  if (!res.ok) {
    const text = await res.text().catch(() => "Unknown error");
    throw new Error(`Lab API error ${res.status}: ${text}`);
  }
  return res.json();
}

async function get<T>(path: string): Promise<T> {
  const res = await fetch(`${BASE}${path}`);
  if (!res.ok) throw new Error(`Lab API error ${res.status}`);
  return res.json();
}

export async function uploadText(text: string, title?: string): Promise<{ docId: string }> {
  return post("/upload-text", { text, title });
}

export async function uploadPdf(file: File): Promise<{ docId: string }> {
  const form = new FormData();
  form.append("file", file);
  const res = await fetch(`${BASE}/upload`, { method: "POST", body: form });
  if (!res.ok) {
    const text = await res.text().catch(() => "Unknown error");
    throw new Error(`Lab API error ${res.status}: ${text}`);
  }
  return res.json();
}

export function startLesson(docId: string): Promise<LessonView> {
  return post<LessonView>("/lessons", { docId });
}

export function getLesson(id: string): Promise<LessonView> {
  return get<LessonView>(`/lessons/${id}`);
}

export function approveLesson(
  id: string,
  objectives: Objective[],
  questionsPerQuiz: number,
): Promise<LessonView> {
  return post<LessonView>(`/lessons/${id}/approve`, { objectives, questionsPerQuiz });
}

export function submitResult(id: string, score: number, total: number): Promise<LessonView> {
  return post<LessonView>(`/lessons/${id}/submit`, { score, total });
}

export function askTutor(id: string, question: string): Promise<{ answer: string }> {
  return post<{ answer: string }>(`/lessons/${id}/ask`, { question });
}
