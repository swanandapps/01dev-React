import { useState } from "react";
import { BookOpen, Target, TrendingUp, Network, GraduationCap } from "lucide-react";
import { StudyGuideModal } from "./StudyGuideModal";
import { AdaptiveModal } from "./AdaptiveModal";
import { InsightModal } from "./InsightModal";
import { ConceptMapModal } from "./ConceptMapModal";
import { TutorModal } from "./TutorModal";
import type { Course } from "../../types/learn";

/**
 * The per-course AI tools as a row of buttons plus their modals:
 *   - Study Guide   (structured guide for the whole course)
 *   - Adaptive      (personalized practice that targets weak concepts)
 *   - My Progress   (how you're doing — quiz perf + rewatches + chat history)
 * Parents supply the surrounding card/layout so it can be reused.
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
  const [tool, setTool] = useState<"guide" | "adaptive" | "insight" | "map" | "tutor" | null>(null);
  const pad = size === "sm" ? "px-3 py-1.5 text-xs" : "px-4 py-2 text-sm";
  const icon = size === "sm" ? "w-3.5 h-3.5" : "w-4 h-4";

  return (
    <>
      <div className="flex flex-wrap items-center gap-2">
        <button
          onClick={() => setTool("tutor")}
          className={`flex items-center gap-1.5 font-medium text-white bg-indigo-600 hover:bg-indigo-500 rounded-lg transition-colors ${pad}`}
        >
          <GraduationCap className={icon} /> AI Tutor
        </button>
        <button
          onClick={() => setTool("guide")}
          className={`flex items-center gap-1.5 font-medium text-indigo-300 hover:text-indigo-200 bg-indigo-600/15 hover:bg-indigo-600/25 border border-indigo-500/30 rounded-lg transition-colors ${pad}`}
        >
          <BookOpen className={icon} /> Study Guide
        </button>
        <button
          onClick={() => setTool("adaptive")}
          className={`flex items-center gap-1.5 font-medium text-violet-300 hover:text-violet-200 bg-violet-600/15 hover:bg-violet-600/25 border border-violet-500/30 rounded-lg transition-colors ${pad}`}
        >
          <Target className={icon} /> Adaptive Quiz
        </button>
        <button
          onClick={() => setTool("map")}
          className={`flex items-center gap-1.5 font-medium text-cyan-300 hover:text-cyan-200 bg-cyan-600/15 hover:bg-cyan-600/25 border border-cyan-500/30 rounded-lg transition-colors ${pad}`}
        >
          <Network className={icon} /> Concept Map
        </button>
        <button
          onClick={() => setTool("insight")}
          className={`flex items-center gap-1.5 font-medium text-sky-300 hover:text-sky-200 bg-sky-600/15 hover:bg-sky-600/25 border border-sky-500/30 rounded-lg transition-colors ${pad}`}
        >
          <TrendingUp className={icon} /> My Progress
        </button>
      </div>

      {tool === "tutor" && <TutorModal course={course} userId={userId} onClose={() => setTool(null)} />}
      {tool === "guide" && <StudyGuideModal course={course} onClose={() => setTool(null)} />}
      {tool === "adaptive" && <AdaptiveModal course={course} userId={userId} onClose={() => setTool(null)} />}
      {tool === "map" && <ConceptMapModal course={course} userId={userId} onClose={() => setTool(null)} />}
      {tool === "insight" && <InsightModal course={course} userId={userId} onClose={() => setTool(null)} />}
    </>
  );
}
