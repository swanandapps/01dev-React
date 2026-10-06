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
    assert len(rows) == 21
    assert {r["id"] for r in rows if r["style"] == "vague"} == {"hand-vague-weak", "hand-vague-this", "hand-vague-example"}
    assert all(r["expect"] == "not_covered" and not r.get("gold_lecture_ids") for r in rows if r["style"] == "vague")
    tok = next(r for r in rows if r["id"] == "hand-tokenizer-loop")
    assert tok["gold_lecture_ids"] == ["programming-language-5-1"]


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


def test_every_generated_row_loads_and_no_positive_has_only_an_outro_gold():
    path = BACKEND / "eval/retrieval/generated_set.json"
    rows = json.loads(path.read_text())
    seed = json.loads((BACKEND / "app/data/seed_transcripts.json").read_text())
    kinds = {lec["lecture_id"]: lec["kind"] for lec in g.lectures_from_seed(seed)}
    assert len({r["id"] for r in rows}) == len(rows)
    for d in rows:
        r = Row.from_dict(d)
        assert r.lecture_kind in ("intro", "body", "outro")
        if r.expect == "covered":
            assert r.gold_lecture_ids and any(kinds[lid] != "outro" for lid in r.gold_lecture_ids), r.id
        else:
            assert not r.gold_lecture_ids
    assert sum(r.get("leaks_title", False) for r in rows) / len(rows) < 0.25


def test_lecture_kinds_from_titles():
    seed = json.loads((BACKEND / "app/data/seed_transcripts.json").read_text())
    kinds = {lec["lecture_id"]: lec["kind"] for lec in g.lectures_from_seed(seed)}
    assert kinds["web-apis-4-1"] == "outro" and kinds["custom-library-11-1"] == "outro"
    assert kinds["react-perf-0-0"] == "intro" and kinds["custom-library-0-1"] == "intro"
    assert kinds["react-perf-4-0"] == "body"


def test_leak_tags():
    assert g.leaks_title("what is an IIFE to the rescue", "6.5 - IIFE, To The Rescue")      # bigram "to the" + rescue
    assert g.leaks_title("how do I handle tokens and lexemes", "6.1 - Tokens, Lexemes and Token Types")
    assert not g.leaks_title("what does react do", "1.2 - Render vs Commit: What React Actually Does")
    assert not g.leaks_title("why is my javascript slow", "2.1 - Why JavaScript Evolved This Way")
    assert g.leaks_project("what datatypes does Ember have") and not g.leaks_project("what datatypes exist")


def test_navigate_phrase_must_be_spoken_not_code():
    for phrase in ["node --trace-opt flag", "set(partial, 'cart/addItem')", "one two three four five six seven eight"]:
        raw = _good(["direct", "casual", "keyword"])
        raw["navigate_phrase"] = phrase
        assert g.validate_generation(raw, {"c-0-0-0"}, ["direct", "casual", "keyword"]) is None
    assert not any("explained" in t or "video" in t for t in g.NAV_TEMPLATES)


def test_cache_key_includes_prompt_version_and_model(monkeypatch):
    lec = g.lectures_from_seed(_seed())[0]
    a = g.lecture_sha(lec)
    monkeypatch.setattr(g, "PROMPT_VERSION", "other")
    assert g.lecture_sha(lec) != a
    monkeypatch.setattr(g, "PROMPT_VERSION", "v2")
    monkeypatch.setattr(g, "MODEL", "other-model")
    assert g.lecture_sha(lec) != a


async def test_retry_feedback_names_the_phrase_and_how_do_i_falls_back_to_direct(tmp_path, monkeypatch):
    seen = []

    async def fake_complete(system, user):
        seen.append(user)
        styles = user.split("Styles, in order:")[1].split("\n")[0]
        if "how_do_i" in styles:
            bad = _good(["direct", "casual", "keyword"])
            bad["questions"][2]["question"] = "How do I understand the video?"
            return bad
        return _good(["direct", "casual", "direct"])

    monkeypatch.setattr(g, "_complete", fake_complete)
    lec = g.lectures_from_seed(_seed())[0]
    gen = await g._generate(lec, ["direct", "casual", "how_do_i"])
    assert gen and [q["style"] for q in gen["questions"]] == ["direct", "casual", "direct"]
    assert 'forbidden phrase "How do I understand"' in seen[1] and len(seen) == 4


def test_outro_gold_is_relabelled_or_dropped(monkeypatch):
    monkeypatch.setattr(g, "RELABEL_MIN_SCORE", 0.5)
    seed = [
        {"chunk_id": "x-0-0-0", "course_id": "x", "course_title": "X", "lecture_id": "x-0-0", "lecture_title": "1.1 - Intro",
         "text": "welcome", "start_time": 0, "end_time": 5},
        {"chunk_id": "x-1-0-0", "course_id": "x", "course_title": "X", "lecture_id": "x-1-0", "lecture_title": "2.1 - Bodies",
         "text": "the flamingo scheduler batches flamingo jobs every night", "start_time": 0, "end_time": 5},
        {"chunk_id": "x-1-0-1", "course_id": "x", "course_title": "X", "lecture_id": "x-1-0", "lecture_title": "2.1 - Bodies",
         "text": "unrelated gardening talk about tomatoes", "start_time": 5, "end_time": 9},
        {"chunk_id": "x-2-0-0", "course_id": "x", "course_title": "X", "lecture_id": "x-2-0", "lecture_title": "3.1 - Where from Here?",
         "text": "recap of the flamingo scheduler", "start_time": 0, "end_time": 5},
    ]
    lecs = g.lectures_from_seed(seed)
    base = {"scope_course": "x", "expect": "covered", "gold_lecture_ids": ["x-2-0"], "gold_chunk_ids": ["x-2-0-0"],
            "style": "keyword", "intent": "explain", "source": "generated", "lecture_kind": "outro"}
    rows = [{**base, "id": "a", "question": "flamingo scheduler batches"}, {**base, "id": "b", "question": "what next?"}]
    out = g.relabel_outros(rows, lecs)
    assert [r["id"] for r in out] == ["a"]
    assert out[0]["gold_lecture_ids"] == ["x-1-0", "x-2-0"] and out[0]["gold_chunk_ids"] == ["x-1-0-0"]


def test_cross_course_rows_spread_over_the_course():
    gen = [{"id": f"gen-s-{i}-0-q1", "question": f"term{i} question", "scope_course": "react-perf", "expect": "covered",
            "gold_lecture_ids": [f"react-perf-{i}-0"], "style": "keyword", "intent": "explain"} for i in range(20)]
    cross = g.cross_course_rows(gen)
    assert len(cross) == g.CROSS_PER_PAIR
    assert cross[-1]["id"].startswith("cross-s-14") or int(cross[-1]["id"].split("-")[2]) >= 14
