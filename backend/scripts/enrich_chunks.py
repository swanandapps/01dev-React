"""Offline chunk enrichment (spec §3): summary, keywords and likely questions per transcript chunk,
written by gpt-4.1-mini, one call per batch of <= 12 consecutive chunks of one lecture. Results go to
backend/data/enrichment/<slug>.json keyed by chunk_id + text hash (see app/retrieval/enrichment.py),
saved after every batch, so the run is resumable; fresh entries are skipped, so it is idempotent.
Suspected speech-to-text errors are collected in backend/data/glossary/<slug>.suggested.json for a
human to copy into <slug>.json (literal term/replacement entries) -- never applied automatically.
Never changes the seed.

Run from backend/ with the key inline and the database off:
  env OPENAI_API_KEY=... DATABASE_URL= .venv/bin/python scripts/enrich_chunks.py [--only slug] [--limit N] [--force]
"""
import argparse
import asyncio
import json
import os
import sys
from pathlib import Path
from typing import Optional

BACKEND = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND))

from app.models import TranscriptChunk  # noqa: E402
from app.retrieval.enrichment import (ENRICH_DIR, GLOSSARY_DIR, apply_enrichment, load_enrichment,  # noqa: E402
                                      save_enrichment, text_sha)

SEED = BACKEND / "app" / "data" / "seed_transcripts.json"
MODEL = "gpt-4.1-mini"
BATCH_CHUNKS = 12
CHARS = {"in": 0, "out": 0}   # rough usage (chars) for the cost estimate printed at the end

SYSTEM = """You index lecture transcripts for a course search engine. For each passage you are given, write:
- summary: one sentence (at most 30 words) saying what the passage teaches or shows, in plain words. Name the concrete technique, command or term. Never start with "In this passage" or mention "the instructor".
- keywords: 3 to 8 search terms a student might type for this passage: technical terms, acronyms, commands, function or package names, written the standard way (e.g. "IIFE", "npm link", "useMemo", "ES modules"). Correct obvious speech-to-text spellings in keywords (e.g. "iffy" -> "IIFE").
- questions: 2 or 3 short questions a student could ask that this passage answers. Each must make sense on its own (never "in this video" or "in this lecture").
Also list "fixes": words in the passages that look like speech-to-text mistakes for technical terms, as {"heard": "<word as written>", "means": "<correct term>"}; [] if none. Only list fixes you are confident about.
The passages are consecutive parts of one lecture: use the neighbouring passages for context, but describe each passage on its own.
Return only JSON: {"chunks": [{"id": "<passage id>", "summary": "...", "keywords": ["..."], "questions": ["..."]}], "fixes": [{"heard": "...", "means": "..."}]}"""


async def _complete(system: str, user: str) -> Optional[dict]:
    from app.services.llm import llm
    out = await llm.generate_json(system, user, temperature=0.2, max_tokens=2000)
    CHARS["in"] += len(system) + len(user)
    CHARS["out"] += len(json.dumps(out)) if out else 0
    return out


def _user(batch: list[TranscriptChunk]) -> str:
    c0 = batch[0]
    body = "\n".join(f"[{c.chunk_id}] {c.text_clean or c.text}" for c in batch)
    return f"Course: {c0.course_title}\nChapter: {c0.chapter}\nLecture: {c0.lecture_title}\n\nPassages:\n{body}"


def make_batches(chunks: list[TranscriptChunk], todo_ids: set[str], size: int = BATCH_CHUNKS):
    by_lecture: dict[str, list[TranscriptChunk]] = {}
    for c in chunks:
        if c.chunk_id in todo_ids:
            by_lecture.setdefault(c.lecture_id, []).append(c)
    return [group[i:i + size] for group in by_lecture.values() for i in range(0, len(group), size)]


def _strings(v, limit: int, max_len: int) -> list[str]:
    out: list[str] = []
    for s in v if isinstance(v, list) else []:
        s = str(s).strip()
        if s and len(s) <= max_len and s not in out:
            out.append(s)
    return out[:limit]


