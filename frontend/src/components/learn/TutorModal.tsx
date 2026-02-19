import { useEffect, useRef, useState } from "react";
import { X, Send, Loader2, GraduationCap, User } from "lucide-react";
import { streamTutor } from "../../lib/learnApi";
import type { Course } from "../../types/learn";

interface Msg {
  id: string;
  role: "user" | "assistant";
  content: string;
  streaming?: boolean;
}

const rid = () => Math.random().toString(36).slice(2);

export function TutorModal({
  course,
  userId,
  onClose,
}: {
  course: Course;
  userId: string;
  onClose: () => void;
}) {
  const [messages, setMessages] = useState<Msg[]>([]);
  const [input, setInput] = useState("");
  const [busy, setBusy] = useState(false);
  const bottomRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: busy ? "auto" : "smooth" });
  }, [messages, busy]);

  const send = (text: string) => {
    const q = text.trim();
    if (!q || busy) return;

    const aId = rid();
    const next: Msg[] = [
      ...messages,
      { id: rid(), role: "user", content: q },
      { id: aId, role: "assistant", content: "", streaming: true },
    ];
    setMessages(next);
    setInput("");
    setBusy(true);

    const history = next
      .filter((m) => !m.streaming)
      .map((m) => ({ role: m.role, content: m.content }));

    const patch = (fn: (m: Msg) => Msg) =>
      setMessages((prev) => prev.map((m) => (m.id === aId ? fn(m) : m)));

    streamTutor(
      { user_id: userId, course_id: course.course_id, messages: history },
      {
        onToken: (t) => patch((m) => ({ ...m, content: m.content + t })),
        onDone: () => {
          patch((m) => ({ ...m, streaming: false }));
          setBusy(false);
        },
        onError: (e) => {
          patch((m) => ({ ...m, content: m.content || `Sorry — ${e.message}`, streaming: false }));
          setBusy(false);
        },
      },
    ).catch((e: Error) => {
      patch((m) => ({ ...m, content: m.content || `Sorry — ${e.message}`, streaming: false }));
      setBusy(false);
    });
  };

  const starters = [
    "Explain the hardest idea in this course simply",
    "Quiz me on my weak areas",
    "Where should I focus next?",
  ];

  return (
    <div className="fixed inset-0 z-50 bg-black/70 flex items-center justify-center p-4" onClick={onClose}>
      <div
        className="bg-zinc-900 border border-zinc-700 rounded-2xl w-full max-w-xl flex flex-col h-[80vh]"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="flex items-center justify-between px-6 py-4 border-b border-zinc-800 flex-shrink-0">
          <div className="flex items-center gap-2">
            <div className="w-8 h-8 rounded-lg bg-indigo-600/20 border border-indigo-500/30 flex items-center justify-center">
              <GraduationCap className="w-4 h-4 text-indigo-400" />
            </div>
            <div>
              <h2 className="text-sm font-semibold text-zinc-100">AI Tutor</h2>
              <p className="text-xs text-zinc-500">{course.title} · knows how you're doing</p>
            </div>
          </div>
          <button onClick={onClose} className="text-zinc-500 hover:text-zinc-200">
            <X className="w-5 h-5" />
          </button>
        </div>

        <div className="flex-1 overflow-y-auto px-5 py-4">
          {messages.length === 0 ? (
            <div className="h-full flex flex-col items-center justify-center text-center px-6">
              <div className="w-12 h-12 rounded-2xl bg-indigo-600/20 border border-indigo-500/30 flex items-center justify-center mb-4">
                <GraduationCap className="w-6 h-6 text-indigo-400" />
              </div>
              <p className="text-sm text-zinc-300 mb-1">Your personal tutor for this course</p>
              <p className="text-xs text-zinc-600 mb-6">It uses the course material and your quiz performance.</p>
              <div className="space-y-2 w-full max-w-sm">
                {starters.map((s) => (
                  <button
                    key={s}
                    onClick={() => send(s)}
                    className="w-full text-left text-sm text-zinc-300 hover:text-zinc-100 bg-zinc-800/60 hover:bg-zinc-800 border border-zinc-700/50 rounded-xl px-4 py-2.5 transition-colors"
                  >
                    {s}
                  </button>
                ))}
              </div>
            </div>
          ) : (
            <div className="space-y-4">
              {messages.map((m) =>
                m.role === "user" ? (
                  <div key={m.id} className="flex justify-end gap-2.5">
                    <div className="max-w-[80%] bg-indigo-600 text-white rounded-2xl rounded-tr-sm px-4 py-2.5 text-sm leading-relaxed">
                      {m.content}
                    </div>
                    <div className="w-7 h-7 rounded-full bg-indigo-700 flex items-center justify-center flex-shrink-0 mt-0.5">
                      <User className="w-3.5 h-3.5 text-white" />
                    </div>
                  </div>
                ) : (
                  <div key={m.id} className="flex gap-2.5">
                    <div className="w-7 h-7 rounded-full bg-zinc-700 border border-zinc-600 flex items-center justify-center flex-shrink-0 mt-0.5">
                      <GraduationCap className="w-3.5 h-3.5 text-indigo-400" />
                    </div>
                    <div className="max-w-[80%] bg-zinc-800/70 border border-zinc-700/50 rounded-2xl rounded-tl-sm px-4 py-2.5">
                      {m.content || m.streaming ? (
                        <p className="text-sm text-zinc-100 leading-relaxed whitespace-pre-wrap">
                          {m.content}
                          {m.streaming && (
                            <span className="inline-block w-1.5 h-4 ml-0.5 align-text-bottom bg-indigo-400 animate-pulse" />
                          )}
                        </p>
                      ) : (
                        <Loader2 className="w-4 h-4 text-zinc-400 animate-spin" />
                      )}
                    </div>
                  </div>
                ),
              )}
              <div ref={bottomRef} />
            </div>
          )}
        </div>

        <div className="px-4 py-3 border-t border-zinc-800 flex-shrink-0">
          <div className="flex items-end gap-2 bg-zinc-800/80 border border-zinc-700 focus-within:border-indigo-500/60 rounded-xl px-3 py-2 transition-colors">
            <textarea
              value={input}
              onChange={(e) => setInput(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === "Enter" && !e.shiftKey) {
                  e.preventDefault();
                  send(input);
                }
              }}
              placeholder="Ask your tutor anything about this course…"
              rows={1}
              className="flex-1 bg-transparent text-sm text-zinc-100 placeholder-zinc-600 resize-none outline-none leading-relaxed max-h-28 py-1"
              disabled={busy}
            />
            <button
              onClick={() => send(input)}
              disabled={!input.trim() || busy}
              className="w-8 h-8 rounded-lg bg-indigo-600 hover:bg-indigo-500 disabled:bg-zinc-700 disabled:cursor-not-allowed flex items-center justify-center flex-shrink-0 transition-colors"
            >
              {busy ? <Loader2 className="w-4 h-4 text-white animate-spin" /> : <Send className="w-4 h-4 text-white" />}
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}
