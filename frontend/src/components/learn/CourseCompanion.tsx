import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { BookOpen, Target, TrendingUp, GraduationCap, Lock, NotebookPen } from "lucide-react";
import { StudyGuideModal } from "./StudyGuideModal";
import { AdaptiveModal } from "./AdaptiveModal";
import { InsightModal } from "./InsightModal";
import { TutorModal } from "./TutorModal";
import { NotesQuizModal } from "./NotesQuizModal";
import { useUserSessionStore } from "../../store/userSession";
import type { Course } from "../../types/learn";

type Tool = "guide" | "adaptive" | "insight" | "tutor" | "notes";

/**
 * The per-course AI tools as a row of buttons plus their modals. Tools require
 * sign-in: signed-out users see the buttons (a glimpse) but are sent to sign-in.
 */
export function CourseCompanion({
  course,
  userId,
  size = "md",
}: {
  course: Course;
  userId: string;
  size?: "sm" | "md";
}) {
  const [tool, setTool] = useState<Tool | null>(null);
  const navigate = useNavigate();
  const isUserLoggedIn = useUserSessionStore((s) => s.isUserLoggedIn);

  const pad = size === "sm" ? "px-3 py-1.5 text-xs" : "px-4 py-2 text-sm";
  const icon = size === "sm" ? "w-3.5 h-3.5" : "w-4 h-4";

  const open = (t: Tool) => (isUserLoggedIn ? setTool(t) : navigate("/signin"));

  return (
    <>
      <div className="flex flex-wrap items-center gap-2">
        <button
          onClick={() => open("tutor")}
          className={`flex items-center gap-1.5 font-medium text-white bg-indigo-600 hover:bg-indigo-500 rounded-lg transition-colors ${pad}`}
        >
          <GraduationCap className={icon} /> AI Tutor
        </button>
        <button
          onClick={() => open("guide")}
          className={`flex items-center gap-1.5 font-medium text-indigo-300 hover:text-indigo-200 bg-indigo-600/15 hover:bg-indigo-600/25 border border-indigo-500/30 rounded-lg transition-colors ${pad}`}
        >
          <BookOpen className={icon} /> Study Guide
        </button>
        <button
          onClick={() => open("adaptive")}
          className={`flex items-center gap-1.5 font-medium text-violet-300 hover:text-violet-200 bg-violet-600/15 hover:bg-violet-600/25 border border-violet-500/30 rounded-lg transition-colors ${pad}`}
        >
          <Target className={icon} /> Adaptive Quiz
        </button>
        <button
          onClick={() => open("insight")}
          className={`flex items-center gap-1.5 font-medium text-sky-300 hover:text-sky-200 bg-sky-600/15 hover:bg-sky-600/25 border border-sky-500/30 rounded-lg transition-colors ${pad}`}
        >
          <TrendingUp className={icon} /> My Progress
        </button>
        <button
          onClick={() => open("notes")}
          className={`flex items-center gap-1.5 font-medium text-teal-300 hover:text-teal-200 bg-teal-600/15 hover:bg-teal-600/25 border border-teal-500/30 rounded-lg transition-colors ${pad}`}
        >
          <NotebookPen className={icon} /> QuizMe
        </button>
      </div>

      {!isUserLoggedIn && (
        <p className="flex items-center gap-1.5 text-xs text-zinc-500 mt-2.5">
          <Lock className="w-3 h-3" />
          Sign in to use the AI tools — free with your Google account.
        </p>
      )}

      {tool === "tutor" && <TutorModal course={course} userId={userId} onClose={() => setTool(null)} />}
      {tool === "guide" && <StudyGuideModal course={course} onClose={() => setTool(null)} />}
      {tool === "adaptive" && <AdaptiveModal course={course} userId={userId} onClose={() => setTool(null)} />}
      {tool === "insight" && <InsightModal course={course} userId={userId} onClose={() => setTool(null)} />}
      {tool === "notes" && <NotesQuizModal onClose={() => setTool(null)} />}
    </>
  );
}
