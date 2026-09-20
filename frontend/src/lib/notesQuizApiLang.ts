// LangGraph-backed QuizMe client — IDENTICAL interface to notesQuizApi.ts (the
// Mastra/Memorang V2 client). Only the backend differs: a local sovereign
// LangGraph service instead of the cloud Mastra service. This is the "same
// contract, swapped stack" proof — the exact same UI drives either one.
//
// Contract implemented by backend/lesson_service (see HERMES_HLD / mapping doc).

import type {
  LessonView, Objective,
} from "./notesQuizApi";
export type {
  Difficulty, Objective, Question, Quiz, Result, Summary, LessonStatus, LessonView,
} from "./notesQuizApi";

const BASE = import.meta.env.VITE_QUIZME_LANG_URL || "http://localhost:8090";

async function post<T>(path: string, body: unknown): Promise<T> {
  const res = await fetch(`${BASE}${path}`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  if (!res.ok) {
    const text = await res.text().catch(() => "Unknown error");
    throw new Error(`QuizMe (LangGraph) API error ${res.status}: ${text}`);
  }
  return res.json();
}

async function get<T>(path: string): Promise<T> {
  const res = await fetch(`${BASE}${path}`);
  if (!res.ok) throw new Error(`QuizMe (LangGraph) API error ${res.status}`);
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
    throw new Error(`QuizMe (LangGraph) API error ${res.status}: ${text}`);
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
