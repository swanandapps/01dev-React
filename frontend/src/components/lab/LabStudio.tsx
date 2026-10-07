import { useEffect, useRef, useState } from "react";
import type { ReactNode } from "react";
import {
  Upload, NotebookPen, Loader2, Sparkles, ChevronRight, Check, RotateCcw,
  FlaskConical, X, Video,
} from "lucide-react";
import * as quizApi from "../../lib/notesQuizApiLang";
import { generateOutputs, getLectures, uploadLecture, OUTPUT_LABELS } from "../../lib/labApi";
import type { LabArtifacts, Lecture, OutputType } from "../../lib/labApi";
import type { Course } from "../../types/learn";
import { ArtifactView } from "./ArtifactView";
import { NotesQuizModal } from "../learn/NotesQuizModal";

type InputMode = "lecture" | "topic" | "notes" | "pdf";
type Step = "input" | "generating" | "results";

const ALL_OUTPUTS: OutputType[] = ["quiz", "flashcards", "summary", "study_plan"];

// Shared chrome so every step — including the quiz hand-off — carries a
// visible "Lab" title and a close control that actually calls onClose.
// Matches the header idiom in NotesQuizModal's own modal chrome and
// AdaptiveModal (icon + title/subtitle left, X right).
function StudioHeader({
  subtitle,
  onClose,
  extra,
}: {
  subtitle: string;
  onClose: () => void;
  extra?: ReactNode;
}) {
  return (
    <div className="flex items-center justify-between">
      <div className="flex items-center gap-2">
        <FlaskConical className="w-4 h-4 text-indigo-400" />
        <div>
          <h2 className="text-sm font-semibold text-zinc-100">Lab</h2>
          <p className="text-xs text-zinc-500">{subtitle}</p>
        </div>
      </div>
      <div className="flex items-center gap-3">
        {extra}
        <button
          onClick={onClose}
          aria-label="Close"
          className="text-zinc-500 hover:text-zinc-200"
        >
          <X className="w-5 h-5" />
        </button>
      </div>
    </div>
  );
}

const SOURCES: { mode: InputMode; label: string; hint: string; icon: typeof Upload }[] = [
  { mode: "lecture", label: "A lecture", hint: "From your courses", icon: Video },
  { mode: "topic", label: "A topic", hint: "“React hooks”, “BST”…", icon: Sparkles },
  { mode: "notes", label: "Your notes", hint: "Paste or type", icon: NotebookPen },
  { mode: "pdf", label: "A PDF", hint: "Upload a file", icon: Upload },
];

const MAKE_LABEL: Record<OutputType, string> = {
  quiz: "Make my quiz", flashcards: "Make my flashcards", summary: "Make my revision notes", study_plan: "Make my study plan",
};

/** A small picture of each output, so the choice reads at a glance (decorative). */
function OutputPreview({ kind, on }: { kind: OutputType; on: boolean }) {
  const bar = on ? "bg-teal-300/30" : "bg-zinc-700";
  return (
    <span aria-hidden="true" className={`h-14 rounded-lg border flex flex-col justify-center gap-1.5 px-2.5 ${on ? "border-teal-500/30 bg-teal-950/40" : "border-zinc-800 bg-zinc-950"}`}>
      {kind === "quiz" && (<><span className={`h-1.5 w-3/4 rounded ${bar}`} /><span className={`h-1.5 rounded ${on ? "bg-teal-400" : "bg-zinc-600"} w-1/2`} /><span className={`h-1.5 w-2/3 rounded ${bar}`} /></>)}
      {kind === "flashcards" && (<span className={`mx-auto h-9 w-16 rounded-md border ${on ? "border-teal-400/60" : "border-zinc-600"} flex items-center justify-center text-[10px] ${on ? "text-teal-200" : "text-zinc-500"}`}>flip</span>)}
      {kind === "summary" && (<><span className={`h-1.5 w-full rounded ${bar}`} /><span className={`h-1.5 w-5/6 rounded ${bar}`} /><span className={`h-1.5 w-2/3 rounded ${bar}`} /></>)}
      {kind === "study_plan" && (<><span className={`h-1.5 w-1/2 rounded ${bar}`} /><span className={`h-1.5 w-2/3 rounded ml-2 ${bar}`} /><span className={`h-1.5 w-1/2 rounded ml-4 ${bar}`} /></>)}
    </span>
  );
}

