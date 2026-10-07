import { useEffect, useRef, useState } from "react";
import type { PointerEvent as ReactPointerEvent } from "react";
import { useNavigate } from "react-router-dom";
import { Send, Loader2, GraduationCap, User, CirclePlay, Undo2, ExternalLink, PanelRight, GripVertical } from "lucide-react";
import { streamTutor } from "../../lib/learnApi";
import type { TutorNavigate } from "../../lib/learnApi";
import { formatTimestamp } from "../../lib/lectureMatch";
import { useUserSessionStore } from "../../store/userSession";
import type { Course } from "../../types/learn";

interface Msg {
  id: string;
  role: "user" | "assistant";
  content: string;
  streaming?: boolean;
  jump?: TutorNavigate; // set only when the player actually jumped there
  back?: TutorNavigate; // where the student was before that jump
  suggest?: TutorNavigate[]; // moments offered under the answer; nothing has moved
}
const rid = () => Math.random().toString(36).slice(2);

const FLOAT_W = 380;
const FLOAT_H = 560;
const POS_KEY = "tutor_float_pos";

function clampPos(x: number, y: number) {
  const h = Math.min(FLOAT_H, window.innerHeight * 0.7);
  return {
    x: Math.max(8, Math.min(x, window.innerWidth - FLOAT_W - 8)),
    y: Math.max(72, Math.min(y, window.innerHeight - h - 8)),
  };
}

function initialPos() {
  try {
    const saved = JSON.parse(localStorage.getItem(POS_KEY) || "null");
    if (saved && typeof saved.x === "number" && typeof saved.y === "number") return clampPos(saved.x, saved.y);
  } catch { /* ignore */ }
  return clampPos(window.innerWidth - FLOAT_W - 440, window.innerHeight - FLOAT_H - 24);
}

/**
 * The AI tutor for the course player. Docked, it fills the player's right rail (AI Tutor tab);
 * popped out, it is a floating window the student drags anywhere by its title bar. It stays mounted
 * in both modes, so the conversation survives switching tabs or popping it out.
 */
