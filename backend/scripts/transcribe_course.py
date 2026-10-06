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


def check_audio_complete(audio: Path, source_duration: float, tolerance_s: float = 5.0) -> None:
    """ffmpeg can exit 0 after a dropped connection; a short mp3 must never be cached."""
    got = probe_duration(audio)
    if abs(got - source_duration) > tolerance_s:
        audio.unlink(missing_ok=True)
        raise RuntimeError(f"truncated audio: {got:.0f}s of {source_duration:.0f}s")


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


def transcribe_lecture(client, lecture: Lecture, cache: Path,
                       max_upload_bytes: int = MAX_UPLOAD_BYTES) -> list[dict]:
    """Segments for one lecture, from cache when present."""
    seg_path = cache / f"{lecture.lecture_id}.whisper.json"
    if seg_path.exists():
        cached = json.loads(seg_path.read_text())
        if cached:  # a cached [] is a miss — re-transcribe
            return cached
    audio = cache / f"{lecture.lecture_id}.mp3"
    if not audio.exists():
        tmp = cache / f"{lecture.lecture_id}.partial.mp3"
        src_url = decode_video_url(lecture.src)
        extract_audio(src_url, tmp)
        check_audio_complete(tmp, probe_duration(src_url))
        tmp.rename(audio)
    size = audio.stat().st_size
    parts = plan_audio_parts(size, probe_duration(audio) if size >= max_upload_bytes else 0.0,
                             limit_bytes=max_upload_bytes)
    segments: list[dict] = []
    if len(parts) == 1:
        segments = whisper_segments(client, audio)
    else:
        for i, (offset, length) in enumerate(parts):
            piece = cache / f"{lecture.lecture_id}.part{i}.mp3"
            if not piece.exists():
                extract_audio(str(audio), piece, offset, length)
            segments += offset_segments(whisper_segments(client, piece), offset)
    if not segments:  # never cache an empty result — it would never be retried
        raise RuntimeError("Whisper returned no segments")
    seg_path.write_text(json.dumps(segments, indent=1))
    return segments


def _make_client():
    from dotenv import load_dotenv
    from openai import OpenAI

    load_dotenv(BACKEND / ".env")
    return OpenAI()


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("course_slug")
    ap.add_argument("--only", default="", help="comma-separated lecture_ids (writes review-partial.json)")
    ap.add_argument("--merge", action="store_true", help="merge review.json into seed_transcripts.json")
    ap.add_argument("--max-upload-bytes", type=int, default=MAX_UPLOAD_BYTES,
                    help="split audio so each Whisper upload stays under this size (default %(default)s)")
    args = ap.parse_args(argv)
    cache = CACHE_DIR / args.course_slug
    review = cache / "review.json"

    if args.merge:
        if not review.exists():
            print(f"no {review} — run a full transcription first")
            return 2
        new_chunks = json.loads(review.read_text())
        track_id, _ = find_course(json.loads(CATALOG_PATH.read_text()), args.course_slug)
        expected = {l.lecture_id for l in parse_course_lectures(TRACKS_PATH.read_text(), track_id, args.course_slug)}
        missing = sorted(expected - {c["lecture_id"] for c in new_chunks})
        if missing:
            print(f"{review} is missing {len(missing)} lecture(s): {missing} — refusing to merge")
            return 2
        seed = json.loads(SEED_PATH.read_text())
        merged = merge_into_seed(seed, args.course_slug, new_chunks)
        SEED_PATH.write_text(json.dumps(merged, indent=2))
        print(f"merged {len(new_chunks)} {args.course_slug} chunks; seed now {len(merged)} chunks")
        return 0

    track_id, course_title = find_course(json.loads(CATALOG_PATH.read_text()), args.course_slug)
    lectures = parse_course_lectures(TRACKS_PATH.read_text(), track_id, args.course_slug)
    only = {x.strip() for x in args.only.split(",") if x.strip()}
    unknown = only - {l.lecture_id for l in lectures}
    if unknown:
        print(f"unknown lecture ids: {sorted(unknown)}")
        return 2
    cache.mkdir(parents=True, exist_ok=True)
    client = _make_client()

    chunks: list[dict] = []
    failed: list[tuple[Lecture, str]] = []
    empty: list[Lecture] = []
    for lec in lectures:
        if only and lec.lecture_id not in only:
            continue
        try:
            segments = transcribe_lecture(client, lec, cache, args.max_upload_bytes)
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

    # Only a fully successful full run may produce review.json (the one --merge reads).
    name = "review-partial.json" if only else ("review-incomplete.json" if failed or empty else "review.json")
    out = cache / name
    out.write_text(json.dumps(chunks, indent=2))
    print(f"\nwrote {len(chunks)} chunks → {out}")
    for lec in empty:
        print(f"EMPTY {lec.lecture_id} {lec.name} (no speech segments)")
    for lec, err in failed:
        print(f"FAILED {lec.lecture_id} {lec.name}: {err}")
    return 1 if failed or empty else 0


if __name__ == "__main__":
    sys.exit(main())
