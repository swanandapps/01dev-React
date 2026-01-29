import { useEffect, useState } from "react";
import { Compass, Loader2, ArrowRight } from "lucide-react";
import { getRecommendations } from "../../lib/learnApi";
import type { Recommendation, Course } from "../../types/learn";

export function RecommendationsCard({
  userId,
  courses,
  onPick,
}: {
  userId: string;
  courses: Course[];
  onPick: (course: Course) => void;
}) {
  const [recs, setRecs] = useState<Recommendation[] | null>(null);
  const [error, setError] = useState(false);

  useEffect(() => {
    let cancelled = false;
    getRecommendations(userId)
      .then((r) => !cancelled && setRecs(r.recommendations))
      .catch(() => !cancelled && setError(true));
    return () => {
      cancelled = true;
    };
  }, [userId]);

  if (error) return null;

  return (
    <div className="bg-gradient-to-br from-indigo-950/40 to-zinc-900 border border-indigo-500/20 rounded-2xl px-5 py-4 mb-8">
      <div className="flex items-center gap-2 mb-3">
        <Compass className="w-4 h-4 text-indigo-400" />
        <h2 className="text-sm font-semibold text-zinc-100">What to study next</h2>
      </div>

      {!recs && (
        <div className="flex items-center gap-2 text-zinc-500 py-2">
          <Loader2 className="w-4 h-4 animate-spin" />
          <span className="text-sm">Personalizing for you…</span>
        </div>
      )}

      {recs && (
        <div className="space-y-2">
          {recs.map((r) => {
            const course = courses.find((c) => c.course_id === r.course_id);
            return (
              <button
                key={r.course_id}
                onClick={() => course && onPick(course)}
                disabled={!course}
                className="w-full text-left flex items-start justify-between gap-3 bg-zinc-900/60 hover:bg-zinc-800/60 border border-zinc-800 rounded-xl px-4 py-3 transition-colors group disabled:cursor-default"
              >
                <div className="min-w-0">
                  <p className="text-sm font-medium text-zinc-100">{r.course_title}</p>
                  <p className="text-xs text-zinc-500 mt-0.5 leading-relaxed">{r.reason}</p>
                </div>
                {course && (
                  <ArrowRight className="w-4 h-4 text-indigo-400 flex-shrink-0 mt-0.5 opacity-0 group-hover:opacity-100 transition-opacity" />
                )}
              </button>
            );
          })}
        </div>
      )}
    </div>
  );
}
