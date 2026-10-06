# Real-Feeling Courses — Curricula + Lecture Transcripts for Every Course — Design

**Date:** 2026-10-06 · **Status:** decisions made in conversation; spec under review
**Branch:** `in-course-tutor`

## 1. Why

Build a Custom Library (`custom-library`) is the only recorded course; it now has real
Whisper transcripts. Every other course is seed data, and it shows:

- **Build a Programming Language** (`programming-language`, id 1): lecture titles copy-pasted
  from Build a Custom Library ("2.1 - Libraries: First Principles" ×5), module
  descriptions talking about `window` and libraries, 6 lectures total.
- **Product Engineering Essentials** (`product-engineering`, id 4): course description is a
  placeholder ("This is a 0.1% DEV track."); modules describe JS fundamentals, not its
  actual chapters (engineer mindset → production engineering).
- **JavaScript Deep Dive / Web APIs and Real-Time / React Performance Patterns** (ids 9, 10,
  11 — the demo account's courses): 2–3 lectures each, numbered from chapter 2–4 with
  nothing before them.
- **State Management / Web Framework / JS Engine / Real-Time** (5–8): sound outlines
  (21–24 lectures), no transcripts at all.

Goal (user): "imagine you're creating a proper course … the chapter, the title, the
sub-chapter, the content inside, the description all match … that should feel real …
for all the courses." Only `custom-library` will be shown in the live demo; the rest must
still hold up if anyone opens them or the tutor/Ask page draws on them.

## 2. Decisions (user, 2026-10-06)

1. **Fix + expand.** Rewrite Programming Language's curriculum; write Product Engineering's
   description and align its modules; grow courses 9/10/11 into full courses
   (~15–20 lectures each) **keeping their existing lectures** so the demo dashboard and
   question banks keep working. Then transcripts for every lecture.
2. **Claude subagents write the content** (no OpenAI spend), course by course, each checked
   against its outline.
3. `custom-library` is untouched (real course, real transcripts).

## 3. Design

### 3.1 Curriculum (source of truth: `frontend/src/data/tracks.ts` → `catalog.json`)

`tracks.ts` is the curriculum; `frontend/scripts/export-catalog.mjs` exports
`backend/app/data/catalog.json` and `tests/test_catalog.py` fails on drift. All curriculum
edits happen in `tracks.ts`, then the export is re-run.

Per course, the curriculum must be internally consistent:
- **Course description**: 2–4 sentences, specific to what the course builds/teaches.
- **Modules** (course-page cards): each module corresponds to a real chapter or chapter
  group, with a one-sentence description of that part — no copy-paste.
- **Chapters** `Chapter N - <name>` and **lectures** `N.M - <title>`, numbered contiguously
  from 1.1, in a teaching order that builds (intro → fundamentals → building → advanced →
  wrap-up). 15–24 lectures per course.
- Other `tracks.ts` fields (tags, learnings, duration, level, `src`, `launched`, ids,
  slugs, prices) stay as they are unless they contradict the new curriculum (e.g. a
  "what you'll learn" list) — then align their text only.

Course-specific rules:
- **programming-language (1)**: new curriculum built from its existing chapter themes
  (language history → human vs programming languages → syntax/grammar → language
  components → processors → compilers vs interpreters vs transpilers) plus its module
  themes (grammar design, lexical analysis, AST, interpreting an AST). ~18 lectures.
- **product-engineering (4)**: keep its 6 chapters / 18 lectures; write the description and
  realign the 3 modules to its chapters.
- **javascript-deep-dive (9), web-apis (10), react-perf (11)**: expand to ~15–18 lectures.
  The existing lectures keep their **exact titles and chapter positions** (9: 4.1, 5.1, 6.1;
  10: 2.2, 3.1; 11: 3.2, 4.1); new chapters/lectures are added before, between and after
  them so numbering is contiguous. The courses' fixed concept taxonomy
  (`backend/app/data/demo/taxonomy.json`) must be covered by the curriculum.
- **state-management, web-framework, js-engine, real-time (5–8)**: keep curricula; only fix
  text that contradicts itself.

### 3.2 Transcripts (`backend/app/data/seed_transcripts.json`)

Every lecture of every course except `custom-library` gets a transcript in the existing
`TranscriptChunk` shape:
- `lecture_id = <slug>-<chapterIdx>-<subIdx>` (position-based, 0-indexed — same scheme as
  custom-library), `chunk_id = <lecture_id>-<n>`, `lecture_title` exactly the tracks.ts
  lecture name, `course_title` exactly the course title, `embedding = []`.
- Passages ~45–75 s, contiguous whole-second timestamps from 0; lecture length 4–12 min
  (≈ 5–12 passages); ~130–150 spoken words per minute.
- **Voice**: a real instructor talking over a screen — first person, conversational,
  explains *why* before *how*, narrates code as it's typed ("so here I'll create a
  function called `tokenize`…"), refers back to earlier lectures and forward to the next
  one, occasional asides. No markdown, no bullet lists, no headings — it's speech.
- **Consistency**: each lecture covers what its title promises, in the order of the
  course; facts are technically correct; names/APIs consistent across a course (the
  same running example project per course).
- **Existing demo lectures (9/10/11)**: the hand-written passages
  (`js-deep-4-1/5-1/6-1`, `web-apis-2-2/3-1`, `react-perf-3-2/4-1`) are kept **verbatim**
  as passages inside the new, longer transcript of the same lecture (the question
  banks' explanations quote them). They get new position-based chunk ids;
  `backend/app/eval/golden_set.json` gold ids are remapped.

### 3.3 Production fit

- First boot embeds every new chunk (≈1,000+) into `rag_chunks`; today that happens one
  call at a time (~10 min of 502s). **Batch the boot embedding** (`vector_store`
  pgvector init: embed missing chunks in batches of ~100 per `embeddings.create`), keeping
  the partial-failure → in-memory fallback.
- Ask page: more transcripts mean more not-enrolled pointers to these (mostly
  unlaunched) courses — behaviour unchanged, flagged to the user.

## 4. Process

1. Curriculum task (one agent, all courses): edit `tracks.ts`, re-export catalog, keep
   existing demo lectures in place; output reviewed before any transcript is written.
2. Transcript tasks: one subagent per course writes `backend/data/course_src/<slug>.json`
   (staging, committed), lecture by lecture, from the approved curriculum.
3. A validator + merge script (`backend/scripts/build_course_transcripts.py`): schema,
   ids/titles exactly match tracks.ts, every lecture present, timings contiguous and in
   range, word-rate sane, verbatim passages present for demo lectures, no duplicate
   passages; merges all staging files + custom-library chunks into the seed.
4. Review per course (sampled reading for realism + correctness), batch-embedding change,
   golden-set remap, full suite, Ask demo questions, in-player custom-library checks
   unchanged.

## 5. Out of scope

`custom-library`; real videos for other courses; the `launched` flag; pricing; the
free-enrollment hole; Hermes/Telegram.

## 6. Testing

Validator unit tests on fixtures; `test_catalog` drift check; `test_demo_seed` (banks
reference lectures present in the seed); a test that every tracks.ts lecture of every
course has ≥ 1 chunk; batch-embedding unit test with a stubbed client; full suite;
`demo_check.py --full` (Ask 7/7) and `--player` (custom-library unchanged).
