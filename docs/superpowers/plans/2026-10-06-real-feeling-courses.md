# Real-Feeling Courses Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Every course other than Build a Custom Library gets a coherent curriculum (description, modules, chapters, lectures) and a realistic spoken-lecture transcript for every lecture, merged into the transcript seed and safe to boot in production.

**Architecture:** `frontend/src/data/tracks.ts` stays the curriculum source of truth and is exported to `backend/app/data/catalog.json`. Transcripts are written per course into committed staging files `backend/data/course_src/<slug>.json`, validated and merged into `backend/app/data/seed_transcripts.json` by `backend/scripts/build_course_transcripts.py`. Production boot embeds missing chunks in batches.

**Tech Stack:** TypeScript data module, Node 22 export script, Python 3.12 (pytest), OpenAI embeddings (prod only).

**Spec:** `docs/superpowers/specs/2026-10-06-real-feeling-courses-design.md`

## Global Constraints

- Work from `/Users/swanandkadam/Desktop/01dev-React-hermes/.worktrees/lab-phase0-1` (branch `in-course-tutor`). Never `git add -A`/`.`; never push; commit trailer `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>`. Never create `backend/.env` in the worktree.
- `custom-library` (id 2) is untouched: curriculum, transcripts (340 real chunks) and ids stay byte-identical.
- Curriculum edits only in `tracks.ts`; then `node frontend/scripts/export-catalog.mjs` (from repo root of the worktree). `backend/tests/test_catalog.py` drift check must pass.
- Course ids, slugs, prices, images, trailers, themes, `launched` unchanged. Lectures of courses without video keep `src: ""`; Programming Language's lectures currently point at a Custom Library video — set them to `""`.
- Lecture naming: chapters `Chapter N - <Name>`, lectures `N.M - <Title>`, contiguous from `1.1` within each course. 15–24 lectures per course.
- Demo-course anchors (exact titles, unchanged chapter number): javascript-deep-dive `4.1 - Prototype Inheritance` (Chapter 4), `5.1 - V8 Engine and Hidden Classes` (Chapter 5), `6.1 - The Event Loop and Microtasks` (Chapter 6); web-apis `2.2 - WebSocket Handshake` (Chapter 2), `3.1 - Long-Polling vs WebSockets` (Chapter 3); react-perf `3.2 - Memoization and Computed State` (Chapter 3), `4.1 - React.memo and useCallback` (Chapter 4). Their hand-written passages (current seed chunks of those lectures) are reused **verbatim** inside the new transcripts.
- Transcript chunk shape = `TranscriptChunk` (`backend/app/models.py`): `chunk_id=<lecture_id>-<n>`, `course_id=<slug>`, `course_title=<exact course title>`, `lecture_id=<slug>-<chapterIdx>-<subIdx>` (0-indexed by position in tracks.ts), `lecture_title=<exact lecture name>`, `text`, `start_time`, `end_time` (whole seconds, contiguous from 0, each passage 45–75 s), `embedding=[]`. Lecture length 4–12 min; ~120–160 words per minute of passage.
- Voice: spoken instructor narration (first person, conversational, why-before-how, narrates code being typed, references previous/next lecture, one running example project per course). No markdown, bullets, headings or code fences in `text`; inline code words are fine.
- Tests never touch the real DB or OpenAI (`backend/tests/conftest.py` guard). Full suite: `bash backend/scripts/run_tests.sh`.

## Review Focus

1. A tracks.ts lecture with no transcript (Ask/player search silently has nothing) — pinned by `test_every_lecture_has_a_transcript` (Task 6).
2. A transcript `lecture_title` that differs from tracks.ts by a backtick/space — the player jump and suggest links fail to resolve — pinned by the validator's exact-title check (Task 2).
3. Demo question banks quoting text no longer in the seed — pinned by the validator's verbatim-anchor check (Task 2) and `test_demo_seed` (Task 6).
4. Production first boot with ~1,000+ new chunks — pinned by the batch-embedding test (Task 1).
5. `custom-library` accidentally changed by a merge — pinned by the validator's untouched-course check (Task 2).

## File Structure