export function PlayerTutor({
  course,
  userId,
  lectureTitle,
  floating,
  visible,
  onPopOut,
  onDock,
  onNavigate,
  canJump,
  getPosition,
}: {
  course: Course;
  userId: string;
  lectureTitle: string;
  /** true: a draggable window over the page; false: docked in the right rail. */
  floating: boolean;
  /** Docked mode only: is the AI Tutor tab showing? (hidden, it stays mounted to keep the chat) */
  visible: boolean;
  onPopOut: () => void;
  onDock: () => void;
  /** Jump the player to that lecture + second. Returns false if the lecture isn't in this course (or is locked). */
  onNavigate?: (nav: TutorNavigate) => boolean;
  /** Would onNavigate land? Checked without jumping, so locked/unknown lectures get no button. */
  canJump?: (nav: TutorNavigate) => boolean;
  /** Current video position in seconds, if the lecture has a video. */
  getPosition?: () => number | undefined;
}) {
  const [messages, setMessages] = useState<Msg[]>([]);
  const [input, setInput] = useState("");
  const [busy, setBusy] = useState(false);
  const [pos, setPos] = useState(initialPos);
  const drag = useRef<{ dx: number; dy: number } | null>(null);
  const bottomRef = useRef<HTMLDivElement>(null);
  const navigate = useNavigate();
  const isUserLoggedIn = useUserSessionStore((s) => s.isUserLoggedIn);
  const shown = floating || visible;

  useEffect(() => {
    if (shown) bottomRef.current?.scrollIntoView({ behavior: busy ? "auto" : "smooth" });
  }, [messages, busy, shown]);

  // Keep a floating window on screen when the browser is resized.
  useEffect(() => {
    if (!floating) return;
    const onResize = () => setPos((p) => clampPos(p.x, p.y));
    window.addEventListener("resize", onResize);
    return () => window.removeEventListener("resize", onResize);
  }, [floating]);

  const startDrag = (e: ReactPointerEvent<HTMLDivElement>) => {
    if ((e.target as HTMLElement).closest("button")) return; // header buttons stay clickable
    drag.current = { dx: e.clientX - pos.x, dy: e.clientY - pos.y };
    e.currentTarget.setPointerCapture(e.pointerId);
  };
  const moveDrag = (e: ReactPointerEvent<HTMLDivElement>) => {
    if (!drag.current) return;
    setPos(clampPos(e.clientX - drag.current.dx, e.clientY - drag.current.dy));
  };
  const endDrag = () => {
    if (!drag.current) return;
    drag.current = null;
    try { localStorage.setItem(POS_KEY, JSON.stringify(pos)); } catch { /* ignore */ }
  };

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
    const askedAt = getPosition?.();
    const askedIn = lectureTitle;

    streamTutor(
      { user_id: userId, course_id: course.course_id, lecture: lectureTitle, messages: history, position: askedAt },
      {
        onToken: (t) => patch((m) => ({ ...m, content: m.content + t })),
        onNavigate: (nav) => {
          if (nav.course_slug && nav.course_slug !== course.course_id) return; // never another course
          const back = askedAt !== undefined
            ? { course_slug: course.course_id, lecture_title: askedIn, start_time: Math.floor(askedAt) }
            : undefined;
          if (onNavigate?.(nav)) patch((m) => ({ ...m, jump: nav, back }));
        },
        onSuggest: (s) => {
          if (s.course_slug && s.course_slug !== course.course_id) return; // never another course
          const moments = s.moments.map((mo) => ({ course_slug: s.course_slug, ...mo }));
          patch((m) => ({ ...m, suggest: moments }));
        },
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

  const linkClass =
    "inline-flex items-center gap-1.5 text-[12px] text-indigo-300 hover:text-indigo-200 hover:underline underline-offset-2 text-left";

  const header = (
    <div
      onPointerDown={floating ? startDrag : undefined}
      onPointerMove={floating ? moveDrag : undefined}
      onPointerUp={floating ? endDrag : undefined}
      onPointerCancel={floating ? endDrag : undefined}
      className={`flex items-center justify-between gap-2 px-3 py-2.5 border-b border-zinc-800 flex-shrink-0 ${
        floating ? "cursor-grab active:cursor-grabbing select-none bg-zinc-800/60 rounded-t-2xl touch-none" : ""
      }`}
    >
      <div className="flex items-center gap-2 min-w-0">
        {floating && <GripVertical className="w-4 h-4 text-zinc-500 flex-shrink-0" aria-hidden="true" />}
        <span className="w-2 h-2 rounded-full bg-indigo-400 flex-shrink-0" aria-hidden="true" />
        <p className="text-[12px] text-indigo-200/90 truncate">Watching “{lectureTitle}”</p>
      </div>
      {floating ? (
        <button onClick={onDock} title="Dock in the side panel" aria-label="Dock in the side panel"
                className="w-8 h-8 rounded-lg text-zinc-400 hover:text-zinc-100 hover:bg-zinc-700/60 flex items-center justify-center flex-shrink-0">
          <PanelRight className="w-4 h-4" />
        </button>
      ) : (
        <button onClick={onPopOut} title="Pop out into a floating window" aria-label="Pop out into a floating window"
                className="w-8 h-8 rounded-lg border border-zinc-700 text-zinc-400 hover:text-zinc-100 hover:bg-zinc-800 flex items-center justify-center flex-shrink-0">
          <ExternalLink className="w-4 h-4" />
        </button>
      )}
    </div>
  );

  const body = !isUserLoggedIn ? (
    <div className="flex-1 flex flex-col items-center justify-center gap-3 px-6 text-center">
      <p className="text-sm text-zinc-400">Sign in to ask the tutor about this lecture.</p>
      <button onClick={() => navigate("/signin")}
              className="bg-indigo-600 hover:bg-indigo-500 text-white text-sm font-medium rounded-lg px-4 py-2">
        Sign in
      </button>
    </div>
  ) : (
    <>
      <div className="flex-1 min-h-0 overflow-y-auto px-3 py-3">
        {messages.length === 0 ? (
          <div className="px-1 py-2">
            <p className="text-xs text-zinc-500 mb-3">Ask about what's on screen, or say “take me to …” to jump the video.</p>
            <div className="space-y-2">
              {["Explain this", "Give me an example for this", "I'm confused about this part"].map((s) => (
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
                    {m.jump && (
                      <div className="mt-2 flex flex-col gap-1">
                        <button onClick={() => m.jump && onNavigate?.(m.jump)} className={linkClass}>
                          <CirclePlay className="w-3.5 h-3.5 flex-shrink-0" />
                          Jump to {m.jump.lecture_title} · {formatTimestamp(m.jump.start_time)}
                        </button>
                        {m.back && (
                          <button onClick={() => m.back && onNavigate?.(m.back)} className={linkClass}>
                            <Undo2 className="w-3.5 h-3.5 flex-shrink-0" />
                            Back to {m.back.lecture_title} · {formatTimestamp(m.back.start_time)}
                          </button>
                        )}
                      </div>
                    )}
                    {!m.streaming && (() => {
                      const links = (m.suggest ?? []).filter((n) => canJump?.(n));
                      return links.length > 0 && (
                        <div className="mt-2 flex flex-col gap-1">
                          <span className="text-[11px] text-zinc-400">Covered in:</span>
                          {links.map((n) => (
                            <button key={`${n.lecture_title}@${n.start_time}`} onClick={() => onNavigate?.(n)} className={linkClass}>
                              <CirclePlay className="w-3.5 h-3.5 flex-shrink-0" />
                              {n.lecture_title} · {formatTimestamp(n.start_time)}
                            </button>
                          ))}
                        </div>
                      );
                    })()}
                  </div>
                </div>
              ),
            )}
            <div ref={bottomRef} />
          </div>
        )}
      </div>

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
            aria-label="Ask the tutor"
            rows={1}
            className="flex-1 bg-transparent text-[13px] text-zinc-100 placeholder-zinc-600 resize-none outline-none leading-relaxed max-h-24 py-1"
            disabled={busy}
          />
          <button
            onClick={() => send(input)}
            disabled={!input.trim() || busy}
            aria-label="Send"
            className="w-7 h-7 rounded-lg bg-indigo-600 hover:bg-indigo-500 disabled:bg-zinc-700 disabled:cursor-not-allowed flex items-center justify-center flex-shrink-0 transition-colors"
          >
            {busy ? <Loader2 className="w-3.5 h-3.5 text-white animate-spin" /> : <Send className="w-3.5 h-3.5 text-white" />}
          </button>
        </div>
      </div>
    </>
  );

  if (floating) {
    return (
      <div
        role="dialog"
        aria-label="AI tutor"
        style={{ left: pos.x, top: pos.y, width: FLOAT_W }}
        className="fixed z-50 h-[min(70vh,560px)] bg-zinc-900 border border-zinc-700 rounded-2xl shadow-2xl shadow-black/60 flex flex-col"
      >
        {header}
        {body}
      </div>
    );
  }
  return (
    <div className={visible ? "flex flex-col h-full min-h-0" : "hidden"}>
      {header}
      {body}
    </div>
  );
}
