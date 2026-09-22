import { useRef, useState } from "react";
import { Upload, NotebookPen, Loader2, Sparkles, ChevronRight, Check, RotateCcw } from "lucide-react";
import * as quizApi from "../../lib/notesQuizApiLang";
import { generateOutputs, OUTPUT_LABELS } from "../../lib/labApi";
import type { LabArtifacts, OutputType } from "../../lib/labApi";
import { ArtifactView } from "./ArtifactView";
import { NotesQuizModal } from "../learn/NotesQuizModal";

type InputMode = "text" | "pdf";
type Step = "input" | "generating" | "results";

const ALL_OUTPUTS: OutputType[] = ["quiz", "flashcards", "summary", "study_plan"];

export function LabStudio({
  studentId,
  onClose,
  lectureText,
}: {
  studentId: string;
  onClose: () => void;
  lectureText?: string;
}) {
  const [mode, setMode] = useState<InputMode>(lectureText ? "text" : "text");
  const [topic, setTopic] = useState("");
  const [notes, setNotes] = useState(lectureText ?? "");
  const fileRef = useRef<HTMLInputElement>(null);
  const [fileName, setFileName] = useState("");
  const [pdfFile, setPdfFile] = useState<File | null>(null);

  const [selected, setSelected] = useState<OutputType[]>(["quiz"]);
  const [step, setStep] = useState<Step>("input");
  const [error, setError] = useState("");
  const [artifacts, setArtifacts] = useState<LabArtifacts>({});
  const [lessonId, setLessonId] = useState<string | null>(null);

  const toggle = (t: OutputType) =>
    setSelected((s) => (s.includes(t) ? s.filter((x) => x !== t) : [...s, t]));

  const canSubmit =
    selected.length > 0 && (mode === "pdf" ? !!pdfFile : !!(notes.trim() || topic.trim()));

  async function handleGenerate() {
    setError("");
    setStep("generating");
    try {
      let docId: string;
      if (mode === "pdf") {
        if (!pdfFile) throw new Error("Please choose a PDF file.");
        docId = (await quizApi.uploadPdf(pdfFile)).docId;
      } else {
        const text = notes.trim() || topic.trim();
        if (!text) throw new Error("Please enter some notes or a topic.");
        docId = (await quizApi.uploadText(text, topic.trim() || undefined)).docId;
      }
      const res = await generateOutputs(docId, selected, studentId);
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
    setNotes(lectureText ?? "");
    setTopic("");
    setPdfFile(null);
    setFileName("");
  }

  if (step === "results" && lessonId) {
    // Quiz was selected — hand straight off to the existing, parity-verified
    // quiz UI, with any artifacts shown above it.
    return (
      <div className="flex flex-col gap-6">
        <ArtifactView artifacts={artifacts} />
        <NotesQuizModal
          variant="page"
          resumeLessonId={lessonId}
          onClose={onClose}
        />
      </div>
    );
  }

  return (
    <div className="flex flex-col gap-5">
      {error && (
        <p className="text-sm text-rose-300 bg-rose-950/40 border border-rose-800/50 rounded-xl px-4 py-3">
          {error}
        </p>
      )}

      {step === "input" && (
        <>
          {!lectureText && (
            <div className="flex bg-zinc-800/80 border border-zinc-700/50 rounded-xl p-1 gap-1">
              {(["text", "pdf"] as InputMode[]).map((m) => (
                <button
                  key={m}
                  onClick={() => setMode(m)}
                  className={`flex-1 flex items-center justify-center gap-2 py-2.5 rounded-lg text-sm font-medium transition-colors ${
                    mode === m
                      ? "bg-indigo-600 text-white shadow-lg shadow-indigo-900/40"
                      : "text-zinc-400 hover:text-zinc-200"
                  }`}
                >
                  {m === "pdf" ? <Upload className="w-3.5 h-3.5" /> : <NotebookPen className="w-3.5 h-3.5" />}
                  {m === "pdf" ? "Upload PDF" : "Type notes / topic"}
                </button>
              ))}
            </div>
          )}

          {lectureText && (
            <p className="text-xs text-indigo-300 bg-indigo-950/30 border border-indigo-800/40 rounded-xl px-4 py-3">
              Using this lecture's transcript as your material — no upload needed.
            </p>
          )}

          {mode === "text" ? (
            <div className="flex flex-col gap-3">
              <div>
                <label className="text-xs font-medium text-zinc-500 mb-1.5 block uppercase tracking-wide">
                  Topic
                </label>
                <input
                  value={topic}
                  onChange={(e) => setTopic(e.target.value)}
                  placeholder="e.g. React hooks, OS scheduling, Binary Search Trees…"
                  className="w-full bg-zinc-800/60 border border-zinc-700/60 rounded-xl px-4 py-3 text-sm text-zinc-100 placeholder-zinc-600 outline-none focus:border-indigo-500/60 transition-colors"
                />
              </div>
              <div>
                <label className="text-xs font-medium text-zinc-500 mb-1.5 block uppercase tracking-wide">
                  Notes <span className="normal-case text-zinc-600 font-normal">(optional)</span>
                </label>
                <textarea
                  value={notes}
                  onChange={(e) => setNotes(e.target.value)}
                  rows={6}
                  placeholder="Paste your notes here…"
                  className="w-full bg-zinc-800/60 border border-zinc-700/60 rounded-xl px-4 py-3 text-sm text-zinc-100 placeholder-zinc-600 outline-none focus:border-indigo-500/60 transition-colors resize-none"
                />
              </div>
            </div>
          ) : (
            <div
              onClick={() => fileRef.current?.click()}
              className="border-2 border-dashed border-zinc-700 hover:border-indigo-500/50 rounded-xl p-10 text-center cursor-pointer transition-colors"
            >
              <Upload className="w-5 h-5 text-indigo-400 mx-auto mb-3" />
              {fileName ? (
                <p className="text-sm text-indigo-300 font-medium">{fileName}</p>
              ) : (
                <p className="text-sm font-medium text-zinc-300">Click to choose a PDF</p>
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

          <div>
            <p className="text-xs font-medium text-zinc-500 mb-2 uppercase tracking-wide">
              What should we make from it?
            </p>
            <div className="grid grid-cols-2 gap-2">
              {ALL_OUTPUTS.map((t) => {
                const on = selected.includes(t);
                const { label, blurb } = OUTPUT_LABELS[t];
                return (
                  <button
                    key={t}
                    onClick={() => toggle(t)}
                    aria-pressed={on}
                    className={`text-left rounded-xl border px-4 py-3 transition-colors ${
                      on
                        ? "border-indigo-500/60 bg-indigo-600/10"
                        : "border-zinc-700/60 bg-zinc-800/40 hover:border-zinc-600"
                    }`}
                  >
                    <div className="flex items-center gap-2">
                      <span
                        className={`w-4 h-4 rounded flex items-center justify-center flex-shrink-0 ${
                          on ? "bg-indigo-600" : "border border-zinc-600"
                        }`}
                      >
                        {on && <Check className="w-3 h-3 text-white" />}
                      </span>
                      <span className="text-sm font-semibold text-zinc-100">{label}</span>
                    </div>
                    <p className="text-xs text-zinc-500 mt-1 ml-6">{blurb}</p>
                  </button>
                );
              })}
            </div>
          </div>

          <button
            onClick={handleGenerate}
            disabled={!canSubmit}
            className="w-full flex items-center justify-center gap-2 bg-indigo-600 hover:bg-indigo-500 disabled:bg-zinc-800 disabled:text-zinc-600 text-white text-sm font-semibold rounded-xl py-3.5 transition-colors shadow-lg shadow-indigo-900/30"
          >
            <Sparkles className="w-4 h-4" />
            Generate {selected.length > 1 ? `${selected.length} things` : "it"}
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
          <ArtifactView artifacts={artifacts} />
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
