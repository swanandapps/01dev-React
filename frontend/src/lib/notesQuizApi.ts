// Typed client for the Memorang V2 (Notes Quiz) microservice on Railway.
// Set VITE_NOTES_QUIZ_URL in .env.local to the Railway backend URL.

const BASE =
  import.meta.env.VITE_NOTES_QUIZ_URL ||
  "https://pdf-learning-tutor-v2-production.up.railway.app";

export type Difficulty = "beginner" | "intermediate" | "advanced";

export type Objective = {
  id: string;
  title: string;
  difficulty: Difficulty;
  focus: string;
};

export type Question = {
  question: string;
  options: string[];
  correctIndex: number;
  explanation: string;
  hint: string;
};

export type Quiz = { questions: Question[] };

export type Result = {
  objectiveId: string;
  objectiveTitle: string;
  score: number;
  total: number;
};

export type Summary = {
  overall: string;
  perObjective: { title: string; comment: string }[];
  studyTips: string[];
};

export type LessonStatus = "awaiting_approval" | "quizzing" | "complete";

export type LessonView = {
  id: string;
  status: LessonStatus;
  plan?: { objectives: Objective[] };
  objectives?: Objective[];
  objectiveIndex?: number;
  objectivesCount?: number;
  currentObjective?: Objective;
  quiz?: Quiz;
  results?: Result[];
  summary?: Summary;
};

async function post<T>(path: string, body: unknown): Promise<T> {
  const res = await fetch(`${BASE}${path}`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  if (!res.ok) {
    const text = await res.text().catch(() => "Unknown error");
    throw new Error(`Notes Quiz API error ${res.status}: ${text}`);
  }
  return res.json();
}

async function get<T>(path: string): Promise<T> {
  const res = await fetch(`${BASE}${path}`);
  if (!res.ok) throw new Error(`Notes Quiz API error ${res.status}`);
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
    throw new Error(`Notes Quiz API error ${res.status}: ${text}`);
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
