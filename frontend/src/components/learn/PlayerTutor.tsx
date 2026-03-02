import { useEffect, useRef, useState } from "react";
import { Sparkles, X, Send, Loader2, GraduationCap, User, Minus } from "lucide-react";
import { streamTutor } from "../../lib/learnApi";
import type { Course } from "../../types/learn";

interface Msg {
  id: string;
  role: "user" | "assistant";
  content: string;
  streaming?: boolean;
}
const rid = () => Math.random().toString(36).slice(2);

/**
 * A floating AI tutor for the course player. It does NOT use a backdrop, so the
 * video keeps playing behind it. It's aware of the lecture currently on screen.
 */
export function PlayerTutor({
  course,
  userId,
  lectureTitle,
}: {
  course: Course;
  userId: string;
  lectureTitle: string;
}) {
  const [open, setOpen] = useState(false);
  const [messages, setMessages] = useState<Msg[]>([]);
  const [input, setInput] = useState("");
  const [busy, setBusy] = useState(false);
  const bottomRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (open) bottomRef.current?.scrollIntoView({ behavior: busy ? "auto" : "smooth" });
  }, [messages, busy, open]);

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

    const history = next.filter((m) => !m.streaming).map((m) => ({ role: m.role, content: m.content }));
    const patch = (fn: (m: Msg) => Msg) =>
      setMessages((prev) => prev.map((m) => (m.id === aId ? fn(m) : m)));

    streamTutor(
      { user_id: userId, course_id: course.course_id, lecture: lectureTitle, messages: history },
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

  // Floating button when collapsed.
  if (!open) {
    return (
      <button
        onClick={() => setOpen(true)}
        className="fixed bottom-6 right-6 z-40 flex items-center gap-2 bg-indigo-600 hover:bg-indigo-500 text-white text-sm font-medium rounded-full pl-4 pr-5 py-3 shadow-lg shadow-indigo-900/40 transition-colors"
      >
        <Sparkles className="w-4 h-4" />
        Ask AI
      </button>
    );
  }

  return (
    <div className="fixed bottom-6 right-6 z-40 w-[min(94vw,380px)] h-[min(70vh,560px)] bg-zinc-900 border border-zinc-700 rounded-2xl shadow-2xl shadow-black/50 flex flex-col">
      {/* header */}
      <div className="flex items-center justify-between px-4 py-3 border-b border-zinc-800 flex-shrink-0">
        <div className="flex items-center gap-2 min-w-0">
          <div className="w-7 h-7 rounded-lg bg-indigo-600/20 border border-indigo-500/30 flex items-center justify-center flex-shrink-0">
            <GraduationCap className="w-4 h-4 text-indigo-400" />
          </div>
          <div className="min-w-0">
            <p className="text-sm font-semibold text-zinc-100 leading-tight">AI Tutor</p>
            <p className="text-[11px] text-zinc-500 truncate">on “{lectureTitle}”</p>
          </div>
        </div>
        <button onClick={() => setOpen(false)} className="text-zinc-500 hover:text-zinc-200" title="Minimize">
          <Minus className="w-4 h-4" />
        </button>
      </div>

      {/* messages */}
      <div className="flex-1 overflow-y-auto px-3 py-3">
        {messages.length === 0 ? (
          <div className="px-1 py-2">
            <p className="text-xs text-zinc-500 mb-3">Stuck on this lecture? Ask me anything — I know the course and how you're doing.</p>
            <div className="space-y-2">
              {["Explain what this lecture covers", "I'm confused about this part", "Give me an example"].map((s) => (
                <button
                  key={s}
                  onClick={() => send(s)}
                  className="w-full text-left text-xs text-zinc-300 hover:text-zinc-100 bg-zinc-800/60 hover:bg-zinc-800 border border-zinc-700/50 rounded-lg px-3 py-2 transition-colors"
                >
                  {s}
                </button>
              ))}
            </div>
          </div>
        ) : (
          <div className="space-y-3">
            {messages.map((m) =>
              m.role === "user" ? (
                <div key={m.id} className="flex justify-end gap-2">
                  <div className="max-w-[82%] bg-indigo-600 text-white rounded-2xl rounded-tr-sm px-3 py-2 text-[13px] leading-relaxed">
                    {m.content}
                  </div>
                  <div className="w-6 h-6 rounded-full bg-indigo-700 flex items-center justify-center flex-shrink-0 mt-0.5">
                    <User className="w-3 h-3 text-white" />
                  </div>
                </div>
              ) : (
                <div key={m.id} className="flex gap-2">
                  <div className="w-6 h-6 rounded-full bg-zinc-700 border border-zinc-600 flex items-center justify-center flex-shrink-0 mt-0.5">
                    <GraduationCap className="w-3 h-3 text-indigo-400" />
                  </div>
                  <div className="max-w-[82%] bg-zinc-800/70 border border-zinc-700/50 rounded-2xl rounded-tl-sm px-3 py-2">
                    {m.content || m.streaming ? (
                      <p className="text-[13px] text-zinc-100 leading-relaxed whitespace-pre-wrap">
                        {m.content}
                        {m.streaming && <span className="inline-block w-1.5 h-3.5 ml-0.5 align-text-bottom bg-indigo-400 animate-pulse" />}
                      </p>
                    ) : (
                      <Loader2 className="w-3.5 h-3.5 text-zinc-400 animate-spin" />
                    )}
                  </div>
                </div>
              ),
            )}
            <div ref={bottomRef} />
          </div>
        )}
      </div>

      {/* input */}
      <div className="px-3 py-2.5 border-t border-zinc-800 flex-shrink-0">
        <div className="flex items-end gap-2 bg-zinc-800/80 border border-zinc-700 focus-within:border-indigo-500/60 rounded-xl px-3 py-1.5 transition-colors">
          <textarea
            value={input}
            onChange={(e) => setInput(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === "Enter" && !e.shiftKey) {
                e.preventDefault();
                send(input);
              }
            }}
            placeholder="Ask about this lecture…"
            rows={1}
            className="flex-1 bg-transparent text-[13px] text-zinc-100 placeholder-zinc-600 resize-none outline-none leading-relaxed max-h-24 py-1"
            disabled={busy}
          />
          <button
            onClick={() => send(input)}
            disabled={!input.trim() || busy}
            className="w-7 h-7 rounded-lg bg-indigo-600 hover:bg-indigo-500 disabled:bg-zinc-700 disabled:cursor-not-allowed flex items-center justify-center flex-shrink-0 transition-colors"
          >
            {busy ? <Loader2 className="w-3.5 h-3.5 text-white animate-spin" /> : <Send className="w-3.5 h-3.5 text-white" />}
          </button>
        </div>
      </div>
    </div>
  );
}
