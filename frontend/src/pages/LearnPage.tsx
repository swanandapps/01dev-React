import { useEffect, useState } from "react";
import { BookOpen, Loader2, GraduationCap } from "lucide-react";
import Header from "../components/Home/Header";
import { StudyGuideModal } from "../components/learn/StudyGuideModal";
import { getLectures } from "../lib/learnApi";
import type { Lecture } from "../types/learn";

export default function LearnPage() {
  const [lectures, setLectures] = useState<Lecture[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [activeLecture, setActiveLecture] = useState<Lecture | null>(null);

  useEffect(() => {
    getLectures()
      .then(setLectures)
      .catch((e) => setError((e as Error).message))
      .finally(() => setLoading(false));
  }, []);

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
                        className="flex items-center justify-between bg-zinc-900 border border-zinc-800 rounded-xl px-4 py-3 hover:border-zinc-700 transition-colors"
                      >
                        <p className="text-sm text-zinc-200">{lec.lecture_title}</p>
                        <button
                          onClick={() => setActiveLecture(lec)}
                          className="flex items-center gap-1.5 text-xs font-medium text-indigo-300 hover:text-indigo-200 bg-indigo-600/15 hover:bg-indigo-600/25 border border-indigo-500/30 rounded-lg px-3 py-1.5 transition-colors flex-shrink-0"
                        >
                          <BookOpen className="w-3.5 h-3.5" />
                          View Study Guide
                        </button>
                      </div>
                    ))}
                  </div>
                </section>
              ))}
            </div>
          )}
        </div>
      </div>

      {activeLecture && (
        <StudyGuideModal lecture={activeLecture} onClose={() => setActiveLecture(null)} />
      )}
    </div>
  );
}
