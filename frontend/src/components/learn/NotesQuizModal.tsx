import { useRef, useState } from "react";
import { X, Upload, FileText, Loader2, Check, XCircle, ChevronRight, RotateCcw } from "lucide-react";
import {
  uploadText, uploadPdf, startLesson, approveLesson, submitResult, askTutor,
  type LessonView, type Objective, type Question, type Difficulty,
} from "../../lib/notesQuizApi";

type InputMode = "text" | "pdf";
type Step = "input" | "loading" | "plan" | "quizzing" | "complete";

const DIFFICULTIES: Difficulty[] = ["beginner", "intermediate", "advanced"];

const diffBadge: Record<Difficulty, string> = {
  beginner: "text-emerald-400 bg-emerald-500/10 border-emerald-500/30",
  intermediate: "text-amber-400 bg-amber-500/10 border-amber-500/30",
  advanced: "text-rose-400 bg-rose-500/10 border-rose-500/30",
};

export function NotesQuizModal({
  onClose,
  variant = "modal",
}: {
  onClose: () => void;
  variant?: "modal" | "page";
}) {
  // ── input step
  const [mode, setMode] = useState<InputMode>("text");
  const [notes, setNotes] = useState("");
  const [topic, setTopic] = useState("");
  const fileRef = useRef<HTMLInputElement>(null);
  const [fileName, setFileName] = useState("");
  const [pdfFile, setPdfFile] = useState<File | null>(null);

  // ── shared state
  const [step, setStep] = useState<Step>("input");
  const [error, setError] = useState("");
  const [lesson, setLesson] = useState<LessonView | null>(null);

  // ── plan step
  const [objectives, setObjectives] = useState<Objective[]>([]);
  const [perQuiz, setPerQuiz] = useState(3);
  const [planBusy, setPlanBusy] = useState(false);

  // ── quiz step
  const [qIdx, setQIdx] = useState(0);
  const [selected, setSelected] = useState<number | null>(null);
  const [submitted, setSubmitted] = useState(false);
  const [firstTry, setFirstTry] = useState(0);
  const [quizBusy, setQuizBusy] = useState(false);

  // ── tutor
  const [tutorQ, setTutorQ] = useState("");
  const [tutorA, setTutorA] = useState("");
  const [tutorBusy, setTutorBusy] = useState(false);

  // ─── helpers ───────────────────────────────────────────────

  function updateObj(id: string, patch: Partial<Objective>) {
    setObjectives((xs) => xs.map((o) => (o.id === id ? { ...o, ...patch } : o)));
  }
  function removeObj(id: string) {
    setObjectives((xs) => xs.filter((o) => o.id !== id));
  }
  function addObj() {
    setObjectives((xs) => [
      ...xs,
      { id: crypto.randomUUID(), title: "", difficulty: "beginner", focus: "" },
    ]);
  }

  function applyLesson(view: LessonView) {
    setLesson(view);
    if (view.status === "awaiting_approval" && view.plan) {
      setObjectives(view.plan.objectives);
      setStep("plan");
    } else if (view.status === "quizzing") {
      resetQuizState();
      setStep("quizzing");
    } else if (view.status === "complete") {
      setStep("complete");
    }
  }

  function resetQuizState() {
    setQIdx(0);
    setSelected(null);
    setSubmitted(false);
    setFirstTry(0);
    setTutorQ("");
    setTutorA("");
  }

  // ─── actions ──────────────────────────────────────────────

  async function handleGenerate() {
    setError("");
    setStep("loading");
    try {
      let docId: string;
      if (mode === "pdf") {
        if (!pdfFile) throw new Error("Please choose a PDF file.");
        const r = await uploadPdf(pdfFile);
        docId = r.docId;
      } else {
        const text = notes.trim() || topic.trim();
        if (!text) throw new Error("Please enter some notes or a topic.");
        const r = await uploadText(text, topic.trim() || undefined);
        docId = r.docId;
      }
      const view = await startLesson(docId);
      applyLesson(view);
    } catch (e) {
      setError((e as Error).message);
      setStep("input");
    }
  }

  async function handleApprove() {
    if (!lesson) return;
    const valid = objectives.filter((o) => o.title.trim());
    if (!valid.length) return;
    setError("");
    setPlanBusy(true);
    try {
      const view = await approveLesson(lesson.id, valid, perQuiz);
      applyLesson(view);
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setPlanBusy(false);
    }
  }

  async function handleNext() {
    if (!lesson || !lesson.quiz) return;
    const q = lesson.quiz.questions[qIdx];
    const correct = selected === q.correctIndex;
    const last = qIdx + 1 >= lesson.quiz.questions.length;

    if (correct && last) {
      setQuizBusy(true);
      try {
        const view = await submitResult(lesson.id, firstTry + 1, lesson.quiz.questions.length);
        applyLesson(view);
      } catch (e) {
        setError((e as Error).message);
      } finally {
        setQuizBusy(false);
      }
      return;
    }

    if (correct && !last) {
      setQIdx((i) => i + 1);
      setSelected(null);
      setSubmitted(false);
      setTutorA("");
      setTutorQ("");
    }
  }

  async function handleSubmitAnswer() {
    if (selected === null || !lesson?.quiz) return;
    const q = lesson.quiz.questions[qIdx];
    if (selected === q.correctIndex) setFirstTry((n) => n + 1);
    setSubmitted(true);
  }

  async function handleAskTutor() {
    if (!lesson || !tutorQ.trim()) return;
    setTutorBusy(true);
    setTutorA("");
    try {
      const { answer } = await askTutor(lesson.id, tutorQ.trim());
      setTutorA(answer);
    } catch {
      setTutorA("Couldn't reach the tutor right now. Try again.");
    } finally {
      setTutorBusy(false);
    }
  }

  function restart() {
    setStep("input");
    setLesson(null);
    setNotes("");
    setTopic("");
    setPdfFile(null);
    setFileName("");
    setError("");
    resetQuizState();
  }

  // ─── render ───────────────────────────────────────────────

  const q: Question | undefined = lesson?.quiz?.questions[qIdx];
  const correct = submitted && selected !== null && q && selected === q.correctIndex;

  const card = (
      <div
        className="bg-zinc-900 border border-zinc-700 rounded-2xl w-full max-w-xl flex flex-col max-h-[90vh]"
        onClick={(e) => e.stopPropagation()}
      >
        {/* header */}
        <div className="flex items-center justify-between px-6 py-4 border-b border-zinc-800 flex-shrink-0">
          <div className="flex items-center gap-2">
            <FileText className="w-4 h-4 text-teal-400" />
            <div>
              <h2 className="text-sm font-semibold text-zinc-100">Notes → Quiz</h2>
              <p className="text-xs text-zinc-500">
                {step === "input" && "Upload PDF or paste notes to generate a quiz"}
                {step === "loading" && "Analysing your notes…"}
                {step === "plan" && "Review your lesson plan before we begin"}
                {step === "quizzing" && lesson?.currentObjective?.title}
                {step === "complete" && "Session complete"}
              </p>
            </div>
          </div>
          <button onClick={onClose} className="text-zinc-500 hover:text-zinc-200">
            <X className="w-5 h-5" />
          </button>
        </div>

        <div className="overflow-y-auto px-6 py-5 flex flex-col gap-4">
          {error && (
            <p className="text-sm text-rose-300 bg-rose-950/40 border border-rose-800/50 rounded-xl px-4 py-3">
              {error}
            </p>
          )}

          {/* ── INPUT STEP ── */}
          {step === "input" && (
            <div className="flex flex-col gap-4">
              {/* mode toggle */}
              <div className="flex bg-zinc-800 rounded-xl p-1 gap-1">
                {(["text", "pdf"] as InputMode[]).map((m) => (
                  <button
                    key={m}
                    onClick={() => setMode(m)}
                    className={`flex-1 flex items-center justify-center gap-1.5 py-2 rounded-lg text-sm font-medium transition-colors ${
                      mode === m
                        ? "bg-teal-600 text-white"
                        : "text-zinc-400 hover:text-zinc-200"
                    }`}
                  >
                    {m === "pdf" ? <Upload className="w-3.5 h-3.5" /> : <FileText className="w-3.5 h-3.5" />}
                    {m === "pdf" ? "Upload PDF" : "Type notes / topic"}
                  </button>
                ))}
              </div>

              {mode === "text" ? (
                <div className="flex flex-col gap-3">
                  <div>
                    <label className="text-xs text-zinc-500 font-medium mb-1 block">
                      Topic (optional — helps scope the quiz)
                    </label>
                    <input
                      value={topic}
                      onChange={(e) => setTopic(e.target.value)}
                      placeholder="e.g. React hooks, OS scheduling, Binary Search Trees…"
                      className="w-full bg-zinc-800 border border-zinc-700 rounded-xl px-4 py-2.5 text-sm text-zinc-100 placeholder-zinc-600 outline-none focus:border-teal-500/60"
                    />
                  </div>
                  <div>
                    <label className="text-xs text-zinc-500 font-medium mb-1 block">
                      Notes (paste your notes, or leave blank to quiz on the topic above)
                    </label>
                    <textarea
                      value={notes}
                      onChange={(e) => setNotes(e.target.value)}
                      rows={7}
                      placeholder="Paste your notes here…"
                      className="w-full bg-zinc-800 border border-zinc-700 rounded-xl px-4 py-3 text-sm text-zinc-100 placeholder-zinc-600 outline-none focus:border-teal-500/60 resize-none"
                    />
                  </div>
                </div>
              ) : (
                <div
                  onClick={() => fileRef.current?.click()}
                  className="border-2 border-dashed border-zinc-700 hover:border-teal-500/60 rounded-xl p-8 text-center cursor-pointer transition-colors"
                >
                  <Upload className="w-8 h-8 text-zinc-600 mx-auto mb-2" />
                  {fileName ? (
                    <p className="text-sm text-teal-400 font-medium">{fileName}</p>
                  ) : (
                    <>
                      <p className="text-sm text-zinc-400 font-medium">Click to choose a PDF</p>
                      <p className="text-xs text-zinc-600 mt-1">Lecture slides, textbook pages, your handwritten scan</p>
                    </>
                  )}
                  <input
                    ref={fileRef}
                    type="file"
                    accept="application/pdf"
                    className="hidden"
                    onChange={(e) => {
                      const f = e.target.files?.[0];
                      if (f) { setPdfFile(f); setFileName(f.name); }
                    }}
                  />
                </div>
              )}

              <button
                onClick={handleGenerate}
                disabled={mode === "pdf" ? !pdfFile : (!notes.trim() && !topic.trim())}
                className="w-full flex items-center justify-center gap-2 bg-teal-600 hover:bg-teal-500 disabled:bg-zinc-700 disabled:text-zinc-500 text-white text-sm font-semibold rounded-xl py-3 transition-colors"
              >
                Generate Quiz <ChevronRight className="w-4 h-4" />
              </button>
            </div>
          )}

          {/* ── LOADING ── */}
          {step === "loading" && (
            <div className="flex flex-col items-center justify-center py-16 text-center">
              <Loader2 className="w-8 h-8 text-teal-400 animate-spin mb-4" />
              <p className="text-sm text-zinc-300">Analysing your notes and drafting a plan…</p>
              <p className="text-xs text-zinc-500 mt-1">This takes about 10 seconds</p>
            </div>
          )}

          {/* ── PLAN APPROVAL ── */}
          {step === "plan" && (
            <div className="flex flex-col gap-4">
              <div>
                <p className="text-xs font-semibold text-teal-400 uppercase tracking-wide mb-0.5">Step 1 · Review your lesson plan</p>
                <p className="text-base font-semibold text-zinc-100">Here's what we'll cover</p>
                <p className="text-xs text-zinc-500 mt-0.5">Edit, remove, or add objectives. Nothing generates until you approve.</p>
              </div>

              <div className="flex flex-col gap-2">
                {objectives.map((o, i) => (
                  <div key={o.id} className="bg-zinc-800 border border-zinc-700 rounded-xl p-4 flex gap-3">
                    <div className="w-6 h-6 rounded-lg bg-teal-600/20 text-teal-400 text-xs font-bold flex items-center justify-center flex-shrink-0 mt-0.5">
                      {i + 1}
                    </div>
                    <div className="flex-1 min-w-0">
                      <input
                        value={o.title}
                        onChange={(e) => updateObj(o.id, { title: e.target.value })}
                        placeholder="Objective title…"
                        className="w-full bg-transparent text-sm font-semibold text-zinc-100 outline-none placeholder-zinc-600"
                      />
                      <input
                        value={o.focus}
                        onChange={(e) => updateObj(o.id, { focus: e.target.value })}
                        placeholder="What this covers…"
                        className="w-full bg-transparent text-xs text-zinc-500 outline-none placeholder-zinc-600 mt-1"
                      />
                      <select
                        value={o.difficulty}
                        onChange={(e) => updateObj(o.id, { difficulty: e.target.value as Difficulty })}
                        className={`mt-2 text-[10px] font-bold uppercase tracking-wide border rounded-lg px-2 py-1 bg-zinc-900 cursor-pointer outline-none ${diffBadge[o.difficulty]}`}
                      >
                        {DIFFICULTIES.map((d) => <option key={d} value={d}>{d}</option>)}
                      </select>
                    </div>
                    <button onClick={() => removeObj(o.id)} className="text-zinc-600 hover:text-zinc-400 text-lg leading-none flex-shrink-0">×</button>
                  </div>
                ))}

                <button
                  onClick={addObj}
                  className="border border-dashed border-teal-600/40 text-teal-500 text-sm font-medium rounded-xl py-3 hover:bg-teal-600/5 transition-colors"
                >
                  + Add an objective
                </button>
              </div>

              <div className="flex items-center gap-3 text-sm text-zinc-300">
                <span className="font-medium">Questions per objective</span>
                <input
                  type="number"
                  min={1}
                  max={10}
                  value={perQuiz}
                  onChange={(e) => setPerQuiz(Math.max(1, Math.min(10, Number(e.target.value) || 1)))}
                  className="w-16 bg-zinc-800 border border-zinc-700 rounded-lg px-3 py-1.5 text-sm text-zinc-100 outline-none"
                />
              </div>

              <button
                disabled={planBusy || !objectives.some((o) => o.title.trim())}
                onClick={handleApprove}
                className="w-full flex items-center justify-center gap-2 bg-teal-600 hover:bg-teal-500 disabled:bg-zinc-700 disabled:text-zinc-500 text-white text-sm font-semibold rounded-xl py-3 transition-colors"
              >
                {planBusy ? <><Loader2 className="w-4 h-4 animate-spin" /> Preparing first quiz…</> : <>Approve & start <ChevronRight className="w-4 h-4" /></>}
              </button>
            </div>
          )}

          {/* ── QUIZ ── */}
          {step === "quizzing" && lesson && lesson.quiz && q && (
            <div className="flex flex-col gap-4">
              {/* objectives progress bar */}
              {lesson.objectives && (
                <div className="flex gap-2">
                  {lesson.objectives.map((o, i) => {
                    const done = i < (lesson.objectiveIndex ?? 0);
                    const cur = i === (lesson.objectiveIndex ?? 0);
                    const r = lesson.results?.find((x) => x.objectiveId === o.id);
                    return (
                      <div key={o.id} className="flex-1 text-center">
                        <div className={`h-1.5 rounded-full ${done ? "bg-teal-500" : cur ? "bg-teal-500/30 border border-teal-500" : "bg-zinc-700"}`} />
                        <p className={`text-[10px] font-semibold mt-1 ${done || cur ? "text-teal-400" : "text-zinc-600"}`}>
                          {done && r ? `${r.score}/${r.total}` : `Obj ${i + 1}`}
                        </p>
                      </div>
                    );
                  })}
                </div>
              )}

              <div>
                <p className="text-xs font-semibold text-teal-400 uppercase tracking-wide">
                  {lesson.currentObjective?.title}
                </p>
                <div className="flex items-center gap-2 mt-1">
                  <div className="flex-1 h-1.5 bg-zinc-800 rounded-full overflow-hidden">
                    <div
                      className="h-full bg-teal-500 transition-all"
                      style={{ width: `${((qIdx + 1) / lesson.quiz.questions.length) * 100}%` }}
                    />
                  </div>
                  <span className="text-xs text-zinc-500">{qIdx + 1}/{lesson.quiz.questions.length}</span>
                </div>
              </div>

              <div className="bg-zinc-800 border border-zinc-700 rounded-xl p-5">
                <p className="text-base font-semibold text-zinc-100 leading-relaxed mb-4">{q.question}</p>

                <div className="flex flex-col gap-2">
                  {q.options.map((opt, i) => {
                    const isCorrect = i === q.correctIndex;
                    const isChosen = i === selected;
                    let cls = "border-zinc-700 bg-zinc-800/60 hover:bg-zinc-700/60 text-zinc-200";
                    if (submitted) {
                      if (isCorrect) cls = "border-teal-500/50 bg-teal-500/10 text-teal-100";
                      else if (isChosen) cls = "border-rose-500/50 bg-rose-500/10 text-rose-100";
                      else cls = "border-zinc-800 bg-zinc-800/30 text-zinc-500";
                    }
                    return (
                      <button
                        key={i}
                        onClick={() => !submitted && setSelected(i)}
                        disabled={submitted}
                        className={`w-full text-left px-4 py-3 rounded-xl border text-sm flex items-center justify-between transition-colors ${cls} ${submitted ? "cursor-default" : "cursor-pointer"}`}
                      >
                        <span>{opt}</span>
                        {submitted && isCorrect && <Check className="w-4 h-4 text-teal-400 flex-shrink-0" />}
                        {submitted && isChosen && !isCorrect && <XCircle className="w-4 h-4 text-rose-400 flex-shrink-0" />}
                      </button>
                    );
                  })}
                </div>

                {/* feedback */}
                {submitted && correct && (
                  <div className="mt-4 bg-teal-950/40 border border-teal-800/40 rounded-xl px-4 py-3 text-sm text-teal-200">
                    <span className="font-semibold">Correct ✓</span> — {q.explanation}
                  </div>
                )}
                {submitted && !correct && (
                  <div className="mt-4 bg-amber-950/40 border border-amber-700/40 rounded-xl px-4 py-3 text-sm text-amber-200">
                    <span className="font-semibold">Not quite.</span> <span className="text-amber-300">Hint:</span> {q.hint}
                  </div>
                )}

                <div className="flex gap-2 mt-4">
                  {!submitted && (
                    <button
                      onClick={handleSubmitAnswer}
                      disabled={selected === null}
                      className="flex-1 bg-teal-600 hover:bg-teal-500 disabled:bg-zinc-700 disabled:text-zinc-500 text-white text-sm font-semibold rounded-xl py-2.5 transition-colors"
                    >
                      Submit
                    </button>
                  )}
                  {submitted && !correct && (
                    <button
                      onClick={() => { setSubmitted(false); setSelected(null); }}
                      className="flex-1 border border-teal-600/40 text-teal-400 text-sm font-semibold rounded-xl py-2.5 hover:bg-teal-600/10 transition-colors"
                    >
                      Try again
                    </button>
                  )}
                  {submitted && correct && (
                    <button
                      onClick={handleNext}
                      disabled={quizBusy}
                      className="flex-1 bg-teal-600 hover:bg-teal-500 disabled:opacity-50 text-white text-sm font-semibold rounded-xl py-2.5 transition-colors flex items-center justify-center gap-2"
                    >
                      {quizBusy ? <Loader2 className="w-4 h-4 animate-spin" /> : null}
                      {qIdx + 1 >= lesson.quiz.questions.length ? "Finish objective" : "Next question"}
                    </button>
                  )}
                </div>
              </div>

              {/* inline tutor */}
              <div className="border border-zinc-800 rounded-xl p-4">
                <p className="text-xs font-semibold text-zinc-500 mb-2">Ask the tutor</p>
                <div className="flex gap-2">
                  <input
                    value={tutorQ}
                    onChange={(e) => setTutorQ(e.target.value)}
                    onKeyDown={(e) => e.key === "Enter" && handleAskTutor()}
                    placeholder="Confused about something? Ask without getting the answer…"
                    className="flex-1 bg-zinc-800 border border-zinc-700 rounded-lg px-3 py-2 text-xs text-zinc-200 placeholder-zinc-600 outline-none"
                  />
                  <button
                    onClick={handleAskTutor}
                    disabled={tutorBusy || !tutorQ.trim()}
                    className="px-3 py-2 bg-zinc-700 hover:bg-zinc-600 disabled:opacity-40 rounded-lg text-xs text-zinc-300 font-medium transition-colors"
                  >
                    {tutorBusy ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : "Ask"}
                  </button>
                </div>
                {tutorA && (
                  <p className="mt-3 text-xs text-zinc-300 leading-relaxed border-t border-zinc-800 pt-3">{tutorA}</p>
                )}
              </div>
            </div>
          )}

          {/* ── COMPLETE ── */}
          {step === "complete" && lesson?.summary && (
            <div className="flex flex-col gap-4 py-2">
              <div className="text-center">
                <div className="w-14 h-14 rounded-2xl bg-teal-600/20 border border-teal-500/30 flex items-center justify-center mx-auto mb-3">
                  <FileText className="w-7 h-7 text-teal-400" />
                </div>
                <p className="text-base font-semibold text-zinc-100">Session complete</p>
                <p className="text-sm text-zinc-400 mt-1 leading-relaxed">{lesson.summary.overall}</p>
              </div>

              {lesson.results && lesson.results.length > 0 && (
                <div>
                  <p className="text-xs font-semibold text-zinc-500 uppercase tracking-wide mb-2">Scores</p>
                  <div className="flex flex-col gap-2">
                    {lesson.results.map((r) => {
                      const pct = Math.round((r.score / r.total) * 100);
                      const comment = lesson.summary?.perObjective.find((x) => x.title === r.objectiveTitle)?.comment;
                      return (
                        <div key={r.objectiveId} className="bg-zinc-800 border border-zinc-700 rounded-xl px-4 py-3">
                          <div className="flex items-center justify-between mb-1.5">
                            <span className="text-sm font-medium text-zinc-200">{r.objectiveTitle}</span>
                            <span className={`text-sm font-bold ${pct >= 70 ? "text-teal-400" : "text-amber-400"}`}>{r.score}/{r.total}</span>
                          </div>
                          <div className="h-1.5 bg-zinc-700 rounded-full overflow-hidden mb-2">
                            <div className={`h-full ${pct >= 70 ? "bg-teal-500" : "bg-amber-500"}`} style={{ width: `${pct}%` }} />
                          </div>
                          {comment && <p className="text-xs text-zinc-500">{comment}</p>}
                        </div>
                      );
                    })}
                  </div>
                </div>
              )}

              {lesson.summary.studyTips.length > 0 && (
                <div className="bg-zinc-800 border border-zinc-700 rounded-xl px-4 py-3">
                  <p className="text-xs font-semibold text-zinc-400 mb-2">Study tips</p>
                  <ul className="flex flex-col gap-1.5">
                    {lesson.summary.studyTips.map((tip, i) => (
                      <li key={i} className="text-sm text-zinc-300 flex gap-2">
                        <span className="text-teal-500 flex-shrink-0">•</span> {tip}
                      </li>
                    ))}
                  </ul>
                </div>
              )}

              <button
                onClick={restart}
                className="w-full inline-flex items-center justify-center gap-2 bg-zinc-800 hover:bg-zinc-700 text-zinc-200 text-sm font-medium rounded-xl py-3 transition-colors"
              >
                <RotateCcw className="w-4 h-4" /> Try another set of notes
              </button>
            </div>
          )}
        </div>
      </div>
  );

  if (variant === "page") return card;

  return (
    <div
      className="fixed inset-0 z-50 bg-black/70 flex items-center justify-center p-4"
      onClick={onClose}
    >
      {card}
    </div>
  );
}
