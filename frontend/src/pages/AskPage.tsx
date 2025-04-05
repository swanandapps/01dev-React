import { useState, useRef, useEffect } from "react";
import { Send, Sparkles, AlertCircle, Loader2, Bot, User } from "lucide-react";
import { useMutation } from "@tanstack/react-query";
import Header from "../components/Home/Header";
import { RagSourceCard } from "../components/rag/RagSourceCard";
import { askQuestion } from "../lib/ragApi";
import type { ChatMessage } from "../types/rag";

function generateId() {
  return Math.random().toString(36).slice(2);
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
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [input, setInput] = useState("");
  const bottomRef = useRef<HTMLDivElement>(null);

  const mutation = useMutation({
    mutationFn: askQuestion,
    onSuccess: (data) => {
      setMessages((prev) => [
        ...prev,
        {
          id: generateId(),
          role: "assistant",
          content: data.answer,
          sources: data.sources,
          insufficient_context: data.insufficient_context,
          timestamp: new Date(),
        },
      ]);
    },
    onError: (err: Error) => {
      setMessages((prev) => [
        ...prev,
        {
          id: generateId(),
          role: "assistant",
          content: `Something went wrong: ${err.message}. Make sure the RAG backend is running.`,
          insufficient_context: true,
          timestamp: new Date(),
        },
      ]);
    },
  });

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages, mutation.isPending]);

  const submit = (question: string) => {
    const q = question.trim();
    if (!q || mutation.isPending) return;
    setMessages((prev) => [
      ...prev,
      { id: generateId(), role: "user", content: q, timestamp: new Date() },
    ]);
    setInput("");
    mutation.mutate(q);
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
          <span className="text-xs text-zinc-600 bg-zinc-800 px-2.5 py-1 rounded-full border border-zinc-700">
            RAG · semantic search
          </span>
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
                      {msg.insufficient_context ? (
                        <div className="flex items-start gap-2.5 bg-amber-950/40 border border-amber-800/50 rounded-2xl rounded-tl-sm px-4 py-3">
                          <AlertCircle className="w-4 h-4 text-amber-400 flex-shrink-0 mt-0.5" />
                          <p className="text-sm text-amber-200 leading-relaxed">{msg.content}</p>
                        </div>
                      ) : (
                        <div className="bg-zinc-800/70 border border-zinc-700/50 rounded-2xl rounded-tl-sm px-4 py-3">
                          <p className="text-sm text-zinc-100 leading-relaxed whitespace-pre-wrap">{msg.content}</p>
                        </div>
                      )}
                      {msg.sources && msg.sources.length > 0 && (
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
              {mutation.isPending && (
                <div className="flex gap-3">
                  <div className="w-8 h-8 rounded-full bg-zinc-700 border border-zinc-600 flex items-center justify-center flex-shrink-0">
                    <Bot className="w-4 h-4 text-indigo-400" />
                  </div>
                  <div className="bg-zinc-800/70 border border-zinc-700/50 rounded-2xl rounded-tl-sm px-4 py-3">
                    <div className="flex items-center gap-2 text-zinc-400">
                      <Loader2 className="w-4 h-4 animate-spin" />
                      <span className="text-sm">Searching course content…</span>
                    </div>
                  </div>
                </div>
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
                disabled={mutation.isPending}
              />
              <button
                onClick={() => submit(input)}
                disabled={!input.trim() || mutation.isPending}
                className="w-8 h-8 rounded-xl bg-indigo-600 hover:bg-indigo-500 disabled:bg-zinc-700 disabled:cursor-not-allowed flex items-center justify-center flex-shrink-0 transition-colors"
              >
                {mutation.isPending ? (
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
