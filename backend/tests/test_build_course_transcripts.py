import json

import pytest

from scripts import build_course_transcripts as b

CUR = {
    "demo": {
        "title": "Demo Course",
        "lectures": [("demo-0-0", "1.1 - Intro `x`"), ("demo-0-1", "1.2 - Next")],
    }
}
WORDS = " ".join(["word"] * 100)  # 100 words / 50 s = 120 wpm


def mk(lid, title, n, start, end, text=None, **kw):
    c = {
        "chunk_id": f"{lid}-{n}", "course_id": "demo", "course_title": "Demo Course",
        "lecture_id": lid, "lecture_title": title, "text": text or f"{WORDS} {lid} {n}",
        "start_time": start, "end_time": end, "embedding": [],
    }
    c.update(kw)
    return c


def lecture(lid, title, passages=5, length=50):
    # 5 x 50 s = 250 s
    return [mk(lid, title, i, i * length, (i + 1) * length) for i in range(passages)]


def good():
    return lecture("demo-0-0", "1.1 - Intro `x`") + lecture("demo-0-1", "1.2 - Next")


def test_valid_course_has_no_problems():
    assert b.validate_course("demo", good(), CUR, {}) == []


def test_missing_lecture():
    p = b.validate_course("demo", lecture("demo-0-0", "1.1 - Intro `x`"), CUR, {})
    assert any("demo-0-1" in x and "no chunks" in x for x in p)


def test_title_off_by_a_backtick():
    ch = lecture("demo-0-0", "1.1 - Intro x") + lecture("demo-0-1", "1.2 - Next")
    p = b.validate_course("demo", ch, CUR, {})
    assert any("lecture_title" in x for x in p)


def test_wrong_course_fields():
    ch = good()
    ch[0]["course_title"] = "Nope"
    ch[1]["course_id"] = "other"
    p = b.validate_course("demo", ch, CUR, {})
    assert any("course_title" in x for x in p) and any("course_id" in x for x in p)


def test_gap_in_times():
    ch = good()
    ch[1]["start_time"] += 5
    ch[1]["end_time"] += 5
    assert any("contiguous" in x for x in b.validate_course("demo", ch, CUR, {}))


def test_first_passage_must_start_at_zero():
    ch = good()
    for c in ch[:5]:
        c["start_time"] += 1
        c["end_time"] += 1
    assert any("start at 0" in x for x in b.validate_course("demo", ch, CUR, {}))


def test_passage_90s_too_long():
    ch = lecture("demo-0-0", "1.1 - Intro `x`", passages=4) + lecture("demo-0-1", "1.2 - Next")
    ch[1]["end_time"] = 140
    ch[2].update(start_time=140, end_time=190)
    ch[3].update(start_time=190, end_time=240)
    ch[1]["text"] = " ".join(["w"] * 200) + " a"
    p = b.validate_course("demo", ch, CUR, {})
    assert any("45-75" in x for x in p)


def test_last_passage_may_be_short_but_not_below_20():
    ch = lecture("demo-0-0", "1.1 - Intro `x`", passages=4) + lecture("demo-0-1", "1.2 - Next")
    # 4*50=200 +30 = 230 total -> too short overall, use 5 passages: 4x60 + 30
    ch = []
    for lid, t in [("demo-0-0", "1.1 - Intro `x`"), ("demo-0-1", "1.2 - Next")]:
        l = [mk(lid, t, i, i * 60, (i + 1) * 60, text=" ".join(["w", lid, str(i)] * 40)) for i in range(4)]
        l.append(mk(lid, t, 4, 240, 270, text=" ".join(["w", lid, "L"] * 25)))
        ch += l
    assert b.validate_course("demo", ch, CUR, {}) == []
    ch[4].update(end_time=255, text=" ".join(["w", "z"] * 18))  # 15 s
    assert any("last passage" in x for x in b.validate_course("demo", ch, CUR, {}))


def test_lecture_total_too_short():
    ch = lecture("demo-0-0", "1.1 - Intro `x`", passages=3) + lecture("demo-0-1", "1.2 - Next")
    assert any("total" in x for x in b.validate_course("demo", ch, CUR, {}))


def test_wpm_out_of_range():
    ch = good()
    ch[2]["text"] = "too few words here"
    assert any("wpm" in x for x in b.validate_course("demo", ch, CUR, {}))


@pytest.mark.parametrize("bad", ["# Heading", "- bullet", "* bullet", "use **bold**", "see ```code```"])
def test_markdown_rejected(bad):
    ch = good()
    ch[0]["text"] = f"{bad}\n{WORDS}" if bad[0] in "#-*" else f"{WORDS} {bad}"
    assert any("markdown" in x for x in b.validate_course("demo", ch, CUR, {}))


