import { useEffect, useState } from "react";
import { X, Loader2, CheckCircle2, XCircle } from "lucide-react";
import { getQuickQuiz } from "../../lib/learnApi";
import type { QuickQuestion } from "../../lib/learnApi";

/**
 * The player's "Quiz me": a few questions on what the student has watched, answered on the spot.
 * No objectives, no steps — pick an answer, see why, see the score. (Lab's page keeps the full flow.)
 */
export function QuickQuiz({
  courseSlug,
  lecture,
  position,
  onClose,
}: {
  courseSlug: string;
  lecture: string;
  position?: number;
  onClose: () => void;
}) {
  const [questions, setQuestions] = useState<QuickQuestion[] | null>(null);
  const [picked, setPicked] = useState<(number | null)[]>([]);
  const [error, setError] = useState("");
  const [round, setRound] = useState(0);

  useEffect(() => {
    let cancelled = false;
    setQuestions(null);
    setError("");
    getQuickQuiz(courseSlug, lecture, position)
      .then((qs) => {
        if (cancelled) return;
        setQuestions(qs);
        setPicked(qs.map(() => null));
      })
      .catch((e: Error) => { if (!cancelled) setError(e.message); });
    return () => { cancelled = true; };
    // position is read once per round: "what you've watched" when the round started
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [courseSlug, lecture, round]);

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => { if (e.key === "Escape") onClose(); };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [onClose]);

  const answered = picked.filter((p) => p !== null).length;
  const score = questions ? questions.filter((q, i) => picked[i] === q.correctIndex).length : 0;
  const done = !!questions && questions.length > 0 && answered === questions.length;

  return (
    <div className="fixed inset-0 z-50 bg-black/70 flex items-center justify-center p-4" onClick={onClose}>
      <div role="dialog" aria-label="Quick quiz"
           className="bg-zinc-900 border border-zinc-700/60 rounded-2xl w-full max-w-xl max-h-[90vh] overflow-y-auto"
           onClick={(e) => e.stopPropagation()}>
        <div className="flex items-center justify-between gap-3 px-5 py-4 border-b border-zinc-800 sticky top-0 bg-zinc-900">
          <div className="min-w-0">
            <p className="text-sm font-bold text-teal-100">Check yourself</p>
            <p className="text-xs text-zinc-400 truncate">{lecture}</p>
          </div>
          <button onClick={onClose} aria-label="Close" className="w-8 h-8 rounded-lg text-zinc-400 hover:text-zinc-100 hover:bg-zinc-800 flex items-center justify-center">
            <X className="w-4 h-4" />
          </button>
        </div>

        <div className="px-5 py-4 flex flex-col gap-5">
          {error && <p className="text-sm text-red-300">Couldn't make questions right now ({error}).</p>}
          {!questions && !error && (
            <div className="flex items-center gap-2 text-sm text-zinc-400 py-8 justify-center">
              <Loader2 className="w-4 h-4 animate-spin" /> Making questions from what you've watched…
            </div>
          )}

          {questions?.map((q, qi) => {
            const p = picked[qi];
            return (
              <div key={`${round}-${qi}`} className="flex flex-col gap-2">
                <p className="text-[15px] font-semibold text-zinc-100">{qi + 1}. {q.question}</p>
                <div className="flex flex-col gap-1.5">
                  {q.options.map((opt, oi) => {
                    const isRight = oi === q.correctIndex;
                    const state = p === null ? "idle" : isRight ? "right" : p === oi ? "wrong" : "dim";
                    return (
                      <button
                        key={oi}
                        disabled={p !== null}
                        onClick={() => setPicked((xs) => xs.map((x, k) => (k === qi ? oi : x)))}
                        className={`text-left text-sm rounded-xl px-3.5 py-2.5 border flex items-start gap-2 transition-colors ${
                          state === "idle" ? "bg-zinc-800/60 border-zinc-700 text-zinc-200 hover:border-teal-500/60"
                          : state === "right" ? "bg-green-950/50 border-green-600 text-green-100"
                          : state === "wrong" ? "bg-red-950/40 border-red-600 text-red-100"
                          : "bg-zinc-900 border-zinc-800 text-zinc-500"}`}
                      >
                        {state === "right" && <CheckCircle2 className="w-4 h-4 mt-0.5 flex-shrink-0 text-green-400" />}
                        {state === "wrong" && <XCircle className="w-4 h-4 mt-0.5 flex-shrink-0 text-red-400" />}
                        <span>{opt}</span>
                      </button>
                    );
                  })}
                </div>
                {p !== null && <p className="text-[13px] text-zinc-400 leading-relaxed">{q.explanation}</p>}
              </div>
            );
          })}

          {done && (
            <div className="flex flex-wrap items-center gap-3 border-t border-zinc-800 pt-4">
              <p className="flex-1 text-sm font-semibold text-zinc-100">
                You got {score} of {questions!.length}{score === questions!.length ? " — nice." : "."}
              </p>
              <button onClick={() => setRound((r) => r + 1)}
                      className="text-sm border border-teal-800 text-teal-200 hover:bg-teal-900/40 rounded-lg px-3 py-2">
                New questions
              </button>
              <button onClick={onClose} className="text-sm bg-teal-500 hover:bg-teal-400 text-teal-950 font-bold rounded-lg px-4 py-2">
                Back to the lecture
              </button>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
