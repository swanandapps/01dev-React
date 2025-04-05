import { Clock, BookOpen, ArrowRight } from "lucide-react";
import { useNavigate } from "react-router-dom";
import type { RagSourceCard as RagSourceCardType } from "../../types/rag";
import { RAG_COURSE_MAP } from "../../types/rag";

interface Props {
  source: RagSourceCardType;
}

const scoreColor = (score: number) => {
  if (score >= 0.7) return "text-emerald-400 bg-emerald-900/30";
  if (score >= 0.45) return "text-amber-400 bg-amber-900/30";
  return "text-zinc-400 bg-zinc-800";
};

export function RagSourceCard({ source }: Props) {
  const navigate = useNavigate();

  const handleClick = () => {
    const courseNumId = RAG_COURSE_MAP[source.course_id];
    if (courseNumId) {
      navigate(`/course/${courseNumId}?t=${source.start_time}`);
    }
  };

  return (
    <button
      onClick={handleClick}
      className="group text-left w-full bg-zinc-800/50 hover:bg-zinc-800 border border-zinc-700/60 hover:border-indigo-500/40 rounded-xl p-3.5 transition-all"
    >
      <div className="flex items-start justify-between gap-2 mb-2">
        <div className="flex items-center gap-1.5 min-w-0">
          <BookOpen className="w-3.5 h-3.5 text-indigo-400 flex-shrink-0" />
          <span className="text-xs text-indigo-400 font-medium truncate">{source.course_title}</span>
        </div>
        <span className={`text-xs font-medium px-2 py-0.5 rounded-full flex-shrink-0 ${scoreColor(source.score)}`}>
          {Math.round(source.score * 100)}%
        </span>
      </div>

      <p className="text-sm font-semibold text-zinc-200 leading-snug mb-1.5">{source.lecture_title}</p>

      <div className="flex items-center gap-1.5 mb-2">
        <Clock className="w-3.5 h-3.5 text-zinc-500" />
        <span className="text-xs text-zinc-400 font-mono">{source.timestamp}</span>
      </div>

      <p className="text-xs text-zinc-500 leading-relaxed line-clamp-2">{source.snippet}</p>

      <div className="flex items-center gap-1 mt-2 text-indigo-400 opacity-0 group-hover:opacity-100 transition-opacity">
        <span className="text-xs font-medium">Jump to lecture</span>
        <ArrowRight className="w-3.5 h-3.5" />
      </div>
    </button>
  );
}
