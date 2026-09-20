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
  onSources: (
    sources: RagSourceCard[],
    insufficientContext: boolean,
    model: string,
    offerGeneral?: boolean,
  ) => void;
  onToken: (token: string) => void;
  onDone: () => void;
  onError: (err: Error) => void;
}

/**
 * Parses an SSE `data:` stream, dispatching sources/token/done/error to callbacks.
 * Shared by the RAG and Hermes streams (identical event contract).
 */
async function pumpSSE(res: Response, cb: StreamCallbacks): Promise<void> {
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
            cb.onSources(msg.sources, msg.insufficient_context, msg.model, msg.offer_general);
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

/**
 * Streams a grounded answer from the SOVEREIGN Hermes tutor
 * (`POST /api/hermes/chat`): access gate + EU-AI-Act audit + a local model.
 * Same SSE contract as askQuestionStream, but requires a signed-in user_id.
 */
export async function askHermesStream(
  question: string,
  opts: { userId: string; courseSlug?: string; allowGeneral?: boolean },
  cb: StreamCallbacks,
  signal?: AbortSignal,
): Promise<void> {
  const res = await fetch(`${API_BASE}/api/hermes/chat`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      question,
      user_id: opts.userId,
      course_slug: opts.courseSlug ?? "all-courses",
      allow_general: opts.allowGeneral ?? false,
    }),
    signal,
  });
  await pumpSSE(res, cb);
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
            cb.onSources(msg.sources, msg.insufficient_context, msg.model, msg.offer_general);
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
