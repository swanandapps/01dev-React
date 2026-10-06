import json

from app.models import TranscriptChunk
from app.retrieval import enrichment as en
from app.retrieval.text import last_sentence, norm_title


def _c(n, text, lecture="custom-library-5-2", title="6.5 - IIFE, To The Rescue"):
    return TranscriptChunk(chunk_id=f"{lecture}-{n}", course_id="custom-library", course_title="Build a Custom Library",
                           lecture_id=lecture, lecture_title=title, text=text, start_time=n * 60,
                           end_time=n * 60 + 60)


def _dirs(tmp_path, entries=None, glossary=None):
    e, g = tmp_path / "enrichment", tmp_path / "glossary"
    e.mkdir()
    g.mkdir()
    if entries is not None:
        (e / "custom-library.json").write_text(json.dumps({"version": 1, "model": "m", "chunks": entries}))
    if glossary is not None:
        (g / "custom-library.json").write_text(json.dumps({"replacements": glossary}))
    return e, g


def test_text_helpers():
    assert norm_title("8.1 - The `npm link`   Command") == "8.1 - the npm link command"
    assert last_sentence("First one. Second one is here.") == "Second one is here."
    assert last_sentence("no punctuation at all") == "no punctuation at all"
    assert len(last_sentence("x" * 500)) == 200


def test_glossary_fixes_text_clean_only(tmp_path):
    e, g = _dirs(tmp_path, glossary=[{"pattern": r"\biffy\b", "replace": "IIFE"},
                                     {"pattern": r"\bmodel pattern(s?)\b", "replace": r"module pattern\1"}])
    raw = "the new pattern  was iffy, the model patterns before modules"
    out = en.apply_enrichment([_c(0, raw)], e, g)[0]
    assert out.text == raw                                   # text_raw untouched
    assert out.text_clean == "the new pattern was IIFE, the module patterns before modules"
    assert (out.start_time, out.end_time, out.chunk_id) == (0, 60, "custom-library-5-2-0")


def test_embed_text_has_header_summary_terms_overlap_and_text(tmp_path):
    first, second = _c(0, "Intro. We wrap the function in parens."), _c(1, "Then we call it at once.")
    e, g = _dirs(tmp_path, entries={second.chunk_id: {"text_sha": en.text_sha(second.text),
                                                      "summary": "Calling the wrapped function immediately.",
                                                      "keywords": ["IIFE", "scope"],
                                                      "questions": ["what is an IIFE?"]}})
    a, b = en.apply_enrichment([first, second], e, g)
    assert a.summary == "" and a.keywords == []
    from app.services import catalog_service
    assert b.chapter == catalog_service.by_slug("custom-library")["chapters"][5]["name"]   # lecture id ...-5-2
    lines = b.embed_text.split("\n")
    assert lines[0].startswith("Build a Custom Library › ") and lines[0].endswith("› 6.5 - IIFE, To The Rescue")
    assert "Summary: Calling the wrapped function immediately." in lines
    assert "Key terms: IIFE, scope" in lines
    assert "Previously: We wrap the function in parens." in lines
    assert lines[-1] == "Then we call it at once."
    assert "Previously:" not in a.embed_text                 # first chunk of a lecture has no overlap
    assert b.embed_model == en.EMBED_MODEL and b.content_hash == en.content_hash(b.embed_text)
    assert b.questions == ["what is an IIFE?"]


def test_stale_enrichment_is_ignored(tmp_path):
    c = _c(0, "edited transcript text")
    e, g = _dirs(tmp_path, entries={c.chunk_id: {"text_sha": en.text_sha("the OLD text"), "summary": "old",
                                                 "keywords": ["old"], "questions": []}})
    out = en.apply_enrichment([c], e, g)[0]
    assert out.summary == "" and out.keywords == [] and "old" not in out.embed_text


def test_content_hash_changes_with_text_model_or_glossary(tmp_path):
    e, g = _dirs(tmp_path)
    h1 = en.apply_enrichment([_c(0, "an iffy")], e, g)[0].content_hash
    assert en.apply_enrichment([_c(0, "an iffy")], e, g)[0].content_hash == h1          # deterministic
    assert en.content_hash("x", "text-embedding-3-large") != en.content_hash("x")
    (g / "custom-library.json").write_text(json.dumps({"replacements": [{"pattern": r"\biffy\b", "replace": "IIFE"}]}))
    assert en.apply_enrichment([_c(0, "an iffy")], e, g)[0].content_hash != h1


