import { useEffect, useRef, useState } from "react";
import { BookOpen, Loader2, GraduationCap, Dumbbell, Target } from "lucide-react";
import Header from "../components/Home/Header";
import { StudyGuideModal } from "../components/learn/StudyGuideModal";
import { QuizModal } from "../components/learn/QuizModal";
import { AdaptiveModal } from "../components/learn/AdaptiveModal";
import { getLectures, getQuestions, generateQuestions, buildKnowledgeGraph } from "../lib/learnApi";
import { useUserSessionStore } from "../store/userSession";
import type { Lecture } from "../types/learn";

export default function LearnPage() {
  const [lectures, setLectures] = useState<Lecture[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [activeGuide, setActiveGuide] = useState<Lecture | null>(null);
  const [activeQuiz, setActiveQuiz] = useState<Lecture | null>(null);
  const [activeAdaptive, setActiveAdaptive] = useState<Lecture | null>(null);
  // lecture_id -> whether a question bank is ready
  const [quizReady, setQuizReady] = useState<Record<string, boolean>>({});
  const pollRef = useRef<ReturnType<typeof setInterval> | null>(null);

  const currentuser = useUserSessionStore((s) => s.currentuser);
  const userId = (currentuser?.uid as string) || "anonymous";

  useEffect(() => {
    getLectures()
      .then(setLectures)
      .catch((e) => setError((e as Error).message))
      .finally(() => setLoading(false));
  }, []);

  // Check which lectures already have a question bank (Practice button visibility).
  useEffect(() => {
    if (!lectures.length) return;
    let cancelled = false;

    const check = async () => {
      const entries = await Promise.all(
        lectures.map(async (l) => {
          try {
            const res = await getQuestions(l.lecture_id);
            // Generate on first access so the Practice button can light up.
            if (res.status === "none") generateQuestions(l.lecture_id).catch(() => {});
            // Build the (internal) knowledge graph in the background too.
            if (res.status === "ready") buildKnowledgeGraph(l.lecture_id).catch(() => {});
            return [l.lecture_id, res.status === "ready"] as const;
          } catch {
            return [l.lecture_id, false] as const;
          }
        }),
      );
      if (cancelled) return;
      setQuizReady(Object.fromEntries(entries));
      // Stop polling once every lecture is ready.
      if (entries.every(([, ready]) => ready) && pollRef.current) {
        clearInterval(pollRef.current);
        pollRef.current = null;
      }
    };

    check();
    pollRef.current = setInterval(check, 4000);
    return () => {
      cancelled = true;
      if (pollRef.current) clearInterval(pollRef.current);
    };
  }, [lectures]);

  // Group lectures by course for a tidy list.
  const byCourse = lectures.reduce<Record<string, Lecture[]>>((acc, l) => {
    (acc[l.course_title] ??= []).push(l);
    return acc;
  }, {});

  return (
    <div className="bg-zinc-950 text-[#F0F0F0] min-h-screen">
      <Header />
      <div className="pt-16">
        <div className="max-w-3xl mx-auto px-6 py-8">
          <div className="flex items-center gap-3 mb-2">
            <div className="w-10 h-10 rounded-xl bg-indigo-600/20 border border-indigo-500/30 flex items-center justify-center">
              <GraduationCap className="w-6 h-6 text-indigo-400" />
            </div>
            <div>
              <h1 className="text-xl font-semibold text-zinc-100">Learn</h1>
              <p className="text-sm text-zinc-500">AI study tools for lectures with transcripts</p>
            </div>
          </div>

          {loading && (
            <div className="flex items-center gap-2 text-zinc-400 py-16 justify-center">
              <Loader2 className="w-5 h-5 animate-spin" />
              <span className="text-sm">Loading lectures…</span>
            </div>
          )}

          {error && !loading && (
            <p className="text-sm text-amber-300 bg-amber-950/40 border border-amber-800/50 rounded-xl px-4 py-3 mt-6">
              Couldn’t load lectures: {error}
            </p>
          )}

          {!loading && !error && (
            <div className="mt-6 space-y-8">
              {Object.entries(byCourse).map(([course, items]) => (
                <section key={course}>
                  <h2 className="text-xs font-semibold text-zinc-500 uppercase tracking-wide mb-3">{course}</h2>
                  <div className="space-y-2">
                    {items.map((lec) => (
                      <div
                        key={lec.lecture_id}
                        className="flex items-center justify-between gap-3 bg-zinc-900 border border-zinc-800 rounded-xl px-4 py-3 hover:border-zinc-700 transition-colors"
                      >
                        <p className="text-sm text-zinc-200 min-w-0">{lec.lecture_title}</p>
                        <div className="flex items-center gap-2 flex-shrink-0">
                          <button
                            onClick={() => setActiveGuide(lec)}
                            className="flex items-center gap-1.5 text-xs font-medium text-indigo-300 hover:text-indigo-200 bg-indigo-600/15 hover:bg-indigo-600/25 border border-indigo-500/30 rounded-lg px-3 py-1.5 transition-colors"
                          >
                            <BookOpen className="w-3.5 h-3.5" />
                            Study Guide
                          </button>
                          {quizReady[lec.lecture_id] ? (
                            <>
                              <button
                                onClick={() => setActiveQuiz(lec)}
                                className="flex items-center gap-1.5 text-xs font-medium text-emerald-300 hover:text-emerald-200 bg-emerald-600/15 hover:bg-emerald-600/25 border border-emerald-500/30 rounded-lg px-3 py-1.5 transition-colors"
                              >
                                <Dumbbell className="w-3.5 h-3.5" />
                                Practice
                              </button>
                              <button
                                onClick={() => setActiveAdaptive(lec)}
                                className="flex items-center gap-1.5 text-xs font-medium text-violet-300 hover:text-violet-200 bg-violet-600/15 hover:bg-violet-600/25 border border-violet-500/30 rounded-lg px-3 py-1.5 transition-colors"
                              >
                                <Target className="w-3.5 h-3.5" />
                                Adaptive
                              </button>
                            </>
                          ) : (
                            <span className="flex items-center gap-1.5 text-xs text-zinc-600 px-3 py-1.5">
                              <Loader2 className="w-3.5 h-3.5 animate-spin" />
                              Prep…
                            </span>
                          )}
                        </div>
                      </div>
                    ))}
                  </div>
                </section>
              ))}
            </div>
          )}
        </div>
      </div>

      {activeGuide && (
        <StudyGuideModal lecture={activeGuide} onClose={() => setActiveGuide(null)} />
      )}
      {activeQuiz && (
        <QuizModal lecture={activeQuiz} userId={userId} onClose={() => setActiveQuiz(null)} />
      )}
      {activeAdaptive && (
        <AdaptiveModal lecture={activeAdaptive} userId={userId} onClose={() => setActiveAdaptive(null)} />
      )}
    </div>
  );
}
