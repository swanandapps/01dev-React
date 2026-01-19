import { useEffect, useRef, useState } from "react";
import { X, Loader2, Check, XCircle, Target, RotateCcw } from "lucide-react";
import { startAdaptive, answerAdaptive } from "../../lib/learnApi";
import type { Lecture, MCQQuestion, AdaptiveSummary } from "../../types/learn";

const difficultyColor: Record<string, string> = {
  easy: "text-emerald-400 bg-emerald-500/10 border-emerald-500/30",
  medium: "text-amber-400 bg-amber-500/10 border-amber-500/30",
  hard: "text-rose-400 bg-rose-500/10 border-rose-500/30",
};

export function AdaptiveModal({
  lecture,
  userId,
  onClose,
}: {
  lecture: Lecture;
  userId: string;
  onClose: () => void;
}) {
  const [question, setQuestion] = useState<MCQQuestion | null>(null);
  const [selected, setSelected] = useState<number | null>(null);
  const [answeredCount, setAnsweredCount] = useState(0);
  const [finished, setFinished] = useState(false);
  const [summary, setSummary] = useState<AdaptiveSummary | null>(null);
  const [error, setError] = useState<string | null>(null);
  const sessionId = useRef<string | null>(null);
  const pollRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  useEffect(() => {
    let cancelled = false;
    const begin = async () => {
      try {
        const res = await startAdaptive(userId, lecture.lecture_id);
        if (cancelled) return;
        if (res.status === "preparing") {
          pollRef.current = setTimeout(begin, 2500); // questions still generating
          return;
        }
        sessionId.current = res.session_id ?? null;
        setQuestion(res.question ?? null);
        if (res.status === "done") {
          setFinished(true);
          setSummary(res.summary ?? null);
        }
      } catch (e) {
        if (!cancelled) setError((e as Error).message);
      }
    };
    begin();
    return () => {
      cancelled = true;
      if (pollRef.current) clearTimeout(pollRef.current);
    };
  }, [lecture.lecture_id, userId]);

  const answered = selected !== null;

  const choose = async (optionIdx: number) => {
    if (answered || !question || !sessionId.current) return;
    setSelected(optionIdx);
  };

  const next = async () => {
    if (!question || !sessionId.current || selected === null) return;
    const correct = selected === question.correct_index;
    const concept = question.concept;
    try {
      const res = await answerAdaptive({
        session_id: sessionId.current,
        question_id: question.id,
        concept,
        correct,
      });
      setAnsweredCount((c) => c + 1);
      if (res.status === "done") {
        setFinished(true);
        setSummary(res.summary ?? null);
        setQuestion(null);
      } else {
        setQuestion(res.question ?? null);
        setSelected(null);
      }
    } catch (e) {
      setError((e as Error).message);
    }
  };

  return (
    <div className="fixed inset-0 z-50 bg-black/70 flex items-center justify-center p-4" onClick={onClose}>
      <div
        className="bg-zinc-900 border border-zinc-700 rounded-2xl w-full max-w-xl flex flex-col max-h-[88vh]"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="flex items-center justify-between px-6 py-4 border-b border-zinc-800 flex-shrink-0">
          <div className="flex items-center gap-2">
            <Target className="w-4 h-4 text-indigo-400" />
            <div>
              <h2 className="text-sm font-semibold text-zinc-100">Adaptive Practice</h2>
              <p className="text-xs text-zinc-500">
                {finished ? lecture.lecture_title : `${lecture.lecture_title} · adapts to you`}
              </p>
            </div>
          </div>
          <button onClick={onClose} className="text-zinc-500 hover:text-zinc-200">
            <X className="w-5 h-5" />
          </button>
        </div>

        <div className="overflow-y-auto px-6 py-5">
          {!question && !finished && !error && (
            <div className="flex flex-col items-center justify-center py-16 text-center">
              <Loader2 className="w-8 h-8 text-indigo-400 animate-spin mb-4" />
              <p className="text-sm text-zinc-300">Setting up your adaptive session…</p>
            </div>
          )}
          {error && (
            <p className="text-sm text-amber-300 bg-amber-950/40 border border-amber-800/50 rounded-xl px-4 py-3">
              {error}
            </p>
          )}

          {question && !finished && (
            <div>
              <div className="flex items-center justify-between mb-3">
                <span className={`inline-block text-[10px] font-semibold uppercase tracking-wide px-2 py-0.5 rounded-full border ${difficultyColor[question.difficulty]}`}>
                  {question.difficulty} · {question.concept}
                </span>
                <span className="text-xs text-zinc-600">Answered: {answeredCount}</span>
              </div>
              <p className="text-base text-zinc-100 font-medium mb-4 leading-relaxed">{question.question}</p>

              <div className="space-y-2">
                {question.options.map((opt, i) => {
                  const isCorrect = i === question.correct_index;
                  const isChosen = i === selected;
                  let cls = "border-zinc-700 bg-zinc-800/60 hover:bg-zinc-800 text-zinc-200";
                  if (answered) {
                    if (isCorrect) cls = "border-emerald-500/50 bg-emerald-500/10 text-emerald-100";
                    else if (isChosen) cls = "border-rose-500/50 bg-rose-500/10 text-rose-100";
                    else cls = "border-zinc-800 bg-zinc-800/30 text-zinc-500";
                  }
                  return (
                    <button
                      key={i}
                      onClick={() => choose(i)}
                      disabled={answered}
                      className={`w-full text-left px-4 py-3 rounded-xl border text-sm flex items-center justify-between transition-colors ${cls} ${answered ? "cursor-default" : "cursor-pointer"}`}
                    >
                      <span>{opt}</span>
                      {answered && isCorrect && <Check className="w-4 h-4 text-emerald-400 flex-shrink-0" />}
                      {answered && isChosen && !isCorrect && <XCircle className="w-4 h-4 text-rose-400 flex-shrink-0" />}
                    </button>
                  );
                })}
              </div>

              {answered && (
                <div className="mt-4">
                  <div className="bg-zinc-800/60 border border-zinc-700/50 rounded-xl px-4 py-3">
                    <p className="text-xs font-semibold text-zinc-400 mb-1">
                      {selected === question.correct_index ? "Correct ✓" : "Not quite"}
                    </p>
                    <p className="text-sm text-zinc-300 leading-relaxed">{question.explanation}</p>
                  </div>
                  <button
                    onClick={next}
                    className="mt-4 w-full bg-indigo-600 hover:bg-indigo-500 text-white text-sm font-medium rounded-xl py-2.5 transition-colors"
                  >
                    Next
                  </button>
                </div>
              )}
            </div>
          )}

          {finished && (
            <div className="py-2">
              <div className="text-center mb-5">
                <div className="w-14 h-14 rounded-2xl bg-indigo-600/20 border border-indigo-500/30 flex items-center justify-center mx-auto mb-3">
                  <Target className="w-7 h-7 text-indigo-400" />
                </div>
                <p className="text-lg font-semibold text-zinc-100">Session complete</p>
                <p className="text-sm text-zinc-500">{answeredCount} questions · adapted to your performance</p>
              </div>

              {summary && (
                <>
                  <p className="text-xs font-semibold text-zinc-500 uppercase tracking-wide mb-2">Concept mastery</p>
                  <div className="space-y-2 mb-5">
                    {summary.mastery.map((m) => {
                      const pct = Math.round(m.accuracy * 100);
                      return (
                        <div key={m.concept} className="flex items-center gap-3">
                          <span className="text-sm text-zinc-300 w-40 truncate">{m.concept}</span>
                          <div className="flex-1 h-2 bg-zinc-800 rounded-full overflow-hidden">
                            <div
                              className={`h-full ${m.mastered ? "bg-emerald-500" : pct >= 50 ? "bg-amber-500" : "bg-rose-500"}`}
                              style={{ width: `${Math.max(pct, 4)}%` }}
                            />
                          </div>
                          <span className={`text-xs w-16 text-right ${m.mastered ? "text-emerald-400" : "text-zinc-500"}`}>
                            {m.attempts ? `${pct}%` : "—"}
                          </span>
                        </div>
                      );
                    })}
                  </div>

                  {summary.revisit.length > 0 && (
                    <div className="bg-amber-950/30 border border-amber-800/40 rounded-xl px-4 py-3 mb-5">
                      <p className="text-xs font-semibold text-amber-300 mb-1">Concepts to revisit</p>
                      <p className="text-sm text-amber-200/90">{summary.revisit.join(" · ")}</p>
                    </div>
                  )}
                </>
              )}

              <button
                onClick={onClose}
                className="w-full inline-flex items-center justify-center gap-2 bg-zinc-800 hover:bg-zinc-700 text-zinc-200 text-sm font-medium rounded-xl px-5 py-2.5 transition-colors"
              >
                <RotateCcw className="w-4 h-4" />
                Back to lectures
              </button>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