def validate_batch(raw: Optional[dict], ids: set[str]) -> tuple[dict[str, dict], list[dict]]:
    if not isinstance(raw, dict):
        return {}, []
    entries: dict[str, dict] = {}
    for item in raw.get("chunks") or []:
        if not isinstance(item, dict) or item.get("id") not in ids or item["id"] in entries:
            continue
        summary = str(item.get("summary") or "").strip()
        keywords = _strings(item.get("keywords"), 8, 40)
        questions = _strings(item.get("questions"), 3, 200)
        if summary and len(summary) <= 300 and keywords and questions:
            entries[item["id"]] = {"summary": summary, "keywords": keywords, "questions": questions}
    fixes = [{"heard": str(f["heard"]).strip(), "means": str(f["means"]).strip()}
             for f in raw.get("fixes") or []
             if isinstance(f, dict) and str(f.get("heard") or "").strip() and str(f.get("means") or "").strip()]
    return entries, fixes


def _save_suggestions(slug: str, fixes: list[tuple[dict, str]], glossary_dir: Path) -> None:
    p = Path(glossary_dir) / f"{slug}.suggested.json"
    data = json.loads(p.read_text()) if p.exists() else {}
    for fix, chunk_id in fixes:
        row = data.setdefault(fix["heard"], {"means": fix["means"], "count": 0, "chunk_ids": []})
        row["count"] += 1
        if chunk_id not in row["chunk_ids"]:
            row["chunk_ids"].append(chunk_id)
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.with_name(p.name + ".tmp")
    tmp.write_text(json.dumps(dict(sorted(data.items())), indent=1, ensure_ascii=False) + "\n")
    os.replace(tmp, p)


async def enrich(chunks: list[TranscriptChunk], enrich_dir: Path = ENRICH_DIR, glossary_dir: Path = GLOSSARY_DIR,
                 *, limit: Optional[int] = None, force: bool = False, concurrency: int = 4) -> dict:
    chunks = apply_enrichment(chunks, enrich_dir, glossary_dir)   # chapter + text_clean for the prompt
    stats = {"calls": 0, "enriched": 0, "skipped_fresh": 0, "failed_batches": 0}
    entries = {slug: load_enrichment(slug, enrich_dir) for slug in dict.fromkeys(c.course_id for c in chunks)}
    todo = set()
    for c in chunks:
        e = entries[c.course_id].get(c.chunk_id)
        if not force and e and e.get("text_sha") == text_sha(c.text):
            stats["skipped_fresh"] += 1
        else:
            todo.add(c.chunk_id)
    batches = make_batches(chunks, todo)
    if limit is not None:
        batches = batches[:limit]
    sem, lock = asyncio.Semaphore(concurrency), asyncio.Lock()

    async def one(batch: list[TranscriptChunk]):
        slug = batch[0].course_id
        async with sem:
            stats["calls"] += 1
            try:
                got, fixes = validate_batch(await _complete(SYSTEM, _user(batch)), {c.chunk_id for c in batch})
            except Exception as e:  # noqa: BLE001 -- one batch failing must not stop the run
                print(f"  {batch[0].lecture_id}: {e!r}")
                got, fixes = {}, []
            if not got:
                stats["failed_batches"] += 1
                return
            async with lock:  # one writer per file; saved after every batch (resumable)
                for c in batch:
                    if c.chunk_id in got:
                        entries[slug][c.chunk_id] = {"text_sha": text_sha(c.text), **got[c.chunk_id]}
                        stats["enriched"] += 1
                save_enrichment(slug, entries[slug], MODEL, enrich_dir)
                if fixes:
                    _save_suggestions(slug, [(f, batch[0].chunk_id) for f in fixes], glossary_dir)

    await asyncio.gather(*(one(b) for b in batches))
    return stats


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--only", help="only this course slug")
    ap.add_argument("--limit", type=int, help="at most N LLM calls (trial run)")
    ap.add_argument("--force", action="store_true", help="re-enrich even fresh entries")
    ap.add_argument("--concurrency", type=int, default=4)
    a = ap.parse_args(argv)
    chunks = [TranscriptChunk(**c) for c in json.loads(SEED.read_text())]
    if a.only:
        chunks = [c for c in chunks if c.course_id == a.only]
    stats = asyncio.run(enrich(chunks, limit=a.limit, force=a.force, concurrency=a.concurrency))
    tin, tout = CHARS["in"] / 4, CHARS["out"] / 4
    print(stats, f"~{tin:.0f} in / ~{tout:.0f} out tokens, ~${tin * 0.4e-6 + tout * 1.6e-6:.3f}")
    return 1 if stats["failed_batches"] else 0


if __name__ == "__main__":
    sys.exit(main())
