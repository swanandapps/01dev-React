import type { LabTopic, LabTopicsResponse, LectureStatus } from "../../lib/learnApi";
import { viewedLectures } from "../../lib/learnApi";

export const STATUS_LABEL: Record<LectureStatus, string> = { solid: "solid", shaky: "shaky", not_tried: "not tried" };

export const STATUS_CHIP: Record<LectureStatus, string> = {
  solid: "bg-green-950/60 border-green-800 text-green-200",
  shaky: "bg-amber-950/50 border-amber-800 text-amber-200",
  not_tried: "bg-zinc-900 border-zinc-700 text-zinc-300",
};

export const STATUS_DOT: Record<LectureStatus, string> = {
  solid: "bg-green-500",
  shaky: "bg-amber-500",
  not_tried: "bg-zinc-600",
};

/** Solid / shaky / not tried as one stacked bar. */
export function TopicBar({ topic, className = "" }: { topic: LabTopic; className?: string }) {
  const n = topic.lectures.length || 1;
  return (
    <span className={`h-2 rounded-full bg-zinc-800 flex overflow-hidden ${className}`} aria-hidden="true">
      <span className="bg-green-500" style={{ width: `${(100 * topic.solid) / n}%` }} />
      <span className="bg-amber-500" style={{ width: `${(100 * topic.shaky) / n}%` }} />
    </span>
  );
}

/** "Coming up in your course": the first topic after the furthest chapter you've opened that isn't all solid. */
export function comingUp(data: LabTopicsResponse): { slug: string; topic: number } | null {
  const viewed = viewedLectures();
  for (const c of data.courses) {
    let furthest = -1;
    c.topics.forEach((t) => { if (t.lectures.some((l) => viewed.has(l.title))) furthest = t.index; });
    const next = c.topics.find((t) => t.index > furthest && t.solid < t.lectures.length);
    if (next) return { slug: c.slug, topic: next.index };
  }
  return null;
}

/** The lectures a topic session will ask about: shaky (weakest first), then not tried, then solid — max 3. */
export function needsWork(topic: LabTopic, max = 3) {
  const order: Record<LectureStatus, number> = { shaky: 0, not_tried: 1, solid: 2 };
  return [...topic.lectures]
    .sort((a, b) => order[a.status] - order[b.status]
      || (a.total ? a.right / a.total : 0) - (b.total ? b.right / b.total : 0) || a.sub - b.sub)
    .slice(0, max);
}
