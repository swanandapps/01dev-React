import { useEffect, useState } from "react";
import { X, Loader2, TrendingUp, CheckCircle2, AlertTriangle, ArrowRight } from "lucide-react";
import { getCourseInsight, readChatQuestions, readRewatchedLectures } from "../../lib/learnApi";
import type { Course, CourseInsight } from "../../types/learn";

export function InsightModal({
  course,
  userId,
  onClose,
}: {
  course: Course;
  userId: string;
  onClose: () => void;
}) {
  const [insight, setInsight] = useState<CourseInsight | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    getCourseInsight({
      user_id: userId,
      course_id: course.course_id,
      chat_questions: readChatQuestions(),
      rewatched_lectures: readRewatchedLectures(),
    })
      .then((r) => !cancelled && setInsight(r))
      .catch((e) => !cancelled && setError((e as Error).message));
    return () => {
      cancelled = true;
    };
  }, [course.course_id, userId]);

  return (
    <div className="fixed inset-0 z-50 bg-black/70 flex items-center justify-center p-4" onClick={onClose}>
      <div
        className="bg-zinc-900 border border-zinc-700 rounded-2xl w-full max-w-xl flex flex-col max-h-[88vh]"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="flex items-center justify-between px-6 py-4 border-b border-zinc-800 flex-shrink-0">
          <div className="flex items-center gap-2">
            <TrendingUp className="w-4 h-4 text-indigo-400" />
            <div>
              <h2 className="text-sm font-semibold text-zinc-100">How you're doing</h2>
              <p className="text-xs text-zinc-500">{course.title}</p>
            </div>
          </div>
          <button onClick={onClose} className="text-zinc-500 hover:text-zinc-200">
            <X className="w-5 h-5" />
          </button>
        </div>

        <div className="overflow-y-auto px-6 py-5">
          {!insight && !error && (
            <div className="flex flex-col items-center justify-center py-16 text-center">
              <Loader2 className="w-8 h-8 text-indigo-400 animate-spin mb-4" />
              <p className="text-sm text-zinc-300">Analyzing your progress…</p>
              <p className="text-xs text-zinc-600 mt-1">From your quizzes, rewatches, and questions.</p>
            </div>
          )}

          {error && (
            <p className="text-sm text-amber-300 bg-amber-950/40 border border-amber-800/50 rounded-xl px-4 py-3">
              {error}
            </p>
          )}

          {insight && (
            <div className="space-y-6">
              <p className="text-sm text-zinc-200 leading-relaxed bg-zinc-800/50 border border-zinc-700/40 rounded-xl px-4 py-3">
                {insight.summary}
              </p>

              {insight.doing_well.length > 0 && (
                <section>
                  <h3 className="flex items-center gap-2 text-xs font-semibold text-emerald-400 uppercase tracking-wide mb-2.5">
                    <CheckCircle2 className="w-3.5 h-3.5" /> Doing well
                  </h3>
                  <ul className="space-y-1.5">
                    {insight.doing_well.map((d, i) => (
                      <li key={i} className="flex items-start gap-2 text-sm text-zinc-300">
                        <span className="text-emerald-500 mt-0.5">✓</span>
                        <span className="leading-relaxed">{d}</span>
                      </li>
                    ))}
                  </ul>
                </section>
              )}

              {insight.improve.length > 0 && (
                <section>
                  <h3 className="flex items-center gap-2 text-xs font-semibold text-amber-400 uppercase tracking-wide mb-2.5">
                    <AlertTriangle className="w-3.5 h-3.5" /> Where to improve
                  </h3>
                  <ul className="space-y-1.5">
                    {insight.improve.map((d, i) => (
                      <li key={i} className="flex items-start gap-2 text-sm text-zinc-300">
                        <span className="text-amber-500 mt-0.5">→</span>
                        <span className="leading-relaxed">{d}</span>
                      </li>
                    ))}
                  </ul>
                </section>
              )}

              {insight.next_steps.length > 0 && (
                <section>
                  <h3 className="flex items-center gap-2 text-xs font-semibold text-indigo-400 uppercase tracking-wide mb-2.5">
                    <ArrowRight className="w-3.5 h-3.5" /> Next steps
                  </h3>
                  <div className="space-y-2">
                    {insight.next_steps.map((d, i) => (
                      <div key={i} className="text-sm text-zinc-200 bg-indigo-950/30 border border-indigo-500/15 rounded-lg px-3 py-2 leading-relaxed">
                        {d}
                      </div>
                    ))}
                  </div>
                </section>
              )}
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
