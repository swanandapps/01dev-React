// Lab — the student content pipeline. Ingestion and the quiz flow live in
// notesQuizApiLang.ts (same LessonView contract as before); this module adds
// the output-selection call.
//
// Contract implemented by backend/app/services/lab.
import type { Objective } from "../types/lab";
import { authHeaders } from "./authHeaders";

// Same base-URL resolution as notesQuizApiLang.ts: strip any trailing slash
// from VITE_RAG_API_URL so a `.../` env value can't turn this into
// `.../ /api/lab` (a `//api/lab` that 404s everywhere).
const RAG_API_URL = (import.meta.env.VITE_RAG_API_URL || "http://localhost:8080").replace(/\/+$/, "");
const BASE = import.meta.env.VITE_QUIZME_LANG_URL || `${RAG_API_URL}/api/lab`;

export type OutputType = "quiz" | "flashcards" | "summary" | "study_plan";

export type Flashcard = { front: string; back: string };
export type StudyPlanStep = { step: number; title: string; detail: string };

export type LabArtifacts = Partial<Record<Exclude<OutputType, "quiz">, unknown>>;

export type GenerateResponse = {
  run_id: string;
  status: string;
  artifacts: LabArtifacts;
  lesson_id: string | null;
  proposed_objectives?: Objective[];
};

async function post<T>(path: string, body: unknown): Promise<T> {
  const res = await fetch(`${BASE}${path}`, {
    method: "POST",
    headers: { "Content-Type": "application/json", ...(await authHeaders()) },
    body: JSON.stringify(body),
  });
  if (!res.ok) {
    const text = await res.text().catch(() => "Unknown error");
    throw new Error(`Lab API error ${res.status}: ${text}`);
  }
  return res.json();
}

export function generateOutputs(
  docId: string,
  outputs: OutputType[],
  studentId = "",
): Promise<GenerateResponse> {
  return post<GenerateResponse>("/generate", {
    docId,
    outputs,
    student_id: studentId,
  });
}

export const OUTPUT_LABELS: Record<OutputType, { label: string; blurb: string }> = {
  quiz: { label: "Quiz me", blurb: "Adaptive questions with hints and a tutor" },
  flashcards: { label: "Flashcards", blurb: "Front-and-back cards to drill" },
  summary: { label: "Quick revision", blurb: "A short summary to re-read" },
  study_plan: { label: "Study plan", blurb: "An ordered roadmap to work through" },
};
