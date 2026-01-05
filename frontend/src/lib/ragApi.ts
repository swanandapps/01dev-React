import type { AskResponse, RagSourceCard } from "../types/rag";

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

export interface StreamCallbacks {
  onSources: (sources: RagSourceCard[], insufficientContext: boolean, model: string) => void;
  onToken: (token: string) => void;
  onDone: () => void;
  onError: (err: Error) => void;
}

/**
 * Streams a RAG answer over Server-Sent Events. Resolves when the stream ends.
 * Emits sources first, then answer tokens, then completes.
 */
export async function askQuestionStream(
  question: string,
  cb: StreamCallbacks,
  signal?: AbortSignal,
): Promise<void> {
  const res = await fetch(`${API_BASE}/api/ai/ask/stream`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ question }),
    signal,
  });

  if (!res.ok || !res.body) {
    const text = await res.text().catch(() => "Unknown error");
    throw new Error(`Backend error ${res.status}: ${text}`);
  }

  const reader = res.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";

  try {
    while (true) {
      const { done, value } = await reader.read();
      if (done) break;
      buffer += decoder.decode(value, { stream: true });

      // SSE messages are separated by a blank line.
      const parts = buffer.split("\n\n");
      buffer = parts.pop() ?? "";
      for (const part of parts) {
        const line = part.trim();
        if (!line.startsWith("data:")) continue;
        const json = line.slice(5).trim();
        if (!json) continue;
        const msg = JSON.parse(json);
        switch (msg.type) {
          case "sources":
            cb.onSources(msg.sources, msg.insufficient_context, msg.model);
            break;
          case "token":
            cb.onToken(msg.value);
            break;
          case "done":
            cb.onDone();
            break;
          case "error":
            cb.onError(new Error(msg.message));
            break;
        }
      }
    }
  } finally {
    reader.releaseLock();
  }
}
