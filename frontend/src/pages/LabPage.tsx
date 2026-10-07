import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import Header from "../components/Home/Header";
import { LabStudio } from "../components/lab/LabStudio";
import { useUserSessionStore } from "../store/userSession";
import { getCourses, getEnrollment, getLabOverview } from "../lib/learnApi";
import type { LabOverview } from "../lib/learnApi";
import type { Course } from "../types/learn";

const when = (iso: string) => {
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return "";
  const days = Math.floor((Date.now() - d.getTime()) / 86_400_000);
  return days <= 0 ? "today" : days === 1 ? "yesterday" : `${days} days ago`;
};

export default function LabPage() {
  const navigate = useNavigate();
  const { currentuser, isUserLoggedIn } = useUserSessionStore();
  const studentId = (currentuser?.uid as string) || "";
  const [courses, setCourses] = useState<Course[]>([]);
  const [overview, setOverview] = useState<LabOverview | null>(null);
  const [prefill, setPrefill] = useState<{ topic: string; n: number } | undefined>();

  // "A lecture" offers the student's own courses that have lectures to practise from.
  useEffect(() => {
    if (!isUserLoggedIn || !studentId) return;
    Promise.all([getCourses(), getEnrollment(studentId)])
      .then(([all, owned]) => {
        const titles = new Set(owned.map((c) => c.title));
        setCourses(all.filter((c) => titles.has(c.title) && c.lecture_count > 0));
      })
      .catch(() => setCourses([]));
    getLabOverview().then(setOverview).catch(() => setOverview(null));
  }, [isUserLoggedIn, studentId]);

  const hasSide = !!overview && (overview.recent.length > 0 || overview.weak.length > 0);

  return (
    <div className="bg-zinc-950 min-h-screen">
      <Header />
      <div className={`mx-auto px-5 sm:px-8 pt-24 pb-16 ${hasSide ? "max-w-6xl" : "max-w-4xl"}`}>
        <div className="mb-8 flex flex-col gap-2">
          <h1 className="text-3xl sm:text-4xl font-extrabold tracking-tight text-zinc-50">Lab</h1>
          <p className="text-base text-zinc-400">Turn a lecture, your notes or a PDF into a quiz, flashcards or a study plan.</p>
        </div>

        <div className={hasSide ? "grid grid-cols-1 lg:grid-cols-[minmax(0,1fr)_320px] gap-10" : ""}>
          <div className="flex flex-col gap-7">
            <LabStudio studentId={studentId} onClose={() => navigate(-1)} courses={courses} chrome={false} prefill={prefill} />
          </div>

          {hasSide && overview && (
            <aside className="flex flex-col gap-6">
              {overview.weak.length > 0 && (
                <section className="bg-violet-950/30 border border-violet-900/60 rounded-2xl p-4 flex flex-col gap-3">
                  <h2 className="text-[13px] font-bold text-violet-200">Worth revisiting</h2>
                  {overview.weak.map((w) => (
                    <div key={w.concept} className="flex flex-col gap-1.5">
                      <div className="flex items-center justify-between gap-2">
                        <span className="text-sm text-zinc-100">{w.concept}</span>
                        <button onClick={() => setPrefill({ topic: w.concept, n: Date.now() })}
                                className="text-[13px] font-semibold text-violet-300 hover:text-violet-200">
                          Practise
                        </button>
                      </div>
                      <div className="h-1.5 bg-zinc-800 rounded">
                        <div className="h-1.5 bg-amber-500 rounded" style={{ width: `${Math.round(w.accuracy * 100)}%` }} />
                      </div>
                      <span className="text-[11px] text-zinc-500">{Math.round(w.accuracy * 100)}% right over {w.attempts} questions</span>
                    </div>
                  ))}
                </section>
              )}
              {overview.recent.length > 0 && (
                <section className="flex flex-col gap-2.5">
                  <h2 className="text-[13px] font-bold text-zinc-400">Recent sessions</h2>
                  {overview.recent.map((r, i) => {
                    const ratio = r.total ? r.score / r.total : 0;
                    return (
                      <div key={i} className="bg-zinc-900 border border-zinc-800 rounded-xl px-3.5 py-3 flex flex-col gap-1">
                        <span className="text-sm font-semibold text-zinc-100 leading-snug">{r.title}</span>
                        <span className="flex items-center justify-between text-xs text-zinc-500">
                          <span>{r.kind} · {when(r.completed_at)}</span>
                          <span className={`font-bold ${ratio >= 0.8 ? "text-green-400" : ratio >= 0.5 ? "text-amber-400" : "text-rose-400"}`}>
                            {r.score} / {r.total}
                          </span>
                        </span>
                      </div>
                    );
                  })}
                </section>
              )}
            </aside>
          )}
        </div>
      </div>
    </div>
  );
}
