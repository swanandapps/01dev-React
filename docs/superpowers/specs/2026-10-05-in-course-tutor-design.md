# In-Course Tutor — Course-First Answers, Real Transcripts, "Take Me There" — Design

**Date:** 2026-10-05 · **Status:** approved in conversation, spec under review
**Branch:** `in-course-tutor` (from `lab-phase2`, carries two unshipped fixes: 2ac9ca3, 4b02cc1)

## 1. Why

In a live demo the presenter sits inside one course (Build a Custom Library — the
npm-publishing course) and talks to the in-player AI tutor. Today that tutor:

- searches every course, so a vague question can surface another course and append a
  "you're not enrolled in X" pointer (seen live: "Give me an example" in 1.1 → Product
  Engineering Essentials);
- has transcripts for only 3 hand-written snippets of this course (all lecture 8.1), so
  it cannot find the lecture where the package is actually published (11.1 "Publishing
  using `np`");
- cannot move the video: "take me to where you write the publish commands" can at best
  produce text.

## 2. Requirements (from the user)

1. **The current course comes first.** In the player, every search, every bit of
   grounding and every answer comes from the course being watched. Jumping to another
   course is bad.
2. **Off-topic questions** (event loop while watching the npm course): if this course has
   a genuinely related part, cite it; either way give a solid general answer, phrased for
   this student (their tone and level).
3. **"Take me to …"** finds the moment in this course and the player jumps there by
   itself — no click needed. A clickable fallback is acceptable alongside.
4. Must work in the live demo of Build a Custom Library.

**Assumptions agreed:** the player tutor never mentions or links other courses (the Ask
page keeps its cross-course pointer behaviour); jump to the exact second when known,
else the lecture start; "personalised" = match tone/level from the student's own
messages and stored memory, no new profile system.

## 3. Design

### 3.1 Real transcripts for Build a Custom Library

New script `backend/scripts/transcribe_course.py <course-slug>` — run locally, once:

1. Read the course's lectures from `frontend/src/data/tracks.ts` (chapter name,
   subchapter name, encoded `src`); decode `src` with the same XOR+base64 scheme as
   `frontend/src/lib/videoDecoder.ts`.
2. Download each video, extract mono 16 kHz audio with ffmpeg (keeps files under the
   25 MB API limit), transcribe with OpenAI `whisper-1` (`verbose_json`, segment
   timestamps) using the existing `OPENAI_API_KEY` from `backend/.env`. No new account.
3. Group segments into passages of ~45–75 s (break on segment boundaries), each with
   `start_time`/`end_time` in whole seconds.
4. Emit chunks in the existing `TranscriptChunk` shape: `course_id="custom-library"`,
   `course_title`, `lecture_id="custom-library-<chapterIdx>-<subIdx>"` (position-based,
   0-indexed — the titles' own numbering has gaps, e.g. 6.2 → 6.5), `lecture_title` = the
   subchapter name exactly as in tracks.ts, `chunk_id = <lecture_id>-<n>`.
5. Write to a review file first; after a spot-check (11.1 contains the `np` publish
   commands, timestamps monotonic, no empty lectures unexplained), merge into
   `backend/app/data/seed_transcripts.json`, replacing the 3 hand-written 8.1 snippets.

Cache downloaded audio and raw Whisper output under a git-ignored dir so re-runs are
free. Lectures whose video fails to download/transcribe are reported, not fatal.

**Production pickup:** chunk metadata always comes from the seed file; `rag_chunks`
only caches embeddings by `chunk_id`, and missing ones are embedded on startup. Stale
rows for removed chunk ids are never loaded, so no cleanup is required. Backend deploy
ships the new seed.

### 3.2 Player tutor is course-first

`ChatScope` gains `in_player: bool = False`, set to True only by the player route
(`/api/ai/tutor/stream`). The Ask page can also send a course slug (its course filter),
so "a course is set" is NOT the trigger. With `in_player`, `course_lookup` runs in
in-course mode; without it, behaviour is unchanged:

- Transcript search is restricted to chunks of the current course (with the lecture
  title still prefixed to the transcript query — 4b02cc1). No catalog search.
- Outcome, from the best in-course score:
  - **IN_COURSE_MATCH** (≥ `TRANSCRIPT_THRESHOLD`): answer from the excerpt, cite the
    lecture + timestamp.
  - **IN_COURSE_RELATED** (≥ a lower `RELATED_THRESHOLD`, calibrated on real
    transcripts; start at 0.40): general answer first, then "this course touches on it
    in <lecture> at <mm:ss>".
  - **IN_COURSE_NONE**: general answer only. The course-outline fallback (4b02cc1) still
    applies for vague in-lecture questions.
- Never another course: no cross-course hits in COURSE FACTS, and `_missing_pointer` is
  never applied in the player.
- Grounding prompt: in-course rules for the three outcomes; "match the student's tone,
  vocabulary and level from their messages and STUDENT MEMORY".

### 3.3 "Take me to …" — `find_moment` tool + `navigate` event

- New tutor tool `find_moment(what: str)` (`tutor_agent.py`), available only when
  `scope.in_player` (the tool list is chosen per turn). The model calls it when the student asks to be taken /
  shown / jumped to a part, rewriting the request into a search phrase.
- The tool searches the current course's transcript chunks only, returns the best
  passage `{lecture_title, start_time, end_time, excerpt, score}` or `{found: false}`
  below `RELATED_THRESHOLD`. It can only return a real chunk's lecture and time — the
  model cannot invent timestamps.
- The pipeline turns a successful `find_moment` call into an SSE event
  `{"type": "navigate", "course_slug", "lecture_title", "start_time"}` emitted before
  `done` (once per turn; last call wins).
- Frontend: `learnApi` stream parser handles `navigate` → `PlayerTutor` `onNavigate`
  prop → `CoursePlayerPage` finds the chapter/subchapter whose name matches
  `lecture_title` (normalised: case, backticks, whitespace), switches to it, seeks to
  `start_time`, plays. The tutor message also shows a "Jump to <lecture> · mm:ss"
  link that does the same (fallback if autoplay is blocked). Unknown lecture title →
  no jump, link hidden, answer text still says where it is.

## 4. Out of scope

Other courses' transcripts (same script later); Ask-page behaviour; Hermes/Telegram;
a student profile/personality system; the free-enrollment hole (tracked separately).

## 5. Testing

- Unit (no real DB/OpenAI — conftest guard): in-course lookup filters other courses and
  skips the catalog; the three outcomes by score; no pointer in player scope; Ask scope
  unchanged, including Ask with a course filter; `find_moment` returns only in-course chunks / `found: false`; pipeline emits
  exactly one `navigate` event from a tool result; transcript chunker (segment grouping,
  ids, monotonic times) on fixture Whisper output.
- Frontend: type-check + build; lecture-title matcher handles backticks/case.
- Real model, in-memory store, real transcripts: "take me to where you publish the npm
  package" → navigate to 11.1 at the right second; "how does the event loop work" in
  course 2 → general answer, no other course named; "give me an example" in 1.1;
  the 7 demo questions on the Ask page unchanged.
- Live, after deploy: in the browser on the01.dev, signed in, course 2 — the jump happens.

## 6. Order

Transcripts (3.1) first — the jump has nothing real to land on without them — then 3.2,
then 3.3, then deploy (backend, then frontend after the merge).
