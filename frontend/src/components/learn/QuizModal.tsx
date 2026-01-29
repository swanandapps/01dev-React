import { useEffect, useRef, useState } from "react";
import { X, Loader2, Check, XCircle, Trophy, RotateCcw } from "lucide-react";
import { getQuestions, generateQuestions, saveQuizSession } from "../../lib/learnApi";
import type { Course, MCQQuestion, QuizSession, QuizAnswer } from "../../types/learn";

const difficultyColor: Record<string, string> = {
  easy: "text-emerald-400 bg-emerald-500/10 border-emerald-500/30",
  medium: "text-amber-400 bg-amber-500/10 border-amber-500/30",
  hard: "text-rose-400 bg-rose-500/10 border-rose-500/30",
};

export function QuizModal({
  course,
  userId,
  onClose,
}: {
  course: Course;
  userId: string;
  onClose: () => void;
}) {
  const [questions, setQuestions] = useState<MCQQuestion[] | null>(null);
  const [error, setError] = useState<string | null>(null);

  const [index, setIndex] = useState(0);
  const [selected, setSelected] = useState<number | null>(null);
  const [answers, setAnswers] = useState<QuizAnswer[]>([]);
  const [finished, setFinished] = useState(false);
  const [session, setSession] = useState<QuizSession | null>(null);
  const [saving, setSaving] = useState(false);

  const startedAt = useRef<number>(Date.now());
  const pollRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  // Load questions (poll while generating).
  useEffect(() => {
    let cancelled = false;
    const poll = async () => {
      try {
        const res = await getQuestions(course.course_id);
        if (cancelled) return;
        if (res.status === "ready" && res.questions) {
          setQuestions(res.questions.questions);
          startedAt.current = Date.now();
        } else {
          if (res.status === "none") await generateQuestions(course.course_id);
          pollRef.current = setTimeout(poll, 2500);
        }
      } catch (e) {
        if (!cancelled) setError((e as Error).message);
      }
    };
    poll();
    return () => {
      cancelled = true;
      if (pollRef.current) clearTimeout(pollRef.current);
    };
  }, [course.course_id]);

  const current = questions?.[index];
  const answered = selected !== null;

  const choose = (optionIdx: number) => {
    if (answered || !current) return;
    setSelected(optionIdx);
    const correct = optionIdx === current.correct_index;
    setAnswers((prev) => [
      ...prev,
      {
        question_id: current.id,
        concept: current.concept,
        difficulty: current.difficulty,
        correct,
        time_taken_ms: Date.now() - startedAt.current,
        lecture: current.lecture,
      },
    ]);
  };

  const next = async () => {
    if (!questions) return;
    if (index < questions.length - 1) {
      setIndex((i) => i + 1);
      setSelected(null);
      startedAt.current = Date.now();
      return;
    }
    // Last question → finish + save.
    setFinished(true);
    setSaving(true);
    try {
      const saved = await saveQuizSession({
        user_id: userId,
        course_id: course.course_id,
        answers,
      });
      setSession(saved);
    } catch {
      /* session save is best-effort; still show local results */
    } finally {
      setSaving(false);
    }
  };

  const scoreLocal = answers.filter((a) => a.correct).length;

  return (
    <div className="fixed inset-0 z-50 bg-black/70 flex items-center justify-center p-4" onClick={onClose}>
      <div
        className="bg-zinc-900 border border-zinc-700 rounded-2xl w-full max-w-xl flex flex-col max-h-[88vh]"
        onClick={(e) => e.stopPropagation()}
      >
        {/* Header */}
        <div className="flex items-center justify-between px-6 py-4 border-b border-zinc-800 flex-shrink-0">
          <div>
            <h2 className="text-sm font-semibold text-zinc-100">Practice — {course.title}</h2>
            {questions && !finished && (
              <p className="text-xs text-zinc-500">Question {index + 1} of {questions.length}</p>
            )}
          </div>
          <button onClick={onClose} className="text-zinc-500 hover:text-zinc-200">
            <X className="w-5 h-5" />
          </button>
        </div>

        {/* Progress bar */}
        {questions && !finished && (
          <div className="h-1 bg-zinc-800 flex-shrink-0">
            <div
              className="h-full bg-indigo-500 transition-all"
              style={{ width: `${((index + (answered ? 1 : 0)) / questions.length) * 100}%` }}
            />
          </div>
        )}

        <div className="overflow-y-auto px-6 py-5">
          {/* Loading / error */}
          {!questions && !error && (
            <div className="flex flex-col items-center justify-center py-16 text-center">
              <Loader2 className="w-8 h-8 text-indigo-400 animate-spin mb-4" />
              <p className="text-sm text-zinc-300">Preparing your practice questions…</p>
            </div>
          )}
          {error && (
            <p className="text-sm text-amber-300 bg-amber-950/40 border border-amber-800/50 rounded-xl px-4 py-3">
              Couldn’t load questions: {error}
            </p>
          )}

          {/* Question */}
          {current && !finished && (
            <div>
              <span
                className={`inline-block text-[10px] font-semibold uppercase tracking-wide px-2 py-0.5 rounded-full border mb-3 ${difficultyColor[current.difficulty]}`}
              >
                {current.difficulty} · {current.concept}
              </span>
              <p className="text-base text-zinc-100 font-medium mb-4 leading-relaxed">{current.question}</p>

              <div className="space-y-2">
                {current.options.map((opt, i) => {
                  const isCorrect = i === current.correct_index;
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
                      {selected === current.correct_index ? "Correct ✓" : "Not quite"}
                    </p>
                    <p className="text-sm text-zinc-300 leading-relaxed">{current.explanation}</p>
                  </div>
                  <button
                    onClick={next}
                    className="mt-4 w-full bg-indigo-600 hover:bg-indigo-500 text-white text-sm font-medium rounded-xl py-2.5 transition-colors"
                  >
                    {index < (questions?.length ?? 0) - 1 ? "Next question" : "Finish"}
                  </button>
                </div>
              )}
            </div>
          )}

          {/* End screen */}
          {finished && (
            <div className="text-center py-4">
              <div className="w-14 h-14 rounded-2xl bg-indigo-600/20 border border-indigo-500/30 flex items-center justify-center mx-auto mb-4">
                <Trophy className="w-7 h-7 text-indigo-400" />
              </div>
              <p className="text-2xl font-bold text-zinc-100">
                {scoreLocal} / {answers.length}
              </p>
              <p className="text-sm text-zinc-500 mb-6">
                {saving ? "Saving your results…" : "Quiz complete"}
              </p>

              {session && (
                <div className="text-left space-y-2 mb-6">
                  <p className="text-xs font-semibold text-zinc-500 uppercase tracking-wide mb-2">Concept breakdown</p>
                  {session.concept_breakdown.map((c) => {
                    const pct = Math.round(c.accuracy * 100);
                    const strong = c.accuracy >= 0.8;
                    const weak = c.accuracy < 0.5;
                    return (
                      <div key={c.concept} className="flex items-center justify-between bg-zinc-800/50 border border-zinc-700/40 rounded-lg px-3 py-2">
                        <span className="text-sm text-zinc-300">{c.concept}</span>
                        <span className={`text-xs font-medium ${strong ? "text-emerald-400" : weak ? "text-rose-400" : "text-amber-400"}`}>
                          {c.correct}/{c.attempts} · {pct}%{strong ? " · strong" : weak ? " · revisit" : ""}
                        </span>
                      </div>
                    );
                  })}
                </div>
              )}

              <button
                onClick={onClose}
                className="inline-flex items-center gap-2 bg-zinc-800 hover:bg-zinc-700 text-zinc-200 text-sm font-medium rounded-xl px-5 py-2.5 transition-colors"
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
