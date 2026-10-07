import { useEffect, useState } from "react";
import { X, Loader2, CheckCircle2, XCircle } from "lucide-react";
import { getQuickQuiz, submitQuickQuiz } from "../../lib/learnApi";
import type { QuickQuestion, QuickQuizResult } from "../../lib/learnApi";

/**
 * The player's "Quiz me": a few questions on what the student has watched. Pick an answer for each, Submit,
 * see what was right and why. The result counts toward the student's progress like any course quiz.
 */
export function QuickQuiz({
  courseSlug,
  lecture,
  position,
  onClose,
  start,
  title = "Check yourself",
  onSubmitted,
}: {
  courseSlug: string;
  lecture: string;
  position?: number;
  onClose: () => void;
  /** Lab topics: start a different quiz (e.g. a whole topic) instead of one lecture's. */
  start?: () => Promise<{ quiz_id: string; questions: QuickQuestion[] }>;
  title?: string;
  /** Called once the answers are graded and saved (e.g. to refresh progress). */
  onSubmitted?: () => void;
}) {
  const [quizId, setQuizId] = useState("");
  const [questions, setQuestions] = useState<QuickQuestion[] | null>(null);
  const [picked, setPicked] = useState<(number | null)[]>([]);
  const [result, setResult] = useState<QuickQuizResult | null>(null);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState("");
  const [round, setRound] = useState(0);

  useEffect(() => {
    let cancelled = false;
    setQuestions(null);
    setResult(null);
    setError("");
    (start ? start() : getQuickQuiz(courseSlug, lecture, position))
      .then((q) => {
        if (cancelled) return;
        setQuizId(q.quiz_id);
        setQuestions(q.questions);
        setPicked(q.questions.map(() => null));
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

  const allAnswered = !!questions && questions.length > 0 && picked.every((p) => p !== null);

  const submit = () => {
    if (!allAnswered || submitting) return;
    setSubmitting(true);
    setError("");
    submitQuickQuiz(quizId, picked as number[])
      .then((r) => { setResult(r); onSubmitted?.(); })
      .catch((e: Error) => setError(e.message))
      .finally(() => setSubmitting(false));
  };

  return (
    <div className="fixed inset-0 z-50 bg-black/70 flex items-center justify-center p-4" onClick={onClose}>
      <div role="dialog" aria-label="Quick quiz"
           className="bg-zinc-900 border border-zinc-700/60 rounded-2xl w-full max-w-xl max-h-[90vh] overflow-y-auto"
           onClick={(e) => e.stopPropagation()}>
        <div className="flex items-center justify-between gap-3 px-5 py-4 border-b border-zinc-800 sticky top-0 bg-zinc-900 z-10">
          <div className="min-w-0">
            <p className="text-sm font-bold text-teal-100">{title}</p>
            <p className="text-xs text-zinc-400 truncate">{lecture}</p>
          </div>
          <button onClick={onClose} aria-label="Close" className="w-8 h-8 rounded-lg text-zinc-400 hover:text-zinc-100 hover:bg-zinc-800 flex items-center justify-center">
            <X className="w-4 h-4" />
          </button>
        </div>

        <div className="px-5 py-4 flex flex-col gap-6">
          {!questions && !error && (
            <div className="flex items-center gap-2 text-sm text-zinc-400 py-8 justify-center">
              <Loader2 className="w-4 h-4 animate-spin" /> {start ? "Making questions from the lectures that need work…" : "Making questions from what you've watched…"}
            </div>
          )}

          {questions?.map((q, qi) => {
            const p = picked[qi];
            const r = result?.results[qi];
            return (
              <fieldset key={`${round}-${qi}`} className="flex flex-col gap-2">
                <legend className="text-[15px] font-semibold text-zinc-100 mb-2">
                  {start && q.lecture && <span className="block text-[11px] font-mono font-normal text-teal-300/80 mb-1">From {q.lecture}</span>}
                  {qi + 1}. {q.question}
                </legend>
                <div className="flex flex-col gap-1.5">
                  {q.options.map((opt, oi) => {
                    const state = !r
                      ? (p === oi ? "picked" : "idle")
                      : oi === r.correctIndex ? "right" : p === oi ? "wrong" : "dim";
                    return (
                      <button
                        key={oi}
                        type="button"
                        aria-pressed={p === oi}
                        disabled={!!result}
                        onClick={() => setPicked((xs) => xs.map((x, k) => (k === qi ? oi : x)))}
                        className={`text-left text-sm rounded-xl px-3.5 py-2.5 border flex items-start gap-2 transition-colors ${
                          state === "idle" ? "bg-zinc-800/60 border-zinc-700 text-zinc-200 hover:border-teal-500/60"
                          : state === "picked" ? "bg-teal-950/60 border-teal-400 text-teal-50"
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
                {r && <p className="text-[13px] text-zinc-400 leading-relaxed">{r.explanation}</p>}
              </fieldset>
            );
          })}

          {error && <p className="text-sm text-red-300">Something went wrong ({error}). Please try again.</p>}

          {questions && !result && (
            <div className="flex items-center justify-between gap-3 border-t border-zinc-800 pt-4">
              <span className="text-xs text-zinc-500">
                {picked.filter((p) => p !== null).length} of {questions.length} answered
              </span>
              <button onClick={submit} disabled={!allAnswered || submitting}
                      className="bg-teal-500 hover:bg-teal-400 disabled:bg-zinc-700 disabled:text-zinc-400 disabled:cursor-not-allowed text-teal-950 text-sm font-bold rounded-lg px-5 py-2 flex items-center gap-2">
                {submitting && <Loader2 className="w-4 h-4 animate-spin" />} Submit
              </button>
            </div>
          )}

          {result && (
            <div className="flex flex-wrap items-center gap-3 border-t border-zinc-800 pt-4">
              <p className="flex-1 text-sm font-semibold text-zinc-100">
                You got {result.score} of {result.total}{result.score === result.total ? " — nice." : "."}
              </p>
              <button onClick={() => setRound((n) => n + 1)}
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
