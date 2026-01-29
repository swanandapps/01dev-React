import { useEffect, useRef, useState } from "react";
import { BookOpen, Loader2, GraduationCap, Dumbbell, Target } from "lucide-react";
import Header from "../components/Home/Header";
import { StudyGuideModal } from "../components/learn/StudyGuideModal";
import { QuizModal } from "../components/learn/QuizModal";
import { AdaptiveModal } from "../components/learn/AdaptiveModal";
import { RecommendationsCard } from "../components/learn/RecommendationsCard";
import { getCourses, getQuestions, generateQuestions, buildKnowledgeGraph } from "../lib/learnApi";
import { useUserSessionStore } from "../store/userSession";
import type { Course } from "../types/learn";

export default function LearnPage() {
  const [courses, setCourses] = useState<Course[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [activeGuide, setActiveGuide] = useState<Course | null>(null);
  const [activeQuiz, setActiveQuiz] = useState<Course | null>(null);
  const [activeAdaptive, setActiveAdaptive] = useState<Course | null>(null);
  const [quizReady, setQuizReady] = useState<Record<string, boolean>>({});
  const pollRef = useRef<ReturnType<typeof setInterval> | null>(null);

  const currentuser = useUserSessionStore((s) => s.currentuser);
  const userId = (currentuser?.uid as string) || "anonymous";

  useEffect(() => {
    getCourses()
      .then(setCourses)
      .catch((e) => setError((e as Error).message))
      .finally(() => setLoading(false));
  }, []);

  // Check which courses already have a question bank (Practice button visibility).
  useEffect(() => {
    if (!courses.length) return;
    let cancelled = false;

    const check = async () => {
      const entries = await Promise.all(
        courses.map(async (c) => {
          try {
            const res = await getQuestions(c.course_id);
            if (res.status === "none") generateQuestions(c.course_id).catch(() => {});
            if (res.status === "ready") buildKnowledgeGraph(c.course_id).catch(() => {});
            return [c.course_id, res.status === "ready"] as const;
          } catch {
            return [c.course_id, false] as const;
          }
        }),
      );
      if (cancelled) return;
      setQuizReady(Object.fromEntries(entries));
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
  }, [courses]);

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
              <p className="text-sm text-zinc-500">AI study tools for each course</p>
            </div>
          </div>

          {loading && (
            <div className="flex items-center gap-2 text-zinc-400 py-16 justify-center">
              <Loader2 className="w-5 h-5 animate-spin" />
              <span className="text-sm">Loading courses…</span>
            </div>
          )}

          {error && !loading && (
            <p className="text-sm text-amber-300 bg-amber-950/40 border border-amber-800/50 rounded-xl px-4 py-3 mt-6">
              Couldn’t load courses: {error}
            </p>
          )}

          {!loading && !error && courses.length > 0 && (
            <div className="mt-6">
              <RecommendationsCard userId={userId} courses={courses} onPick={setActiveGuide} />
            </div>
          )}

          {!loading && !error && (
            <div className="space-y-3">
              {courses.map((course) => (
                <div
                  key={course.course_id}
                  className="bg-zinc-900 border border-zinc-800 rounded-xl px-5 py-4 hover:border-zinc-700 transition-colors"
                >
                  <div className="flex items-center justify-between gap-3 mb-3">
                    <div>
                      <p className="text-sm font-semibold text-zinc-100">{course.title}</p>
                      <p className="text-xs text-zinc-500">{course.lecture_count} lecture{course.lecture_count === 1 ? "" : "s"}</p>
                    </div>
                  </div>
                  <div className="flex flex-wrap items-center gap-2">
                    <button
                      onClick={() => setActiveGuide(course)}
                      className="flex items-center gap-1.5 text-xs font-medium text-indigo-300 hover:text-indigo-200 bg-indigo-600/15 hover:bg-indigo-600/25 border border-indigo-500/30 rounded-lg px-3 py-1.5 transition-colors"
                    >
                      <BookOpen className="w-3.5 h-3.5" />
                      Study Guide
                    </button>
                    {quizReady[course.course_id] ? (
                      <>
                        <button
                          onClick={() => setActiveQuiz(course)}
                          className="flex items-center gap-1.5 text-xs font-medium text-emerald-300 hover:text-emerald-200 bg-emerald-600/15 hover:bg-emerald-600/25 border border-emerald-500/30 rounded-lg px-3 py-1.5 transition-colors"
                        >
                          <Dumbbell className="w-3.5 h-3.5" />
                          Practice
                        </button>
                        <button
                          onClick={() => setActiveAdaptive(course)}
                          className="flex items-center gap-1.5 text-xs font-medium text-violet-300 hover:text-violet-200 bg-violet-600/15 hover:bg-violet-600/25 border border-violet-500/30 rounded-lg px-3 py-1.5 transition-colors"
                        >
                          <Target className="w-3.5 h-3.5" />
                          Adaptive
                        </button>
                      </>
                    ) : (
                      <span className="flex items-center gap-1.5 text-xs text-zinc-600 px-3 py-1.5">
                        <Loader2 className="w-3.5 h-3.5 animate-spin" />
                        Preparing practice…
                      </span>
                    )}
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>
      </div>

      {activeGuide && <StudyGuideModal course={activeGuide} onClose={() => setActiveGuide(null)} />}
      {activeQuiz && <QuizModal course={activeQuiz} userId={userId} onClose={() => setActiveQuiz(null)} />}
      {activeAdaptive && (
        <AdaptiveModal course={activeAdaptive} userId={userId} onClose={() => setActiveAdaptive(null)} />
      )}
    </div>
  );
}
