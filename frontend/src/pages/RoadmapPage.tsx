import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { Route as RouteIcon, Loader2, Check, Lock, Play, ArrowRight } from "lucide-react";
import Header from "../components/Home/Header";
import { getCourses, listQuizSessions } from "../lib/learnApi";
import { useUserSessionStore } from "../store/userSession";
import tracks from "../data/tracks";
import type { Course, QuizSession } from "../types/learn";

// Curriculum order (foundations → advanced). Unlisted courses fall to the end.
const ORDER = ["javascript-deep-dive", "web-apis", "react-perf", "custom-library"];
const orderIdx = (id: string) => {
  const i = ORDER.indexOf(id);
  return i === -1 ? 999 : i;
};

type Status = "mastered" | "in-progress" | "not-started" | "locked";

interface RoadmapItem {
  course: Course;
  trackId?: number;
  best: number; // best score fraction across sessions
  attempts: number;
  unlocked: boolean;
  status: Status;
}

function build(courses: Course[], sessions: QuizSession[]): RoadmapItem[] {
  const ordered = [...courses].sort((a, b) => orderIdx(a.course_id) - orderIdx(b.course_id));
  const items: RoadmapItem[] = [];
  let prevReached50 = true; // first course is always unlocked

  for (let i = 0; i < ordered.length; i++) {
    const course = ordered[i];
    const cs = sessions.filter((s) => s.course_id === course.course_id);
    const best = cs.length ? Math.max(...cs.map((s) => s.score / Math.max(s.total, 1))) : 0;
    const unlocked: boolean = i === 0 || prevReached50;
    let status: Status;
    if (!unlocked) status = "locked";
    else if (best >= 0.8) status = "mastered";
    else if (cs.length > 0) status = "in-progress";
    else status = "not-started";

    items.push({
      course,
      trackId: tracks.find((t) => t.title === course.title)?.id,
      best,
      attempts: cs.length,
      unlocked,
      status,
    });

    prevReached50 = unlocked && best >= 0.5;
  }
  return items;
}

const STATUS_META: Record<Status, { label: string; ring: string; bar: string; chip: string }> = {
  mastered: { label: "Mastered", ring: "border-emerald-500 text-emerald-400", bar: "bg-emerald-500", chip: "text-emerald-300 bg-emerald-500/10 border-emerald-500/30" },
  "in-progress": { label: "In progress", ring: "border-indigo-500 text-indigo-400", bar: "bg-indigo-500", chip: "text-indigo-300 bg-indigo-500/10 border-indigo-500/30" },
  "not-started": { label: "Not started", ring: "border-zinc-600 text-zinc-400", bar: "bg-zinc-600", chip: "text-zinc-400 bg-zinc-700/30 border-zinc-700" },
  locked: { label: "Locked", ring: "border-zinc-800 text-zinc-700", bar: "bg-zinc-700", chip: "text-zinc-600 bg-zinc-800/50 border-zinc-800" },
};

