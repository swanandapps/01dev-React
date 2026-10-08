"""
Question banks for the FULL concept graph (app/data/concept_graph_preview.json): 2 easy, 2 medium, 2 hard
questions per concept, generated chapter by chapter from that chapter's transcripts, with the same prompt and
validation as scripts/build_demo_question_banks.py.

The existing demo banks (app/data/demo/question_banks.json) are kept as they are, ids included, because past
quiz answers reference those ids. New questions get ids {slug}-g{n} ("g" = graph), which never collide with the
demo banks' {slug}-t{n} or the app's {slug}-q{n}.

Also writes the full taxonomy (app/data/full/taxonomy.json, same shape as app/data/demo/taxonomy.json) so the
seed script can load the whole graph.

  cd backend && env OPENAI_API_KEY=... .venv/bin/python scripts/build_full_question_banks.py
Resumable: chapters already in app/data/full/question_banks.partial.json are skipped.
"""
import asyncio
import json
import os
import random
import re
import sys
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

BACKEND = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BACKEND))
sys.path.insert(0, str(BACKEND / "scripts"))

import build_demo_question_banks as demo  # noqa: E402  (prompt, validation, transcript helpers)

DATA = BACKEND / "app" / "data"
FULL = DATA / "full"
PREVIEW = DATA / "concept_graph_preview.json"
PARTIAL = FULL / "question_banks.partial.json"
CONCURRENCY = 8
MANUAL_LINKS = {"javascript-deep-dive": [{"source": "call-stack", "target": "event-loop", "type": "prerequisite_of"}]}


def full_taxonomy(preview: dict) -> dict:
    """Preview graph -> taxonomy.json shape: {slug: {title, concepts: [{name, description}], relationships}}."""
    sys.path.insert(0, str(BACKEND / "scripts"))
    from build_concept_graph_preview import clean_relationships
    out = {}
    for slug, g in preview["courses"].items():
        names = {c["name"] for c in g["concepts"]}
        rels = clean_relationships(MANUAL_LINKS.get(slug, []) + g["relationships"], names)
        out[slug] = {"title": g["title"],
                     "concepts": [{"name": c["name"], "description": c["description"], "chapter": c["chapter"],
                                   "lectures": c["lectures"]} for c in g["concepts"]],
                     "relationships": rels}
    return out


async def build_chapter(slug: str, ci: int, chapter: str, tags: list[str], lectures: list[str], sem) -> list[dict]:
    from app.services.llm import llm
    chunks = [c for c in demo.load_chunks(slug) if c["lecture_title"] in set(lectures)]
    if not chunks or not tags:
        return []
    text = demo.transcript_text(chunks)
    buckets, seen = defaultdict(list), set()
    async with sem:
        for attempt in range(1, demo.MAX_RETRIES + 2):
            left = demo.missing_buckets(buckets, tags) if attempt > 1 else {(t, d): demo.PER_DIFFICULTY
                                                                             for t in tags for d in demo.DIFFICULTIES}
            if not left:
                break
            slots = "\n".join(f"- {t} / {d}: {n}" for (t, d), n in left.items())
            user = (f"CONCEPT TAGS (use exactly): {', '.join(tags)}\n\nQUESTIONS NEEDED (concept / difficulty: count):\n"
                    f"{slots}\n\nTRANSCRIPTS:\n{text[:24000]}")
            if seen:
                user += "\n\nDo NOT repeat or reword these existing questions:\n" + "\n".join(f"- {q}" for q in sorted(seen))
            data = await llm.generate_json(demo.SYSTEM_PROMPT, user, temperature=0.4, max_tokens=6000)
            raw = (data or {}).get("questions") or []
            for q in raw:     # the model copies the transcript marker: "[Lecture: 4.3 - ...]" -> "4.3 - ..."
                if isinstance(q, dict) and isinstance(q.get("lecture"), str):
                    q["lecture"] = re.sub(r"^\[?\s*Lecture:\s*", "", q["lecture"]).rstrip("]").strip()
            demo.add_valid(raw, buckets, seen, tags, lectures)
    missing = demo.missing_buckets(buckets, tags)
    print(f"  {slug} ch{ci + 1}: {len(tags)} concepts, missing slots: {sum(missing.values())}", flush=True)
    out = []
    for t in tags:
        for d in demo.DIFFICULTIES:
            out += [{**q, "concept": t, "difficulty": d} for q in buckets[(t, d)][:demo.PER_DIFFICULTY]]
    return out


