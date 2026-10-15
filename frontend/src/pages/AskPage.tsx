import { useState, useRef, useEffect } from "react";
import { Send, Sparkles, AlertCircle, Loader2, GraduationCap, Plus, Play, ListChecks, ArrowUp } from "lucide-react";
import Header from "../components/Home/Header";
import { AnswerText } from "../components/ask/AnswerText";
import { MomentPanel } from "../components/ask/MomentPanel";
import { QuickQuiz } from "../components/learn/QuickQuiz";
import { comingUp } from "../components/lab/topicBits";
import { getFollowups, getLabOverview, getLabTopics } from "../lib/learnApi";
import { askHermesStream } from "../lib/ragApi";
import { FBgetChatHistory, FBsaveChatHistory } from "../lib/firebase";
import { useUserSessionStore } from "../store/userSession";
import { FeatureGlimpse } from "../components/common/FeatureGlimpse";
import type { ChatMessage, RagSourceCard } from "../types/rag";

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

type Suggestion = { tag: string; tint: string; text: string };

const humanize = (concept: string) => concept.replace(/[-_]+/g, " ");

/** Four starting questions from the student's own data: weakest concept, next lecture, progress, last question. */
async function personalSuggestions(lastQuestion: string | null): Promise<Suggestion[]> {
  const out: Suggestion[] = [];
  const [overview, topics] = await Promise.all([getLabOverview().catch(() => null), getLabTopics().catch(() => null)]);
  const weak = overview?.weak[0];
  if (weak) out.push({ tag: "YOUR WEAKEST TOPIC", tint: "text-amber-300", text: `Explain ${humanize(weak.concept)} with an example` });
  const next = topics ? comingUp(topics) : null;
  const course = topics?.courses.find((c) => c.slug === next?.slug);
  const lecture = course?.topics.find((t) => t.index === next?.topic)?.lectures.find((l) => l.status !== "solid");
  if (lecture) out.push({ tag: "NEXT IN YOUR COURSE", tint: "text-violet-300", text: `What is “${lecture.title.replace(/^\d+\.\d+\s*-\s*/, "")}” about?` });
  out.push({ tag: "YOUR PROGRESS", tint: "text-teal-300", text: "How am I doing, and what should I study next?" });
  out.push(lastQuestion
    ? { tag: "PICK UP WHERE YOU LEFT OFF", tint: "text-sky-300", text: lastQuestion }
    : { tag: "YOUR QUIZZES", tint: "text-sky-300", text: "What did I score in my last quiz?" });
  return out;
}

function StartScreen({ onQuestion, lastQuestion }: { onQuestion: (q: string) => void; lastQuestion: string | null }) {
  const [text, setText] = useState("");
  const [suggestions, setSuggestions] = useState<Suggestion[] | null>(null);
  useEffect(() => { personalSuggestions(lastQuestion).then(setSuggestions).catch(() => setSuggestions([])); }, [lastQuestion]);
  return (
    <div className="flex flex-col items-center justify-center min-h-full px-5 py-12 gap-8">
      <div className="flex flex-col items-center gap-3 text-center">
        <span className="w-12 h-12 rounded-2xl bg-violet-950 text-violet-300 flex items-center justify-center"><GraduationCap className="w-6 h-6" /></span>
        <h1 className="text-3xl sm:text-4xl font-extrabold tracking-tight text-zinc-50">What are you working on?</h1>
        <p className="text-base text-zinc-400 max-w-xl">Ask about anything you're learning. When your course teaches it, you'll get a link to the exact moment.</p>
      </div>
      <form onSubmit={(e) => { e.preventDefault(); if (text.trim()) onQuestion(text); }}
            className="w-full max-w-3xl flex items-center gap-3 bg-zinc-900 border border-zinc-700 focus-within:border-violet-500/70 rounded-2xl pl-5 pr-2.5 py-2.5 shadow-2xl shadow-black/50">
        <input value={text} onChange={(e) => setText(e.target.value)} aria-label="Your question" autoFocus
               placeholder="e.g. how do I publish my library to npm?"
               className="flex-1 bg-transparent text-base text-zinc-100 placeholder-zinc-500 outline-none py-1.5" />
        <button type="submit" aria-label="Ask" disabled={!text.trim()}
                className="w-11 h-11 rounded-xl bg-violet-600 hover:bg-violet-500 disabled:bg-zinc-700 flex items-center justify-center">
          <ArrowUp className="w-5 h-5 text-white" />
        </button>
      </form>
      <div className="w-full max-w-3xl grid grid-cols-1 sm:grid-cols-2 gap-3">
        {(suggestions ?? []).map((sg) => (
          <button key={sg.text} onClick={() => onQuestion(sg.text)}
                  className="text-left bg-zinc-900 hover:bg-zinc-800/80 border border-zinc-800 hover:border-zinc-600 rounded-2xl px-4 py-3.5 flex flex-col gap-1.5 transition-colors">
            <span className={`text-[11px] font-extrabold tracking-widest ${sg.tint}`}>{sg.tag}</span>
            <span className="text-sm font-bold text-zinc-100">{sg.text}</span>
          </button>
        ))}
        {suggestions === null && [0, 1, 2, 3].map((i) => <div key={i} className="h-20 rounded-2xl bg-zinc-900 animate-pulse" />)}
      </div>
    </div>
  );
}

