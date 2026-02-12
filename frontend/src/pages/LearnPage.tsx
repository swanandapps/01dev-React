import { useEffect, useState } from "react";
import { Loader2, GraduationCap, Compass, BarChart3 } from "lucide-react";
import Header from "../components/Home/Header";
import { CourseCompanion } from "../components/learn/CourseCompanion";
import { getCourses, getRecommendations, listQuizSessions } from "../lib/learnApi";
import { useUserSessionStore } from "../store/userSession";
import type { Course, Recommendation, QuizSession } from "../types/learn";

// Group sessions by course so a course shows once — with attempt count and the
// latest result as a comparable percentage (adaptive runs vary in length).
function groupProgressByCourse(sessions: QuizSession[]) {
  const byCourse: Record<string, { course_id: string; title: string; attempts: number; latest: QuizSession; bestPct: number }> = {};
  for (const s of sessions) {
    const pct = s.score / Math.max(s.total, 1);
    const g = byCourse[s.course_id];
    if (!g) {
      byCourse[s.course_id] = { course_id: s.course_id, title: s.course_title, attempts: 1, latest: s, bestPct: pct };
    } else {
      g.attempts += 1;
      g.bestPct = Math.max(g.bestPct, pct);
      if (s.completed_at > g.latest.completed_at) g.latest = s;
    }
  }
  return Object.values(byCourse)
    .map((g) => ({ ...g, latestPct: g.latest.score / Math.max(g.latest.total, 1) }))
    .sort((a, b) => (b.latest.completed_at > a.latest.completed_at ? 1 : -1));
}

// Aggregate per-concept accuracy across all of a user's quiz sessions.
function aggregateWeakConcepts(sessions: QuizSession[]) {
  const agg: Record<string, { attempts: number; correct: number }> = {};
  for (const s of sessions) {
    for (const c of s.concept_breakdown) {
      const a = (agg[c.concept] ??= { attempts: 0, correct: 0 });
      a.attempts += c.attempts;
      a.correct += c.correct;
    }
  }
  return Object.entries(agg)
    .map(([concept, v]) => ({ concept, accuracy: v.correct / Math.max(v.attempts, 1) }))
    .filter((c) => c.accuracy < 0.8)
    .sort((a, b) => a.accuracy - b.accuracy)
    .slice(0, 6);
}