def _finalize(slug: str, raw: list[dict]) -> list[dict]:
    out = []
    for i, q in enumerate(raw, 1):
        qid = f"{slug}-g{i}"
        correct = str(q["options"][q["correct_index"]]).strip()
        opts = [str(o).strip() for o in q["options"]]
        random.Random(qid).shuffle(opts)
        out.append({"id": qid, "question": q["question"].strip(), "options": opts, "correct_index": opts.index(correct),
                    "explanation": q["explanation"].strip(), "concept": q["concept"], "difficulty": q["difficulty"],
                    "lecture": q["lecture"]})
    return out


async def main() -> None:
    from app.services.llm import GEN_MODEL, llm
    if not llm.available:
        raise SystemExit("OPENAI_API_KEY not set")
    FULL.mkdir(parents=True, exist_ok=True)
    preview = json.loads(PREVIEW.read_text())
    taxonomy = full_taxonomy(preview)
    (FULL / "taxonomy.json").write_text(json.dumps({"_comment": "Full concept graph, generated from "
                                                    "concept_graph_preview.json (scripts/build_full_question_banks.py).",
                                                    "courses": taxonomy}, indent=2, ensure_ascii=False) + "\n")
    demo_banks = json.loads((DATA / "demo" / "question_banks.json").read_text())
    catalog = {c["slug"]: c for c in json.loads((DATA / "catalog.json").read_text())}
    partial = json.loads(PARTIAL.read_text()) if PARTIAL.exists() else {}

    jobs = []
    for slug, g in preview["courses"].items():
        have = {q["concept"] for q in demo_banks.get(slug, {}).get("questions", [])}
        by_ch = defaultdict(list)
        for c in g["concepts"]:
            if c["name"] not in have and c["chapter_index"] is not None:
                by_ch[c["chapter_index"]].append(c["name"])
        for ci, tags in sorted(by_ch.items()):
            key = f"{slug}:{ci}"
            if partial.get(key):          # done and non-empty; an empty chapter is retried
                continue
            ch = catalog[slug]["chapters"][ci]
            jobs.append((key, slug, ci, ch["name"], tags, ch["subchapters"]))
    print(f"{len(jobs)} chapters to generate ({sum(1 for v in partial.values() if v)} already done)")
    sem = asyncio.Semaphore(CONCURRENCY)

    async def run(job):
        key, slug, ci, name, tags, lectures = job
        qs = await build_chapter(slug, ci, name, tags, lectures, sem)
        partial[key] = qs
        PARTIAL.write_text(json.dumps(partial, ensure_ascii=False))   # resumable
    await asyncio.gather(*(run(j) for j in jobs))

    banks = {}
    for slug, g in preview["courses"].items():
        old = demo_banks.get(slug, {}).get("questions", [])
        new = [q for key in sorted(k for k in partial if k.startswith(slug + ":")) for q in partial[key]]
        banks[slug] = {"course_id": slug, "course_title": g["title"], "questions": old + _finalize(slug, new),
                       "model": GEN_MODEL, "generated_at": datetime.now(timezone.utc).isoformat()}
    (FULL / "question_banks.json").write_text(json.dumps(banks, indent=1, ensure_ascii=False) + "\n")
    print(f"wrote {FULL / 'question_banks.json'}: {sum(len(b['questions']) for b in banks.values())} questions")


if __name__ == "__main__":
    for var in ("DATABASE_URL", "FIREBASE_SERVICE_ACCOUNT_JSON", "GOOGLE_APPLICATION_CREDENTIALS"):
        os.environ[var] = ""          # never touch a real store from this script
    os.environ.setdefault("LANGSMITH_TRACING", "false")
    asyncio.run(main())