def test_missing_files_mean_header_plus_text(tmp_path):
    e, g = _dirs(tmp_path)
    out = en.apply_enrichment([_c(0, "plain")], e, g)[0]
    assert out.embed_text.split("\n")[-1] == "plain" and en.embed_input(out) == out.embed_text
    assert en.embed_input(_c(0, "raw only")) == "raw only"


def test_save_then_load_round_trip_is_sorted_and_atomic(tmp_path):
    entries = {"b-1": {"text_sha": "1", "summary": "s", "keywords": [], "questions": []},
               "a-1": {"text_sha": "2", "summary": "t", "keywords": [], "questions": []}}
    p = en.save_enrichment("x", entries, "gpt-4.1-mini", tmp_path)
    assert list(json.loads(p.read_text())["chunks"]) == ["a-1", "b-1"]
    assert en.load_enrichment("x", tmp_path) == entries
    assert en.load_enrichment("missing", tmp_path) == {}
    assert not list(tmp_path.glob("*.tmp"))


def test_glossary_term_is_whole_word_and_regex_needs_boundary(tmp_path):
    e, g = _dirs(tmp_path, glossary=[{"term": "tree shucking", "replacement": "tree shaking"},
                                     {"pattern": r"\bnp\b", "replace": "npm"}])
    out = en.apply_enrichment([_c(0, "Tree  Shucking and np and npm and np-x")], e, g)[0]
    assert out.text_clean.lower() == "tree shaking and npm and npm and npm-x"
    (g / "custom-library.json").write_text(json.dumps({"replacements": [{"term": "np", "replacement": "npm"}]}))
    assert en.apply_enrichment([_c(0, "npm np")], e, g)[0].text_clean == "npm npm"
    (g / "custom-library.json").write_text(json.dumps({"replacements": [{"pattern": "np", "replace": "npm"}]}))
    assert en.load_glossary("custom-library", g) == []      # bad entry skipped, not raised


def test_overlap_resets_per_lecture_and_follows_time_order(tmp_path):
    e, g = _dirs(tmp_path)
    a = _c(0, "Lecture A ends here.", lecture="custom-library-5-1")
    b0, b1 = _c(0, "B opens.", lecture="custom-library-5-2"), _c(1, "B continues.", lecture="custom-library-5-2")
    out = en.apply_enrichment([a, b1, b0], e, g)           # b1 listed before b0
    assert [c.chunk_id for c in out] == [a.chunk_id, b1.chunk_id, b0.chunk_id]
    assert "Previously:" not in out[2].embed_text and "Previously: B opens." in out[1].embed_text
    assert "Previously:" not in out[0].embed_text


def test_bad_data_files_skip_only_the_bad_part(tmp_path):
    e, g = _dirs(tmp_path)
    gp, ep = g / "custom-library.json", e / "custom-library.json"
    gp.write_text("{not json")
    assert en.load_glossary("custom-library", g) == []
    gp.write_text(json.dumps({"replacements": [{"pattern": "np", "replace": "x"}, {"term": "a"},
                                               {"term": "tree shucking", "replacement": "tree shaking"}]}))
    assert len(en.load_glossary("custom-library", g)) == 1      # only the good entry survives
    ep.write_text("{not json")
    assert en.load_enrichment("custom-library", e) == {}
    ep.write_text(json.dumps({"chunks": {"a": {"text_sha": "x"}, "b": "junk"}}))
    assert list(en.load_enrichment("custom-library", e)) == ["a"]
    out = en.apply_enrichment([_c(0, "hello")], e, g)           # entry missing keys: no raise
    assert out[0].embed_text and out[0].summary == ""


def test_last_sentence_never_cuts_a_word_on_unpunctuated_text():
    text = " ".join(f"word{i}" for i in range(60))
    out = last_sentence(text)
    assert out == " ".join(f"word{i}" for i in range(35, 60))      # last 25 whole words
    assert all(w in text.split() for w in out.split())
    assert last_sentence("short one. " + text).startswith("word35")
