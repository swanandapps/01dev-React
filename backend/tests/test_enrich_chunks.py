import json

from app.models import TranscriptChunk
from app.retrieval import enrichment as en
from scripts import enrich_chunks as ec


WORDS = "an IIFE wraps code so its variables stay out of the global scope"


def _chunks(texts, lecture="custom-library-5-2"):
    return [TranscriptChunk(chunk_id=f"{lecture}-{i}", course_id="custom-library", course_title="Build a Custom Library",
                            lecture_id=lecture, lecture_title="6.5 - IIFE, To The Rescue", text=t,
                            start_time=60 * i, end_time=60 * i + 60) for i, t in enumerate(texts)]


def _reply(ids, fixes=()):
    return {"chunks": [{"id": i, "summary": f"about {i}", "keywords": ["IIFE", "scope"],
                        "questions": [f"what is {i}?"]} for i in ids], "fixes": list(fixes)}


def test_validate_batch_keeps_only_sent_ids_and_cleans_fields():
    raw = {"chunks": [
        {"id": "a", "summary": " s ", "keywords": ["k"] * 3 + [f"k{n}" for n in range(10)],
         "questions": [f"q{n}?" for n in range(5)]},
        {"id": "zzz", "summary": "s", "keywords": ["k"], "questions": ["q?"]},
        {"id": "b", "summary": "", "keywords": ["k"], "questions": ["q?"]},
    ], "fixes": [{"heard": "iffy", "means": "IIFE"}, {"heard": "", "means": "x"}]}
    entries, fixes = ec.validate_batch(raw, {"a", "b"})
    assert list(entries) == ["a"]                                   # zzz never sent, b has no summary
    assert entries["a"]["summary"] == "s"
    assert entries["a"]["keywords"] == ["k"] + [f"k{n}" for n in range(7)]   # deduped, max 8
    assert len(entries["a"]["questions"]) == 3
    assert fixes == [{"heard": "iffy", "means": "IIFE"}]
    assert ec.validate_batch(None, {"a"}) == ({}, [])


def test_batches_stay_inside_one_lecture_and_respect_the_size():
    chunks = _chunks([WORDS] * 13) + _chunks([WORDS] * 2, lecture="custom-library-9-0")
    out = ec.make_batches(chunks, {c.chunk_id for c in chunks}, size=12)
    assert [len(b) for b in out] == [12, 1, 2]
    assert all(len({c.lecture_id for c in b}) == 1 for b in out)


async def test_enrich_is_resumable_idempotent_and_keyed_by_text(tmp_path, monkeypatch):
    calls = []

    async def fake(system, user):
        ids = [line.split("]")[0][1:] for line in user.splitlines() if line.startswith("[")]
        calls.append(ids)
        return _reply(ids, fixes=[{"heard": "iffy", "means": "IIFE"}])

    monkeypatch.setattr(ec, "_complete", fake)
    e, g = tmp_path / "enrichment", tmp_path / "glossary"
    chunks = _chunks([WORDS + " iffy"] * 13)
    s1 = await ec.enrich(chunks, e, g, limit=1)
    assert s1["calls"] == 1 and s1["enriched"] == 12
    assert len(en.load_enrichment("custom-library", e)) == 12      # saved after the batch: resumable
    s2 = await ec.enrich(chunks, e, g)
    assert s2["calls"] == 1 and s2["enriched"] == 1 and s2["skipped_fresh"] == 12
    s3 = await ec.enrich(chunks, e, g)
    assert s3["calls"] == 0                                         # idempotent
    chunks[0].text = "edited iffy text with several different words"
    s4 = await ec.enrich(chunks, e, g)
    assert s4["calls"] == 1 and s4["enriched"] == 1                 # stale text_sha -> re-enriched
    entry = en.load_enrichment("custom-library", e)["custom-library-5-2-0"]
    assert entry["text_sha"] == en.text_sha("edited iffy text with several different words")
    sugg = json.loads((g / "custom-library.suggested.json").read_text())
    assert sugg["iffy"]["means"] == "IIFE" and sugg["iffy"]["count"] >= 1
    assert sorted(p.name for p in tmp_path.rglob("*") if p.is_file()) == ["custom-library.json",
                                                                          "custom-library.suggested.json"]


async def test_a_failed_batch_is_reported_and_saves_nothing(tmp_path, monkeypatch):
    async def boom(system, user):
        raise TimeoutError("slow")

    monkeypatch.setattr(ec, "_complete", boom)
    s = await ec.enrich(_chunks([WORDS, WORDS + " again"]), tmp_path / "e", tmp_path / "g")
    assert s["failed_batches"] == 1 and s["enriched"] == 0 and s["missing"] == 2
    assert en.load_enrichment("custom-library", tmp_path / "e") == {}


async def test_junk_and_listed_chunks_are_skipped_and_partial_rejection_is_visible(tmp_path, monkeypatch):
    async def fake(system, user):
        ids = [line.split("]")[0][1:] for line in user.splitlines() if line.startswith("[")]
        return _reply(ids[:-1])                     # model drops the last chunk of the batch

    monkeypatch.setattr(ec, "_complete", fake)
    e, g = tmp_path / "e", tmp_path / "g"
    e.mkdir()
    (e / "skip.json").write_text(json.dumps({"custom-library-5-2-1": "whisper hallucination"}))
    chunks = _chunks([WORDS, WORDS, "? ? ? ?", "run it again run it", WORDS])   # ids 0..4
    s = await ec.enrich(chunks, e, g)
    assert s["skipped_junk"] == 3                    # listed (1), no letters (2), too few unique words (3)
    assert s["enriched"] == 1 and s["failed_batches"] == 1 and s["missing"] == 1
    assert set(en.load_enrichment("custom-library", e)) == {"custom-library-5-2-0"}


def test_grounding_drops_keywords_not_in_the_passage_or_title():
    text = "the browser exposes variables and nodes of the document"
    kept = ec.ground_keywords(["variable", "HTML nodes", "JIT compilation", "knowledge gap", "IIFE"], text,
                              "6.1 - What is Window")
    assert kept == ["variable", "HTML nodes"]       # "nodes" is in the text; the rest are ungrounded
    out, _ = ec.validate_batch(_reply(["a"]), {"a"}, {"a": "iife wraps scope"})
    assert out["a"]["keywords"] == ["IIFE", "scope"]
    dropped = []
    out, _ = ec.validate_batch(_reply(["a"]), {"a"}, {"a": "nothing relevant here about scope"}, dropped)
    assert out["a"]["keywords"] == ["scope"] and dropped == [("a", "IIFE")]


async def test_suggestions_are_credited_only_to_the_chunk_containing_the_term(tmp_path, monkeypatch):
    async def fake(system, user):
        ids = [line.split("]")[0][1:] for line in user.splitlines() if line.startswith("[")]
        return _reply(ids, fixes=[{"heard": "iffy", "means": "IIFE"}, {"heard": "ghost", "means": "x"}])

    monkeypatch.setattr(ec, "_complete", fake)
    chunks = _chunks([WORDS, "the iffy pattern wraps everything in a function scope", WORDS])
    await ec.enrich(chunks, tmp_path / "e", tmp_path / "g")
    sugg = json.loads((tmp_path / "g" / "custom-library.suggested.json").read_text())
    assert sugg["iffy"]["chunk_ids"] == ["custom-library-5-2-1"] and "ghost" not in sugg
