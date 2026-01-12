import { useEffect, useRef, useState } from "react";
import { X, Loader2, Sparkles, BookOpen, HelpCircle, AlertTriangle } from "lucide-react";
import { getStudyGuide, generateStudyGuide, generateQuestions } from "../../lib/learnApi";
import type { Lecture, StudyGuide } from "../../types/learn";

export function StudyGuideModal({ lecture, onClose }: { lecture: Lecture; onClose: () => void }) {
  const [guide, setGuide] = useState<StudyGuide | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const pollRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  useEffect(() => {
    let cancelled = false;

    // Lecture accessed → warm up practice questions in the background (Feature 3),
    // so they're ready by the time the student wants to practice.
    generateQuestions(lecture.lecture_id).catch(() => {});

    const poll = async () => {
      try {
        const res = await getStudyGuide(lecture.lecture_id);
        if (cancelled) return;
        if (res.status === "ready" && res.guide) {
          setGuide(res.guide);
          setLoading(false);
        } else {
          // none -> kick off generation; generating -> keep polling
          if (res.status === "none") await generateStudyGuide(lecture.lecture_id);
          pollRef.current = setTimeout(poll, 2500);
        }
      } catch (e) {
        if (cancelled) return;
        setError((e as Error).message);
        setLoading(false);
      }
    };
    poll();

    return () => {
      cancelled = true;
      if (pollRef.current) clearTimeout(pollRef.current);
    };
  }, [lecture.lecture_id]);

  return (
    <div
      className="fixed inset-0 z-50 bg-black/70 flex items-center justify-center p-4"
      onClick={onClose}
    >
      <div
        className="bg-zinc-900 border border-zinc-700 rounded-2xl w-full max-w-2xl max-h-[85vh] flex flex-col"
        onClick={(e) => e.stopPropagation()}
      >
        {/* Header */}
        <div className="flex items-start justify-between px-6 py-4 border-b border-zinc-800 flex-shrink-0">
          <div className="flex items-center gap-3">
            <div className="w-9 h-9 rounded-xl bg-indigo-600/20 border border-indigo-500/30 flex items-center justify-center">
              <BookOpen className="w-5 h-5 text-indigo-400" />
            </div>
            <div>
              <h2 className="text-sm font-semibold text-zinc-100">Study Guide</h2>
              <p className="text-xs text-zinc-500">{lecture.lecture_title}</p>
            </div>
          </div>
          <button onClick={onClose} className="text-zinc-500 hover:text-zinc-200 transition-colors">
            <X className="w-5 h-5" />
          </button>
        </div>

        {/* Body */}
        <div className="overflow-y-auto px-6 py-5">
          {loading && (
            <div className="flex flex-col items-center justify-center py-16 text-center">
              <Loader2 className="w-8 h-8 text-indigo-400 animate-spin mb-4" />
              <p className="text-sm text-zinc-300">Generating your study guide…</p>
              <p className="text-xs text-zinc-600 mt-1">Reading the lecture transcript — this takes a few seconds.</p>
            </div>
          )}

          {error && !loading && (
            <div className="flex items-start gap-2.5 bg-amber-950/40 border border-amber-800/50 rounded-xl px-4 py-3">
              <AlertTriangle className="w-4 h-4 text-amber-400 flex-shrink-0 mt-0.5" />
              <p className="text-sm text-amber-200">Couldn’t load the study guide: {error}</p>
            </div>
          )}

          {guide && !loading && (
            <div className="space-y-6">
              {/* Key concepts */}
              <section>
                <h3 className="flex items-center gap-2 text-xs font-semibold text-indigo-400 uppercase tracking-wide mb-3">
                  <Sparkles className="w-3.5 h-3.5" /> Key Concepts
                </h3>
                <div className="space-y-2.5">
                  {guide.key_concepts.map((c, i) => (
                    <div key={i} className="bg-zinc-800/60 border border-zinc-700/50 rounded-xl px-4 py-3">
                      <p className="text-sm font-medium text-zinc-100">{c.name}</p>
                      <p className="text-sm text-zinc-400 mt-0.5 leading-relaxed">{c.description}</p>
                    </div>
                  ))}
                </div>
              </section>

              {/* Summary */}
              <section>
                <h3 className="text-xs font-semibold text-indigo-400 uppercase tracking-wide mb-3">Summary</h3>
                <p className="text-sm text-zinc-300 leading-relaxed whitespace-pre-wrap">{guide.summary}</p>
              </section>

              {/* Practice questions */}
              <section>
                <h3 className="flex items-center gap-2 text-xs font-semibold text-indigo-400 uppercase tracking-wide mb-3">
                  <HelpCircle className="w-3.5 h-3.5" /> Practice Questions
                </h3>
                <div className="space-y-3">
                  {guide.practice_questions.map((q, i) => (
                    <details key={i} className="bg-zinc-800/60 border border-zinc-700/50 rounded-xl px-4 py-3 group">
                      <summary className="text-sm font-medium text-zinc-200 cursor-pointer list-none flex items-start gap-2">
                        <span className="text-indigo-400">{i + 1}.</span>
                        <span>{q.question}</span>
                      </summary>
                      <p className="text-sm text-zinc-400 mt-2 pl-5 leading-relaxed">{q.answer}</p>
                    </details>
                  ))}
                </div>
              </section>

              {/* Misconceptions */}
              <section>
                <h3 className="flex items-center gap-2 text-xs font-semibold text-amber-400 uppercase tracking-wide mb-3">
                  <AlertTriangle className="w-3.5 h-3.5" /> Common Misconceptions
                </h3>
                <ul className="space-y-2">
                  {guide.misconceptions.map((m, i) => (
                    <li key={i} className="flex items-start gap-2 text-sm text-zinc-300">
                      <span className="text-amber-500 mt-1">✗</span>
                      <span className="leading-relaxed">{m}</span>
                    </li>
                  ))}
                </ul>
              </section>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