export function LabStudio({
  studentId,
  onClose,
  courseId,
  initialLectureTitle,
  initialOutputs,
  autoStart = false,
  courses,
  chrome = true,
  prefill,
}: {
  studentId: string;
  onClose: () => void;
  courseId?: string;
  /** In a course: preselect this lecture (by title) instead of the first one. */
  initialLectureTitle?: string;
  initialOutputs?: OutputType[];
  /** Generate straight away once the lecture is known (the player's "Quiz me" / "Flashcards"). */
  autoStart?: boolean;
  /** Lab page: the student's courses that have lectures to practise from (adds "A lecture" with a course picker). */
  courses?: Course[];
  /** false on the Lab page, which has its own heading: no studio header while picking material. */
  chrome?: boolean;
  /** "Practise this" from the Lab page: start a quiz on this topic (n changes to re-apply). */
  prefill?: { topic: string; n: number };
}) {
  const [mode, setMode] = useState<InputMode>(courseId || courses?.length ? "lecture" : "topic");
  const [pickedCourse, setPickedCourse] = useState(courses?.[0]?.course_id ?? "");
  const lectureCourse = courseId || pickedCourse;
  const [topic, setTopic] = useState("");
  const [notes, setNotes] = useState("");
  const [lectures, setLectures] = useState<Lecture[]>([]);
  const [lectureId, setLectureId] = useState("");
  const [lecturesError, setLecturesError] = useState(false);
  const fileRef = useRef<HTMLInputElement>(null);
  const [fileName, setFileName] = useState("");
  const [pdfFile, setPdfFile] = useState<File | null>(null);

  const [selected, setSelected] = useState<OutputType[]>(initialOutputs?.length ? initialOutputs : ["quiz"]);
  const started = useRef(false);
  const [step, setStep] = useState<Step>("input");
  const [error, setError] = useState("");
  const [artifacts, setArtifacts] = useState<LabArtifacts>({});
  const [lessonId, setLessonId] = useState<string | null>(null);

  // Esc closes Lab the same way the header X does, wherever Lab is presented
  // (in-course modal or the full page).
  // Not while they're typing: Esc in the notes textarea would close Lab and
  // discard everything they'd written, with no undo.
  useEffect(() => {
    function handleKey(e: KeyboardEvent) {
      if (e.key !== "Escape") return;
      const el = e.target as HTMLElement | null;
      const tag = el?.tagName;
      if (tag === "TEXTAREA" || tag === "INPUT" || el?.isContentEditable) return;
      onClose();
    }
    window.addEventListener("keydown", handleKey);
    return () => window.removeEventListener("keydown", handleKey);
  }, [onClose]);

  // Courses can arrive after the first render on the Lab page.
  useEffect(() => {
    if (!courseId && courses?.length && !pickedCourse) {
      setPickedCourse(courses[0].course_id);
      setMode((m) => (m === "topic" && !topic && !notes ? "lecture" : m));
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [courses]);

  useEffect(() => {
    if (!prefill?.topic) return;
    setMode("topic");
    setTopic(prefill.topic);
    setSelected(["quiz"]);
  }, [prefill]);

  // Ask the backend which lectures of the chosen course have transcripts.
  useEffect(() => {
    if (!lectureCourse) return;
    getLectures(lectureCourse)
      .then((ls) => {
        setLecturesError(false);
        setLectures(ls);
        const norm = (t: string) => t.toLowerCase().replace(/[`'"]/g, "").replace(/\s+/g, " ").trim();
        const wanted = initialLectureTitle ? ls.find((l) => norm(l.lecture_title) === norm(initialLectureTitle)) : undefined;
        setLectureId((cur) => wanted?.lecture_id ?? (ls.some((l) => l.lecture_id === cur) ? cur : ls[0]?.lecture_id ?? ""));
      })
      .catch(() => {
        setLectures([]);
        setLectureId("");
        setLecturesError(true);
      });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [lectureCourse]);

  // The player's "Quiz me" / "Flashcards": go straight to generating once the lecture is picked.
  useEffect(() => {
    if (!autoStart || started.current || mode !== "lecture" || !lectureId) return;
    started.current = true;
    void handleGenerate();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [autoStart, lectureId, mode]);

  const toggle = (t: OutputType) =>
    setSelected((s) => (s.includes(t) ? s.filter((x) => x !== t) : [...s, t]));

  const canSubmit =
    selected.length > 0 &&
    (mode === "pdf"
      ? !!pdfFile
      : mode === "lecture"
      ? !!lectureId
      : mode === "topic"
      ? !!topic.trim()
      : !!notes.trim());

  async function handleGenerate() {
    setError("");
    setStep("generating");
    try {
      let docId: string;
      if (mode === "pdf") {
        if (!pdfFile) throw new Error("Please choose a PDF file.");
        docId = (await quizApi.uploadPdf(pdfFile)).docId;
      } else if (mode === "lecture") {
        if (!lectureId) throw new Error("Please pick a lecture.");
        docId = (await uploadLecture(lectureId)).docId;
      } else {
        const text = mode === "topic" ? topic.trim() : notes.trim();
        if (!text) throw new Error(mode === "topic" ? "Please enter a topic." : "Please paste some notes.");
        docId = (await quizApi.uploadText(text, mode === "topic" ? text : undefined)).docId;
      }
      const res = await generateOutputs(docId, selected);
      setArtifacts(res.artifacts ?? {});
      setLessonId(res.lesson_id);
      setStep("results");
    } catch (e) {
      setError((e as Error).message);
      setStep("input");
    }
  }

  function restart() {
    setStep("input");
    setArtifacts({});
    setLessonId(null);
    setError("");
    setNotes("");
    setTopic("");
    setPdfFile(null);
    setFileName("");
  }

  if (step === "results" && lessonId) {
    // Quiz was selected — hand straight off to the existing, parity-verified
    // quiz UI, with any artifacts shown above it. "Back to Lab" stays
    // reachable the whole time (plan/quizzing/complete, below), and is also
    // wired into NotesQuizModal's own completion screen via onRestart — so
    // neither abandoning nor finishing the quiz can strand the student in
    // NotesQuizModal's retired standalone upload form.
    return (
      <div className="flex flex-col gap-6">
        <StudioHeader
          subtitle="Continuing into your quiz"
          onClose={onClose}
          extra={
            <button
              onClick={restart}
              className="text-xs font-medium text-indigo-400 hover:text-indigo-300 transition-colors"
            >
              Back to Lab
            </button>
          }
        />
        <ArtifactView artifacts={artifacts} />
        <NotesQuizModal
          resumeLessonId={lessonId}
          onRestart={restart}
        />
      </div>
    );
  }

  const subtitle =
    step === "generating"
      ? "Working through your material…"
      : step === "results"
      ? "Here's what we made"
      : courseId
      ? "Use a lecture from this course, or your own material"
      : "Bring your material, then pick what to make";

  return (
    <div className="flex flex-col gap-5">
      {(chrome || step !== "input") && <StudioHeader subtitle={subtitle} onClose={onClose} />}

      {error && (
        <p className="text-sm text-rose-300 bg-rose-950/40 border border-rose-800/50 rounded-xl px-4 py-3">
          {error}
        </p>
      )}

      {step === "input" && (
        <>
          <section className="flex flex-col gap-3">
            <h3 className="text-[13px] font-bold text-zinc-400"><span className="text-violet-400">1</span> · Start from</h3>
            <div className="grid grid-cols-2 sm:grid-cols-4 gap-2.5">
              {SOURCES.filter((src) => src.mode !== "lecture" || courseId || courses?.length).map((src) => {
                const on = mode === src.mode;
                return (
                  <button key={src.mode} type="button" aria-pressed={on} onClick={() => setMode(src.mode)}
                          className={`text-left rounded-2xl px-4 py-3.5 border transition-colors flex flex-col gap-1 ${
                            on ? "border-violet-500 bg-violet-500/10" : "border-zinc-800 bg-zinc-900 hover:border-zinc-600"}`}>
                    <src.icon className={`w-4 h-4 mb-1 ${on ? "text-violet-300" : "text-zinc-400"}`} />
                    <span className="text-sm font-bold text-zinc-100">{src.label}</span>
                    <span className={`text-xs ${on ? "text-violet-200/80" : "text-zinc-500"}`}>{src.hint}</span>
                  </button>
                );
              })}
            </div>

            {mode === "lecture" && (
              <div className="flex flex-col sm:flex-row gap-2.5">
                {!courseId && courses && courses.length > 0 && (
                  <select aria-label="Course" value={pickedCourse} onChange={(e) => setPickedCourse(e.target.value)}
                          className="sm:flex-1 bg-zinc-900 border border-zinc-700 rounded-xl px-3.5 py-3 text-sm text-zinc-100 outline-none focus:border-violet-500/60">
                    {courses.map((c) => <option key={c.course_id} value={c.course_id}>{c.title}</option>)}
                  </select>
                )}
                {lecturesError ? (
                  <p className="sm:flex-[2] text-sm text-rose-300 bg-rose-950/40 border border-rose-800/50 rounded-xl px-4 py-3">
                    Couldn't load lectures. Check your connection and try again.
                  </p>
                ) : lectures.length === 0 ? (
                  <p className="sm:flex-[2] text-sm text-zinc-500 bg-zinc-900 border border-zinc-800 rounded-xl px-4 py-3">
                    No lectures to practise from in this course yet. Try a topic or your notes.
                  </p>
                ) : (
                  <select aria-label="Lecture" value={lectureId} onChange={(e) => setLectureId(e.target.value)}
                          className="sm:flex-[2] bg-zinc-900 border border-zinc-700 rounded-xl px-3.5 py-3 text-sm text-zinc-100 outline-none focus:border-violet-500/60">
                    {lectures.map((l) => <option key={l.lecture_id} value={l.lecture_id}>{l.lecture_title}</option>)}
                  </select>
                )}
              </div>
            )}
            {mode === "topic" && (
              <input aria-label="Topic" value={topic} onChange={(e) => setTopic(e.target.value)}
                     placeholder="e.g. React hooks, OS scheduling, binary search trees…"
                     className="w-full bg-zinc-900 border border-zinc-700 rounded-xl px-4 py-3 text-sm text-zinc-100 placeholder-zinc-600 outline-none focus:border-violet-500/60" />
            )}
            {mode === "notes" && (
              <textarea aria-label="Your notes" value={notes} onChange={(e) => setNotes(e.target.value)} rows={6}
                        placeholder="Paste your notes here…"
                        className="w-full bg-zinc-900 border border-zinc-700 rounded-xl px-4 py-3 text-sm text-zinc-100 placeholder-zinc-600 outline-none focus:border-violet-500/60 resize-none" />
            )}
            {mode === "pdf" && (
              <button type="button" onClick={() => fileRef.current?.click()}
                      className="border-2 border-dashed border-zinc-700 hover:border-violet-500/50 rounded-xl p-8 text-center transition-colors">
                <Upload className="w-5 h-5 text-violet-300 mx-auto mb-2" />
                <span className={`text-sm font-medium ${fileName ? "text-violet-200" : "text-zinc-300"}`}>{fileName || "Choose a PDF"}</span>
                <input ref={fileRef} type="file" accept="application/pdf" className="hidden"
                       onChange={(e) => { const f = e.target.files?.[0]; if (f) { setPdfFile(f); setFileName(f.name); } }} />
              </button>
            )}
          </section>

          <section className="flex flex-col gap-3">
            <h3 className="text-[13px] font-bold text-zinc-400"><span className="text-violet-400">2</span> · Make</h3>
            <div className="grid grid-cols-2 sm:grid-cols-4 gap-2.5">
              {ALL_OUTPUTS.map((t) => {
                const on = selected.includes(t);
                const { label, blurb } = OUTPUT_LABELS[t];
                return (
                  <button key={t} type="button" onClick={() => toggle(t)} aria-pressed={on}
                          className={`text-left rounded-2xl border p-3.5 transition-colors flex flex-col gap-2.5 ${
                            on ? "border-teal-400 bg-teal-500/10" : "border-zinc-800 bg-zinc-900 hover:border-zinc-600"}`}>
                    <span className="flex items-center justify-between gap-2">
                      <span className="text-sm font-bold text-zinc-100">{label}</span>
                      <span className={`w-4 h-4 rounded flex items-center justify-center flex-shrink-0 ${on ? "bg-teal-500" : "border border-zinc-600"}`}>
                        {on && <Check className="w-3 h-3 text-teal-950" />}
                      </span>
                    </span>
                    <OutputPreview kind={t} on={on} />
                    <span className="text-xs text-zinc-500 leading-snug">{blurb}</span>
                  </button>
                );
              })}
            </div>
          </section>

          <button onClick={handleGenerate} disabled={!canSubmit}
                  className="self-start flex items-center gap-2 bg-violet-600 hover:bg-violet-500 disabled:bg-zinc-800 disabled:text-zinc-500 text-white text-sm font-bold rounded-xl px-6 py-3.5 transition-colors">
            <Sparkles className="w-4 h-4" />
            {selected.length === 1 ? MAKE_LABEL[selected[0]] : `Make ${selected.length} things`}
            <ChevronRight className="w-4 h-4" />
          </button>
        </>
      )}

      {step === "generating" && (
        <div className="flex flex-col items-center justify-center py-20 text-center">
          <Loader2 className="w-7 h-7 text-indigo-400 animate-spin mb-4" />
          <p className="text-base font-semibold text-zinc-100 mb-1">Working through your material…</p>
          <p className="text-sm text-zinc-500">
            {selected.map((t) => OUTPUT_LABELS[t].label).join(" · ")}
          </p>
        </div>
      )}

      {step === "results" && !lessonId && (
        <>
          {Object.keys(artifacts).length > 0 ? (
            <ArtifactView artifacts={artifacts} />
          ) : (
            <p className="text-sm text-zinc-400 bg-zinc-800/40 border border-zinc-700/50 rounded-xl px-4 py-4">
              Nothing usable came back for this material — try again, or add more detail and retry.
            </p>
          )}
          <button
            onClick={restart}
            className="w-full inline-flex items-center justify-center gap-2 bg-zinc-800 hover:bg-zinc-700 border border-zinc-700/50 text-zinc-300 text-sm font-medium rounded-xl py-3 transition-colors"
          >
            <RotateCcw className="w-4 h-4" /> Make something else
          </button>
        </>
      )}
    </div>
  );
}