- Modify `backend/app/services/vector_store.py` — batch the boot embedding of missing chunks.
- Create `backend/scripts/build_course_transcripts.py` — validate staging files, merge into seed.
- Create `backend/tests/test_build_course_transcripts.py`, `backend/tests/test_vector_store_batch.py`.
- Modify `frontend/src/data/tracks.ts`, regenerate `backend/app/data/catalog.json`.
- Create `backend/data/course_src/<slug>.json` ×9 (staging; committed).
- Modify `backend/app/data/seed_transcripts.json`, `backend/app/eval/golden_set.json`.
- Create `backend/tests/test_course_coverage.py`.

---

### Task 1: Batch the boot embedding

**Files:** Modify `backend/app/services/vector_store.py` (pgvector init that embeds chunks missing from `rag_chunks`, ~lines 70–125); Test `backend/tests/test_vector_store_batch.py`.

- [ ] Read the init path. Today it embeds and inserts missing chunks one at a time, and falls back to in-memory embedding on failure.
- [ ] Write failing tests with a stubbed embedding client and a stubbed pool/connection (follow existing vector_store tests' stubbing if any; never the real DB/OpenAI):
  - 250 missing chunks → 3 `embeddings.create` calls with inputs of ≤100 texts, in chunk order, and all 250 rows inserted (an executemany or batched inserts);
  - a failure on batch 2 keeps batch 1's rows and triggers the existing fallback;
  - zero missing chunks → no embed calls.
- [ ] Implement: `EMBED_BATCH = 100`; embed missing texts in batches via the embedding service's batch-capable call (add `embed_many(texts) -> list[list[float]]` to `backend/app/services/embeddings.py` if absent, using one `embeddings.create(input=[...])` per batch and the local fallback when OpenAI is off); insert per batch.
- [ ] `bash backend/scripts/run_tests.sh` → ALL PASSED. Commit `perf(vector-store): embed missing chunks in batches at boot`.

### Task 2: Validator + merge script

**Files:** Create `backend/scripts/build_course_transcripts.py`, `backend/tests/test_build_course_transcripts.py`.

**Interfaces — Produces:**
- `load_curriculum() -> dict[slug, {"title": str, "lectures": [(lecture_id, lecture_title)]}]` — parsed from `backend/app/data/catalog.json` (chapters/subchapters, position-based ids), excluding `custom-library`.
- `validate_course(slug, chunks, curriculum, anchors) -> list[str]` (empty = valid). Checks: every chunk's `course_id`/`course_title` exact; `lecture_id`/`lecture_title` pair exists in the curriculum (exact title match); every curriculum lecture has ≥ 1 chunk; `chunk_id` = `<lecture_id>-<n>` contiguous from 0; times whole ints, first passage starts at 0, contiguous (`start == prev end`), each 45–75 s except the last passage may be 20–75 s; lecture total 240–720 s; words-per-minute per passage 100–180; no markdown (`#`, ``` ``` ```, leading `- `/`* `, `**`); no two passages with identical text; `embedding == []`; for demo anchors every anchor passage text appears verbatim in some chunk of the matching lecture.
- `anchors()` — read the CURRENT seed's hand-written chunks for the 7 demo-anchor lectures (ids `js-deep-4-1*`, `js-deep-5-1*`, `js-deep-6-1*`, `web-apis-2-2*`, `web-apis-3-1*`, `react-perf-3-2*`, `react-perf-4-1*`) keyed by lecture title — and snapshot them to `backend/data/course_src/_anchors.json` on first run so they survive the merge.
- CLI: `python scripts/build_course_transcripts.py --check [slug…]` (validate staging files, print problems, exit 1 if any) and `--merge` (validate all 9; refuse unless all valid; write seed = custom-library chunks unchanged + all staging chunks, ordered by course order in catalog then lecture position; `json.dumps(indent=2)` + trailing newline like today).
- [ ] TDD each check with tiny fixtures (a fake curriculum of 2 lectures). Include: missing lecture, title off by a backtick, gap in times, passage 90 s, markdown bullet, missing anchor text, custom-library untouched by merge, merge refuses when any course invalid, merge idempotent.
- [ ] Run `--snapshot-anchors` (or first `--check`) now to write `_anchors.json` from the current seed; commit it.
- [ ] Full suite → ALL PASSED. Commit `feat(courses): transcript validator and seed merge`.

### Task 3: Curriculum rewrite (USER CHECKPOINT)

**Files:** Modify `frontend/src/data/tracks.ts`; regenerate `backend/app/data/catalog.json`; write a human-readable summary to `.superpowers/sdd/2026-10-06-real-feeling-courses/curriculum-review.md`.

- [ ] For each course except custom-library, make description, modules, chapters and lectures coherent per the spec §3.1 and Global Constraints:
  - **programming-language**: new ~18-lecture curriculum (history → human vs programming languages → syntax & grammar → language components → processors → compilers/interpreters/transpilers → design a grammar → lexical analysis → AST → interpreting the AST → wrap-up). Modules map to chapter groups. Rewrite the description to match. Lecture `src: ""`.
  - **product-engineering**: keep its 6 chapters/18 lectures; write a specific description; realign its 3 modules (titles + descriptions) to its chapter groups.
  - **javascript-deep-dive, web-apis, react-perf**: expand to 15–18 lectures around the anchors (anchors keep exact title and chapter number); new chapters before/between/after; modules updated to cover the new chapters (keep existing module titles if still accurate); description updated if it no longer fits; `learnings` aligned. Concepts in `backend/app/data/demo/taxonomy.json` for each course must each be covered by some lecture title or module.
  - **state-management, web-framework, js-engine, real-time**: check every description/module/chapter/lecture for contradictions or copy-paste; fix text only where wrong.
- [ ] `node frontend/scripts/export-catalog.mjs`; `cd frontend && npx tsc -b && npm run build`; `bash backend/scripts/run_tests.sh` (test_catalog drift + demo seed must pass).
- [ ] Write `curriculum-review.md`: per course, description, modules, and the full chapter/lecture outline, with a one-line note of what changed. Commit `feat(courses): coherent curricula for every course`.
- [ ] **STOP: the controller shows curriculum-review.md to the user and waits for approval before Task 4.**

### Task 4: Transcripts, one course per subagent (×9)

**Files:** Create `backend/data/course_src/<slug>.json` (a JSON array of chunks).

For each slug in: product-engineering, state-management, web-framework, js-engine, real-time, programming-language, javascript-deep-dive, web-apis, react-perf:
- [ ] Read the course's approved outline from `catalog.json` and the style constraints above. Pick one running example project for the course and keep names consistent.
- [ ] Write every lecture's transcript as passages, lecture by lecture, appending to the staging file as you go (never hold more than one lecture unwritten). For anchor lectures, place each anchor passage verbatim at a natural point and write the surrounding passages to flow into and out of it.
- [ ] `cd backend && .venv/bin/python scripts/build_course_transcripts.py --check <slug>` → no problems.
- [ ] Commit `content(<slug>): lecture transcripts`.

### Task 5: Merge + dependents

- [ ] `.venv/bin/python scripts/build_course_transcripts.py --check` (all 9) → clean; then `--merge`.
- [ ] Remap `backend/app/eval/golden_set.json` gold chunk ids that pointed at removed hand-written chunks to the new chunks containing the same anchor text (script it; assert every gold id exists in the seed).
- [ ] `backend/app/data/demo/question_banks.json`: every `lecture` value must exist as a `lecture_title` in the seed for that course (anchors keep their titles, so expect no change; fix any that differ).
- [ ] Full suite → ALL PASSED. Commit `content: merge course transcripts into seed`.

### Task 6: Coverage test + verification

- [ ] Create `backend/tests/test_course_coverage.py::test_every_lecture_has_a_transcript` — every catalog lecture of every course has ≥ 1 seed chunk, and chunk lecture_titles all exist in the catalog.
- [ ] Fold in: grounding prompt "links are shown under the answer" → "may be shown"; `_suggest_moments` dedupe on `_norm(title)`.
- [ ] Real-model checks (key inline, `DATABASE_URL=` blank): `scripts/demo_check.py --full --enroll 9,11` (Ask 7/7) and `scripts/demo_check.py --player` (custom-library cases unchanged). Report any Ask answer that changed course/case.
- [ ] Full suite + frontend build. Commit.
