import type { AskResponse } from "../types/rag";

const API_BASE = import.meta.env.VITE_RAG_API_URL || "http://localhost:8080";

export async function askQuestion(question: string): Promise<AskResponse> {
  const res = await fetch(`${API_BASE}/api/ai/ask`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ question }),
  });
  if (!res.ok) {
    const text = await res.text().catch(() => "Unknown error");
    throw new Error(`Backend error ${res.status}: ${text}`);
  }
  return res.json();
}