def test_duplicate_text():
    ch = good()
    ch[1]["text"] = ch[0]["text"]
    assert any("duplicate" in x for x in b.validate_course("demo", ch, CUR, {}))


def test_bad_chunk_id_and_embedding():
    ch = good()
    ch[1]["chunk_id"] = "demo-0-0-7"
    ch[2]["embedding"] = [0.1]
    p = b.validate_course("demo", ch, CUR, {})
    assert any("chunk_id" in x for x in p) and any("embedding" in x for x in p)


def test_float_time_rejected():
    ch = good()
    ch[0]["end_time"] = 50.0
    assert any("whole" in x for x in b.validate_course("demo", ch, CUR, {}))


def test_missing_anchor_text():
    anchors = {"1.2 - Next": ["this exact sentence must appear"]}
    assert any("anchor" in x for x in b.validate_course("demo", good(), CUR, anchors))
    ch = good()
    ch[6]["text"] += " this exact sentence must appear"
    assert b.validate_course("demo", ch, CUR, anchors) == []


# ---- curriculum / anchors / merge -------------------------------------------

CAT = [
    {"slug": "custom-library", "title": "Build a Custom Library",
     "chapters": [{"name": "Chapter 1 - A", "subchapters": ["1.1 - X", "1.2 - Y"]}]},
    {"slug": "demo", "title": "Demo Course",
     "chapters": [{"name": "Chapter 1 - A", "subchapters": ["1.1 - Intro `x`", "1.2 - Next"]}]},
]


def test_load_curriculum_excludes_custom_library(tmp_path):
    p = tmp_path / "catalog.json"
    p.write_text(json.dumps(CAT))
    cur = b.load_curriculum(p)
    assert list(cur) == ["demo"]
    assert cur["demo"]["lectures"] == CUR["demo"]["lectures"]


def setup_merge(tmp_path, staging_ok=True):
    cat = tmp_path / "catalog.json"
    cat.write_text(json.dumps(CAT))
    seed = tmp_path / "seed.json"
    cl = [{"chunk_id": "custom-library-0-0-0", "course_id": "custom-library", "course_title": "Build a Custom Library",
           "lecture_id": "custom-library-0-0", "lecture_title": "1.1 - X", "text": "real", "start_time": 0,
           "end_time": 9, "embedding": []}]
    old = [dict(cl[0], chunk_id="demo-0-0-a", course_id="demo", lecture_id="demo-0-0", text="old")]
    seed.write_text(json.dumps(cl + old, indent=2) + "\n")
    src = tmp_path / "src"
    src.mkdir()
    ch = good()
    if not staging_ok:
        ch = ch[:5]
    (src / "demo.json").write_text(json.dumps(ch))
    return cat, seed, src, cl


def test_merge_keeps_custom_library_and_is_idempotent(tmp_path):
    cat, seed, src, cl = setup_merge(tmp_path)
    assert b.merge(cat, seed, src, {}) == []
    data = json.loads(seed.read_text())
    assert data[0] == cl[0]
    assert [c["course_id"] for c in data].count("demo") == 10
    assert not any(c["text"] == "old" for c in data)
    first = seed.read_text()
    assert first.endswith("}\n]\n") or first.endswith("]\n")
    assert b.merge(cat, seed, src, {}) == []
    assert seed.read_text() == first


def test_merge_refuses_when_a_course_invalid(tmp_path):
    cat, seed, src, _ = setup_merge(tmp_path, staging_ok=False)
    before = seed.read_text()
    problems = b.merge(cat, seed, src, {})
    assert problems
    assert seed.read_text() == before


def test_merge_refuses_when_staging_missing(tmp_path):
    cat, seed, src, _ = setup_merge(tmp_path)
    (src / "demo.json").unlink()
    before = seed.read_text()
    assert b.merge(cat, seed, src, {})
    assert seed.read_text() == before


def test_snapshot_anchors_written_once(tmp_path):
    seed = tmp_path / "seed.json"
    seed.write_text(json.dumps([
        {"chunk_id": "js-deep-4-1-a", "course_id": "javascript-deep-dive", "course_title": "t",
         "lecture_id": "js-deep-4-1", "lecture_title": "4.1 - Proto", "text": "alpha", "start_time": 0,
         "end_time": 5, "embedding": []},
        {"chunk_id": "custom-library-0-0-0", "course_id": "custom-library", "course_title": "t",
         "lecture_id": "custom-library-0-0", "lecture_title": "1.1 - X", "text": "real", "start_time": 0,
         "end_time": 5, "embedding": []},
    ]))
    out = tmp_path / "_anchors.json"
    a = b.snapshot_anchors(seed, out)
    assert a == {"4.1 - Proto": ["alpha"]}
    seed.write_text("[]")
    assert b.snapshot_anchors(seed, out) == {"4.1 - Proto": ["alpha"]}  # existing snapshot wins
