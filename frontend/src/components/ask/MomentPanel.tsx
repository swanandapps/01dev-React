import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { Play, X, ListChecks } from "lucide-react";
import tracks from "../../data/tracks";
import { getLabTopics, getLectureMoments } from "../../lib/learnApi";
import type { LectureMoment, TopicLecture } from "../../lib/learnApi";
import { RAG_COURSE_MAP } from "../../types/rag";
import type { RagSourceCard } from "../../types/rag";
import { STATUS_LABEL } from "../lab/topicBits";

const mmss = (t: number) => `${Math.floor(t / 60)}:${String(Math.floor(t % 60)).padStart(2, "0")}`;

/** Ask page: the course moment an answer points to — preview, the instructor's words, the lecture's key moments
 *  with this one highlighted, the student's Lab status for the lecture, and the way into the player. */
export function MomentPanel({ card, onClose, onQuiz }: { card: RagSourceCard; onClose: () => void; onQuiz: () => void }) {
  const navigate = useNavigate();
  const [moments, setMoments] = useState<LectureMoment[]>([]);
  const [status, setStatus] = useState<TopicLecture | null>(null);

  const courseId = RAG_COURSE_MAP[card.course_id];
  const track = tracks.find((t) => t.id === courseId);
  const chapterName = card.chapter != null ? track?.courseContent[card.chapter]?.name : undefined;
  const url = card.url || (courseId ? `/course/${courseId}?t=${Math.floor(card.start_time)}` : null);

  useEffect(() => {
    let cancelled = false;
    setMoments([]);
    setStatus(null);
    getLectureMoments(card.course_id, card.lecture_title).then((m) => { if (!cancelled) setMoments(m); }).catch(() => {});
    getLabTopics()
      .then((d) => {
        if (cancelled) return;
        const lec = d.courses.find((c) => c.slug === card.course_id)
          ?.topics.flatMap((t) => t.lectures).find((l) => l.title === card.lecture_title);
        setStatus(lec ?? null);
      })
      .catch(() => {});
    return () => { cancelled = true; };
  }, [card.course_id, card.lecture_title]);

  const here = moments.reduce((best, m, i) => (m.start_time <= card.start_time ? i : best), -1);

  return (
    <aside aria-label="From your course" className="h-full flex flex-col gap-5 p-6 overflow-y-auto">
      <div className="flex items-center justify-between">
        <span className="text-[11px] font-extrabold tracking-widest text-violet-300">FROM YOUR COURSE</span>
        <button onClick={onClose} aria-label="Close panel" className="w-8 h-8 rounded-lg text-zinc-500 hover:text-zinc-200 hover:bg-zinc-800 flex items-center justify-center">
          <X className="w-4 h-4" />
        </button>
      </div>

      <button onClick={() => url && navigate(url)} disabled={!url}
              className="relative aspect-video rounded-2xl bg-zinc-800/80 border border-zinc-700 flex items-center justify-center group">
        <span className="w-14 h-14 rounded-full bg-white/90 group-hover:bg-white flex items-center justify-center">
          <Play className="w-6 h-6 text-zinc-950 fill-zinc-950 ml-0.5" />
        </span>
        <span className="absolute bottom-3 left-3 text-xs text-white bg-black/60 rounded-md px-2 py-1">Opens at {mmss(card.start_time)}</span>
      </button>

      <div className="flex flex-col gap-1">
        <h2 className="text-lg font-extrabold text-zinc-50 leading-snug">{card.lecture_title}</h2>
        <p className="text-[13px] text-zinc-400">
          {card.course_title}{chapterName ? ` · ${chapterName}` : ""}
        </p>
      </div>

      {card.snippet && (
        <blockquote className="border-l-[3px] border-violet-500 pl-3.5 py-1 text-sm leading-relaxed text-zinc-300">
          “{card.snippet.replace(/…$/, "")}…”
        </blockquote>
      )}

      {moments.length > 0 && (
        <section className="flex flex-col gap-1">
          <h3 className="text-[11px] font-extrabold tracking-widest text-zinc-400 mb-1">IN THIS LECTURE</h3>
          {moments.map((m, i) => (
            <button key={m.start_time}
                    onClick={() => courseId && navigate(`/course/${courseId}?chapter=${card.chapter ?? 0}&sub=${card.sub ?? 0}&t=${m.start_time}`)}
                    className={`flex gap-3 text-left rounded-lg px-2.5 py-1.5 text-[13px] transition-colors ${
                      i === here ? "bg-violet-500/15 text-violet-50" : "text-zinc-400 hover:bg-zinc-800/70 hover:text-zinc-200"}`}>
              <span className={`font-mono text-xs w-9 flex-shrink-0 pt-0.5 ${i === here ? "text-violet-300" : "text-zinc-500"}`}>{mmss(m.start_time)}</span>
              <span className="leading-snug line-clamp-2">{m.summary}</span>
            </button>
          ))}
        </section>
      )}

      <div className="mt-auto flex flex-col gap-2.5">
        {status && (
          <p className="text-[13px] text-teal-200 bg-teal-950/40 border border-teal-900 rounded-xl px-3.5 py-2.5">
            In your Lab: this lecture is <strong>{STATUS_LABEL[status.status]}</strong>
            {status.total ? ` (${status.right} of ${status.total} right)` : ""}.
          </p>
        )}
        <div className="flex gap-2">
          <button onClick={() => url && navigate(url)} disabled={!url}
                  className="flex-1 bg-violet-600 hover:bg-violet-500 text-white text-sm font-bold rounded-xl py-2.5">
            Open in player
          </button>
          <button onClick={onQuiz}
                  className="flex items-center gap-1.5 border border-teal-800 text-teal-200 hover:bg-teal-900/40 text-sm font-semibold rounded-xl px-3.5">
            <ListChecks className="w-4 h-4" /> Quiz me
          </button>
        </div>
      </div>
    </aside>
  );
}
