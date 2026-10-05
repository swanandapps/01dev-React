# In-Course Tutor Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make the in-player AI tutor answer from the course being watched only (with real Whisper transcripts for Build a Custom Library) and let it move the video to the right lecture and second when the student says "take me to …".

**Architecture:** A one-off local script (`backend/scripts/transcribe_course.py`) turns the course videos into `TranscriptChunk` rows in `backend/app/data/seed_transcripts.json`. `ChatScope` gains `in_player`; when set (player route only), `course_lookup` searches only the current course's chunks and returns one of three new in-course outcomes, and the tutor agent gets a per-turn `find_moment` tool whose successful result the pipeline turns into one `navigate` SSE event. The frontend stream parser forwards `navigate` to `CoursePlayerPage`, which matches the lecture by normalised title, switches, seeks and plays, and the message shows a "Jump to …" link as fallback.

**Tech Stack:** Python 3.12 / FastAPI / LangChain tutor agent / OpenAI SDK 3.24.0 (`whisper-1`), ffmpeg; React 19 + TypeScript + Vite.

**Spec:** `docs/superpowers/specs/2026-10-05-in-course-tutor-design.md` (approved, binding — read it before any task).

## Global Constraints

- All commands run from the worktree root `/Users/swanandkadam/Desktop/01dev-React-hermes/.worktrees/lab-phase0-1` (branch `in-course-tutor`) unless a step says `cd backend` / `cd frontend`.
- Never `git add -A` / `git add .` — add the exact paths listed in each task. Every commit message ends with the trailer line `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>`. Never push.
- Tests never touch the real DB or real OpenAI: `backend/tests/conftest.py` fails any test that reaches `db.get_pool` or `EmbeddingService._openai_embed`. Stub stores/embeddings like the existing tests do. The transcription script's OpenAI/ffmpeg/download functions are never called from tests.
- Full backend suite: `bash backend/scripts/run_tests.sh` (must end `ALL PASSED`). Single backend file: `cd backend && .venv/bin/pytest tests/<file> -q`.
- Frontend verification: `cd frontend && npx tsc -b && npm run build`.
- Transcripts: OpenAI `whisper-1`, `response_format="verbose_json"`, `timestamp_granularities=["segment"]`, `OPENAI_API_KEY` from `backend/.env` (no new account). Audio: mono 16 kHz via ffmpeg, each upload < 25 MB (split by time with an offset if larger).
- Passages: ~45–75 s, broken only on Whisper segment boundaries, `start_time`/`end_time` in whole seconds.
- Chunk shape = existing `TranscriptChunk` (`backend/app/models.py`): `course_id="custom-library"`, `course_title="Build a Custom Library"`, `lecture_id="custom-library-<chapterIdx>-<subIdx>"` (position-based, 0-indexed — titles' own numbering has gaps, e.g. 6.2 → 6.5), `lecture_title` = the subchapter name exactly as in `frontend/src/data/tracks.ts`, `chunk_id = <lecture_id>-<n>`, `embedding=[]`.
- Downloaded audio and raw Whisper output are cached under a git-ignored dir (`backend/data/transcribe_cache/`). A lecture that fails to download/transcribe is reported, not fatal.
- The merged seed replaces the 3 hand-written `custom-library` 8.1 chunks (`custom-lib-8-1-a/b/c`); other courses' chunks are untouched.
- `ChatScope` gains `in_player: bool = False`, set to `True` only by the player route `/api/ai/tutor/stream`. A course slug on the scope (the Ask page's course filter) is NOT the trigger.
- In-player outcomes from the best in-course score: `IN_COURSE_MATCH` (≥ `TRANSCRIPT_THRESHOLD`), `IN_COURSE_RELATED` (≥ `RELATED_THRESHOLD`, start value `0.40`, calibrated on real transcripts), `IN_COURSE_NONE` (below). In player: no catalog search, no other-course chunk anywhere in COURSE FACTS, `_missing_pointer` never applied; the lecture title is still prefixed to the transcript query (4b02cc1) and the course-outline fallback still applies.
- Grounding prompt adds in-course rules for the three outcomes and: "match the student's tone, vocabulary and level from their messages and STUDENT MEMORY".
- Tool: `find_moment(what: str)`, bound only when `scope.in_player`. Returns `{lecture_title, start_time, end_time, excerpt, score}` from a real in-course chunk, or `{found: false}` below `RELATED_THRESHOLD`.
- SSE event, exact shape: `{"type": "navigate", "course_slug", "lecture_title", "start_time"}`, emitted before `done`, at most once per turn, last successful `find_moment` call wins.
- Frontend lecture match normalises case, backticks and whitespace. The message link text is `Jump to <lecture> · mm:ss`. Unknown lecture title → no jump, no link (answer text still says where).
- Ask page behaviour (with or without its course filter) is unchanged, and the existing Ask tests are not edited.
- Deploy is NOT part of this plan.

## Review Focus

Inputs the spec implies but does not spell out, most likely first. Each one has a pinning test in the task named.

1. **Vague in-lecture question that now hits the lecture's real transcript only weakly** ("give me an example" in 1.1 scoring IN_COURSE_RELATED) — must be answered about the current lecture, not as an off-topic general answer. Pinned: prompt rule + `test_prompt_has_the_in_course_cases_and_tone_matching` (Task C); real-model check "give me an example" (Task F).
2. **Player opened before any lecture is picked** (page sends the course title as `lecture`; the route blanks it) — still course-only search with the bare question, no in-lecture mode. Pinned: `test_player_with_no_lecture_selected_searches_the_bare_question_in_this_course` (Task C).
3. **"Take me to" a lecture in a chapter the student has not unlocked** — no jump and no link (the answer text still says where). Pinned: `resolveJump` assertions in `frontend/scripts/lectureMatch.check.ts` (Task E).
4. **`--merge` after only a trial `--only` run** — must refuse instead of shrinking the course to one lecture. Pinned: `test_merge_never_uses_a_partial_review` (Task A).
5. **`--merge` run twice** (executor re-runs a step) — same seed, no duplicated chunks. Pinned: `test_merge_into_seed_twice_is_idempotent` (Task A).

## File Structure

| File | Action | Responsibility |
|---|---|---|
| `backend/scripts/transcribe_course.py` | Create | CLI: read course lectures from `tracks.ts`, decode `src`, download → ffmpeg → whisper (thin I/O), group segments into passages, emit chunks to a review file, `--merge` into the seed. Pure functions are importable for tests. |
| `backend/tests/test_transcribe_course.py` | Create | Unit tests for the pure parts: tracks.ts parsing, `decode_video_url`, `group_segments`, `build_chunks`, `merge_into_seed`, audio-split plan. |
| `backend/tests/fixtures/whisper_verbose_sample.json` | Create | Fixture Whisper `verbose_json` output (segments with float start/end). |
| `backend/.gitignore` | Modify | Ignore `data/transcribe_cache/`. |
| `backend/app/data/seed_transcripts.json` | Modify (Task B, generated) | Real custom-library chunks replace `custom-lib-8-1-a/b/c`. |
| `backend/app/data/demo/question_banks.json`, `backend/app/eval/golden_set.json` | Modify (Task B) | Follow the real 8.1 title (with backticks) and the new 8.1 chunk ids. |
| `backend/scripts/calibrate_in_course.py` | Create (Task C) | Real-embedding scores on labelled custom-library questions → `RELATED_THRESHOLD`. |
| `backend/app/services/course_lookup.py` | Modify | `ChatScope.in_player`, three `IN_COURSE_*` cases, `RELATED_THRESHOLD`, in-course search path, `search_in_course` helper reused by the tool. |
| `backend/app/main.py` | Modify | Player route sets `in_player=True`. |
| `backend/app/services/chat_pipeline.py` | Modify | No pointer in player scope; pass scope to the agent; turn the `find_moment` result into one `navigate` event before `done`. |
| `backend/app/grounding/grounding_prompt.md` | Modify | In-course rules + tone/level matching. |
| `backend/app/services/tutor_agent.py` | Modify | `find_moment` tool, per-turn tool list (only when in player), navigate capture. |
| `backend/app/services/tool_descriptions.py` | Modify | `find_moment` description. |
| `backend/tests/test_course_lookup.py`, `test_chat_pipeline.py`, `test_grounding_prompt.py`, `test_tutor_agent.py`, `test_player_tutor_route.py`, `test_ask_chat_route.py` | Modify (append only) | New tests; existing tests untouched. |
| `frontend/src/lib/lectureMatch.ts` | Create | `normaliseLectureTitle`, `findLecture`, `resolveJump`, `formatTimestamp` — pure. |
| `frontend/scripts/lectureMatch.check.ts` | Create | Node (`--experimental-strip-types`) assertion script for the matcher. |
| `frontend/src/lib/learnApi.ts` | Modify | Parse `navigate` SSE event → `onNavigate`. |
| `frontend/src/components/learn/PlayerTutor.tsx` | Modify | `onNavigate` prop, auto-jump, "Jump to …" link on the message. |
| `frontend/src/pages/CoursePlayerPage.tsx` | Modify | Resolve lecture, switch chapter/sub, seek, play. |
| `backend/scripts/demo_check.py` | Modify (Task F) | `--player` mode: the three in-player real-model questions. |

Task order is the spec's (§6): A → B (real transcripts first — the jump needs something real to land on) → C → D → E → F. C's calibration step and all of F need B's data.

---

### Task A: Transcription script (pure parts unit-tested, thin I/O)

**Files:**
- Create: `backend/scripts/transcribe_course.py`
- Create: `backend/tests/test_transcribe_course.py`
- Create: `backend/tests/fixtures/whisper_verbose_sample.json`
- Modify: `backend/.gitignore` (append one line)

**Interfaces:**
- Consumes: `frontend/src/data/tracks.ts` (course `id: 2` → `courseContent: [{ name, subchapters: [{ name, src }] }]`, `src` XOR+base64 encoded with key `"thisisasecretofus"` exactly like `frontend/src/lib/videoDecoder.ts`), `backend/app/data/catalog.json` (list of `{id, slug, title, ...}`; `custom-library` is `id: 2`, title `Build a Custom Library`), OpenAI SDK 3.24.0 `client.audio.transcriptions.create(file=..., model="whisper-1", response_format="verbose_json", timestamp_granularities=["segment"], ...) -> TranscriptionVerbose` whose `.segments: Optional[List[TranscriptionSegment]]` each have `start: float`, `end: float`, `text: str`.
- Produces (module `scripts.transcribe_course`, importable from `backend/` because `pytest.ini` sets `pythonpath = .`):
  - `@dataclass(frozen=True) class Lecture: course_slug: str; chapter_idx: int; sub_idx: int; chapter_name: str; name: str; src: str` with property `lecture_id -> str` (= `f"{course_slug}-{chapter_idx}-{sub_idx}"`).
  - `decode_video_url(encoded: str) -> str`
  - `parse_course_lectures(tracks_src: str, track_id: int, course_slug: str) -> list[Lecture]`
  - `find_course(catalog: list[dict], course_slug: str) -> tuple[int, str]` (track id, title)
  - `group_segments(segments: list[dict], min_s: float = 45, max_s: float = 75) -> list[dict]` → passages `{"start": int, "end": int, "text": str}`
  - `build_lecture_chunks(course_title: str, lecture: Lecture, passages: list[dict]) -> list[dict]` (TranscriptChunk-shaped dicts, `embedding: []`)
  - `merge_into_seed(seed: list[dict], course_slug: str, new_chunks: list[dict]) -> list[dict]`
  - `plan_audio_parts(size_bytes: int, duration_s: float, limit_bytes: int = MAX_UPLOAD_BYTES) -> list[tuple[float, float]]`
  - `offset_segments(segments: list[dict], offset: float) -> list[dict]`
  - CLI: `.venv/bin/python scripts/transcribe_course.py <slug> [--only id1,id2] [--merge]` (run from `backend/`). Full run writes `backend/data/transcribe_cache/<slug>/review.json`; `--only` writes `review-partial.json` (never merged); `--merge` writes `review.json` into `backend/app/data/seed_transcripts.json` with `json.dumps(..., indent=2)` and no trailing newline (the file's current exact format — round-trip verified byte-identical).
  - Lecture of interest for later tasks: `11.1 - Publishing using \`np\`` is chapter index 10, sub index 0 → `lecture_id = "custom-library-10-0"`. `8.1 - The \`npm link\` command` → `custom-library-7-0`. The course has 34 lectures.

- [ ] **Step 1: Write the Whisper fixture**

Create `backend/tests/fixtures/whisper_verbose_sample.json` (the cached shape the script stores: just `start`/`end`/`text` per segment):

```json
[
  {"start": 0.0, "end": 12.4, "text": " Welcome back."},
  {"start": 12.4, "end": 25.0, "text": " In this lecture we publish our library."},
  {"start": 25.0, "end": 38.2, "text": " First install np globally."},
  {"start": 38.2, "end": 50.6, "text": " npm install --global np"},
  {"start": 50.6, "end": 70.0, "text": " Then log in with npm login."},
  {"start": 70.0, "end": 88.0, "text": "   "},
  {"start": 88.0, "end": 101.0, "text": " Run np in the project root and pick the version bump."},
  {"start": 101.0, "end": 190.0, "text": " A single very long segment that runs past the maximum on its own."},
  {"start": 190.0, "end": 200.0, "text": " Thanks for watching."}
]
```

- [ ] **Step 2: Write the failing tests**

Create `backend/tests/test_transcribe_course.py`:

```python
"""transcribe_course: the pure parts (no network, no ffmpeg, no OpenAI)."""
import base64
import json
from pathlib import Path

import pytest

from scripts import transcribe_course as tc

FIXTURE = Path(__file__).resolve().parent / "fixtures" / "whisper_verbose_sample.json"
REPO = Path(__file__).resolve().parents[2]
KEY = b"thisisasecretofus"


def _encode(url: str) -> str:
    raw = bytes(b ^ KEY[i % len(KEY)] for i, b in enumerate(url.encode("latin-1")))
    return base64.b64encode(raw).decode()


TRACKS_SNIPPET = '''
const tracks: Track[] = [
  {
    id: 1,
    title: "Other",
    courseContent: [
      { name: "Chapter 1 - Intro", subchapters: [{ name: "1.1 - Other", src: "https://x/1.mp4" }] },
    ],
    modules: [],
  },
  {
    id: 2,
    title: "Build a Custom Library",
    courseContent: [
      { name: "Chapter 1 - Introduction", subchapters: [
        { name: "1.1 - What is this course", src: "ENC_A" },
        { name: "1.2 - What will we build", src: "ENC_B" },
      ]},
      { name: "Chapter 11 - Publishing", subchapters: [
        { name: "11.1 - Publishing using `np`", src: "ENC_C" },
      ]},
    ],
    modules: [
      { id: 1, title: "Library: First Principles", src: "https://x/m.mp4" },
    ],
  },
];
'''


def test_decode_video_url_round_trips_the_frontend_scheme():
    url = "https://firebasestorage.googleapis.com/v0/b/x/o/CustomLibrary%2F11.1.mp4?alt=media"
    assert tc.decode_video_url(_encode(url)) == url


def test_parse_course_lectures_reads_only_the_requested_track_by_position():
    src = (TRACKS_SNIPPET.replace("ENC_A", _encode("https://v/a.mp4"))
           .replace("ENC_B", _encode("https://v/b.mp4"))
           .replace("ENC_C", _encode("https://v/c.mp4")))
    lectures = tc.parse_course_lectures(src, 2, "custom-library")
    assert [(l.chapter_idx, l.sub_idx, l.name) for l in lectures] == [
        (0, 0, "1.1 - What is this course"),
        (0, 1, "1.2 - What will we build"),
        (1, 0, "11.1 - Publishing using `np`"),
    ]
    assert lectures[2].lecture_id == "custom-library-1-0"
    assert lectures[2].chapter_name == "Chapter 11 - Publishing"
    assert tc.decode_video_url(lectures[2].src) == "https://v/c.mp4"


def test_parse_course_lectures_unknown_track_raises():
    with pytest.raises(ValueError):
        tc.parse_course_lectures(TRACKS_SNIPPET, 99, "x")


def test_real_tracks_file_has_the_publish_lecture_at_10_0():
    lectures = tc.parse_course_lectures(
        (REPO / "frontend" / "src" / "data" / "tracks.ts").read_text(), 2, "custom-library")
    by_id = {l.lecture_id: l for l in lectures}
    assert len(lectures) == 34
    assert by_id["custom-library-10-0"].name == "11.1 - Publishing using `np`"
    assert by_id["custom-library-7-0"].name == "8.1 - The `npm link` command"
    assert tc.decode_video_url(by_id["custom-library-10-0"].src).startswith("https://")


def test_find_course_by_slug():
    catalog = [{"id": 1, "slug": "a", "title": "A"}, {"id": 2, "slug": "custom-library",
                                                      "title": "Build a Custom Library"}]
    assert tc.find_course(catalog, "custom-library") == (2, "Build a Custom Library")
    with pytest.raises(ValueError):
        tc.find_course(catalog, "nope")


def test_group_segments_on_fixture():
    passages = tc.group_segments(json.loads(FIXTURE.read_text()))
    assert [(p["start"], p["end"]) for p in passages] == [(0, 51), (50, 101), (101, 190), (190, 200)]
    assert passages[0]["text"] == ("Welcome back. In this lecture we publish our library. "
                                   "First install np globally. npm install --global np")
    # the whitespace-only segment is dropped, not joined as a double space
    assert passages[1]["text"] == ("Then log in with npm login. "
                                   "Run np in the project root and pick the version bump.")


def test_group_segments_never_exceeds_max_by_joining():
    segs = [{"start": 0.0, "end": 40.0, "text": "a"}, {"start": 40.0, "end": 80.0, "text": "b"}]
    assert [(p["start"], p["end"]) for p in tc.group_segments(segs)] == [(0, 40), (40, 80)]


def test_group_segments_short_tail_merges_into_previous_when_it_fits():
    segs = [{"start": 0.0, "end": 50.0, "text": "a"}, {"start": 50.0, "end": 60.0, "text": "b"}]
    assert tc.group_segments(segs) == [{"start": 0, "end": 60, "text": "a b"}]


def test_group_segments_empty_input():
    assert tc.group_segments([]) == []
    assert tc.group_segments([{"start": 0.0, "end": 3.0, "text": " "}]) == []


def test_build_lecture_chunks_ids_and_shape():
    lec = tc.Lecture("custom-library", 10, 0, "Chapter 11 - Publishing", "11.1 - Publishing using `np`", "x")
    passages = tc.group_segments(json.loads(FIXTURE.read_text()))
    chunks = tc.build_lecture_chunks("Build a Custom Library", lec, passages)
    assert [c["chunk_id"] for c in chunks] == [f"custom-library-10-0-{n}" for n in range(4)]
    first = chunks[0]
    assert set(first) == {"chunk_id", "course_id", "course_title", "lecture_id", "lecture_title",
                          "text", "start_time", "end_time", "embedding"}
    assert first["course_id"] == "custom-library"
    assert first["lecture_id"] == "custom-library-10-0"
    assert first["lecture_title"] == "11.1 - Publishing using `np`"
    assert first["embedding"] == []
    starts = [c["start_time"] for c in chunks]
    assert starts == sorted(starts)
    assert all(isinstance(c["start_time"], int) and isinstance(c["end_time"], int)
               and c["end_time"] >= c["start_time"] for c in chunks)
    # every chunk validates as the app's model
    from app.models import TranscriptChunk
    TranscriptChunk(**first)


def test_merge_into_seed_replaces_only_that_course_in_place():
    seed = [{"chunk_id": "o1", "course_id": "other"},
            {"chunk_id": "custom-lib-8-1-a", "course_id": "custom-library"},
            {"chunk_id": "custom-lib-8-1-b", "course_id": "custom-library"},
            {"chunk_id": "o2", "course_id": "other"}]
    new = [{"chunk_id": "custom-library-7-0-0", "course_id": "custom-library"},
           {"chunk_id": "custom-library-10-0-0", "course_id": "custom-library"}]
    out = tc.merge_into_seed(seed, "custom-library", new)
    assert [c["chunk_id"] for c in out] == ["o1", "custom-library-7-0-0", "custom-library-10-0-0", "o2"]
    assert [c["chunk_id"] for c in seed][1] == "custom-lib-8-1-a"  # input not mutated


def test_merge_into_seed_refuses_empty_or_foreign_or_duplicate_chunks():
    seed = [{"chunk_id": "o1", "course_id": "other"}]
    with pytest.raises(ValueError):
        tc.merge_into_seed(seed, "custom-library", [])
    with pytest.raises(ValueError):
        tc.merge_into_seed(seed, "custom-library", [{"chunk_id": "x", "course_id": "other"}])
    dup = [{"chunk_id": "a", "course_id": "custom-library"}, {"chunk_id": "a", "course_id": "custom-library"}]
    with pytest.raises(ValueError):
        tc.merge_into_seed(seed, "custom-library", dup)


def test_merge_into_seed_appends_when_course_absent():
    seed = [{"chunk_id": "o1", "course_id": "other"}]
    new = [{"chunk_id": "n", "course_id": "custom-library"}]
    assert [c["chunk_id"] for c in tc.merge_into_seed(seed, "custom-library", new)] == ["o1", "n"]


def test_merge_into_seed_twice_is_idempotent():
    seed = [{"chunk_id": "o1", "course_id": "other"}, {"chunk_id": "old", "course_id": "custom-library"}]
    new = [{"chunk_id": "custom-library-0-0-0", "course_id": "custom-library"}]
    once = tc.merge_into_seed(seed, "custom-library", new)
    assert tc.merge_into_seed(once, "custom-library", new) == once


def test_merge_never_uses_a_partial_review(tmp_path, monkeypatch):
    # An --only run writes review-partial.json; --merge must refuse rather than shrink the course.
    cache = tmp_path / "cache"
    (cache / "custom-library").mkdir(parents=True)
    (cache / "custom-library" / "review-partial.json").write_text(
        json.dumps([{"chunk_id": "custom-library-10-0-0", "course_id": "custom-library"}]))
    seed = tmp_path / "seed.json"
    seed.write_text("[]")
    monkeypatch.setattr(tc, "CACHE_DIR", cache)
    monkeypatch.setattr(tc, "SEED_PATH", seed)
    assert tc.main(["custom-library", "--merge"]) == 2
    assert seed.read_text() == "[]"


def test_plan_audio_parts_single_when_under_limit():
    assert tc.plan_audio_parts(10_000_000, 600.0) == [(0.0, 600.0)]


def test_plan_audio_parts_splits_evenly_when_over_limit():
    parts = tc.plan_audio_parts(50_000_000, 3000.0, limit_bytes=24_000_000)
    assert parts == [(0.0, 1000.0), (1000.0, 1000.0), (2000.0, 1000.0)]


def test_offset_segments_shifts_times():
    segs = [{"start": 0.0, "end": 2.5, "text": "a"}]
    assert tc.offset_segments(segs, 1000.0) == [{"start": 1000.0, "end": 1002.5, "text": "a"}]
    assert segs[0]["start"] == 0.0
```

- [ ] **Step 3: Run the tests to verify they fail**

Run: `cd backend && .venv/bin/pytest tests/test_transcribe_course.py -q`
Expected: collection error `ImportError: cannot import name 'transcribe_course' from 'scripts'` (module does not exist yet).

- [ ] **Step 4: Write the script**

Create `backend/scripts/transcribe_course.py`:

```python
"""Transcribe one course's lecture videos into TranscriptChunk rows — LOCAL, run once.

  cd backend
  .venv/bin/python scripts/transcribe_course.py custom-library --only custom-library-10-0
  .venv/bin/python scripts/transcribe_course.py custom-library          # all lectures → review.json
  .venv/bin/python scripts/transcribe_course.py custom-library --merge  # review.json → seed

Lectures come from frontend/src/data/tracks.ts (position-based ids, 0-indexed, because
the titles' own numbering has gaps). Each video's audio is pulled by ffmpeg straight
from its (decoded) URL as mono 16 kHz mp3, transcribed with OpenAI whisper-1
(verbose_json, segment timestamps) using OPENAI_API_KEY from backend/.env, and grouped
into ~45–75 s passages on segment boundaries.

Audio and raw Whisper segments are cached under backend/data/transcribe_cache/<slug>/
(git-ignored), so re-runs only redo what failed. A lecture that fails is reported and
skipped; the exit code is 1 if any did.
"""
from __future__ import annotations

import argparse
import base64
import json
import math
import re
import shutil
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[1]
REPO = BACKEND.parent
TRACKS_PATH = REPO / "frontend" / "src" / "data" / "tracks.ts"
CATALOG_PATH = BACKEND / "app" / "data" / "catalog.json"
SEED_PATH = BACKEND / "app" / "data" / "seed_transcripts.json"
CACHE_DIR = BACKEND / "data" / "transcribe_cache"

SECRET_KEY = b"thisisasecretofus"  # same key as frontend/src/lib/videoDecoder.ts
MAX_UPLOAD_BYTES = 24_000_000  # whisper-1 rejects uploads over 25 MB; keep a margin
WHISPER_MODEL = "whisper-1"
# Spelling hints only — whisper-1 uses the prompt as vocabulary, not as instructions.
WHISPER_PROMPT = ("JavaScript, npm, np, npm link, npm publish, package.json, IIFE, prototype, "
                  "ES modules, ESM, CommonJS, window, globalThis, Axios, regex.")
FFMPEG = shutil.which("ffmpeg") or "/opt/homebrew/bin/ffmpeg"
FFPROBE = shutil.which("ffprobe") or "/opt/homebrew/bin/ffprobe"

_JS_STR = r'"((?:[^"\\]|\\.)*)"'
_ENTRY = re.compile(r"\{\s*name:\s*" + _JS_STR + r"\s*,\s*(?:(subchapters):\s*\[|src:\s*" + _JS_STR + r")")


@dataclass(frozen=True)
class Lecture:
    course_slug: str
    chapter_idx: int
    sub_idx: int
    chapter_name: str
    name: str
    src: str  # encoded, exactly as in tracks.ts

    @property
    def lecture_id(self) -> str:
        return f"{self.course_slug}-{self.chapter_idx}-{self.sub_idx}"


# ---------------------------------------------------------------- pure parts

def decode_video_url(encoded: str) -> str:
    """Python twin of frontend/src/lib/videoDecoder.ts: base64, then XOR with the key."""
    raw = base64.b64decode(encoded)
    return bytes(b ^ SECRET_KEY[i % len(SECRET_KEY)] for i, b in enumerate(raw)).decode("latin-1")


def _unescape(js: str) -> str:
    return re.sub(r"\\(.)", r"\1", js)


def parse_course_lectures(tracks_src: str, track_id: int, course_slug: str) -> list[Lecture]:
    """Lectures of track `track_id` in order, from its `courseContent: [...]` block."""
    start = re.search(rf"\n    id: {track_id},\n", tracks_src)
    if not start:
        raise ValueError(f"track id {track_id} not found in tracks.ts")
    rest = tracks_src[start.end():]
    nxt = re.search(r"\n  \{\n    id: \d+,", rest)
    block = rest[: nxt.start()] if nxt else rest
    cc = block.find("courseContent: [")
    if cc < 0:
        raise ValueError(f"track id {track_id} has no courseContent")
    end = block.find("\n    ],", cc)
    body = block[cc: end if end >= 0 else len(block)]

    lectures: list[Lecture] = []
    chapter_idx, chapter_name, sub_idx = -1, "", 0
    for m in _ENTRY.finditer(body):
        name = _unescape(m.group(1))
        if m.group(2):  # a chapter: `{ name: "...", subchapters: [`
            chapter_idx, chapter_name, sub_idx = chapter_idx + 1, name, 0
            continue
        if chapter_idx < 0:
            raise ValueError(f"subchapter {name!r} before any chapter")
        lectures.append(Lecture(course_slug, chapter_idx, sub_idx, chapter_name, name, _unescape(m.group(3))))
        sub_idx += 1
    return lectures


def find_course(catalog: list[dict], course_slug: str) -> tuple[int, str]:
    for c in catalog:
        if c.get("slug") == course_slug:
            return int(c["id"]), c["title"]
    raise ValueError(f"course slug {course_slug!r} not in catalog.json")


def group_segments(segments: list[dict], min_s: float = 45, max_s: float = 75) -> list[dict]:
    """Group Whisper segments into ~min_s–max_s passages, breaking only between segments.

    A passage closes once it reaches min_s; a segment that would push an open passage
    past max_s starts a new one instead. A single segment longer than max_s stays whole.
    A short tail joins the previous passage if the result still fits in max_s.
    Times: start floored, end ceiled, to whole seconds.
    """
    passages: list[dict] = []
    cur: list[dict] = []

    def flush() -> None:
        if cur:
            passages.append({
                "start": int(math.floor(cur[0]["start"])),
                "end": int(math.ceil(cur[-1]["end"])),
                "text": " ".join(s["text"].strip() for s in cur),
                "_t0": cur[0]["start"],
            })
            cur.clear()

    for seg in segments:
        if not seg["text"].strip():
            continue
        if cur and seg["end"] - cur[0]["start"] > max_s:
            flush()
        cur.append(seg)
        if seg["end"] - cur[0]["start"] >= min_s:
            flush()

    if cur:
        tail_end = cur[-1]["end"]
        if passages and tail_end - passages[-1]["_t0"] <= max_s:
            last = passages[-1]
            last["end"] = int(math.ceil(tail_end))
            last["text"] = last["text"] + " " + " ".join(s["text"].strip() for s in cur)
            cur.clear()
        else:
            flush()
    for p in passages:
        p.pop("_t0")
    return passages


def build_lecture_chunks(course_title: str, lecture: Lecture, passages: list[dict]) -> list[dict]:
    return [
        {
            "chunk_id": f"{lecture.lecture_id}-{n}",
            "course_id": lecture.course_slug,
            "course_title": course_title,
            "lecture_id": lecture.lecture_id,
            "lecture_title": lecture.name,
            "text": p["text"],
            "start_time": p["start"],
            "end_time": p["end"],
            "embedding": [],
        }
        for n, p in enumerate(passages)
    ]


def merge_into_seed(seed: list[dict], course_slug: str, new_chunks: list[dict]) -> list[dict]:
    """Drop every chunk of `course_slug` and put `new_chunks` where the first one was."""
    if not new_chunks:
        raise ValueError("refusing to merge zero chunks — the course would lose all transcripts")
    if any(c["course_id"] != course_slug for c in new_chunks):
        raise ValueError(f"new chunks must all have course_id={course_slug!r}")
    ids = [c["chunk_id"] for c in new_chunks]
    if len(set(ids)) != len(ids):
        raise ValueError("duplicate chunk_id in new chunks")
    out: list[dict] = []
    inserted = False
    for c in seed:
        if c["course_id"] == course_slug:
            if not inserted:
                out.extend(new_chunks)
                inserted = True
            continue
        out.append(c)
    if not inserted:
        out.extend(new_chunks)
    return out


def plan_audio_parts(size_bytes: int, duration_s: float,
                     limit_bytes: int = MAX_UPLOAD_BYTES) -> list[tuple[float, float]]:
    """(offset, length) pieces so each piece's upload stays under limit_bytes."""
    if size_bytes < limit_bytes:
        return [(0.0, duration_s)]
    n = size_bytes // limit_bytes + 1
    part = duration_s / n
    return [(i * part, part) for i in range(n)]


def offset_segments(segments: list[dict], offset: float) -> list[dict]:
    return [{**s, "start": s["start"] + offset, "end": s["end"] + offset} for s in segments]


# ---------------------------------------------------------------- thin I/O

def extract_audio(src: str, out_path: Path, offset: float | None = None,
                  length: float | None = None) -> None:
    """ffmpeg: video URL (or audio file) → mono 16 kHz 32 kbps mp3."""
    cmd = [FFMPEG, "-y", "-loglevel", "error"]
    if offset is not None:
        cmd += ["-ss", f"{offset:.2f}"]
    cmd += ["-i", src]
    if length is not None:
        cmd += ["-t", f"{length:.2f}"]
    cmd += ["-vn", "-ac", "1", "-ar", "16000", "-b:a", "32k", str(out_path)]
    subprocess.run(cmd, check=True, timeout=1800)


def probe_duration(path: Path) -> float:
    out = subprocess.run(
        [FFPROBE, "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", str(path)],
        check=True, capture_output=True, text=True, timeout=120)
    return float(out.stdout.strip())


def whisper_segments(client, audio_path: Path) -> list[dict]:
    with open(audio_path, "rb") as f:
        resp = client.audio.transcriptions.create(
            model=WHISPER_MODEL,
            file=f,
            response_format="verbose_json",
            timestamp_granularities=["segment"],
            language="en",
            prompt=WHISPER_PROMPT,
        )
    return [{"start": float(s.start), "end": float(s.end), "text": s.text} for s in (resp.segments or [])]


def transcribe_lecture(client, lecture: Lecture, cache: Path) -> list[dict]:
    """Segments for one lecture, from cache when present."""
    seg_path = cache / f"{lecture.lecture_id}.whisper.json"
    if seg_path.exists():
        return json.loads(seg_path.read_text())
    audio = cache / f"{lecture.lecture_id}.mp3"
    if not audio.exists():
        tmp = cache / f"{lecture.lecture_id}.partial.mp3"
        extract_audio(decode_video_url(lecture.src), tmp)
        tmp.rename(audio)
    parts = plan_audio_parts(audio.stat().st_size, probe_duration(audio)
                             if audio.stat().st_size >= MAX_UPLOAD_BYTES else 0.0)
    segments: list[dict] = []
    if len(parts) == 1:
        segments = whisper_segments(client, audio)
    else:
        for i, (offset, length) in enumerate(parts):
            piece = cache / f"{lecture.lecture_id}.part{i}.mp3"
            if not piece.exists():
                extract_audio(str(audio), piece, offset, length)
            segments += offset_segments(whisper_segments(client, piece), offset)
    seg_path.write_text(json.dumps(segments, indent=1))
    return segments


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("course_slug")
    ap.add_argument("--only", default="", help="comma-separated lecture_ids (writes review-partial.json)")
    ap.add_argument("--merge", action="store_true", help="merge review.json into seed_transcripts.json")
    args = ap.parse_args(argv)
    cache = CACHE_DIR / args.course_slug
    review = cache / "review.json"

    if args.merge:
        if not review.exists():
            print(f"no {review} — run a full transcription first")
            return 2
        new_chunks = json.loads(review.read_text())
        seed = json.loads(SEED_PATH.read_text())
        merged = merge_into_seed(seed, args.course_slug, new_chunks)
        SEED_PATH.write_text(json.dumps(merged, indent=2))
        print(f"merged {len(new_chunks)} {args.course_slug} chunks; seed now {len(merged)} chunks")
        return 0

    from dotenv import load_dotenv
    from openai import OpenAI

    load_dotenv(BACKEND / ".env")
    track_id, course_title = find_course(json.loads(CATALOG_PATH.read_text()), args.course_slug)
    lectures = parse_course_lectures(TRACKS_PATH.read_text(), track_id, args.course_slug)
    only = {x.strip() for x in args.only.split(",") if x.strip()}
    unknown = only - {l.lecture_id for l in lectures}
    if unknown:
        print(f"unknown lecture ids: {sorted(unknown)}")
        return 2
    cache.mkdir(parents=True, exist_ok=True)
    client = OpenAI()

    chunks: list[dict] = []
    failed: list[tuple[Lecture, str]] = []
    empty: list[Lecture] = []
    for lec in lectures:
        if only and lec.lecture_id not in only:
            continue
        try:
            segments = transcribe_lecture(client, lec, cache)
        except Exception as e:  # noqa: BLE001 — report and keep going
            failed.append((lec, f"{type(e).__name__}: {e}"))
            print(f"FAIL  {lec.lecture_id:24} {lec.name}  — {type(e).__name__}: {e}")
            continue
        lec_chunks = build_lecture_chunks(course_title, lec, group_segments(segments))
        if not lec_chunks:
            empty.append(lec)
        chunks += lec_chunks
        last = lec_chunks[-1]["end_time"] if lec_chunks else 0
        print(f"ok    {lec.lecture_id:24} {lec.name[:55]:55} {len(lec_chunks):3} chunks  ends {last // 60:02d}:{last % 60:02d}")

    out = cache / ("review-partial.json" if only else "review.json")
    out.write_text(json.dumps(chunks, indent=2))
    print(f"\nwrote {len(chunks)} chunks → {out}")
    for lec in empty:
        print(f"EMPTY {lec.lecture_id} {lec.name} (no speech segments)")
    for lec, err in failed:
        print(f"FAILED {lec.lecture_id} {lec.name}: {err}")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 5: Ignore the cache dir**

Append to `backend/.gitignore`:

```
# transcription script cache (audio + raw whisper output)
data/transcribe_cache/
```

- [ ] **Step 6: Run the tests to verify they pass**

Run: `cd backend && .venv/bin/pytest tests/test_transcribe_course.py -q`
Expected: `18 passed`.

Then: `git check-ignore -v backend/data/transcribe_cache/x.mp3`
Expected: prints the `backend/.gitignore` rule (exit 0).

- [ ] **Step 7: Run the full suite**

Run: `bash backend/scripts/run_tests.sh`
Expected: ends with `ALL PASSED`.

- [ ] **Step 8: Commit**

```bash
git add backend/scripts/transcribe_course.py backend/tests/test_transcribe_course.py backend/tests/fixtures/whisper_verbose_sample.json backend/.gitignore
git commit -m "feat(transcripts): transcribe_course script — tracks.ts lectures → whisper → 45–75 s chunks

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task B: Transcribe Build a Custom Library, review, merge into the seed

This task runs the Task A script for real (network, ffmpeg, OpenAI — roughly $0.006 per audio minute with whisper-1, a few dollars for the course) and commits generated data. No product code changes.

**Files:**
- Modify (generated): `backend/app/data/seed_transcripts.json`
- Modify: `backend/app/data/demo/question_banks.json` (custom-library questions' `"lecture"` field)
- Modify: `backend/app/eval/golden_set.json` (the two npm-link questions' `gold_chunk_ids`)

**Interfaces:**
- Consumes: Task A CLI `scripts/transcribe_course.py <slug> [--only ids] [--merge]`; cache `backend/data/transcribe_cache/custom-library/{review.json, review-partial.json, <lecture_id>.whisper.json, <lecture_id>.mp3}`.
- Produces: `seed_transcripts.json` where every `course_id == "custom-library"` chunk has `chunk_id = custom-library-<c>-<s>-<n>`, `lecture_title` exactly a `tracks.ts` subchapter name (e.g. ``"11.1 - Publishing using `np`"``), whole-second times. The hand-written `custom-lib-8-1-a/b/c` are gone. Tasks C, D and F search these chunks.

Why the two extra JSON edits: `backend/tests/test_demo_seed.py::test_every_bank_question_is_valid` asserts every bank question's `"lecture"` is a `lecture_title` present in the seed for that course — today all custom-library questions say `"8.1 - The npm link command"`, but the real title (from tracks.ts) is ``"8.1 - The `npm link` command"``. And `backend/app/eval/golden_set.json` (read by `backend/app/eval/accuracy.py`, an offline eval) names the removed chunk ids.

- [ ] **Step 1: Make the real key available to the worktree**

`backend/.env` is git-ignored and exists only in the main checkout, and it also holds the PRODUCTION `DATABASE_URL`. Do NOT link or copy it into the worktree (every later script/test run there would then see production). Export ONLY the OpenAI key into the shell that runs the transcription steps of this task:

```bash
export OPENAI_API_KEY="$(grep '^OPENAI_API_KEY=' /Users/swanandkadam/Desktop/01dev-React-hermes/backend/.env | cut -d= -f2- | tr -d '"')"
[ -n "$OPENAI_API_KEY" ] && echo key-present
[ -e backend/.env ] && echo "UNEXPECTED backend/.env in worktree — stop" || echo no-worktree-env
/opt/homebrew/bin/ffmpeg -version | head -1
```
Expected: `key-present`, `no-worktree-env` and an `ffmpeg version …` line. If any is missing, stop and ask. (`load_dotenv(BACKEND / ".env")` in the script is then a no-op; the exported key is used.)

**Shell state does not persist between separate command invocations.** In every later step of this task and of Task F that needs OpenAI, prefix the command with
`env OPENAI_API_KEY="$(grep '^OPENAI_API_KEY=' /Users/swanandkadam/Desktop/01dev-React-hermes/backend/.env | cut -d= -f2- | tr -d '"')" DATABASE_URL=` — and never create `backend/.env` in the worktree.

- [ ] **Step 2: Trial run on the one lecture the demo depends on (11.1)**

```bash
cd backend && .venv/bin/python scripts/transcribe_course.py custom-library --only custom-library-10-0
```
Expected: one `ok    custom-library-10-0   11.1 - Publishing using `np` …  N chunks  ends mm:ss` line with N ≥ 1, `wrote N chunks → …/review-partial.json`, exit 0.

Spot-check that the publish commands are in it and print each passage's time + start of text:

```bash
cd backend && .venv/bin/python - <<'EOF'
import json, re
rows = json.load(open("data/transcribe_cache/custom-library/review-partial.json"))
for c in rows:
    print(f'{c["chunk_id"]:24} {c["start_time"]//60:02d}:{c["start_time"]%60:02d}-{c["end_time"]//60:02d}:{c["end_time"]%60:02d}  {c["text"][:110]}')
hits = [c["chunk_id"] for c in rows if re.search(r"\bnp\b", c["text"]) and re.search(r"publish", c["text"], re.I)]
print("np+publish chunks:", hits)
assert hits, "11.1 transcript has no passage mentioning `np` and publishing — listen to the video before going on"
EOF
```
Expected: the passages print, `np+publish chunks:` lists at least one id, no AssertionError. Read the printed text: it must be English speech about publishing with `np` (if Whisper wrote "NP"/"n p", the regex still needs a `np` token — if it fails only because of spelling, note the spelling in your report and continue; the search is semantic).

- [ ] **Step 3: Full run**

```bash
cd backend && .venv/bin/python scripts/transcribe_course.py custom-library
```
Expected: 34 lecture lines (`ok`/`FAIL`), `wrote … → …/review.json`. 11.1 comes from the cache (no second charge). Exit 1 means some lectures failed: re-run the same command once (cached lectures are skipped); if a lecture still fails, read its error, and if it is a dead/forbidden video URL record it for the commit message and continue — it is reported, not fatal.

- [ ] **Step 4: Review the full output**

```bash
cd backend && .venv/bin/python - <<'EOF'
import json, re, sys
from collections import defaultdict
sys.path.insert(0, ".")
from scripts.transcribe_course import parse_course_lectures, TRACKS_PATH
rows = json.load(open("data/transcribe_cache/custom-library/review.json"))
lectures = parse_course_lectures(TRACKS_PATH.read_text(), 2, "custom-library")
by_lec = defaultdict(list)
for c in rows:
    by_lec[c["lecture_id"]].append(c)
problems = []
for lec in lectures:
    cs = by_lec.get(lec.lecture_id, [])
    durs = [c["end_time"] - c["start_time"] for c in cs]
    print(f'{lec.lecture_id:22} {lec.name[:52]:52} {len(cs):3} chunks  '
          f'{(cs[-1]["end_time"] // 60) if cs else 0:3d} min  dur {min(durs, default=0)}–{max(durs, default=0)} s')
    if not cs:
        problems.append(f"EMPTY {lec.lecture_id} {lec.name}")
    for i, c in enumerate(cs):
        if c["chunk_id"] != f"{lec.lecture_id}-{i}": problems.append(f"bad id {c['chunk_id']}")
        if c["lecture_title"] != lec.name: problems.append(f"bad title {c['chunk_id']}")
        if not c["text"].strip(): problems.append(f"empty text {c['chunk_id']}")
        if c["end_time"] < c["start_time"]: problems.append(f"end<start {c['chunk_id']}")
        if i and c["start_time"] < cs[i - 1]["start_time"]: problems.append(f"non-monotonic {c['chunk_id']}")
assert len({c["chunk_id"] for c in rows}) == len(rows), "duplicate chunk ids"
pub = [c for c in by_lec["custom-library-10-0"] if re.search(r"\bnp\b", c["text"])]
print("\n11.1 np passages:", [(c["chunk_id"], c["start_time"]) for c in pub])
print("total chunks:", len(rows))
print("\n".join(problems) or "NO PROBLEMS")
EOF
```
Expected: 34 lines, `11.1 np passages:` non-empty, `NO PROBLEMS`. Most `dur` ranges fall in 45–75 s (a single long Whisper segment or a whole short lecture may sit outside — fine). For any `EMPTY` line not already explained by a Step 3 failure: play that lecture's audio (`open backend/data/transcribe_cache/custom-library/<lecture_id>.mp3`) and write the reason (e.g. "music-only outro") into the commit message. Also read 3 random passages end-to-end and confirm they are coherent English about the lecture's topic.

- [ ] **Step 5: Merge into the seed**

```bash
cd backend && .venv/bin/python scripts/transcribe_course.py custom-library --merge
```
Expected: `merged <total> custom-library chunks; seed now <total + 18> chunks` (the seed held 21 chunks, 3 of them custom-library).

Verify the other courses are byte-for-byte untouched and the hand-written ids are gone:

```bash
git diff --stat backend/app/data/seed_transcripts.json
cd backend && .venv/bin/python - <<'EOF'
import json, subprocess
new = json.load(open("app/data/seed_transcripts.json"))
old = json.loads(subprocess.run(["git", "show", "HEAD:backend/app/data/seed_transcripts.json"],
                                capture_output=True, text=True, check=True).stdout)
assert [c for c in new if c["course_id"] != "custom-library"] == [c for c in old if c["course_id"] != "custom-library"]
assert not any(c["chunk_id"].startswith("custom-lib-8-1") for c in new)
print("other courses unchanged; custom-library chunks:", sum(c["course_id"] == "custom-library" for c in new))
EOF
```
Expected: `other courses unchanged; custom-library chunks: <total>`.

- [ ] **Step 6: Point the demo question bank and golden set at the real titles/ids**

```bash
cd backend && .venv/bin/python - <<'EOF'
import json, re
from pathlib import Path
banks_p = Path("app/data/demo/question_banks.json")
raw = banks_p.read_text()
fixed = raw.replace('"lecture": "8.1 - The npm link command"', '"lecture": "8.1 - The `npm link` command"')
assert fixed != raw
banks_p.write_text(fixed)

seed = json.load(open("app/data/seed_transcripts.json"))
link_ids = [c["chunk_id"] for c in seed if c["lecture_id"] == "custom-library-7-0" and re.search(r"npm link|\blink\b", c["text"], re.I)]
assert link_ids, "no 8.1 passage mentions npm link"
gold_p = Path("app/eval/golden_set.json")
# text replace, not json.dumps: the file keeps its arrays on one line
gold = gold_p.read_text()
new_gold = (gold.replace('["custom-lib-8-1-a", "custom-lib-8-1-c"]', json.dumps(link_ids))
                .replace('["custom-lib-8-1-b"]', json.dumps(link_ids)))
assert "custom-lib-8-1" not in new_gold
gold_p.write_text(new_gold)
print("8.1 link chunks:", link_ids)
EOF
git diff --stat backend/app/data/demo/question_banks.json backend/app/eval/golden_set.json
```
Expected: `8.1 link chunks: [...]`; the diff stat shows only those two files changed, and `git diff backend/app/eval/golden_set.json` shows exactly two changed lines (the two npm-link questions' `gold_chunk_ids`).

- [ ] **Step 7: Full suite (seed is loaded by several tests)**

Run: `bash backend/scripts/run_tests.sh`
Expected: `ALL PASSED` (notably `tests/test_demo_seed.py`).

- [ ] **Step 8: Commit**

```bash
git add backend/app/data/seed_transcripts.json backend/app/data/demo/question_banks.json backend/app/eval/golden_set.json
git commit -m "data(transcripts): real whisper transcripts for Build a Custom Library

Replaces the 3 hand-written 8.1 snippets with <total> passages across 34 lectures
(scripts/transcribe_course.py). Bank lecture titles and golden-set ids follow the
real tracks.ts titles / new chunk ids.
<list any failed or empty lectures and why, or 'All 34 lectures transcribed.'>

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```
(Replace the two `<…>` bits in the message with the real count and outcome before committing.)

---

### Task C: Player tutor is course-first (in-course lookup, no pointer, prompt rules)

**Files:**
- Modify: `backend/app/services/course_lookup.py` (constants block lines 16–22, `LookupCase` 25–28, `ChatScope` 31–34, after `_transcript_hits` 71–75, `course_lookup` 87–88, `render_facts` 156–178)
- Modify: `backend/app/services/chat_pipeline.py:44-47` (`_missing_pointer`)
- Modify: `backend/app/main.py:180-184` (player route `TurnRequest`)
- Modify: `backend/app/grounding/grounding_prompt.md` (insert after line 38, before `# MODE: in-lecture`)
- Create: `backend/scripts/calibrate_in_course.py`
- Test (append only): `backend/tests/test_course_lookup.py`, `backend/tests/test_chat_pipeline.py`, `backend/tests/test_player_tutor_route.py`, `backend/tests/test_ask_chat_route.py`, `backend/tests/test_grounding_prompt.py`

**Interfaces:**
- Consumes: Task B's real `custom-library` chunks (for the calibration step only).
- Produces (all in `app.services.course_lookup`):
  - `ChatScope(course_slug: Optional[str] = None, lecture_title: Optional[str] = None, in_player: bool = False)` — frozen dataclass; field order unchanged so `ChatScope("react-perf", "4.1 …")` still works.
  - `LookupCase.IN_COURSE_MATCH = "in_course_match"`, `IN_COURSE_RELATED = "in_course_related"`, `IN_COURSE_NONE = "in_course_none"` — added members; the three existing members, their values, and every non-player code path are unchanged, so the Ask page (with or without its course filter) can never produce the new members.
  - `RELATED_THRESHOLD: float` (module constant, start `0.40`, set by the calibration step).
  - `async def search_in_course(query: str, course_slug: str, top_k: int = 8) -> list[tuple[TranscriptChunk, float]]` — best-first chunks of that course only. Task D's `find_moment` calls it as `course_lookup.search_in_course(...)` (module attribute, so tests can monkeypatch it).
  - `render_facts(lookup, scope, weak_concepts=None)` — same signature; with `scope.in_player` it names only the watched course and labels matches `[THIS COURSE]`.
- `chat_pipeline._missing_pointer(lookup, answer, scope)` returns `None` whenever `scope.in_player`.

**Backward-compatibility decision (LookupCase):** the new outcomes are new enum members, produced only by a new `_in_course_lookup` branch that runs iff `scope.in_player`. The old function body below that branch is not edited, so every existing `test_course_lookup.py`, `test_chat_pipeline.py`, `test_ask_chat_route.py` and `demo_check.py` expectation (which build `ChatScope` without `in_player`) keeps its meaning, including the existing tests that pass a `lecture_title` without `in_player` — those now model "Ask with a course filter / any non-player caller".

- [ ] **Step 1: Write the failing lookup tests**

Append to `backend/tests/test_course_lookup.py`:

```python
# ---- in-player (course-first) mode — spec §3.2 ---------------------------------

PUBLISH_CHUNK = _chunk("custom-library", "Build a Custom Library", "11.1 - Publishing using `np`",
                       "run np and pick the version", start=200)
PLAYER = cl.ChatScope(course_slug="custom-library", lecture_title="8.1 - The `npm link` command", in_player=True)


def test_chat_scope_in_player_defaults_off_and_positional_args_still_work():
    assert cl.ChatScope().in_player is False
    s = cl.ChatScope("react-perf", "4.1 - React.memo and useCallback")
    assert (s.course_slug, s.lecture_title, s.in_player) == ("react-perf", "4.1 - React.memo and useCallback", False)


@pytest.fixture
def patch_in_course(monkeypatch, patch_sources):
    monkeypatch.setattr(cl, "TRANSCRIPT_THRESHOLD", 0.54)
    monkeypatch.setattr(cl, "RELATED_THRESHOLD", 0.40)
    seen = {}

    def apply(results=(), enrolled_ids=()):
        patch_sources(enrolled_ids=enrolled_ids)

        async def fake_search(query, course_slug, top_k=8):
            seen["query"], seen["slug"] = query, course_slug
            return list(results)

        async def no_catalog(query, top_k=5):
            raise AssertionError("the player tutor must not search the catalog")

        async def no_global_transcripts(question, top_k=8):
            raise AssertionError("the player tutor must not search other courses' transcripts")

        monkeypatch.setattr(cl, "search_in_course", fake_search)
        monkeypatch.setattr(cl.catalog_index, "search", no_catalog)
        monkeypatch.setattr(cl, "_transcript_hits", no_global_transcripts)
        return seen
    return apply


async def test_player_searches_only_this_course_with_the_lecture_title_and_skips_the_catalog(patch_in_course):
    seen = patch_in_course(results=[(PUBLISH_CHUNK, 0.61)])
    out = await cl.course_lookup("how do I publish", "s", PLAYER)
    assert seen == {"query": "8.1 - The `npm link` command how do I publish", "slug": "custom-library"}
    assert out.case == cl.LookupCase.IN_COURSE_MATCH
    assert [h.course_slug for h in out.hits] == ["custom-library"]
    assert out.hits[0].title == "11.1 - Publishing using `np`" and out.hits[0].start_time == 200


@pytest.mark.parametrize("score,case,n_hits", [
    (0.60, "IN_COURSE_MATCH", 1), (0.54, "IN_COURSE_MATCH", 1),
    (0.47, "IN_COURSE_RELATED", 1), (0.40, "IN_COURSE_RELATED", 1),
    (0.39, "IN_COURSE_NONE", 0), (0.10, "IN_COURSE_NONE", 0),
])
async def test_player_outcome_follows_the_best_in_course_score(patch_in_course, score, case, n_hits):
    patch_in_course(results=[(PUBLISH_CHUNK, score)])
    out = await cl.course_lookup("q", "s", PLAYER)
    assert out.case == cl.LookupCase[case]
    assert len(out.hits) == n_hits


async def test_player_with_no_results_is_in_course_none(patch_in_course):
    patch_in_course(results=[])
    out = await cl.course_lookup("how do I bake bread", "s", PLAYER)
    assert out.case == cl.LookupCase.IN_COURSE_NONE and out.hits == []


async def test_player_match_keeps_only_match_strength_hits(patch_in_course):
    weak = _chunk("custom-library", "Build a Custom Library", "8.2 - Testing Our NPM Package", "symlink", start=10)
    patch_in_course(results=[(PUBLISH_CHUNK, 0.62), (weak, 0.45)])
    out = await cl.course_lookup("q", "s", PLAYER)
    assert out.case == cl.LookupCase.IN_COURSE_MATCH
    assert [h.score for h in out.hits] == [0.62]


async def test_player_drops_any_other_course_chunk_even_if_search_returns_one(patch_in_course):
    patch_in_course(results=[(MEMO_CHUNK, 0.90), (PUBLISH_CHUNK, 0.45)])
    out = await cl.course_lookup("q", "s", PLAYER)
    assert [h.course_slug for h in out.hits] == ["custom-library"]
    assert out.case == cl.LookupCase.IN_COURSE_RELATED


async def test_player_ranks_the_current_lecture_first_among_matches(patch_in_course):
    here = _chunk("custom-library", "Build a Custom Library", "8.1 - The npm link command", "npm link", start=30)
    patch_in_course(results=[(PUBLISH_CHUNK, 0.70), (here, 0.58)])
    out = await cl.course_lookup("what does this mean", "s", PLAYER)
    assert out.hits[0].title == "8.1 - The npm link command"
    assert out.case == cl.LookupCase.IN_COURSE_MATCH


async def test_player_with_no_lecture_selected_searches_the_bare_question_in_this_course(patch_in_course):
    # CoursePlayerPage sends the course title as `lecture` before a lecture is picked; the
    # route blanks it, so the scope has no lecture_title — still course-only.
    seen = patch_in_course(results=[(PUBLISH_CHUNK, 0.47)])
    scope = cl.ChatScope(course_slug="custom-library", in_player=True)
    out = await cl.course_lookup("how do I publish", "s", scope)
    assert seen == {"query": "how do I publish", "slug": "custom-library"}
    assert out.case == cl.LookupCase.IN_COURSE_RELATED
    assert "MODE: in-lecture" not in cl.render_facts(out, scope)


async def test_ask_with_a_course_filter_is_unchanged(patch_sources):
    # The Ask page's course filter also sets course_slug: it must keep cross-course
    # search, the catalog and the enrolled / not-enrolled cases.
    patch_sources(transcripts=[(MEMO_CHUNK, 0.6)], catalog=[(NPM_MODULE, 0.58)], enrolled_ids=[11])
    out = await cl.course_lookup("q", "s", cl.ChatScope(course_slug="custom-library"))
    assert out.case == cl.LookupCase.NOT_ENROLLED_MATCH
    assert {h.course_slug for h in out.hits} == {"react-perf", "custom-library"}
    assert {h.source for h in out.hits} == {"transcript", "catalog"}


async def test_search_in_course_keeps_only_that_course_best_first(monkeypatch):
    from app.models import SearchResult
    results = [SearchResult(chunk=MEMO_CHUNK, score=0.9), SearchResult(chunk=PUBLISH_CHUNK, score=0.6),
               SearchResult(chunk=NPM_CHUNK, score=0.5)]

    class FakeStore:
        chunks = [r.chunk for r in results]
        calls: list = []

        def search(self, emb, top_k=5, threshold=0.25, query_text=""):
            self.calls.append((top_k, threshold, query_text))
            return results[:top_k]

    async def fake_embed(text):
        return [1.0, 0.0]

    fake = FakeStore()
    monkeypatch.setattr(cl, "vector_store", fake)
    monkeypatch.setattr(cl.embedding_service, "embed", fake_embed)
    assert await cl.search_in_course("publish", "custom-library", top_k=1) == [(PUBLISH_CHUNK, 0.6)]
    assert await cl.search_in_course("publish", "custom-library") == [(PUBLISH_CHUNK, 0.6), (NPM_CHUNK, 0.5)]
    assert await cl.search_in_course("publish", "nope") == []
    assert fake.calls[0] == (3, 0.0, "publish")  # whole store ranked, then filtered


def test_player_facts_name_only_this_course():
    hit = cl.Hit(source="transcript", course_id=2, course_slug="custom-library", course_title="Build a Custom Library",
                 title="11.1 - Publishing using `np`", score=0.47, enrolled=False, text="run np",
                 lecture_id="custom-library-10-0", start_time=200, end_time=250, url="/course/2")
    lookup = cl.CourseLookup(case=cl.LookupCase.IN_COURSE_RELATED, hits=[hit],
                             enrolled_titles=["JavaScript Deep Dive", "React Performance Patterns"])
    facts = cl.render_facts(lookup, PLAYER)
    assert "CASE: IN_COURSE_RELATED" in facts
    assert "[THIS COURSE] 11.1 - Publishing using `np` @ 03:20" in facts
    assert "JavaScript Deep Dive" not in facts and "React Performance Patterns" not in facts
    assert "NOT ENROLLED" not in facts and "enrolled in" not in facts.lower()
    assert "never name, recommend or link another course" in facts
    assert "the01.dev/course/" not in facts
    assert "MODE: in-lecture" in facts


def test_player_none_in_a_lecture_still_gets_the_outline():
    scope = cl.ChatScope(course_slug="custom-library", lecture_title="1.1 - What is this course", in_player=True)
    facts = cl.render_facts(cl.CourseLookup(case=cl.LookupCase.IN_COURSE_NONE, hits=[], enrolled_titles=["X"]), scope)
    assert "CASE: IN_COURSE_NONE" in facts
    assert "No transcript excerpt for this lecture" in facts and "Chapter 1 - Introduction" in facts
```

- [ ] **Step 2: Run them to verify they fail**

Run: `cd backend && .venv/bin/pytest tests/test_course_lookup.py -q`
Expected: the new tests FAIL (`TypeError: ChatScope.__init__() got an unexpected keyword argument 'in_player'` at import of `PLAYER` → collection error); old tests are not reached. That collection error is the expected red.

- [ ] **Step 3: Implement the in-course lookup**

In `backend/app/services/course_lookup.py`:

(a) Add the import below `from app.services.vector_store import vector_store` (line 14):

```python
from app.models import TranscriptChunk
```

(b) Replace line 22 `MAX_HITS = 5` with:

```python
MAX_HITS = 5
# Player only (spec §3.2): below TRANSCRIPT_THRESHOLD but at least this → "this course
# touches on it". Start value 0.40; recalibrated on the real transcripts by
# scripts/calibrate_in_course.py.
RELATED_THRESHOLD = 0.40
```

(c) Replace the `LookupCase` and `ChatScope` classes (lines 25–34) with:

```python
class LookupCase(str, Enum):
    ENROLLED_MATCH = "enrolled_match"
    NOT_ENROLLED_MATCH = "not_enrolled_match"
    NO_MATCH = "no_match"
    # Player tutor only (ChatScope.in_player) — this course's transcripts, nothing else.
    IN_COURSE_MATCH = "in_course_match"
    IN_COURSE_RELATED = "in_course_related"
    IN_COURSE_NONE = "in_course_none"


@dataclass(frozen=True)
class ChatScope:
    course_slug: Optional[str] = None    # None = all courses (Ask page)
    lecture_title: Optional[str] = None  # set by the video player
    # True only on the player route (/api/ai/tutor/stream). The Ask page's course filter
    # also sets course_slug, so a course being set is NOT the trigger.
    in_player: bool = False
```

(d) Insert after `_transcript_hits` (after line 75):

```python
async def search_in_course(query: str, course_slug: str, top_k: int = 8) -> list[tuple[TranscriptChunk, float]]:
    """Best-first transcript chunks of ONE course. Ranks the whole store, then filters,
    so another course's chunk can never stand in for this course's."""
    if not vector_store.chunks:
        await vector_store.initialize()
    emb = await embedding_service.embed(query)
    results = vector_store.search(emb, top_k=len(vector_store.chunks), threshold=0.0, query_text=query)
    return [(r.chunk, r.score) for r in results if r.chunk.course_id == course_slug][:top_k]
```

(e) In `course_lookup`, right after `enrolled_ids, enrolled_titles = await _enrollments(student_id)` (line 88), insert:

```python
    if scope.in_player:
        return await _in_course_lookup(question, scope, enrolled_ids, enrolled_titles)
```

(f) Insert this new function directly after `course_lookup` (after line 134):

```python
async def _in_course_lookup(question: str, scope: ChatScope, enrolled_ids: set[int],
                            enrolled_titles: list[str]) -> CourseLookup:
    """Player tutor (spec §3.2): this course's transcripts only — no catalog search, no
    other course. The case comes from the best in-course score."""
    slug = scope.course_slug or ""
    course = catalog_service.by_slug(slug)
    cid = course["id"] if course else None
    # The lecture title still steers the transcript search (4b02cc1).
    transcript_q = f"{scope.lecture_title} {question}" if scope.lecture_title else question
    scored = [(c, s) for c, s in await search_in_course(transcript_q, slug) if c.course_id == slug]
    best = max((s for _, s in scored), default=0.0)
    if best >= TRANSCRIPT_THRESHOLD:
        case, floor = LookupCase.IN_COURSE_MATCH, TRANSCRIPT_THRESHOLD
    elif best >= RELATED_THRESHOLD:
        case, floor = LookupCase.IN_COURSE_RELATED, RELATED_THRESHOLD
    else:
        return CourseLookup(case=LookupCase.IN_COURSE_NONE, hits=[], enrolled_titles=enrolled_titles)
    hits = [Hit(source="transcript", course_id=cid, course_slug=slug, course_title=c.course_title,
                title=c.lecture_title, score=s, enrolled=cid in enrolled_ids, text=c.text,
                lecture_id=c.lecture_id, start_time=c.start_time, end_time=c.end_time,
                url=course["url"] if course else None)
            for c, s in scored if s >= floor]
    here = _norm(scope.lecture_title or "")
    hits.sort(key=lambda h: (bool(here) and _norm(h.title) == here, h.score), reverse=True)
    return CourseLookup(case=case, hits=hits[:MAX_HITS], enrolled_titles=enrolled_titles)
```

(g) Replace the whole `render_facts` function (lines 156–178) with:

```python
def render_facts(lookup: CourseLookup, scope: ChatScope, weak_concepts: Optional[list[str]] = None) -> str:
    if scope.in_player:
        watched = catalog_service.by_slug(scope.course_slug or "")
        name = watched["title"] if watched else "this course"
        lines = [
            f"COURSE FACTS (looked up in {name} only — the course the student is watching):",
            f"CASE: {lookup.case.name}",
            f"COURSE: {name}. Answer from this course or general knowledge; "
            "never name, recommend or link another course.",
        ]
    else:
        lines = [
            "COURSE FACTS (looked up in the01.dev's course library for this question):",
            f"CASE: {lookup.case.name}",
            "Student is enrolled in: " + (", ".join(lookup.enrolled_titles) or "no courses yet"),
        ]
    if scope.lecture_title:
        course = catalog_service.by_slug(scope.course_slug or "")
        where = f" in {course['title']}" if course else ""
        lines.append(f'MODE: in-lecture — the student is watching "{scope.lecture_title}"{where} right now.')
        if course and not _has_lecture_excerpt(lookup, scope):
            lines.extend(_course_outline(course, scope.lecture_title))
    if weak_concepts:
        lines.append("Weak concepts in this course: " + ", ".join(weak_concepts))
    if lookup.hits:
        lines.append("Matches:")
        for i, h in enumerate(lookup.hits, 1):
            if scope.in_player:
                lines.append(f"{i}. [THIS COURSE] {h.title} @ {_mmss(h.start_time)} (score {h.score:.2f})")
            else:
                label = "ENROLLED" if h.enrolled else "NOT ENROLLED"
                where = f"{h.title} @ {_mmss(h.start_time)}" if h.source == "transcript" else h.title
                page = f" — course page: the01.dev{h.url}" if h.url else ""
                lines.append(f"{i}. [{label}] {h.course_title} → {where} ({h.source}, score {h.score:.2f}){page}")
            lines.append(f'   "{h.text[:600]}"')
    return "\n".join(lines)
```

- [ ] **Step 4: Run the lookup tests**

Run: `cd backend && .venv/bin/pytest tests/test_course_lookup.py -q`
Expected: `32 passed` (15 pre-existing + 17 new).

- [ ] **Step 5: Write the failing pipeline / route / prompt tests**

Append to `backend/tests/test_chat_pipeline.py`:

```python
async def test_no_pointer_in_the_player_even_for_a_not_enrolled_lookup(wired, monkeypatch):
    # The player tutor never mentions another course (spec §3.2): _missing_pointer is off.
    # wired lookup is NOT_ENROLLED_MATCH → custom-library with a url; the answer has no url.
    async def fake_stream(*, system_prompt, history, question, student_id, model=None, **player_kw):
        yield {"type": "token", "value": "Short answer."}  # **player_kw: Task D adds in_course for the player
    monkeypatch.setattr(tutor_agent, "stream_answer", fake_stream)
    req = chat_pipeline.TurnRequest(question="what is npm link", student_id="alice",
                                    scope=cl.ChatScope(course_slug="react-perf", lecture_title="4.1 - x",
                                                       in_player=True),
                                    history=[], memory_slug="react-perf")
    events = [e async for e in chat_pipeline.chat_turn(req)]
    assert [e["value"] for e in events if e["type"] == "token"] == ["Short answer."]


def test_missing_pointer_is_none_for_any_player_scope():
    hit = cl.Hit(source="catalog", course_id=1, course_slug="programming-language", course_title="Build a PL",
                 title="Lexers", score=0.6, enrolled=False, url="/course/1")
    lookup = cl.CourseLookup(case=cl.LookupCase.NOT_ENROLLED_MATCH, hits=[hit], enrolled_titles=[])
    assert chat_pipeline._missing_pointer(lookup, "answer", cl.ChatScope(course_slug="x", in_player=True)) is None
    assert chat_pipeline._missing_pointer(lookup, "answer", cl.ChatScope()) is not None
```

Append to `backend/tests/test_player_tutor_route.py`:

```python
def test_player_route_marks_the_scope_in_player(client, monkeypatch):
    seen = {}

    async def fake_turn(req, model=None):
        seen["req"] = req
        yield {"type": "done"}

    monkeypatch.setattr(chat_pipeline, "chat_turn", fake_turn)
    client.post("/api/ai/tutor/stream", json=_body(course_id="custom-library"))
    assert seen["req"].scope.in_player is True
    assert seen["req"].scope.course_slug == "custom-library"
```

Append to `backend/tests/test_ask_chat_route.py`:

```python
def test_ask_route_never_sets_in_player_even_with_a_course_filter(client, monkeypatch):
    seen = {}

    async def fake_turn(req, model=None):
        seen["req"] = req
        yield {"type": "done"}

    monkeypatch.setattr(chat_pipeline, "chat_turn", fake_turn)
    client.post("/api/hermes/chat", json={"question": "what is npm link", "course_slug": "custom-library"})
    assert seen["req"].scope.course_slug == "custom-library"
    assert seen["req"].scope.in_player is False
```

Append to `backend/tests/test_grounding_prompt.py`:

```python
def test_prompt_has_the_in_course_cases_and_tone_matching():
    text = loader.read_grounding_prompt()
    for marker in ("CASE: IN_COURSE_MATCH", "CASE: IN_COURSE_RELATED", "CASE: IN_COURSE_NONE"):
        assert marker in text
    assert "match the student's tone, vocabulary and level from their messages and STUDENT MEMORY" in text
    assert "never name, recommend or link another course" in text.lower()
    assert "is about the current lecture whatever the in_course case" in " ".join(text.lower().split())
```

- [ ] **Step 6: Run them to verify they fail**

Run: `cd backend && .venv/bin/pytest tests/test_chat_pipeline.py tests/test_player_tutor_route.py tests/test_ask_chat_route.py tests/test_grounding_prompt.py -q`
Expected: 4 FAIL — `test_no_pointer_in_the_player_even_for_a_not_enrolled_lookup` (pointer appended), `test_missing_pointer_is_none_for_any_player_scope`, `test_player_route_marks_the_scope_in_player` (`in_player is False`), `test_prompt_has_the_in_course_cases_and_tone_matching`. `test_ask_route_never_sets_in_player_even_with_a_course_filter` already passes (it pins the Ask behaviour).

- [ ] **Step 7: Implement pipeline, route and prompt**

(a) `backend/app/services/chat_pipeline.py` — in `_missing_pointer`, replace the first two body lines (46–47):

```python
    if lookup.case != LookupCase.NOT_ENROLLED_MATCH:
        return None
```
with:
```python
    if scope.in_player:
        return None  # the player tutor never points at another course (spec §3.2)
    if lookup.case != LookupCase.NOT_ENROLLED_MATCH:
        return None
```

(b) `backend/app/main.py` line 182 — replace:
```python
        scope=ChatScope(course_slug=req.course_id, lecture_title=lecture or None),
```
with:
```python
        scope=ChatScope(course_slug=req.course_id, lecture_title=lecture or None, in_player=True),
```

(c) `backend/app/grounding/grounding_prompt.md` — insert between line 38 (last NO_MATCH bullet) and line 40 (`# MODE: in-lecture`):

```markdown

## CASE: IN_COURSE_MATCH
Only inside the video player. These COURSE FACTS were looked up in the course the
student is watching and nowhere else. The answer is in this course.
- Answer from the matched excerpt and cite the lecture and timestamp, e.g.
  "around 03:20 in 11.1 - Publishing using `np`".
- If you go beyond what the lecture says, say so.

## CASE: IN_COURSE_RELATED
This course touches on the question but does not answer it directly.
- Give a solid general answer first, from your general knowledge.
- Then one sentence pointing at the related part: "This course touches on it in
  {lecture} at {mm:ss}." Take the lecture and time from the first Match.

## CASE: IN_COURSE_NONE
This course does not cover it.
- Give a solid, accurate general answer. Don't claim it comes from the course, and
  say at most once that the course doesn't cover it.

## Every IN_COURSE case
- Never name, recommend or link another course, and never talk about enrollment. The
  student is in this course; keep them here.
- Always match the student's tone, vocabulary and level from their messages and STUDENT MEMORY:
  a casual beginner question gets plain words and one small example; a precise
  technical question gets a precise technical answer.
- With MODE: in-lecture, a vague question about the lecture ("give me an example", "what does
  this mean?") is about the current lecture whatever the IN_COURSE case: ground it in that
  lecture's excerpt if one is listed, else in the outline. Never answer it as off-topic.
```

(The test asserts `match the student's tone, vocabulary and level from their messages and STUDENT MEMORY` as one unbroken string — keep that phrase on one line.)

- [ ] **Step 8: Run the tests**

Run: `cd backend && .venv/bin/pytest tests/test_course_lookup.py tests/test_chat_pipeline.py tests/test_player_tutor_route.py tests/test_ask_chat_route.py tests/test_grounding_prompt.py -q`
Expected: all pass.

- [ ] **Step 9: Calibrate RELATED_THRESHOLD on the real transcripts**

Create `backend/scripts/calibrate_in_course.py`:

```python
"""Measure in-course (player) transcript scores on labelled questions for Build a Custom
Library and suggest course_lookup.RELATED_THRESHOLD (spec §3.2). Needs the real
transcripts in seed_transcripts.json.

Run from backend/ (blanks DATABASE_URL itself — in-memory store, never production):
    .venv/bin/python scripts/calibrate_in_course.py
"""
import asyncio
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from dotenv import load_dotenv  # noqa: E402

os.environ["DATABASE_URL"] = ""
load_dotenv(Path(__file__).resolve().parents[1] / ".env")

if not os.getenv("OPENAI_API_KEY"):
    print("calibrate_in_course: OPENAI_API_KEY is not set — thresholds are only meaningful "
          "for OpenAI embeddings. Aborting.")
    sys.exit(2)

from app.services import course_lookup as cl  # noqa: E402

SLUG = "custom-library"
# (question, label): "match" = a lecture of this course answers it; "related" = a lecture
# touches on it; "none" = nothing in this course is about it.
LABELLED = [
    ("how do I publish my package with np", "match"),
    ("what does npm link do", "match"),
    ("what is an IIFE and why do we use it", "match"),
    ("how do I attach my library to the window object", "match"),
    ("what are ES modules", "match"),
    ("how do regular expressions help build the library methods", "match"),
    ("what is a closure in javascript", "related"),
    ("how does semantic versioning decide the next version number", "related"),
    ("what is a symlink", "related"),
    ("how do I write unit tests with jest", "related"),
    ("how do I bake sourdough bread", "none"),
    ("how does React reconciliation work", "none"),
    ("what is a SQL join", "none"),
    ("how does kubernetes schedule pods", "none"),
    ("what is the CSS box model", "none"),
]
UNLABELLED = ["how does the event loop work", "give me an example", "take me to where you publish the npm package"]


async def best(q: str):
    rows = await cl.search_in_course(q, SLUG, top_k=1)
    return (rows[0][1], rows[0][0].lecture_title, rows[0][0].start_time) if rows else (0.0, "-", 0)


async def main() -> None:
    scored = []
    for q, label in LABELLED + [(q, "?") for q in UNLABELLED]:
        s, title, t = await best(q)
        if label != "?":
            scored.append((label, s))
        print(f"{label:8} {s:.3f}  {title[:44]:44} {t // 60:02d}:{t % 60:02d}  {q}")
    none_max = max(s for l, s in scored if l == "none")
    related_min = min(s for l, s in scored if l == "related")
    match_min = min(s for l, s in scored if l == "match")
    print(f"\nnone max {none_max:.3f} | related min {related_min:.3f} | match min {match_min:.3f} "
          f"| TRANSCRIPT_THRESHOLD {cl.TRANSCRIPT_THRESHOLD} | current RELATED_THRESHOLD {cl.RELATED_THRESHOLD}")
    cap = round(cl.TRANSCRIPT_THRESHOLD - 0.02, 2)
    if related_min > none_max:
        pick = round((none_max + related_min) / 2, 2)
        how = "midpoint of none-max and related-min"
    else:
        pick = round(none_max + 0.01, 2)
        how = "no clean split — just above the best 'none'"
    print(f"suggested RELATED_THRESHOLD = {min(pick, cap):.2f} ({how}; capped at {cap})")


asyncio.run(main())
```

Run: `cd backend && .venv/bin/python scripts/calibrate_in_course.py`
Expected: 18 score lines and a `suggested RELATED_THRESHOLD = 0.xx (…)` line. Check each labelled line's printed lecture: if a "related"/"match" label is plainly wrong for this course (e.g. the best lecture shown has nothing to do with the question), fix that label in `LABELLED`, re-run, and mention it in the commit. Then set `RELATED_THRESHOLD` in `course_lookup.py` to the suggested value and replace its comment with one that records the run, e.g.:

```python
# Player only (spec §3.2): below TRANSCRIPT_THRESHOLD but at least this → "this course
# touches on it". calibrated 2026-10-05 on 15 labelled custom-library questions
# (scripts/calibrate_in_course.py): none max 0.xx, related min 0.xx → 0.xx.
RELATED_THRESHOLD = 0.xx
```
(Write the real numbers — the test suite pins its own thresholds, so it does not depend on this value.)

- [ ] **Step 10: Full suite**

Run: `bash backend/scripts/run_tests.sh`
Expected: `ALL PASSED`.

- [ ] **Step 11: Commit**

```bash
git add backend/app/services/course_lookup.py backend/app/services/chat_pipeline.py backend/app/main.py backend/app/grounding/grounding_prompt.md backend/scripts/calibrate_in_course.py backend/tests/test_course_lookup.py backend/tests/test_chat_pipeline.py backend/tests/test_player_tutor_route.py backend/tests/test_ask_chat_route.py backend/tests/test_grounding_prompt.py
git commit -m "feat(player-tutor): course-first lookup — in-course match/related/none, no other course, tone matching

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task D: `find_moment` tool + `navigate` SSE event

**Files:**
- Modify: `backend/app/services/tutor_agent.py` (imports 9–23, `ChatContext` 26–28, `search_course_content` 54–70, new tool after `explain_concept` 119–124, `TOOLS` 127–128, `stream_answer` 136–155)
- Modify: `backend/app/services/tool_descriptions.py` (append `FIND_MOMENT`)
- Modify: `backend/app/services/chat_pipeline.py` (`chat_turn` lines 86–119)
- Modify: `backend/app/grounding/grounding_prompt.md` (`# Tools` list)
- Test (append only): `backend/tests/test_tutor_agent.py`, `backend/tests/test_chat_pipeline.py`, `backend/tests/test_grounding_prompt.py`

**Interfaces:**
- Consumes (Task C): `course_lookup.search_in_course(query: str, course_slug: str, top_k: int = 8) -> list[tuple[TranscriptChunk, float]]`, `course_lookup.RELATED_THRESHOLD`, `ChatScope.in_player`. Both are read as module attributes at call time (`cl.search_in_course`, `cl.RELATED_THRESHOLD`) so the calibrated value and test monkeypatches apply.
- Produces:
  - `tutor_agent.ChatContext(student_id: str, in_course: Optional[str] = None)`.
  - `tutor_agent.find_moment` — LangChain tool `find_moment(what: str)`, `response_format="content_and_artifact"`. Content: JSON `{"lecture_title", "start_time", "end_time", "excerpt", "score"}` or `{"found": false}`. Artifact: `{"course_slug", "lecture_title", "start_time"}` or `None`.
  - `tutor_agent.tools_for(in_course: Optional[str]) -> list` — `TOOLS` when falsy, `TOOLS + [find_moment]` otherwise.
  - `tutor_agent.stream_answer(*, system_prompt, history, question, student_id, model=None, in_course: Optional[str] = None)` — new internal event `{"type": "moment", "moment": <artifact>}` per successful `find_moment` call. Never sent to the client.
  - `chat_pipeline.chat_turn` passes `in_course=req.scope.course_slug` to `stream_answer` **only** when `req.scope.in_player` (Ask turns call it exactly as before, so the existing fakes without an `in_course` parameter keep working), and yields at most one client event `{"type": "navigate", "course_slug": str, "lecture_title": str, "start_time": int}` immediately before `{"type": "done"}`, built from the last `moment`.
  - Inside the player, the follow-up tool `search_course_content` searches only `in_course` and labels excerpts `[THIS COURSE]` (spec §3.2 "every search … comes from the course being watched").

- [ ] **Step 1: Write the failing agent tests**

Append to `backend/tests/test_tutor_agent.py`:

```python
# ---- find_moment (player only) — spec §3.3 -----------------------------------

def _moment_chunk(course="custom-library", lecture="11.1 - Publishing using `np`", start=200):
    from app.models import TranscriptChunk
    return TranscriptChunk(chunk_id=f"{course}-10-0-3", course_id=course, course_title="Build a Custom Library",
                           lecture_id=f"{course}-10-0", lecture_title=lecture, text="now run np " * 60,
                           start_time=start, end_time=start + 55)


def _player_runtime(slug="custom-library"):
    from types import SimpleNamespace
    return SimpleNamespace(context=tutor_agent.ChatContext(student_id="alice", in_course=slug))


def test_find_moment_is_bound_only_in_the_player():
    assert tutor_agent.find_moment not in tutor_agent.TOOLS
    assert tutor_agent.tools_for(None) == tutor_agent.TOOLS
    assert tutor_agent.tools_for("custom-library") == tutor_agent.TOOLS + [tutor_agent.find_moment]


def test_find_moment_schema_takes_only_what():
    props = convert_to_openai_tool(tutor_agent.find_moment)["function"]["parameters"]["properties"]
    assert list(props) == ["what"]


async def test_find_moment_returns_the_best_in_course_passage(monkeypatch):
    import json
    from app.services import course_lookup
    seen = {}

    async def fake_search(query, course_slug, top_k=8):
        seen["args"] = (query, course_slug, top_k)
        return [(_moment_chunk(), 0.66)]

    monkeypatch.setattr(course_lookup, "search_in_course", fake_search)
    monkeypatch.setattr(course_lookup, "RELATED_THRESHOLD", 0.40)
    content, artifact = await tutor_agent.find_moment.coroutine(what="publish with np", runtime=_player_runtime())
    assert seen["args"] == ("publish with np", "custom-library", 1)
    body = json.loads(content)
    assert body["lecture_title"] == "11.1 - Publishing using `np`"
    assert (body["start_time"], body["end_time"], body["score"]) == (200, 255, 0.66)
    assert 0 < len(body["excerpt"]) <= 400
    assert artifact == {"course_slug": "custom-library", "lecture_title": "11.1 - Publishing using `np`",
                        "start_time": 200}


async def test_find_moment_below_the_related_threshold_is_not_found(monkeypatch):
    from app.services import course_lookup

    async def weak(query, course_slug, top_k=8):
        return [(_moment_chunk(), 0.39)]

    monkeypatch.setattr(course_lookup, "search_in_course", weak)
    monkeypatch.setattr(course_lookup, "RELATED_THRESHOLD", 0.40)
    assert await tutor_agent.find_moment.coroutine(what="x", runtime=_player_runtime()) == ('{"found": false}', None)


async def test_find_moment_never_returns_another_course(monkeypatch):
    from app.services import course_lookup

    async def leaky(query, course_slug, top_k=8):
        return [(_moment_chunk(course="react-perf", lecture="4.1 - React.memo"), 0.9)]

    monkeypatch.setattr(course_lookup, "search_in_course", leaky)
    assert await tutor_agent.find_moment.coroutine(what="x", runtime=_player_runtime()) == ('{"found": false}', None)


async def test_find_moment_without_a_course_in_context_is_not_found(monkeypatch):
    from types import SimpleNamespace
    from app.services import course_lookup

    async def boom(*a, **k):
        raise AssertionError("no course → no search")

    monkeypatch.setattr(course_lookup, "search_in_course", boom)
    runtime = SimpleNamespace(context=tutor_agent.ChatContext(student_id="alice"))
    assert await tutor_agent.find_moment.coroutine(what="x", runtime=runtime) == ('{"found": false}', None)


async def test_player_stream_yields_a_moment_event_from_find_moment(monkeypatch):
    from app.services import course_lookup

    async def fake_search(query, course_slug, top_k=8):
        return [(_moment_chunk(), 0.7)]

    monkeypatch.setattr(course_lookup, "search_in_course", fake_search)
    model = FakeToolModel(messages=iter([
        AIMessage("", tool_calls=[{"name": "find_moment", "args": {"what": "publish with np"}, "id": "c1"}]),
        AIMessage("It's at 03:20 in 11.1."),
    ]))
    events = await _collect(tutor_agent.stream_answer(
        system_prompt="sys", history=[], question="take me to where you publish", student_id="alice",
        model=model, in_course="custom-library"))
    assert [e for e in events if e["type"] == "moment"] == [{"type": "moment", "moment": {
        "course_slug": "custom-library", "lecture_title": "11.1 - Publishing using `np`", "start_time": 200}}]
    assert not [e for e in events if e["type"] == "cards"]
    assert "".join(e["value"] for e in events if e["type"] == "token").endswith("It's at 03:20 in 11.1.")


async def test_ask_stream_has_no_find_moment(monkeypatch):
    from app.services import course_lookup

    async def boom(*a, **k):
        raise AssertionError("find_moment must not run outside the player")

    monkeypatch.setattr(course_lookup, "search_in_course", boom)
    model = FakeToolModel(messages=iter([
        AIMessage("", tool_calls=[{"name": "find_moment", "args": {"what": "publish"}, "id": "c1"}]),
        AIMessage("ok"),
    ]))
    events = await _collect(tutor_agent.stream_answer(
        system_prompt="sys", history=[], question="take me there", student_id="alice", model=model))
    assert not [e for e in events if e["type"] == "moment"]


async def test_follow_up_search_in_the_player_stays_in_this_course(monkeypatch):
    from app.services import course_lookup

    async def all_courses(q, top_k=5):
        raise AssertionError("the player's follow-up search must not search every course")

    async def fake_search(query, course_slug, top_k=8):
        assert course_slug == "custom-library"
        return [(_moment_chunk(), 0.7), (_moment_chunk(lecture="8.1 - The `npm link` command", start=10), 0.30)]

    monkeypatch.setattr(grounding, "retrieve", all_courses)
    monkeypatch.setattr(course_lookup, "search_in_course", fake_search)
    content, cards = await tutor_agent.search_course_content.coroutine(query="np", runtime=_player_runtime())
    assert [c["lecture_title"] for c in cards] == ["11.1 - Publishing using `np`"]
    assert "[THIS COURSE]" in content and "ENROLLED" not in content
```

- [ ] **Step 2: Run them to verify they fail**

Run: `cd backend && .venv/bin/pytest tests/test_tutor_agent.py -q`
Expected: 8 of the 9 new tests FAIL (`AttributeError: module 'app.services.tutor_agent' has no attribute 'find_moment'` / `ChatContext.__init__() got an unexpected keyword argument 'in_course'` / `stream_answer() got an unexpected keyword argument 'in_course'`). `test_ask_stream_has_no_find_moment` already passes (create_agent answers an unknown tool call with an error ToolMessage) — it pins that find_moment never runs on the Ask page. Existing tests still pass.

- [ ] **Step 3: Add the tool description**

Append to `backend/app/services/tool_descriptions.py`:

```python
FIND_MOMENT = (
    "Video player only. Find the moment in THIS course where something is shown or said, so the "
    "player can jump there. Call it whenever the student asks to be taken, shown or jumped to a "
    "part (\"take me to where…\", \"show me the part about…\", \"where does he…\"). Pass `what` as a "
    "short search phrase rewritten from the request (e.g. 'publish the package with np'). Returns "
    "the lecture title, start/end second, an excerpt and a score — or {\"found\": false} when this "
    "course has no such part. When found, the player jumps there by itself: tell the student in one "
    "or two sentences what is there, naming that lecture and time exactly as returned. Never invent "
    "a lecture or a time."
)
```

- [ ] **Step 4: Implement the tool, the per-turn tool list and the moment event**

In `backend/app/services/tutor_agent.py`:

(a) Imports — replace line 21 `from app.services.course_lookup import TRANSCRIPT_THRESHOLD` with:

```python
from app.models import SearchResult
from app.services import course_lookup as cl
from app.services.course_lookup import TRANSCRIPT_THRESHOLD
```

(b) Replace `ChatContext` (lines 26–28) with:

```python
@dataclass(frozen=True)
class ChatContext:
    student_id: str
    in_course: Optional[str] = None  # player only: the course being watched (spec §3.2, §3.3)
```

(c) Replace the body of `search_course_content` (lines 59–70, from the `# Same bar as course_lookup` comment to `return text, cards`) with:

```python
    # Same bar as course_lookup: weak matches would surface as citation cards for unrelated lectures.
    in_course = runtime.context.in_course
    if in_course:  # player: this course only (spec §3.2)
        pairs = await cl.search_in_course(query, in_course, top_k=5)
        results = [SearchResult(chunk=c, score=s) for c, s in pairs
                   if c.course_id == in_course and s >= TRANSCRIPT_THRESHOLD]
    else:
        results = [r for r in await grounding.retrieve(query, top_k=5) if r.score >= TRANSCRIPT_THRESHOLD]
    if not results:
        return "No matching course content.", []
    enrolled_ids = set() if in_course else await _enrolled_ids(runtime.context.student_id)
    cards = [c.model_dump() for c in grounding.build_sources(results)]
    text = "\n".join(
        f"[{'THIS COURSE' if in_course else _enrollment_label(r.chunk.course_id, enrolled_ids)}] "
        f"{r.chunk.course_title} → {r.chunk.lecture_title} @ {c['timestamp']}: {r.chunk.text}"
        for r, c in zip(results, cards)
    )
    return text, cards
```

(d) Insert after `explain_concept` (after line 124), before `TOOLS`:

```python
_NOT_FOUND = '{"found": false}'


@tool("find_moment", description=D.FIND_MOMENT, response_format="content_and_artifact")
async def find_moment(
    what: Annotated[str, "Short search phrase for the part to show, rewritten from the student's request, "
                         "e.g. 'publish the package with np'."],
    runtime: ToolRuntime[ChatContext],
) -> tuple[str, Optional[dict]]:
    """Only ever returns a real chunk of the watched course — the model cannot invent a time."""
    slug = runtime.context.in_course
    if not slug:
        return _NOT_FOUND, None
    rows = await cl.search_in_course(what, slug, top_k=1)
    if not rows:
        return _NOT_FOUND, None
    chunk, score = rows[0]
    if chunk.course_id != slug or score < cl.RELATED_THRESHOLD:
        return _NOT_FOUND, None
    found = {"lecture_title": chunk.lecture_title, "start_time": chunk.start_time, "end_time": chunk.end_time,
             "excerpt": chunk.text[:400], "score": round(score, 3)}
    return _dump(found), {"course_slug": slug, "lecture_title": chunk.lecture_title, "start_time": chunk.start_time}
```

(e) After the `TOOLS = [...]` list (after line 128) add:

```python


def tools_for(in_course: Optional[str]) -> list:
    """The tool list is chosen per turn: find_moment exists only inside the player."""
    return TOOLS + [find_moment] if in_course else TOOLS
```

(f) Replace `stream_answer` (lines 136–155) with:

```python
async def stream_answer(*, system_prompt: str, history: list[dict], question: str, student_id: str,
                        model: Optional[object] = None, in_course: Optional[str] = None) -> AsyncIterator[dict]:
    agent = create_agent(model or _default_model(), tools=tools_for(in_course), system_prompt=system_prompt,
                         context_schema=ChatContext)
    messages = [HumanMessage(t["content"]) if t["role"] == "user" else AIMessage(t["content"])
                for t in history if t.get("role") in ("user", "assistant")]
    messages.append(HumanMessage(question))
    spoke = after_tool = False
    async for chunk, meta in agent.astream({"messages": messages},
                                           context=ChatContext(student_id=student_id, in_course=in_course),
                                           stream_mode="messages"):
        if isinstance(chunk, AIMessageChunk) and meta.get("langgraph_node") == "model" and chunk.text:
            if spoke and after_tool:
                # "Let me check." + tool call, then the answer: keep them from running together.
                yield {"type": "token", "value": "\n\n"}
            spoke, after_tool = True, False
            yield {"type": "token", "value": chunk.text}
        elif isinstance(chunk, ToolMessage):
            after_tool = True
            if chunk.name == "find_moment":
                if chunk.artifact:
                    yield {"type": "moment", "moment": dict(chunk.artifact)}
            elif chunk.artifact:
                yield {"type": "cards", "cards": list(chunk.artifact)}
```

- [ ] **Step 5: Run the agent tests**

Run: `cd backend && .venv/bin/pytest tests/test_tutor_agent.py -q`
Expected: all pass (0 failures).

- [ ] **Step 6: Write the failing pipeline + prompt tests**

Append to `backend/tests/test_chat_pipeline.py`:

```python
# ---- navigate event (player only) — spec §3.3 --------------------------------

M1 = {"course_slug": "custom-library", "lecture_title": "8.2 - Testing Our NPM Package", "start_time": 40}
M2 = {"course_slug": "custom-library", "lecture_title": "11.1 - Publishing using `np`", "start_time": 200}


def _player_agent(monkeypatch, calls, events, raise_at_end=False):
    async def fake_stream(*, system_prompt, history, question, student_id, model=None, in_course=None):
        calls["in_course"] = in_course
        for e in events:
            yield e
        if raise_at_end:
            raise RuntimeError("boom")
    monkeypatch.setattr(tutor_agent, "stream_answer", fake_stream)


def _player_req(q="take me to where you publish the npm package"):
    scope = cl.ChatScope(course_slug="custom-library", lecture_title="8.1 - The `npm link` command", in_player=True)
    return chat_pipeline.TurnRequest(question=q, student_id="alice", scope=scope, history=[],
                                     memory_slug="custom-library")


async def test_player_turn_emits_one_navigate_just_before_done_and_the_last_moment_wins(wired, monkeypatch):
    _player_agent(monkeypatch, wired, [{"type": "moment", "moment": M1}, {"type": "token", "value": "Here."},
                                       {"type": "moment", "moment": M2}])
    events = [e async for e in chat_pipeline.chat_turn(_player_req())]
    assert [e for e in events if e["type"] == "navigate"] == [{
        "type": "navigate", "course_slug": "custom-library",
        "lecture_title": "11.1 - Publishing using `np`", "start_time": 200}]
    assert [e["type"] for e in events][-2:] == ["navigate", "done"]
    assert "moment" not in [e["type"] for e in events]
    assert wired["in_course"] == "custom-library"
    assert wired["recorded"][0][3] == "Here."


async def test_player_turn_without_a_moment_has_no_navigate(wired, monkeypatch):
    _player_agent(monkeypatch, wired, [{"type": "token", "value": "Answer."}])
    events = [e async for e in chat_pipeline.chat_turn(_player_req("what is npm link"))]
    assert [e["type"] for e in events] == ["sources", "token", "done"]


async def test_player_turn_agent_failure_sends_no_navigate(wired, monkeypatch):
    _player_agent(monkeypatch, wired, [{"type": "moment", "moment": M2}], raise_at_end=True)
    events = [e async for e in chat_pipeline.chat_turn(_player_req())]
    assert [e["type"] for e in events] == ["sources", "error"]


async def test_ask_turn_calls_the_agent_as_before_and_never_navigates(wired, monkeypatch):
    # _agent's fake has no in_course parameter: passing it on an Ask turn would raise → error event.
    _agent(monkeypatch, wired, events=[{"type": "moment", "moment": M2}, {"type": "token", "value": "x"}])
    events = [e async for e in chat_pipeline.chat_turn(_req())]
    types = [e["type"] for e in events]
    assert "navigate" not in types and "error" not in types and types[-1] == "done"
```

Append to `backend/tests/test_grounding_prompt.py`:

```python
def test_prompt_lists_find_moment():
    text = loader.read_grounding_prompt()
    assert "find_moment" in text and "never invent a lecture or a time" in text.lower()
```

- [ ] **Step 7: Run them to verify they fail**

Run: `cd backend && .venv/bin/pytest tests/test_chat_pipeline.py tests/test_grounding_prompt.py -q`
Expected: 2 FAIL — `test_player_turn_emits_one_navigate_just_before_done_and_the_last_moment_wins` (no navigate event) and `test_prompt_lists_find_moment`. The other three new tests already pass; they pin behaviour that must not change.

- [ ] **Step 8: Implement the navigate event**

In `backend/app/services/chat_pipeline.py` replace lines 87–119 (from `seen = {_card_key(c) for c in cards}` to the final `yield {"type": "done"}`) with:

```python
    seen = {_card_key(c) for c in cards}
    extra: list[dict] = []
    answer: list[str] = []
    moment: Optional[dict] = None
    # Only the player gets find_moment; Ask turns call the agent exactly as before.
    player_kw = {"in_course": req.scope.course_slug} if req.scope.in_player else {}
    try:
        async with contextlib.aclosing(tutor_agent.stream_answer(
                system_prompt=system, history=history, question=question,
                student_id=req.student_id, model=model, **player_kw)) as stream:
            async for event in stream:
                if event["type"] == "token":
                    answer.append(event["value"])
                    yield event
                elif event["type"] == "cards":
                    for c in event["cards"]:
                        if _card_key(c) not in seen:
                            seen.add(_card_key(c))
                            extra.append(c)
                elif event["type"] == "moment":
                    moment = event["moment"]  # last find_moment call wins
    except Exception as e:  # noqa: BLE001 — never leak provider errors to the student
        print(f"[chat_turn] agent failed: {e!r}")
        yield {"type": "error", "message": _ERROR}
        return

    pointer = _missing_pointer(lookup, "".join(answer), req.scope)
    if pointer:
        answer.append(pointer)
        yield {"type": "token", "value": pointer}
    if extra:
        # The client replaces its card list on each sources event, so send the full deduped list.
        yield _sources(cards + extra)
    try:
        await memory_service.record_turn(req.student_id, req.memory_slug, question, "".join(answer))
    except Exception as e:  # noqa: BLE001 — never fail the answer over memory persistence
        print(f"[chat_turn] record_turn failed: {e!r}")
    if moment and req.scope.in_player:
        # Spec §3.3: once per turn, before done. The course is the watched one, never the model's.
        yield {"type": "navigate", "course_slug": req.scope.course_slug,
               "lecture_title": moment["lecture_title"], "start_time": int(moment["start_time"])}
    yield {"type": "done"}
```

In `backend/app/grounding/grounding_prompt.md`, add this bullet at the end of the `# Tools` list (after the `explain_concept` bullet, before `# Style`):

```markdown
- find_moment (video player only): when the student asks to be taken, shown or jumped
  to a part ("take me to where…", "show me the part about…"). Rewrite the request into a
  short search phrase. When it finds the moment the player jumps there by itself: say in
  one or two sentences what is there, naming the lecture and time it returned. Never invent a lecture or a time.
  If it returns found: false, say this course doesn't seem to show that, then answer briefly.
```

- [ ] **Step 9: Run the tests**

Run: `cd backend && .venv/bin/pytest tests/test_tutor_agent.py tests/test_chat_pipeline.py tests/test_grounding_prompt.py -q`
Expected: all pass.

- [ ] **Step 10: Full suite**

Run: `bash backend/scripts/run_tests.sh`
Expected: `ALL PASSED` (the MCP venv also imports `tool_descriptions`; a new constant there changes nothing for it).

- [ ] **Step 11: Commit**

```bash
git add backend/app/services/tutor_agent.py backend/app/services/tool_descriptions.py backend/app/services/chat_pipeline.py backend/app/grounding/grounding_prompt.md backend/tests/test_tutor_agent.py backend/tests/test_chat_pipeline.py backend/tests/test_grounding_prompt.py
git commit -m "feat(player-tutor): find_moment tool + navigate SSE event; follow-up search stays in course

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task E: Frontend — `navigate` → jump to lecture + second, "Jump to …" link

**Files:**
- Create: `frontend/src/lib/lectureMatch.ts`
- Create: `frontend/scripts/lectureMatch.check.ts` (Node assertion script; outside `tsconfig.app.json`'s `include: ["src"]`, run with Node 22's `--experimental-strip-types`; the repo has no frontend test runner)
- Modify: `frontend/src/lib/learnApi.ts:89-129` (`streamTutor`)
- Modify: `frontend/src/components/learn/PlayerTutor.tsx` (imports 1–6, `Msg` 8–13, props 20–30, `streamTutor` callbacks 61–73, assistant bubble 145–154)
- Modify: `frontend/src/pages/CoursePlayerPage.tsx` (imports 1–11, after `handleCanPlay` 107–112, `<PlayerTutor …>` 203)

**Interfaces:**
- Consumes (Task D): SSE event `{"type": "navigate", "course_slug": string, "lecture_title": string, "start_time": number}` sent once, right before `done`, on `/api/ai/tutor/stream`.
- Produces:
  - `learnApi.ts`: `export interface TutorNavigate { course_slug: string; lecture_title: string; start_time: number }`; `streamTutor(body, cb)` where `cb` gains optional `onNavigate?: (nav: TutorNavigate) => void`.
  - `lectureMatch.ts`: `normaliseLectureTitle(title: string): string`, `findLecture(chapters: Chapter[], title: string): LecturePosition | null` (`LecturePosition = { chapter: number; sub: number }`, 0-indexed positions in `track.courseContent`), `resolveJump(chapters: Chapter[], title: string, isLocked: (chapter: number) => boolean): LecturePosition | null`, `formatTimestamp(seconds: number): string` (`200 → "03:20"`).
  - `PlayerTutor` prop `onNavigate?: (nav: TutorNavigate) => boolean` — returns `true` only if the page found an unlocked lecture and jumped. The "Jump to <lecture> · mm:ss" link is shown only when it returned `true`; clicking it calls `onNavigate` again.
  - `CoursePlayerPage` `jumpTo(nav: TutorNavigate): boolean`.

- [ ] **Step 1: Write the failing matcher check**

Create `frontend/scripts/lectureMatch.check.ts`:

```ts
// Run: cd frontend && node --experimental-strip-types scripts/lectureMatch.check.ts
import assert from "node:assert/strict";
import tracks from "../src/data/tracks.ts";
import { findLecture, formatTimestamp, normaliseLectureTitle, resolveJump } from "../src/lib/lectureMatch.ts";

const chapters = [
  { name: "Chapter 8", subchapters: [
    { name: "8.1 - The `npm link` command", src: "" },
    { name: "8.2 - Testing Our NPM Package", src: "" },
  ] },
  { name: "Chapter 11", subchapters: [{ name: "11.1 - Publishing using `np`", src: "" }] },
];

assert.equal(normaliseLectureTitle("  11.1 -  Publishing using `np` "), "11.1 - publishing using np");
assert.deepEqual(findLecture(chapters, "11.1 - Publishing using `np`"), { chapter: 1, sub: 0 });
assert.deepEqual(findLecture(chapters, "11.1 - Publishing using np"), { chapter: 1, sub: 0 });
assert.deepEqual(findLecture(chapters, "8.1 - the NPM LINK   command"), { chapter: 0, sub: 0 });
assert.deepEqual(findLecture(chapters, "8.2 - Testing Our NPM Package"), { chapter: 0, sub: 1 });
assert.equal(findLecture(chapters, "9.9 - Not a lecture"), null);
assert.equal(findLecture(chapters, ""), null);
assert.equal(findLecture(chapters, "   "), null);
assert.equal(findLecture(chapters, "11.1"), null); // never a prefix match
const nothingLocked = () => false;
assert.deepEqual(resolveJump(chapters, "11.1 - Publishing using np", nothingLocked), { chapter: 1, sub: 0 });
assert.equal(resolveJump(chapters, "11.1 - Publishing using np", (c) => c >= 1), null); // locked chapter
assert.equal(resolveJump(chapters, "9.9 - Not a lecture", nothingLocked), null);
assert.equal(formatTimestamp(200), "03:20");
assert.equal(formatTimestamp(0), "00:00");
assert.equal(formatTimestamp(59.9), "00:59");
assert.equal(formatTimestamp(3725), "62:05");

// Every real lecture of Build a Custom Library (course id 2) resolves to its own position.
const course = tracks.find((t) => t.id === 2);
assert.ok(course, "course 2 missing from tracks.ts");
course.courseContent.forEach((ch, c) =>
  ch.subchapters.forEach((sub, s) => assert.deepEqual(findLecture(course.courseContent, sub.name), { chapter: c, sub: s })));
assert.deepEqual(findLecture(course.courseContent, "11.1 - Publishing using `np`"), { chapter: 10, sub: 0 });

console.log("lectureMatch: all checks passed");
```

- [ ] **Step 2: Run it to verify it fails**

Run: `cd frontend && node --experimental-strip-types scripts/lectureMatch.check.ts`
Expected: FAIL — `ERR_MODULE_NOT_FOUND` for `../src/lib/lectureMatch.ts`.

- [ ] **Step 3: Write the matcher**

Create `frontend/src/lib/lectureMatch.ts`:

```ts
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
```

- [ ] **Step 4: Run the check to verify it passes**

Run: `cd frontend && node --experimental-strip-types scripts/lectureMatch.check.ts`
Expected: `lectureMatch: all checks passed` (an `ExperimentalWarning` line about type stripping may precede it — fine), exit 0.

- [ ] **Step 5: Parse the `navigate` event in `streamTutor`**

In `frontend/src/lib/learnApi.ts`, insert directly above the `// Stream a tutor reply over SSE.` comment (line 89):

```ts
// The player tutor's "take me to …" (find_moment): sent once, right before "done".
export interface TutorNavigate {
  course_slug: string;
  lecture_title: string;
  start_time: number;
}

```

Replace the `cb` parameter line (line 97):

```ts
  cb: { onToken: (t: string) => void; onDone: () => void; onError: (e: Error) => void },
```
with:
```ts
  cb: {
    onToken: (t: string) => void;
    onDone: () => void;
    onError: (e: Error) => void;
    onNavigate?: (nav: TutorNavigate) => void;
  },
```

Replace the event dispatch (lines 121–123):

```ts
        if (msg.type === "token") cb.onToken(msg.value);
        else if (msg.type === "done") cb.onDone();
        else if (msg.type === "error") cb.onError(new Error(msg.message));
```
with:
```ts
        if (msg.type === "token") cb.onToken(msg.value);
        else if (msg.type === "navigate" && typeof msg.lecture_title === "string") {
          cb.onNavigate?.({
            course_slug: String(msg.course_slug ?? ""),
            lecture_title: msg.lecture_title,
            start_time: Math.max(0, Number(msg.start_time) || 0),
          });
        }
        else if (msg.type === "done") cb.onDone();
        else if (msg.type === "error") cb.onError(new Error(msg.message));
```

- [ ] **Step 6: PlayerTutor — forward the jump and show the link**

In `frontend/src/components/learn/PlayerTutor.tsx`:

(a) Replace lines 3–4:
```tsx
import { Sparkles, X, Send, Loader2, GraduationCap, User, Minus } from "lucide-react";
import { streamTutor } from "../../lib/learnApi";
```
with:
```tsx
import { Sparkles, X, Send, Loader2, GraduationCap, User, Minus, CirclePlay } from "lucide-react";
import { streamTutor } from "../../lib/learnApi";
import type { TutorNavigate } from "../../lib/learnApi";
import { formatTimestamp } from "../../lib/lectureMatch";
```
(Leave the existing unused `X` import exactly as it is — not this task's concern.)

(b) Replace the `Msg` interface (lines 8–13) with:
```tsx
interface Msg {
  id: string;
  role: "user" | "assistant";
  content: string;
  streaming?: boolean;
  jump?: TutorNavigate; // set only when the player actually jumped there
}
```

(c) Replace the props destructuring and type (lines 20–30) with:
```tsx
export function PlayerTutor({
  course,
  userId,
  lectureTitle,
  onOpenChange,
  onNavigate,
}: {
  course: Course;
  userId: string;
  lectureTitle: string;
  onOpenChange?: (open: boolean) => void;
  /** Jump the player to that lecture + second. Returns false if the lecture isn't in this course (or is locked). */
  onNavigate?: (nav: TutorNavigate) => boolean;
}) {
```

(d) In `send`, replace the `onToken` line (line 64):
```tsx
        onToken: (t) => patch((m) => ({ ...m, content: m.content + t })),
```
with:
```tsx
        onToken: (t) => patch((m) => ({ ...m, content: m.content + t })),
        onNavigate: (nav) => {
          if (nav.course_slug && nav.course_slug !== course.course_id) return; // never another course
          if (onNavigate?.(nav)) patch((m) => ({ ...m, jump: nav }));
        },
```

(e) Replace the assistant bubble body (lines 145–154):
```tsx
                  <div className="max-w-[82%] bg-zinc-800/70 border border-zinc-700/50 rounded-2xl rounded-tl-sm px-3 py-2">
                    {m.content || m.streaming ? (
                      <p className="text-[13px] text-zinc-100 leading-relaxed whitespace-pre-wrap">
                        {m.content}
                        {m.streaming && <span className="inline-block w-1.5 h-3.5 ml-0.5 align-text-bottom bg-indigo-400 animate-pulse" />}
                      </p>
                    ) : (
                      <Loader2 className="w-3.5 h-3.5 text-zinc-400 animate-spin" />
                    )}
                  </div>
```
with:
```tsx
                  <div className="max-w-[82%] bg-zinc-800/70 border border-zinc-700/50 rounded-2xl rounded-tl-sm px-3 py-2">
                    {m.content || m.streaming ? (
                      <p className="text-[13px] text-zinc-100 leading-relaxed whitespace-pre-wrap">
                        {m.content}
                        {m.streaming && <span className="inline-block w-1.5 h-3.5 ml-0.5 align-text-bottom bg-indigo-400 animate-pulse" />}
                      </p>
                    ) : (
                      <Loader2 className="w-3.5 h-3.5 text-zinc-400 animate-spin" />
                    )}
                    {m.jump && (
                      <button
                        onClick={() => m.jump && onNavigate?.(m.jump)}
                        className="mt-2 inline-flex items-center gap-1.5 text-[12px] text-indigo-300 hover:text-indigo-200 hover:underline underline-offset-2 text-left"
                      >
                        <CirclePlay className="w-3.5 h-3.5 flex-shrink-0" />
                        Jump to {m.jump.lecture_title} · {formatTimestamp(m.jump.start_time)}
                      </button>
                    )}
                  </div>
```

- [ ] **Step 7: CoursePlayerPage — resolve the lecture, switch, seek, play**

In `frontend/src/pages/CoursePlayerPage.tsx`:

(a) After line 10 (`import { PlayerTutor } …`) add:
```tsx
import { resolveJump } from "../lib/lectureMatch";
import type { TutorNavigate } from "../lib/learnApi";
```

(b) Insert directly after `handleCanPlay` (after line 112):
```tsx

  // The tutor's "take me to …" (spec §3.3): switch to the lecture, seek, play.
  // Returns false (no jump, no link) for an unknown or locked lecture.
  const jumpTo = (nav: TutorNavigate): boolean => {
    const pos = resolveJump(track.courseContent, nav.lecture_title, isLocked);
    if (!pos) return false;
    setExpandedChapter(pos.chapter);
    const v = videoRef.current;
    if (pos.chapter === activeChapter && pos.sub === activeSub && v) {
      if (v.readyState >= 1) v.currentTime = nav.start_time; // metadata loaded: seek now
      else seekTarget.current = nav.start_time;              // else handleCanPlay seeks
      v.play().catch(() => {});
    } else {
      // The [activeChapter, activeSub] effect reloads + plays; handleCanPlay applies the seek.
      seekTarget.current = nav.start_time;
      setActiveChapter(pos.chapter);
      setActiveSub(pos.sub);
    }
    return true;
  };
```

(c) Replace line 203:
```tsx
        <PlayerTutor course={aiCourse} userId={userId} lectureTitle={currentSub?.name || track.title} onOpenChange={setTutorOpen} />
```
with:
```tsx
        <PlayerTutor course={aiCourse} userId={userId} lectureTitle={currentSub?.name || track.title}
                     onOpenChange={setTutorOpen} onNavigate={jumpTo} />
```

- [ ] **Step 8: Type-check, build, matcher**

Run: `cd frontend && npx tsc -b && npm run build && node --experimental-strip-types scripts/lectureMatch.check.ts`
Expected: no TypeScript errors, Vite prints `✓ built in …`, then `lectureMatch: all checks passed`.

- [ ] **Step 9: Commit**

```bash
git add frontend/src/lib/lectureMatch.ts frontend/scripts/lectureMatch.check.ts frontend/src/lib/learnApi.ts frontend/src/components/learn/PlayerTutor.tsx frontend/src/pages/CoursePlayerPage.tsx
git commit -m "feat(player): tutor navigate event jumps to the lecture + second, with a Jump-to link fallback

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task F: Real-model, in-memory verification (player + Ask unchanged)

Runs the real OpenAI model and embeddings against the in-memory store (blank `DATABASE_URL`, like `backend/scripts/demo_check.py`), on the real transcripts from Task B. Needs network and the OpenAI key passed inline exactly as Task B Step 1 describes (never a `backend/.env` in the worktree), with `DATABASE_URL=` blank.

**Files:**
- Modify: `backend/scripts/demo_check.py` (docstring 1–24, imports 26–39, after `QUESTIONS` 49, guard 64–73)

**Interfaces:**
- Consumes: `ChatScope(course_slug, lecture_title, in_player=True)` (Task C), `chat_pipeline.chat_turn` yielding `{"type": "navigate", "course_slug", "lecture_title", "start_time"}` (Task D), `vector_store.chunks` holding the Task B chunks.
- Produces: `demo_check.py --player` — three in-player questions on `custom-library`; exit 1 on any failed check.

- [ ] **Step 1: Add `--player` to demo_check**

In `backend/scripts/demo_check.py`:

(a) In the module docstring, after the `--whole` lines (line 15), add:

```
  --player       instead of the Ask questions, run three in-player tutor turns on Build a
                 Custom Library (real model): "take me to where you publish the npm
                 package" must jump to 11.1 at a real chunk's second; "how does the event
                 loop work" and "give me an example" must not jump and must not name or
                 link another course.
```

(b) Change line 26 `import asyncio` to:
```python
import asyncio
import re
```

(c) Insert after the `QUESTIONS = [...]` list (after line 49):

```python
PLAYER_COURSE = "custom-library"
PLAYER_QUESTIONS = [
    # (question, lecture on screen, lecture the player must jump to — None = must not jump)
    ("take me to where you publish the npm package", "1.1 - What is this course", "11.1 - Publishing using `np`"),
    ("how does the event loop work", "8.1 - The `npm link` command", None),
    ("give me an example", "1.1 - What is this course", None),
]


async def player_checks(uid: str) -> int:
    """--player: the in-player tutor on Build a Custom Library, real model. Returns the failure count."""
    from app.services.vector_store import vector_store
    others = [c["title"] for c in catalog_service.all_courses() if c["slug"] != PLAYER_COURSE]
    failures = 0
    for i, (q, lecture, jump_to) in enumerate(PLAYER_QUESTIONS, 1):
        student = f"{uid}-p{i}"  # fresh student: no memory of an earlier turn
        scope = ChatScope(course_slug=PLAYER_COURSE, lecture_title=lecture, in_player=True)
        lk = await course_lookup(q, student, scope)
        top = f"{lk.hits[0].title} @ {lk.hits[0].start_time}s ({lk.hits[0].score:.2f})" if lk.hits else "-"
        req = chat_pipeline.TurnRequest(question=q, student_id=student, scope=scope, history=[],
                                        memory_slug=PLAYER_COURSE)
        text, navs, problems, detail = [], [], [], ""
        async for e in chat_pipeline.chat_turn(req):
            if e["type"] == "token":
                text.append(e["value"])
            elif e["type"] == "navigate":
                navs.append(e)
            elif e["type"] == "error":
                problems.append(f"error event: {e.get('message')}")
        answer = " ".join("".join(text).split())
        named = [t for t in others if t.lower() in answer.lower()]
        if named:
            problems.append(f"names another course: {named}")
        if re.search(r"the01\.dev/course/(?!2\b)\d+", answer):
            problems.append("links another course page")
        if len(navs) > 1:
            problems.append(f"{len(navs)} navigate events (max 1)")
        if jump_to is None and navs:
            problems.append(f"jumped when it should not: {navs[0]}")
        if jump_to is not None and not navs:
            problems.append("no navigate event")
        if jump_to is not None and navs:
            nav = navs[-1]
            chunk = next((c for c in vector_store.chunks if c.course_id == PLAYER_COURSE
                          and c.lecture_title == nav["lecture_title"] and c.start_time == nav["start_time"]), None)
            if nav["course_slug"] != PLAYER_COURSE:
                problems.append(f"navigate names course {nav['course_slug']!r}")
            if nav["lecture_title"] != jump_to:
                problems.append(f"jumped to {nav['lecture_title']!r}, expected {jump_to!r}")
            elif chunk is None:
                problems.append(f"no transcript chunk of {jump_to!r} starts at {nav['start_time']}s")
            else:
                t = nav["start_time"]
                detail = f"jump → {jump_to} @ {t // 60:02d}:{t % 60:02d}: \"{chunk.text[:200]}…\""
        failures += bool(problems)
        print(f"[{'ok' if not problems else 'FAIL'}] {lk.case.value:18} {q[:46]:46} (watching {lecture[:26]}) top: {top}")
        if detail:
            print(f"      {detail}")
        for p in problems:
            print(f"      ✗ {p}")
        print(f"      {answer}\n")
    return failures
```

(d) Replace the guard (lines 69–73):
```python
    # --full writes audit/memory/skill rows and --enroll writes enrollments: never outside
    # the in-memory store. Checked before any store or OpenAI call.
    if (full or enroll_arg is not None) and not isinstance(store, InMemoryStore):
        print(f"demo_check: --full and --enroll only run against the in-memory store, not "
              f"{type(store).__name__}. Re-run with `env DATABASE_URL= ...`.")
        sys.exit(2)
```
with:
```python
    # --full / --player write audit/memory/skill rows and --enroll writes enrollments: never
    # outside the in-memory store. Checked before any store or OpenAI call.
    player = "--player" in sys.argv
    if (full or player or enroll_arg is not None) and not isinstance(store, InMemoryStore):
        print(f"demo_check: --full, --player and --enroll only run against the in-memory store, not "
              f"{type(store).__name__}. Re-run with `env DATABASE_URL= ...`.")
        sys.exit(2)
    if player:
        print(f"store: {type(store).__name__} · in-player checks on {PLAYER_COURSE}\n")
        sys.exit(1 if await player_checks(uid) else 0)
```

Syntax check: `cd backend && .venv/bin/python -m py_compile scripts/demo_check.py && echo compiled`
Expected: `compiled`.

Guard check (must refuse a non-memory store without any network call):
`cd backend && env DATABASE_URL=postgres://nobody@127.0.0.1:1/x .venv/bin/python scripts/demo_check.py --player; echo exit=$?`
Expected: `demo_check: --full, --player and --enroll only run against the in-memory store, not …` and `exit=2`. (If the store class chosen for a non-empty URL is constructed lazily and the message names a different class, that is fine — the exit code must be 2.)

- [ ] **Step 2: Run the in-player checks with the real model**

Run: `cd backend && env DATABASE_URL= .venv/bin/python scripts/demo_check.py --player; echo exit=$?`
Expected (first run embeds all transcript chunks in memory, ~1–2 min):
- `[ok] in_course_…  take me to where you publish the npm package …` followed by `jump → 11.1 - Publishing using `np` @ mm:ss: "<text about publishing with np>…"`. Read the quoted text: it must be the moment the publish commands are run/explained. If it is a neighbouring passage (e.g. installing `np`) note the second in your report — it is still a real chunk, but tell the reviewer.
- `[ok] … how does the event loop work …` — case `in_course_related` or `in_course_none`; the answer explains the event loop in general terms and, if `in_course_related`, ends with one "This course touches on it in <lecture> at <mm:ss>" sentence. No other course named.
- `[ok] … give me an example …` — a concrete example on the 1.1 topic (what the course builds), not "what kind of example do you mean?".
- `exit=0`.

If a check fails: re-run once (model output varies). If the jump check fails twice because the model answered in text without calling `find_moment`, strengthen `FIND_MOMENT` in `backend/app/services/tool_descriptions.py` by changing its second sentence to start `ALWAYS call it whenever the student asks to be taken, shown or jumped to a part` and re-run; any other repeated failure → stop and report the printed output (do not loosen the checks).

- [ ] **Step 3: Ask page unchanged — the 7 demo questions**

Run: `cd backend && env DATABASE_URL= .venv/bin/python scripts/demo_check.py --enroll 9,11 --full; echo exit=$?`
Expected: `expected-case checks: on`, 7 lines all `[ok]` with the same cases as before this branch (`not_enrolled_match`, `enrolled_match`, `enrolled_match`, `not_enrolled_match`, `no_match`, then two printed-only), every answer printed with no `[error: …]`, `exit=0`. Q1 ("how do I publish an npm library") still ends with the not-enrolled pointer to `the01.dev/course/2`; its cited lecture may now be a real one (e.g. 11.1) instead of the old hand-written 8.1 — that is the intended effect of Task B, not a regression.

- [ ] **Step 4: Full suite + frontend build once more**

Run: `bash backend/scripts/run_tests.sh && (cd frontend && npx tsc -b && npm run build && node --experimental-strip-types scripts/lectureMatch.check.ts)`
Expected: `ALL PASSED`, a clean build, `lectureMatch: all checks passed`.

- [ ] **Step 5: Commit**

```bash
git add backend/scripts/demo_check.py
# plus backend/app/services/tool_descriptions.py only if Step 2 required the ALWAYS wording
git commit -m "chore(demo-check): --player real-model checks for the in-course tutor

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

Paste the Step 2 and Step 3 outputs (case lines + jump line) into your task report.

---
