import { useState, useRef, useEffect } from "react";
import { Send, Sparkles, AlertCircle, Loader2, Bot, User, Trash2 } from "lucide-react";
import Header from "../components/Home/Header";
import { RagSourceCard } from "../components/rag/RagSourceCard";
import { askQuestionStream, askQuestion } from "../lib/ragApi";
import { FBgetChatHistory, FBsaveChatHistory } from "../lib/firebase";
import { useUserSessionStore } from "../store/userSession";
import type { ChatMessage } from "../types/rag";

function generateId() {
  return Math.random().toString(36).slice(2);
}

const HISTORY_KEY = "rag_chat_history";

// Revive persisted rows into ChatMessages: restore Date, clear any stuck
// streaming flag, and drop assistant turns left empty (e.g. reloaded mid-stream).
function reviveMessages(raw: unknown[]): ChatMessage[] {
  return (raw as Record<string, unknown>[])
    .map((m) => ({
      id: String(m.id),
      role: m.role as ChatMessage["role"],
      content: String(m.content ?? ""),
      sources: (m.sources as ChatMessage["sources"]) ?? undefined,
      insufficient_context: (m.insufficient_context as boolean) ?? undefined,
      streaming: false,
      timestamp: new Date(m.timestamp as string),
    }))
    .filter((m) => m.role === "user" || m.content);
}

// Firestore rejects `undefined`; flatten to a JSON-safe shape with an ISO timestamp.
function serializeMessages(msgs: ChatMessage[]): Record<string, unknown>[] {
  return msgs.map((m) => ({
    id: m.id,
    role: m.role,
    content: m.content,
    sources: m.sources ?? null,
    insufficient_context: m.insufficient_context ?? null,
    timestamp: (m.timestamp instanceof Date ? m.timestamp : new Date(m.timestamp)).toISOString(),
  }));
}

function loadLocalHistory(): ChatMessage[] {
  try {
    const raw = localStorage.getItem(HISTORY_KEY);
    return raw ? reviveMessages(JSON.parse(raw)) : [];
  } catch {
    return [];
  }
}

const EXAMPLE_QUESTIONS = [
  "Why does npm link matter while building a library?",
  "Explain prototype inheritance simply.",
  "What is a WebSocket handshake?",
  "Why does V8 create hidden classes?",
];

function EmptyState({ onQuestion }: { onQuestion: (q: string) => void }) {
  return (
    <div className="flex flex-col items-center justify-center h-full px-6 py-12 text-center">
      <div className="w-14 h-14 rounded-2xl bg-indigo-600/20 border border-indigo-500/30 flex items-center justify-center mb-5">
        <Sparkles className="w-7 h-7 text-indigo-400" />
      </div>
      <h2 className="text-xl font-semibold text-zinc-100 mb-2">Ask anything about the courses</h2>
      <p className="text-sm text-zinc-500 max-w-sm leading-relaxed mb-8">
        The assistant searches across all indexed course transcripts and answers with grounded citations.
      </p>
      <div className="grid grid-cols-1 sm:grid-cols-2 gap-2 w-full max-w-xl">
        {EXAMPLE_QUESTIONS.map((q) => (
          <button
            key={q}
            onClick={() => onQuestion(q)}
            className="text-left px-4 py-3 bg-zinc-800/60 hover:bg-zinc-800 border border-zinc-700/50 hover:border-indigo-500/40 rounded-xl text-sm text-zinc-300 hover:text-zinc-100 transition-all"
          >
            {q}
          </button>
        ))}
      </div>
    </div>
  );
}

