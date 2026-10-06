import type { Chapter } from "../data/tracks";

export interface LecturePosition {
  chapter: number;
  sub: number;
}

/** Same loose comparison as the backend's course_lookup._norm: no backticks, collapsed whitespace, case-insensitive. */
export function normaliseLectureTitle(title: string): string {
  return title.replace(/`/g, "").split(/\s+/).filter(Boolean).join(" ").toLowerCase();
}

/** Position of the lecture whose name matches `title`, or null (never a partial match). */
export function findLecture(chapters: Chapter[], title: string): LecturePosition | null {
  const want = normaliseLectureTitle(title);
  if (!want) return null;
  for (let c = 0; c < chapters.length; c++) {
    const subs = chapters[c].subchapters;
    for (let s = 0; s < subs.length; s++) {
      if (normaliseLectureTitle(subs[s].name) === want) return { chapter: c, sub: s };
    }
  }
  return null;
}

/** Where the tutor's jump lands, or null: unknown title or a locked chapter → no jump, no link. */
export function resolveJump(
  chapters: Chapter[],
  title: string,
  isLocked: (chapter: number) => boolean,
): LecturePosition | null {
  const pos = findLecture(chapters, title);
  return pos && !isLocked(pos.chapter) ? pos : null;
}

/** 200 → "03:20". */
export function formatTimestamp(seconds: number): string {
  const s = Math.max(0, Math.floor(seconds));
  return `${String(Math.floor(s / 60)).padStart(2, "0")}:${String(s % 60).padStart(2, "0")}`;
}
