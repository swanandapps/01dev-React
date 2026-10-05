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


def _stub_run(monkeypatch, tmp_path, fail_ids):
    monkeypatch.setattr(tc, "CACHE_DIR", tmp_path / "cache")
    monkeypatch.setattr(tc, "_make_client", lambda: object())

    def fake(client, lec, cache):
        if lec.lecture_id in fail_ids:
            raise RuntimeError("boom")
        return [{"start": 0.0, "end": 50.0, "text": "hello"}]
    monkeypatch.setattr(tc, "transcribe_lecture", fake)


def test_failed_lecture_means_no_review_json(tmp_path, monkeypatch):
    _stub_run(monkeypatch, tmp_path, {"custom-library-10-0"})
    assert tc.main(["custom-library"]) == 1
    d = tmp_path / "cache" / "custom-library"
    assert not (d / "review.json").exists()
    assert (d / "review-incomplete.json").exists()


def test_clean_full_run_writes_review_json_and_merge_accepts_it(tmp_path, monkeypatch):
    _stub_run(monkeypatch, tmp_path, set())
    assert tc.main(["custom-library"]) == 0
    assert (tmp_path / "cache" / "custom-library" / "review.json").exists()
    seed = tmp_path / "seed.json"
    seed.write_text("[]")
    monkeypatch.setattr(tc, "SEED_PATH", seed)
    assert tc.main(["custom-library", "--merge"]) == 0
    assert len(json.loads(seed.read_text())) == 34


def test_merge_refuses_a_review_missing_a_lecture(tmp_path, monkeypatch):
    cache = tmp_path / "cache"
    (cache / "custom-library").mkdir(parents=True)
    (cache / "custom-library" / "review.json").write_text(
        json.dumps([{"chunk_id": "custom-library-10-0-0", "course_id": "custom-library",
                     "lecture_id": "custom-library-10-0"}]))
    seed = tmp_path / "seed.json"
    seed.write_text("[]")
    monkeypatch.setattr(tc, "CACHE_DIR", cache)
    monkeypatch.setattr(tc, "SEED_PATH", seed)
    assert tc.main(["custom-library", "--merge"]) == 2
    assert seed.read_text() == "[]"


def test_empty_whisper_result_is_failure_and_not_cached(tmp_path, monkeypatch):
    lec = tc.Lecture("c", 0, 0, "ch", "n", "x")
    (tmp_path / "c-0-0.mp3").write_bytes(b"x")
    monkeypatch.setattr(tc, "whisper_segments", lambda client, audio: [])
    with pytest.raises(RuntimeError):
        tc.transcribe_lecture(object(), lec, tmp_path)
    assert not (tmp_path / "c-0-0.whisper.json").exists()