export default function MyLearningPage() {
  const [courses, setCourses] = useState<Course[]>([]);
  const [recs, setRecs] = useState<Recommendation[] | null>(null);
  const [sessions, setSessions] = useState<QuizSession[]>([]);
  const [loading, setLoading] = useState(true);

  const currentuser = useUserSessionStore((s) => s.currentuser);
  const userId = (currentuser?.uid as string) || "anonymous";

  useEffect(() => {
    Promise.all([getCourses(), getRecommendations(userId), listQuizSessions(userId)])
      .then(([cs, r, ss]) => {
        setCourses(cs);
        setRecs(r.recommendations);
        setSessions(ss);
      })
      .catch(() => setRecs([]))
      .finally(() => setLoading(false));
  }, [userId]);

  const weak = aggregateWeakConcepts(sessions);

  return (
    <div className="bg-zinc-950 text-[#F0F0F0] min-h-screen">
      <Header />
      <div className="pt-16">
        <div className="max-w-3xl mx-auto px-6 py-8">
          <div className="flex items-center gap-3 mb-8">
            <div className="w-10 h-10 rounded-xl bg-indigo-600/20 border border-indigo-500/30 flex items-center justify-center">
              <GraduationCap className="w-6 h-6 text-indigo-400" />
            </div>
            <div>
              <h1 className="text-xl font-semibold text-zinc-100">My Learning</h1>
              <p className="text-sm text-zinc-500">Your personalized study hub</p>
            </div>
          </div>

          {loading && (
            <div className="flex items-center gap-2 text-zinc-400 py-16 justify-center">
              <Loader2 className="w-5 h-5 animate-spin" />
              <span className="text-sm">Loading your dashboard…</span>
            </div>
          )}

          {!loading && (
            <div className="space-y-10">
              {/* What to study next */}
              <section>
                <div className="flex items-center gap-2 mb-3">
                  <Compass className="w-4 h-4 text-indigo-400" />
                  <h2 className="text-sm font-semibold text-zinc-100">What to study next</h2>
                </div>
                <div className="space-y-3">
                  {recs && recs.length > 0 ? (
                    recs.map((r) => {
                      const course = courses.find((c) => c.course_id === r.course_id);
                      return (
                        <div
                          key={r.course_id}
                          className="bg-gradient-to-br from-indigo-950/30 to-zinc-900 border border-indigo-500/15 rounded-xl px-5 py-4"
                        >
                          <p className="text-sm font-semibold text-zinc-100">{r.course_title}</p>
                          <p className="text-xs text-zinc-500 mt-0.5 mb-3 leading-relaxed">{r.reason}</p>
                          {course && <CourseCompanion course={course} userId={userId} size="sm" />}
                        </div>
                      );
                    })
                  ) : (
                    <p className="text-sm text-zinc-500">No recommendations yet.</p>
                  )}
                </div>
              </section>

              {/* Your progress */}
              <section>
                <div className="flex items-center gap-2 mb-3">
                  <BarChart3 className="w-4 h-4 text-indigo-400" />
                  <h2 className="text-sm font-semibold text-zinc-100">Your progress</h2>
                </div>

                {sessions.length === 0 ? (
                  <p className="text-sm text-zinc-500 bg-zinc-900 border border-zinc-800 rounded-xl px-5 py-4">
                    Take a practice quiz on any course to start tracking your progress.
                  </p>
                ) : (
                  <div className="space-y-4">
                    {/* One card per course: attempts + latest result as a % */}
                    <div className="space-y-2">
                      {groupProgressByCourse(sessions).map((cp) => {
                        const pct = Math.round(cp.latestPct * 100);
                        const c =
                          cp.latestPct >= 0.8
                            ? { text: "text-emerald-400", bar: "bg-emerald-500" }
                            : cp.latestPct >= 0.5
                            ? { text: "text-amber-400", bar: "bg-amber-500" }
                            : { text: "text-rose-400", bar: "bg-rose-500" };
                        return (
                          <div
                            key={cp.course_id}
                            className="bg-zinc-900 border border-zinc-800 rounded-xl px-4 py-3"
                          >
                            <div className="flex items-center justify-between mb-2">
                              <div>
                                <p className="text-sm text-zinc-200">{cp.title}</p>
                                <p className="text-xs text-zinc-600">
                                  {cp.attempts} {cp.attempts === 1 ? "attempt" : "attempts"} · last{" "}
                                  {new Date(cp.latest.completed_at).toLocaleDateString()}
                                  {cp.attempts > 1 && cp.bestPct > cp.latestPct
                                    ? ` · best ${Math.round(cp.bestPct * 100)}%`
                                    : ""}
                                </p>
                              </div>
                              <span className={`text-sm font-semibold ${c.text}`}>{pct}%</span>
                            </div>
                            <div className="h-1.5 bg-zinc-800 rounded-full overflow-hidden">
                              <div className={`h-full ${c.bar}`} style={{ width: `${Math.max(pct, 3)}%` }} />
                            </div>
                          </div>
                        );
                      })}
                    </div>

                    {/* Weak concepts */}
                    {weak.length > 0 && (
                      <div className="bg-amber-950/20 border border-amber-800/30 rounded-xl px-5 py-4">
                        <p className="text-xs font-semibold text-amber-300 mb-2">Concepts to revisit</p>
                        <div className="flex flex-wrap gap-2">
                          {weak.map((w) => (
                            <span
                              key={w.concept}
                              className="text-xs text-amber-200/90 bg-amber-500/10 border border-amber-500/20 rounded-full px-2.5 py-1"
                            >
                              {w.concept} · {Math.round(w.accuracy * 100)}%
                            </span>
                          ))}
                        </div>
                      </div>
                    )}
                  </div>
                )}
              </section>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
