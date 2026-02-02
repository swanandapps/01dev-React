import { useState } from "react";
import { BookOpen, Dumbbell, Target } from "lucide-react";
import { StudyGuideModal } from "./StudyGuideModal";
import { QuizModal } from "./QuizModal";
import { AdaptiveModal } from "./AdaptiveModal";
import type { Course } from "../../types/learn";

/**
 * The per-course AI tools (Study Guide / Practice / Adaptive) as a row of
 * buttons plus their modals. Parents supply the surrounding card/layout so it
 * can be reused on the Course Details page and the dashboard.
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
  const [tool, setTool] = useState<"guide" | "quiz" | "adaptive" | null>(null);
  const pad = size === "sm" ? "px-3 py-1.5 text-xs" : "px-4 py-2 text-sm";
  const icon = size === "sm" ? "w-3.5 h-3.5" : "w-4 h-4";

  return (
    <>
      <div className="flex flex-wrap items-center gap-2">
        <button
          onClick={() => setTool("guide")}
          className={`flex items-center gap-1.5 font-medium text-indigo-300 hover:text-indigo-200 bg-indigo-600/15 hover:bg-indigo-600/25 border border-indigo-500/30 rounded-lg transition-colors ${pad}`}
        >
          <BookOpen className={icon} /> Study Guide
        </button>
        <button
          onClick={() => setTool("quiz")}
          className={`flex items-center gap-1.5 font-medium text-emerald-300 hover:text-emerald-200 bg-emerald-600/15 hover:bg-emerald-600/25 border border-emerald-500/30 rounded-lg transition-colors ${pad}`}
        >
          <Dumbbell className={icon} /> Practice Quiz
        </button>
        <button
          onClick={() => setTool("adaptive")}
          className={`flex items-center gap-1.5 font-medium text-violet-300 hover:text-violet-200 bg-violet-600/15 hover:bg-violet-600/25 border border-violet-500/30 rounded-lg transition-colors ${pad}`}
        >
          <Target className={icon} /> Adaptive
        </button>
      </div>

      {tool === "guide" && <StudyGuideModal course={course} onClose={() => setTool(null)} />}
      {tool === "quiz" && <QuizModal course={course} userId={userId} onClose={() => setTool(null)} />}
      {tool === "adaptive" && <AdaptiveModal course={course} userId={userId} onClose={() => setTool(null)} />}
    </>
  );
}