export default function AskPage() {
  const [messages, setMessages] = useState<ChatMessage[]>(loadLocalHistory);
  const [input, setInput] = useState("");
  const [isStreaming, setIsStreaming] = useState(false);
  // Until hydration finishes for a signed-in user, don't persist — otherwise the
  // local (guest) history could overwrite their Firestore history before it loads.
  const [hydrated, setHydrated] = useState(false);
  const bottomRef = useRef<HTMLDivElement>(null);

  const currentuser = useUserSessionStore((s) => s.currentuser);
  const uid = (currentuser?.uid as string) || null;

  useEffect(() => {
    // Instant follow while streaming so the newest tokens stay in view;
    // smooth otherwise.
    bottomRef.current?.scrollIntoView({ behavior: isStreaming ? "auto" : "smooth" });
  }, [messages, isStreaming]);

  // Hydrate from the right source: Firestore for signed-in users, localStorage for guests.
  useEffect(() => {
    let cancelled = false;
    if (!uid) {
      setHydrated(true);
      return;
    }
    setHydrated(false);
    FBgetChatHistory(uid)
      .then((remote) => {
        if (cancelled) return;
        if (remote.length) setMessages(reviveMessages(remote));
      })
      .catch(() => {})
      .finally(() => {
        if (!cancelled) setHydrated(true);
      });
    return () => {
      cancelled = true;
    };
  }, [uid]);

  // Persist once a turn settles (avoids a write per streamed token). localStorage
  // always; Firestore additionally for signed-in users so history syncs across devices.
  useEffect(() => {
    if (!hydrated || isStreaming) return;
    try {
      localStorage.setItem(HISTORY_KEY, JSON.stringify(serializeMessages(messages)));
    } catch {
      /* ignore storage quota / private-mode errors */
    }
    if (uid) {
      FBsaveChatHistory(uid, serializeMessages(messages)).catch(() => {});
    }
  }, [messages, isStreaming, hydrated, uid]);

  const submit = (question: string) => {
    const q = question.trim();
    if (!q || isStreaming) return;

    const assistantId = generateId();
    setMessages((prev) => [
      ...prev,
      { id: generateId(), role: "user", content: q, timestamp: new Date() },
      { id: assistantId, role: "assistant", content: "", streaming: true, timestamp: new Date() },
    ]);
    setInput("");
    setIsStreaming(true);

    const patch = (changes: Partial<ChatMessage>) =>
      setMessages((prev) => prev.map((m) => (m.id === assistantId ? { ...m, ...changes } : m)));

    let gotToken = false;

    const finishError = (msg: string) =>
      patch({ content: msg, insufficient_context: true, streaming: false });

    // If streaming is unavailable (e.g. backend mid-deploy without /stream),
    // fall back to the non-streaming endpoint so the assistant still answers.
    const fallbackNonStreaming = async () => {
      try {
        const data = await askQuestion(q);
        patch({
          content: data.answer,
          sources: data.sources,
          insufficient_context: data.insufficient_context,
          streaming: false,
        });
      } catch (err) {
        finishError(
          `Something went wrong: ${(err as Error).message}. Make sure the RAG backend is running.`,
        );
      } finally {
        setIsStreaming(false);
      }
    };

    askQuestionStream(q, {
      onSources: (sources, insufficientContext) =>
        patch({ sources, insufficient_context: insufficientContext }),
      onToken: (token) => {
        gotToken = true;
        setMessages((prev) =>
          prev.map((m) => (m.id === assistantId ? { ...m, content: m.content + token } : m)),
        );
      },
      onDone: () => {
        patch({ streaming: false });
        setIsStreaming(false);
      },
      onError: (err) => {
        if (!gotToken) return void fallbackNonStreaming();
        // Error after partial content: keep what streamed, just stop.
        console.warn("stream interrupted:", err.message);
        patch({ streaming: false });
        setIsStreaming(false);
      },
    }).catch(() => {
      // Request never produced tokens (e.g. /stream 404 during deploy) → fall back.
      if (!gotToken) return void fallbackNonStreaming();
      patch({ streaming: false });
      setIsStreaming(false);
    });
  };

  const clearHistory = () => {
    if (isStreaming) return;
    setMessages([]);
    try {
      localStorage.removeItem(HISTORY_KEY);
    } catch {
      /* ignore */
    }
  };

  const handleKeyDown = (e: React.KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      submit(input);
    }
  };

  return (
    <div className="bg-zinc-950 text-[#F0F0F0] h-screen flex flex-col">
      <Header />

      <div className="flex-1 flex flex-col min-h-0 pt-16">
        {/* Subheader */}
        <div className="px-6 py-3 border-b border-zinc-800 flex items-center justify-between flex-shrink-0">
          <div>
            <h1 className="text-base font-semibold text-zinc-100">Course Assistant</h1>
            <p className="text-xs text-zinc-500">Grounded answers from indexed lectures</p>
          </div>
          <div className="flex items-center gap-3">
            {messages.length > 0 && (
              <button
                onClick={clearHistory}
                disabled={isStreaming}
                className="flex items-center gap-1.5 text-xs text-zinc-500 hover:text-zinc-200 disabled:opacity-40 disabled:cursor-not-allowed transition-colors"
                title="Clear chat history"
              >
                <Trash2 className="w-3.5 h-3.5" />
                Clear
              </button>
            )}
            <span className="text-xs text-zinc-600 bg-zinc-800 px-2.5 py-1 rounded-full border border-zinc-700">
              RAG · semantic search
            </span>
          </div>
        </div>

        {/* Messages */}
        <div className="flex-1 overflow-y-auto">
          {messages.length === 0 ? (
            <EmptyState onQuestion={submit} />
          ) : (
            <div className="px-6 py-6 space-y-6 max-w-3xl mx-auto w-full">
              {messages.map((msg) =>
                msg.role === "user" ? (
                  <div key={msg.id} className="flex justify-end gap-3">
                    <div className="max-w-[75%]">
                      <div className="bg-indigo-600 text-white rounded-2xl rounded-tr-sm px-4 py-3 text-sm leading-relaxed">
                        {msg.content}
                      </div>
                    </div>
                    <div className="w-8 h-8 rounded-full bg-indigo-700 flex items-center justify-center flex-shrink-0 mt-0.5">
                      <User className="w-4 h-4 text-white" />
                    </div>
                  </div>
                ) : (
                  <div key={msg.id} className="flex gap-3">
                    <div className="w-8 h-8 rounded-full bg-zinc-700 border border-zinc-600 flex items-center justify-center flex-shrink-0 mt-0.5">
                      <Bot className="w-4 h-4 text-indigo-400" />
                    </div>
                    <div className="flex-1 min-w-0">
                      {msg.streaming && !msg.content ? (
                        <div className="bg-zinc-800/70 border border-zinc-700/50 rounded-2xl rounded-tl-sm px-4 py-3">
                          <div className="flex items-center gap-2 text-zinc-400">
                            <Loader2 className="w-4 h-4 animate-spin" />
                            <span className="text-sm">Searching course content…</span>
                          </div>
                        </div>
                      ) : msg.insufficient_context ? (
                        <div className="flex items-start gap-2.5 bg-amber-950/40 border border-amber-800/50 rounded-2xl rounded-tl-sm px-4 py-3">
                          <AlertCircle className="w-4 h-4 text-amber-400 flex-shrink-0 mt-0.5" />
                          <p className="text-sm text-amber-200 leading-relaxed">{msg.content}</p>
                        </div>
                      ) : (
                        <div className="bg-zinc-800/70 border border-zinc-700/50 rounded-2xl rounded-tl-sm px-4 py-3">
                          <p className="text-sm text-zinc-100 leading-relaxed whitespace-pre-wrap">
                            {msg.content}
                            {msg.streaming && (
                              <span className="inline-block w-1.5 h-4 ml-0.5 align-text-bottom bg-indigo-400 animate-pulse" />
                            )}
                          </p>
                        </div>
                      )}
                      {!msg.streaming && msg.sources && msg.sources.length > 0 && (
                        <div className="mt-3">
                          <p className="text-xs text-zinc-500 font-medium mb-2 ml-1">Sources</p>
                          <div className="grid grid-cols-1 sm:grid-cols-2 gap-2">
                            {msg.sources.map((src) => (
                              <RagSourceCard key={`${src.lecture_id}-${src.start_time}`} source={src} />
                            ))}
                          </div>
                        </div>
                      )}
                    </div>
                  </div>
                )
              )}
              <div ref={bottomRef} />
            </div>
          )}
        </div>

        {/* Input */}
        <div className="px-6 py-4 border-t border-zinc-800 flex-shrink-0">
          <div className="max-w-3xl mx-auto">
            <div className="flex items-end gap-3 bg-zinc-800/80 border border-zinc-700 focus-within:border-indigo-500/60 rounded-2xl px-4 py-3 transition-colors">
              <textarea
                value={input}
                onChange={(e) => setInput(e.target.value)}
                onKeyDown={handleKeyDown}
                placeholder="Ask anything about the course content…"
                rows={1}
                className="flex-1 bg-transparent text-sm text-zinc-100 placeholder-zinc-600 resize-none outline-none leading-relaxed max-h-32"
                style={{ height: "auto", minHeight: "1.5rem" }}
                onInput={(e) => {
                  const el = e.currentTarget;
                  el.style.height = "auto";
                  el.style.height = `${el.scrollHeight}px`;
                }}
                disabled={isStreaming}
              />
              <button
                onClick={() => submit(input)}
                disabled={!input.trim() || isStreaming}
                className="w-8 h-8 rounded-xl bg-indigo-600 hover:bg-indigo-500 disabled:bg-zinc-700 disabled:cursor-not-allowed flex items-center justify-center flex-shrink-0 transition-colors"
              >
                {isStreaming ? (
                  <Loader2 className="w-4 h-4 text-white animate-spin" />
                ) : (
                  <Send className="w-4 h-4 text-white" />
                )}
              </button>
            </div>
            <p className="text-xs text-zinc-700 text-center mt-2">
              Enter to send · Shift+Enter for new line
            </p>
          </div>
        </div>
      </div>
    </div>
  );
}
