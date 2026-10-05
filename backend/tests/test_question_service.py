"""question_service — generated banks reuse the course's fixed concept tags.

In-memory store, LLM and vector store patched: no network, no database."""
import copy
import hashlib

import pytest

from app.services import question_service
from app.services.store import InMemoryStore

SLUG = "react-perf"
TAGS = [
    ("react-memo", "React.memo skips re-render when props are shallowly equal."),
    ("use-memo", "useMemo caches a computed value between renders."),
    ("use-callback", "useCallback keeps a function identity stable."),
]


def _raw(question, concept, correct="Right", difficulty="medium"):
    return {
        "question": question,
        "options": [correct, "Wrong 1", "Wrong 2", "Wrong 3"],
        "correct_index": 0,
        "explanation": "because",
        "concept": concept,
        "difficulty": difficulty,
        "lecture": "Lecture 1",
    }


def _hid(question, correct="Right"):
    return f"{SLUG}-h{hashlib.sha1((question + correct).encode()).hexdigest()[:10]}"


def _bank_q(i, concept, prefix="t"):
    return {
        "id": f"{SLUG}-{prefix}{i}",
        "question": f"Existing question {prefix}{i}?",
        "options": ["a", "b", "c", "d"],
        "correct_index": 1,
        "explanation": "x",
        "concept": concept,
        "difficulty": "easy",
        "lecture": "L",
    }


@pytest.fixture
def env(monkeypatch):
    st = InMemoryStore()
    calls = []
    out = {"questions": []}

    async def fake_generate_json(system, user, **kwargs):
        calls.append({"system": system, "user": user})
        return copy.deepcopy(out["response"]) if "response" in out else {"questions": out["questions"]}

    monkeypatch.setattr(question_service, "store", st)
    monkeypatch.setattr(question_service.llm, "generate_json", fake_generate_json)
    monkeypatch.setattr(question_service.vector_store, "get_course_meta",
                        lambda cid: {"course_title": "React Perf", "lecture_count": 3})
    monkeypatch.setattr(question_service.vector_store, "get_course_transcript",
                        lambda cid: "[Lecture: Lecture 1] memo memo memo")
    question_service._in_progress.discard(SLUG)
    return st, calls, out


async def _add_concepts(st, slug=SLUG):
    for name, desc in TAGS:
        await st.set("concepts", f"{slug}::{name}", {"course_id": slug, "name": name, "description": desc})


async def _bank(st):
    return (await st.get("questions", SLUG))["questions"]


async def test_initial_generation_keeps_only_allowed_tags_and_prompts_them(env):
    st, calls, out = env
    await _add_concepts(st)
    out["questions"] = [
        _raw("What does React.memo do?", "react-memo"),
        _raw("When does useMemo recompute?", "Use Memo"),
        _raw("Why use useCallback?", " use_callback "),
        _raw("What is the useMemo hook?", "useMemo hook"),
        _raw("What is a virtual DOM?", "virtual-dom"),
    ]

    await question_service._generate(SLUG, initial=True)

    bank = await _bank(st)
    assert [q["concept"] for q in bank] == ["react-memo", "use-memo", "use-callback"]
    assert [q["id"] for q in bank] == [
        _hid("What does React.memo do?"), _hid("When does useMemo recompute?"), _hid("Why use useCallback?")]
    system = calls[0]["system"]
    for name, desc in TAGS:
        assert name in system and desc in system
    assert "verbatim" in system


async def test_prompt_asks_for_the_tags_the_bank_has_fewest_of(env):
    st, calls, out = env
    await _add_concepts(st)
    existing = [_bank_q(i, "react-memo") for i in range(1, 7)] + [_bank_q(7, "use-memo")]
    await st.set("questions", SLUG, {"course_id": SLUG, "course_title": "React Perf", "questions": existing,
                                     "model": "m", "generated_at": "2026-10-01T00:00:00+00:00"})
    out["questions"] = []

    await question_service._generate(SLUG, initial=False)

    system = calls[0]["system"]
    focus = system[system.index("fewest"):]
    assert focus.index("use-callback") < focus.index("use-memo") < focus.index("react-memo")


