import json
from pathlib import Path

import pytest

from app.eval.retrieval_metrics import Row
from scripts import generate_eval_set as g

BACKEND = Path(__file__).resolve().parents[1]


def _seed():
    return [
        {"chunk_id": "c-0-0-0", "course_id": "c", "course_title": "C", "lecture_id": "c-0-0",
         "lecture_title": "1.1 - IIFE", "text": "an iffy wraps code", "start_time": 0, "end_time": 50},
        {"chunk_id": "c-0-0-1", "course_id": "c", "course_title": "C", "lecture_id": "c-0-0",
         "lecture_title": "1.1 - IIFE", "text": "it runs at once", "start_time": 50, "end_time": 100},
        {"chunk_id": "d-0-0-0", "course_id": "d", "course_title": "D", "lecture_id": "d-0-0",
         "lecture_title": "1.1 - Tokens", "text": "a token is", "start_time": 0, "end_time": 50},
    ]


def _good(styles):
    return {"questions": [{"style": s, "question": f"q {s}?", "gold_chunk_id": "c-0-0-0"} for s in styles],
            "navigate_phrase": "the IIFE pattern"}


def test_styles_rotate_and_hand_set_loads():
    assert g.styles_for(0) == ["direct", "casual", "keyword"]
    assert g.styles_for(1) == ["casual", "keyword", "how_do_i"]
    rows = json.loads((BACKEND / "eval/retrieval/hand_set.json").read_text())
    assert len({r["id"] for r in rows}) == len(rows)
    for r in rows:
        Row.from_dict(r)  # every field is a Row field


def test_validate_relabels_styles_and_drops_unknown_gold_chunks():
    raw = _good(["x", "y", "z"])
    raw["questions"][1]["gold_chunk_id"] = "not-a-chunk"
    out = g.validate_generation(raw, {"c-0-0-0", "c-0-0-1"}, ["direct", "casual", "keyword"])
    assert [q["style"] for q in out["questions"]] == ["direct", "casual", "keyword"]
    assert out["questions"][1]["gold_chunk_id"] is None


@pytest.mark.parametrize("raw", [
    None, {}, {"questions": []}, {"questions": [{"question": "a"}] * 2, "navigate_phrase": "x"},
    {"questions": [{"question": "what does the lecture say?"}] * 3, "navigate_phrase": "x"},
    {"questions": [{"question": "a?"}] * 3, "navigate_phrase": ""},
])
def test_validate_rejects_bad_generations(raw):
    assert g.validate_generation(raw, {"c-0-0-0"}, ["direct", "casual", "keyword"]) is None


def test_rows_for_lecture_has_three_explain_rows_and_one_navigate_row():
    lec = g.lectures_from_seed(_seed())[0]
    rows = g.rows_for_lecture(lec, 0, g.validate_generation(_good(g.styles_for(0)), {"c-0-0-0", "c-0-0-1"},
                                                            g.styles_for(0)))
    assert [r["intent"] for r in rows] == ["explain", "explain", "explain", "navigate"]
    assert all(r["gold_lecture_ids"] == ["c-0-0"] and r["scope_course"] == "c" for r in rows)
    assert rows[0]["gold_chunk_ids"] == ["c-0-0-0"]
    assert rows[3]["navigate_phrase"] == "the IIFE pattern" and "the IIFE pattern" in rows[3]["question"]


async def test_build_set_is_resumable_and_uses_the_cache(tmp_path, monkeypatch):
    calls = []

    async def fake_complete(system, user):
        calls.append(user)
        styles = [s for s in g.STYLES if s in user.split("Styles, in order:")[1].split("\n")[0]]
        return _good(styles)

    monkeypatch.setattr(g, "_complete", fake_complete)
    lectures = g.lectures_from_seed(_seed())
    first = await g.build_set(lectures, tmp_path, limit=1)
    assert len(calls) == 1 and len(first) == 4           # --limit 1: one lecture generated
    second = await g.build_set(lectures, tmp_path)
    assert len(calls) == 2                               # only the missing lecture was requested
    assert second[:4] == first and len(second) == 8
    again = await g.build_set(lectures, tmp_path)
    assert len(calls) == 2 and again == second          # idempotent: everything cached


async def test_changed_lecture_text_invalidates_its_cache(tmp_path, monkeypatch):
    calls = []

    async def fake_complete(system, user):
        calls.append(user)
        return _good(["direct", "casual", "keyword"])

    monkeypatch.setattr(g, "_complete", fake_complete)
    seed = _seed()[:2]
    await g.build_set(g.lectures_from_seed(seed), tmp_path)
    seed[1]["text"] = "it runs immediately"
    await g.build_set(g.lectures_from_seed(seed), tmp_path)
    assert len(calls) == 2


def test_negatives_cross_course_and_golden_rows():
    negs = g.negative_rows(["custom-library", "react-perf"])
    assert negs and all(r["expect"] == "not_covered" and r["style"] == "off_topic" for r in negs)
    assert {r["scope_course"] for r in negs} == {"custom-library", "react-perf"}
    gen = [{"id": "gen-react-perf-0-0-q1", "question": "what triggers a re-render", "scope_course": "react-perf",
            "expect": "covered", "gold_lecture_ids": ["react-perf-0-0"], "style": "keyword", "intent": "explain"}]
    cross = g.cross_course_rows(gen)
    assert cross == [{"id": "cross-react-perf-0-0-q1-in-programming-language", "question": "what triggers a re-render",
                      "scope_course": "programming-language", "expect": "not_covered", "gold_lecture_ids": [],
                      "style": "cross_course", "intent": "explain", "source": "generated"}]
    seed = json.loads((BACKEND / "app/data/seed_transcripts.json").read_text())
    golden = g.golden_rows(seed)
    assert len(golden) == 14 and golden[0]["gold_lecture_ids"] == ["custom-library-7-0"]