/** One card per lecture, in the order the answer cited them. */
function distinctMoments(sources: RagSourceCard[] = []): RagSourceCard[] {
  const seen = new Set<string>();
  return sources.filter((s) => (seen.has(s.lecture_title) ? false : (seen.add(s.lecture_title), true)));
}

const mmss = (t: number) => `${Math.floor(t / 60)}:${String(Math.floor(t % 60)).padStart(2, "0")}`;

export default function AskPage() {
  const [messages, setMessages] = useState<ChatMessage[]>(loadLocalHistory);
  const [input, setInput] = useState("");
  const [isStreaming, setIsStreaming] = useState(false);
  // Until hydration finishes for a signed-in user, don't persist — otherwise the
  // local (guest) history could overwrite their Firestore history before it loads.
  const [hydrated, setHydrated] = useState(false);
  const bottomRef = useRef<HTMLDivElement>(null);
  const [selected, setSelected] = useState<RagSourceCard | null>(null);
  const [quizCard, setQuizCard] = useState<RagSourceCard | null>(null);
  const [lastQuestion, setLastQuestion] = useState<string | null>(null);
  // Set when an answer finishes streaming: open its first course moment and fetch follow-up chips, once.
  const finished = useRef<{ id: string; question: string } | null>(null);
  useEffect(() => {
    const f = finished.current;
    if (!f) return;
    const done = messages.find((m) => m.id === f.id);
    if (!done || done.streaming) return;
    finished.current = null;
    const first = distinctMoments(done.sources)[0];
    if (first) setSelected(first);
    if (done.content && !done.insufficient_context) {
      getFollowups(f.question, done.content).then((chips) => {
        if (chips.length) setMessages((prev) => prev.map((m) => (m.id === f.id ? { ...m, followups: chips } : m)));
      });
    }
  }, [messages]);

  const currentuser = useUserSessionStore((s) => s.currentuser);
  const isUserLoggedIn = useUserSessionStore((s) => s.isUserLoggedIn);
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

  const runTutor = (
    question: string,
    opts: { allowGeneral?: boolean; addUserBubble?: boolean } = {},
  ) => {
    const q = question.trim();
    if (!q || isStreaming) return;
    const { allowGeneral = false, addUserBubble = true } = opts;

    const assistantId = generateId();
    setMessages((prev) => [
      ...prev,
      ...(addUserBubble
        ? [{ id: generateId(), role: "user" as const, content: q, timestamp: new Date() }]
        : []),
      { id: assistantId, role: "assistant" as const, content: "", streaming: true, timestamp: new Date() },
    ]);
    if (addUserBubble) setInput("");
    setIsStreaming(true);

    const patch = (changes: Partial<ChatMessage>) =>
      setMessages((prev) => prev.map((m) => (m.id === assistantId ? { ...m, ...changes } : m)));

    let gotToken = false;

    const finishError = (msg: string) =>
      patch({ content: msg, insufficient_context: true, streaming: false });

    const tutorUnavailable = (detail: string) =>
      finishError(`The tutor is temporarily unavailable (${detail}). Please try again in a moment.`);

    askHermesStream(
      q,
      { userId: uid ?? "", courseSlug: "all-courses", allowGeneral },
      {
        onSources: (sources, insufficientContext, _model, offerGeneral) =>
          patch({
            sources,
            insufficient_context: insufficientContext,
            offer_general: offerGeneral,
            general_prompt: offerGeneral ? q : undefined,
          }),
        onToken: (token) => {
          gotToken = true;
          setMessages((prev) =>
            prev.map((m) => (m.id === assistantId ? { ...m, content: m.content + token } : m)),
          );
        },
        onDone: () => {
          patch({ streaming: false });
          setIsStreaming(false);
          finished.current = { id: assistantId, question: q };
        },
        onError: (err) => {
          if (!gotToken) tutorUnavailable(err.message);
          else {
            // Error after partial content: keep what streamed, just stop.
            console.warn("stream interrupted:", err.message);
            patch({ streaming: false });
          }
          setIsStreaming(false);
        },
      },
    ).catch((err) => {
      if (!gotToken) tutorUnavailable((err as Error).message);
      else patch({ streaming: false });
      setIsStreaming(false);
    });
  };

  const submit = (question: string) => runTutor(question);

  const clearHistory = () => {
    if (isStreaming) return;
    const lastUser = [...messages].reverse().find((m) => m.role === "user");
    setLastQuestion(lastUser?.content ?? null);
    setSelected(null);
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

  if (!isUserLoggedIn) {
    return (
      <div className="bg-zinc-950 text-[#F0F0F0] min-h-screen">
        <Header />
        <div className="pt-16">
          <FeatureGlimpse
            icon={Sparkles}
            title="Course AI Assistant"
            tagline="Ask anything about your courses and jump straight to the moment it's taught."
            bullets={[
              "Answers as you type, drawn from your lectures",
              "Source cards linking to the right lecture & timestamp",
              "Your chat history saved across devices",
            ]}
            sample={
              <div className="space-y-2 text-left">
                <div className="bg-indigo-600 text-white rounded-2xl rounded-tr-sm px-3 py-2 text-xs ml-auto max-w-[80%] w-fit">
                  What does npm link do?
                </div>
                <div className="bg-zinc-800/70 border border-zinc-700/50 rounded-2xl rounded-tl-sm px-3 py-2 text-xs text-zinc-200 max-w-[85%]">
                  npm link lets you test a library locally without publishing — it creates a global symlink…
                </div>
              </div>
            }
          />
        </div>
      </div>
    );
  }

  const lastAssistant = [...messages].reverse().find((m) => m.role === "assistant");

  return (
    <div className="bg-zinc-950 text-[#F0F0F0] h-screen flex flex-col">
      <Header />

      <div className="flex-1 flex flex-col min-h-0 pt-16">
        <div className="px-5 sm:px-8 py-3 border-b border-zinc-800 flex items-center justify-between flex-shrink-0">
          <h1 className="text-base font-bold text-zinc-100">Ask AI</h1>
          {messages.length > 0 && (
            <button onClick={clearHistory} disabled={isStreaming}
                    className="flex items-center gap-1.5 text-sm text-zinc-300 hover:text-white border border-zinc-700 hover:border-zinc-500 rounded-full px-3.5 py-1.5 disabled:opacity-40 transition-colors">
              <Plus className="w-4 h-4" /> New chat
            </button>
          )}
        </div>

        <div className="flex-1 flex min-h-0">
          <div className="flex-1 flex flex-col min-w-0">
            <div className="flex-1 overflow-y-auto">
              {messages.length === 0 ? (
                <StartScreen onQuestion={submit} lastQuestion={lastQuestion} />
              ) : (
                <div className="px-5 sm:px-8 py-8 flex flex-col gap-8 max-w-3xl mx-auto w-full">
                  {messages.map((msg) =>
                    msg.role === "user" ? (
                      <div key={msg.id} className="flex justify-end">
                        <div className="max-w-[80%] bg-violet-800 text-violet-50 rounded-2xl rounded-br-md px-4 py-2.5 text-[15px] leading-relaxed">
                          {msg.content}
                        </div>
                      </div>
                    ) : (
                      <div key={msg.id} className="flex flex-col gap-3.5">
                        {msg.streaming && !msg.content ? (
                          <div className="flex items-center gap-2 text-zinc-400 text-sm">
                            <Loader2 className="w-4 h-4 animate-spin" /> Thinking…
                          </div>
                        ) : msg.insufficient_context ? (
                          <div className="flex items-start gap-2.5 bg-amber-950/40 border border-amber-800/50 rounded-2xl px-4 py-3">
                            <AlertCircle className="w-4 h-4 text-amber-400 flex-shrink-0 mt-0.5" />
                            <p className="text-sm text-amber-200 leading-relaxed">{msg.content}</p>
                          </div>
                        ) : (
                          <AnswerText text={msg.content} streaming={msg.streaming} />
                        )}

                        {!msg.streaming && msg.offer_general && msg.general_prompt && (
                          <button onClick={() => runTutor(msg.general_prompt!, { allowGeneral: true, addUserBubble: false })}
                                  disabled={isStreaming}
                                  className="self-start inline-flex items-center gap-1.5 text-xs font-medium text-violet-300 bg-violet-600/10 hover:bg-violet-600/20 border border-violet-500/40 rounded-lg px-3 py-2 disabled:opacity-50">
                            <Sparkles className="w-3.5 h-3.5" /> Answer from general knowledge
                          </button>
                        )}

                        {!msg.streaming && distinctMoments(msg.sources).length > 0 && (
                          <div className="flex flex-wrap gap-2">
                            {distinctMoments(msg.sources).slice(0, 3).map((src) => {
                              const on = selected?.lecture_title === src.lecture_title && selected?.start_time === src.start_time;
                              return (
                                <button key={`${src.lecture_title}-${src.start_time}`} onClick={() => setSelected(src)}
                                        className={`flex items-center gap-2 rounded-full px-3 py-1.5 text-[13px] font-semibold border transition-colors ${
                                          on ? "bg-violet-500/15 border-violet-500 text-violet-50" : "bg-zinc-900 border-zinc-700 text-zinc-300 hover:border-zinc-500"}`}>
                                  <Play className="w-3 h-3 fill-current" />
                                  {src.lecture_title.split(" - ")[0]} · {mmss(src.start_time)}
                                  <span className="font-normal text-zinc-400 hidden sm:inline">{src.lecture_title.split(" - ").slice(1).join(" - ")}</span>
                                </button>
                              );
                            })}
                          </div>
                        )}

                        {!msg.streaming && msg.id === lastAssistant?.id && (
                          <div className="flex flex-wrap gap-2 pt-1">
                            {(msg.followups ?? []).map((f) => (
                              <button key={f} onClick={() => submit(f)} disabled={isStreaming}
                                      className="text-[13px] text-zinc-300 hover:text-white bg-zinc-900 hover:bg-zinc-800 border border-zinc-800 hover:border-zinc-600 rounded-full px-3.5 py-1.5 disabled:opacity-50">
                                {f}
                              </button>
                            ))}
                            {distinctMoments(msg.sources)[0] && (
                              <button onClick={() => setQuizCard(distinctMoments(msg.sources)[0])}
                                      className="flex items-center gap-1.5 text-[13px] font-semibold text-teal-200 bg-teal-950/40 border border-teal-800 hover:border-teal-600 rounded-full px-3.5 py-1.5">
                                <ListChecks className="w-3.5 h-3.5" /> Quiz me on {distinctMoments(msg.sources)[0].lecture_title.split(" - ")[0]}
                              </button>
                            )}
                          </div>
                        )}
                      </div>
                    ),
                  )}
                  <div ref={bottomRef} />
                </div>
              )}
            </div>

            {messages.length > 0 && (
              <div className="px-5 sm:px-8 py-4 border-t border-zinc-800 flex-shrink-0">
                <div className="max-w-3xl mx-auto flex items-end gap-3 bg-zinc-900 border border-zinc-700 focus-within:border-violet-500/60 rounded-2xl pl-4 pr-2.5 py-2.5 transition-colors">
                  <textarea
                    value={input}
                    onChange={(e) => setInput(e.target.value)}
                    onKeyDown={handleKeyDown}
                    placeholder="Ask a follow-up…"
                    aria-label="Ask a follow-up"
                    rows={1}
                    className="flex-1 bg-transparent text-[15px] text-zinc-100 placeholder-zinc-500 resize-none outline-none leading-relaxed max-h-32 py-1.5"
                    style={{ height: "auto", minHeight: "1.5rem" }}
                    onInput={(e) => {
                      const el = e.currentTarget;
                      el.style.height = "auto";
                      el.style.height = `${el.scrollHeight}px`;
                    }}
                    disabled={isStreaming}
                  />
                  <button onClick={() => submit(input)} disabled={!input.trim() || isStreaming} aria-label="Send"
                          className="w-10 h-10 rounded-xl bg-violet-600 hover:bg-violet-500 disabled:bg-zinc-700 disabled:cursor-not-allowed flex items-center justify-center flex-shrink-0 transition-colors">
                    {isStreaming ? <Loader2 className="w-4 h-4 text-white animate-spin" /> : <Send className="w-4 h-4 text-white" />}
                  </button>
                </div>
              </div>
            )}
          </div>

          {selected && (
            <div className="hidden lg:block w-[440px] flex-shrink-0 border-l border-zinc-800 bg-zinc-950">
              <MomentPanel card={selected} onClose={() => setSelected(null)} onQuiz={() => setQuizCard(selected)} />
            </div>
          )}
        </div>
      </div>

      {quizCard && (
        <QuickQuiz courseSlug={quizCard.course_id} lecture={quizCard.lecture_title} onClose={() => setQuizCard(null)} />
      )}
    </div>
  );
}