async def test_top_up_on_tag_locked_bank_appends_hash_ids_and_dedupes(env):
    st, calls, out = env
    await _add_concepts(st)
    existing = [_bank_q(i, TAGS[i % 3][0]) for i in range(1, 25)]
    await st.set("questions", SLUG, {"course_id": SLUG, "course_title": "React Perf",
                                     "questions": copy.deepcopy(existing),
                                     "model": "m", "generated_at": "2026-10-01T00:00:00+00:00"})
    out["questions"] = [
        _raw("Fresh one?", "use-memo"),
        _raw("Fresh one?", "use-memo"),             # in-batch duplicate
        _raw("Fresh two?", "react-memo", correct="Yes"),
        _raw("Off taxonomy?", "rendering perf"),    # dropped
    ]

    await question_service._generate(SLUG, initial=False)

    bank = await _bank(st)
    assert bank[:24] == existing
    new = bank[24:]
    assert [q["id"] for q in new] == [_hid("Fresh one?"), _hid("Fresh two?", correct="Yes")]
    assert all("-q" not in q["id"] for q in new)

    # A second top-up that re-produces an existing question adds nothing for it.
    out["questions"] = [_raw("Fresh one?", "use-memo"), _raw("Fresh three?", "use-callback")]
    await question_service._generate(SLUG, initial=False)
    bank2 = await _bank(st)
    assert bank2[:26] == bank
    assert [q["id"] for q in bank2[26:]] == [_hid("Fresh three?")]


async def test_skips_generated_question_whose_id_already_exists(env):
    """Same text + same correct option but a reworded stem elsewhere: the id
    check is the backstop even when the text-norm dedupe doesn't fire."""
    st, calls, out = env
    await _add_concepts(st)
    prior = _raw("Dup?", "use-memo")
    existing = [{**_bank_q(1, "use-memo"), "id": _hid("Dup?"), "question": "Dup?  (older wording)"}]
    await st.set("questions", SLUG, {"course_id": SLUG, "course_title": "React Perf", "questions": existing,
                                     "model": "m", "generated_at": "2026-10-01T00:00:00+00:00"})
    out["questions"] = [prior, _raw("Other?", "use-memo")]

    await question_service._generate(SLUG, initial=False)

    assert [q["id"] for q in await _bank(st)] == [_hid("Dup?"), _hid("Other?")]


async def test_top_up_respects_the_cap_without_touching_existing(env):
    st, calls, out = env
    await _add_concepts(st)
    existing = [_bank_q(i, "use-memo") for i in range(1, 49)]
    await st.set("questions", SLUG, {"course_id": SLUG, "course_title": "React Perf",
                                     "questions": copy.deepcopy(existing),
                                     "model": "m", "generated_at": "2026-10-01T00:00:00+00:00"})
    out["questions"] = [_raw(f"New {i}?", "use-memo") for i in range(5)]

    await question_service._generate(SLUG, initial=False)

    bank = await _bank(st)
    assert len(bank) == question_service.MAX_BANK
    assert bank[:48] == existing


async def test_all_invalid_output_appends_nothing(env):
    st, calls, out = env
    await _add_concepts(st)
    existing = [_bank_q(i, "use-memo") for i in range(1, 4)]
    await st.set("questions", SLUG, {"course_id": SLUG, "course_title": "React Perf",
                                     "questions": copy.deepcopy(existing),
                                     "model": "m", "generated_at": "2026-10-01T00:00:00+00:00"})
    out["questions"] = [
        _raw("Bad tag?", "memoization in general"),
        {"question": "Three options?", "options": ["a", "b", "c"], "concept": "use-memo"},
        {"question": "", "options": ["a", "b", "c", "d"], "concept": "use-memo"},
    ]

    await question_service._generate(SLUG, initial=False)

    assert await _bank(st) == existing


async def test_garbage_llm_response_does_not_crash(env):
    st, calls, out = env
    await _add_concepts(st)
    out["response"] = {"questions": [None, "nope", 3]}

    await question_service._generate(SLUG, initial=True)

    assert await st.get("questions", SLUG) is None
    assert SLUG not in question_service._in_progress


async def test_course_without_concepts_keeps_free_tags(env):
    st, calls, out = env
    out["questions"] = [_raw("What is a closure?", "Closures and scope"), _raw("Hoisting?", "hoisting")]

    await question_service._generate(SLUG, initial=True)

    bank = await _bank(st)
    assert [q["concept"] for q in bank] == ["Closures and scope", "hoisting"]
    assert calls[0]["system"] == question_service.SYSTEM_PROMPT
    # every option survives the shuffle and correct_index still points at the right answer
    for q in bank:
        assert sorted(q["options"]) == sorted(["Right", "Wrong 1", "Wrong 2", "Wrong 3"])
        assert q["options"][q["correct_index"]] == "Right"


async def test_other_courses_concepts_do_not_constrain(env):
    st, calls, out = env
    await _add_concepts(st, slug="javascript-deep-dive")
    out["questions"] = [_raw("Q?", "anything goes")]

    await question_service._generate(SLUG, initial=True)

    assert [q["concept"] for q in await _bank(st)] == ["anything goes"]