export default function RoadmapPage() {
  const [items, setItems] = useState<RoadmapItem[] | null>(null);
  const [error, setError] = useState<string | null>(null);

  const currentuser = useUserSessionStore((s) => s.currentuser);
  const userId = (currentuser?.uid as string) || "anonymous";

  useEffect(() => {
    Promise.all([getCourses(), listQuizSessions(userId)])
      .then(([courses, sessions]) => setItems(build(courses, sessions)))
      .catch((e) => setError((e as Error).message));
  }, [userId]);

  // The course the student should focus on next.
  const nextId = items?.find((it) => it.unlocked && it.status !== "mastered")?.course.course_id;

  return (
    <div className="bg-zinc-950 text-[#F0F0F0] min-h-screen">
      <Header />
      <div className="pt-16">
        <div className="max-w-2xl mx-auto px-6 py-8">
          <div className="flex items-center gap-3 mb-8">
            <div className="w-10 h-10 rounded-xl bg-indigo-600/20 border border-indigo-500/30 flex items-center justify-center">
              <RouteIcon className="w-6 h-6 text-indigo-400" />
            </div>
            <div>
              <h1 className="text-xl font-semibold text-zinc-100">Your Roadmap</h1>
              <p className="text-sm text-zinc-500">Your journey through the courses — unlock as you master each</p>
            </div>
          </div>

          {!items && !error && (
            <div className="flex items-center gap-2 text-zinc-400 py-16 justify-center">
              <Loader2 className="w-5 h-5 animate-spin" />
              <span className="text-sm">Building your roadmap…</span>
            </div>
          )}
          {error && <p className="text-sm text-amber-300">{error}</p>}

          {items && (
            <div>
              {items.map((it, i) => {
                const m = STATUS_META[it.status];
                const pct = Math.round(it.best * 100);
                const isNext = it.course.course_id === nextId;
                const last = i === items.length - 1;
                return (
                  <div key={it.course.course_id} className="flex gap-4">
                    {/* rail */}
                    <div className="flex flex-col items-center">
                      <div className={`w-9 h-9 rounded-full border-2 flex items-center justify-center bg-zinc-950 ${m.ring}`}>
                        {it.status === "mastered" ? (
                          <Check className="w-4 h-4" />
                        ) : it.status === "locked" ? (
                          <Lock className="w-3.5 h-3.5" />
                        ) : (
                          <span className="text-sm font-semibold">{i + 1}</span>
                        )}
                      </div>
                      {!last && <div className="w-0.5 flex-1 bg-zinc-800 my-1" />}
                    </div>

                    {/* card */}
                    <div className={`flex-1 mb-5 rounded-xl border px-5 py-4 ${isNext ? "border-indigo-500/40 bg-indigo-950/20" : "border-zinc-800 bg-zinc-900"} ${it.status === "locked" ? "opacity-60" : ""}`}>
                      <div className="flex items-start justify-between gap-3 mb-2">
                        <div>
                          <div className="flex items-center gap-2">
                            <p className="text-sm font-semibold text-zinc-100">{it.course.title}</p>
                            {isNext && (
                              <span className="text-[10px] font-semibold uppercase tracking-wide text-indigo-300 bg-indigo-500/15 border border-indigo-500/30 rounded-full px-2 py-0.5">
                                {it.attempts > 0 ? "Continue" : "Start here"}
                              </span>
                            )}
                          </div>
                          <p className="text-xs text-zinc-500 mt-0.5">
                            {it.course.lecture_count} lecture{it.course.lecture_count === 1 ? "" : "s"}
                          </p>
                        </div>
                        <span className={`text-[10px] font-semibold uppercase tracking-wide rounded-full border px-2 py-0.5 flex-shrink-0 ${m.chip}`}>
                          {m.label}
                        </span>
                      </div>

                      {it.status !== "locked" && (
                        <div className="flex items-center gap-3 mb-3">
                          <div className="flex-1 h-1.5 bg-zinc-800 rounded-full overflow-hidden">
                            <div className={`h-full ${m.bar}`} style={{ width: `${Math.max(pct, 2)}%` }} />
                          </div>
                          <span className="text-xs text-zinc-500 w-20 text-right">
                            {it.attempts > 0 ? `best ${pct}%` : "—"}
                          </span>
                        </div>
                      )}

                      {it.status === "locked" ? (
                        <p className="text-xs text-zinc-600 flex items-center gap-1.5">
                          <Lock className="w-3 h-3" /> Reach 50% on the previous course to unlock
                        </p>
                      ) : it.trackId ? (
                        <Link
                          to={`/coursedetails/${it.trackId}`}
                          className="inline-flex items-center gap-1.5 text-xs font-medium text-indigo-300 hover:text-indigo-200"
                        >
                          {it.status === "mastered" ? "Review course" : it.attempts > 0 ? "Continue course" : "Start course"}
                          <ArrowRight className="w-3.5 h-3.5" />
                        </Link>
                      ) : (
                        <span className="inline-flex items-center gap-1.5 text-xs text-zinc-600">
                          <Play className="w-3.5 h-3.5" /> Course page coming soon
                        </span>
                      )}
                    </div>
                  </div>
                );
              })}
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
