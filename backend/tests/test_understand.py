import asyncio

import pytest

from app.retrieval import understand as un

HIST = [{"role": "user", "content": "what is the np package?"},
        {"role": "assistant", "content": "np is a tool that runs the publish checks. " + "x" * 600}]


@pytest.mark.parametrize("q", ["what is an IIFE?", "IIFE?", "np", "how do I publish an npm package with np"])
def test_acronym_question_is_self_contained(q):
    assert un.self_contained(q) and not un.needs_rewrite(q, [], None)


@pytest.mark.parametrize("q", ["what does this mean?", "and how do I use it?", "what about the second one he showed",
                               "so why?"])
def test_context_leaning_questions_need_a_rewrite_even_without_history(q):
    assert not un.self_contained(q) and un.needs_rewrite(q, [], None)


def test_any_context_means_a_rewrite():
    assert un.needs_rewrite("what is an IIFE?", HIST, None)
    assert un.needs_rewrite("what is an IIFE?", [], "6.5 - IIFE, To The Rescue")


def test_prompt_has_lecture_last_turns_truncated_and_message():
    long_hist = [{"role": "user", "content": f"q{i}"} for i in range(6)] + HIST
    text = un.build_user_prompt("how do I use it?", long_hist, "11.1 - Publishing using `np`")
    assert text.startswith("Current lecture: 11.1 - Publishing using `np`")
    assert "q3" not in text and "student: q4" in text                # only the last HISTORY_TURNS (4) turns
    assert "student: what is the np package?" in text and "tutor: np is a tool" in text
    assert "x" * un.HISTORY_CHARS not in text
    assert text.rstrip().endswith("New message: how do I use it?")
    assert "Current lecture: none" in un.build_user_prompt("q", [], None)


def test_parse_valid_and_cleaned():
    u = un.parse_understanding({"search_query": " How do I publish a package with np? ",
                                "keywords": ["np", "publish", "np", "", "a", "b", "c", "d", "e"],
                                "intent": "EXPLAIN"}, "how do I use it?")
    assert (u.search_query, u.keywords, u.intent) == ("How do I publish a package with np?",
                                                      ["np", "publish", "a", "b", "c", "d"], "explain")


@pytest.mark.parametrize("raw,expect", [
    ({"search_query": "q2", "keywords": [], "intent": "dance"}, ("q2", "explain")),
    ({"search_query": "", "keywords": [], "intent": "account"}, ("orig", "account")),
    ({"search_query": "y" * 400, "intent": "navigate"}, ("orig", "navigate")),
])
def test_parse_repairs_fields(raw, expect):
    u = un.parse_understanding(raw, "orig")
    assert (u.search_query, u.intent) == expect


@pytest.mark.parametrize("raw", [None, "text", []])
def test_parse_unusable_is_none(raw):
    assert un.parse_understanding(raw, "q") is None


async def test_skip_never_calls_the_model(monkeypatch):
    async def boom(system, user):
        raise AssertionError("self-contained, no context: no LLM call")

    monkeypatch.setattr(un, "_complete", boom)
    u = await un.understand("what is an IIFE?")
    assert u.skipped and (u.search_query, u.intent, u.keywords) == ("what is an IIFE?", "explain", [])


async def test_understand_rewrites_with_history(monkeypatch):
    async def fake(system, user):
        assert "New message: ok how do I use it to publish?" in user
        return {"search_query": "how do I publish a package with np?", "keywords": ["np"], "intent": "explain"}

    monkeypatch.setattr(un, "_complete", fake)
    u = await un.understand("ok how do I use it to publish?", HIST, None)
    assert not u.skipped and not u.fallback and u.search_query == "how do I publish a package with np?"


async def test_timeout_and_errors_fall_back_to_the_raw_question(monkeypatch, capsys):
    async def slow(system, user):
        await asyncio.sleep(1)

    monkeypatch.setattr(un, "UNDERSTAND_TIMEOUT_S", 0.01)
    monkeypatch.setattr(un, "_complete", slow)
    u = await un.understand("what does this mean?", HIST, None)
    assert u.fallback and u.error == "TimeoutError" and (u.search_query, u.intent) == ("what does this mean?", "explain")

    async def boom(system, user):
        raise RuntimeError("down")

    monkeypatch.setattr(un, "_complete", boom)
    assert (await un.understand("what does this mean?", HIST, None)).fallback
    assert "[understand] fallback" in capsys.readouterr().out


@pytest.mark.parametrize("q", ["give me an example", "explain this", "what does this mean?", "my progress",
                               "what am I weak at?"])
def test_vague_in_lecture_question_calls_the_model_with_the_lecture(q):
    assert un.needs_rewrite(q, [], "6.5 - IIFE, To The Rescue")
    assert "Current lecture: 6.5 - IIFE, To The Rescue" in un.build_user_prompt(q, [], "6.5 - IIFE, To The Rescue")


def test_system_prompt_covers_the_phase4_cases():
    s = un.SYSTEM.lower()
    for needle in ("current lecture", "example of", "account", "navigate", "off_topic", "never",
                   "course name"):
        assert needle in s


async def test_vague_question_in_lecture_gets_a_standalone_query(monkeypatch):
    async def fake(system, user):
        assert "Current lecture: 6.5 - IIFE, To The Rescue" in user
        return {"search_query": "example of an IIFE", "keywords": ["IIFE"], "intent": "explain"}

    monkeypatch.setattr(un, "_complete", fake)
    u = await un.understand("give me an example", [], "6.5 - IIFE, To The Rescue")
    assert u.search_query == "example of an IIFE" and u.intent == "explain" and not u.fallback


async def test_vague_question_without_context_stays_vague_on_unusable_reply(monkeypatch):
    async def none(system, user):
        return None

    monkeypatch.setattr(un, "_complete", none)
    u = await un.understand("explain this", [], None)
    assert u.fallback and u.search_query == "explain this" and u.intent == "explain"


@pytest.mark.parametrize("raw,intent,query", [
    ({"search_query": "what courses does the student have", "keywords": [], "intent": "account"}, "account", None),
    ({"search_query": "publishing with np", "keywords": ["np"], "intent": "navigate"}, "navigate", None),
    ({"search_query": "bake sourdough", "keywords": [], "intent": "off_topic"}, "off_topic", None),
    ({"keywords": ["np"], "intent": "explain"}, "explain", "orig"),     # missing key -> raw question kept
])
def test_parse_intents_and_missing_key(raw, intent, query):
    u = un.parse_understanding(raw, "orig")
    assert u.intent == intent and (query is None or u.search_query == query)


@pytest.mark.parametrize("q", ["what am I weak at?", "what courses do I have?", "my progress",
                               "take me to the part about closures"])
def test_account_and_navigation_messages_always_reach_the_model(q):
    assert not un.self_contained(q) and un.needs_rewrite(q, [], None)
