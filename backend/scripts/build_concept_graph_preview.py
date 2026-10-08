"""
PREVIEW of a full concept graph for every course: 2-5 concepts per chapter, extracted once from the
chapter's transcripts, each with a description, the lectures that teach it, and links
(prerequisite_of / part_of / related_to) to concepts from this chapter or earlier ones.

Nothing in the app reads the preview. It's written to its own collections (`concepts_preview`,
`concept_relationships_preview`) and shown through views, so the live graph (16 concepts from
app/data/demo/taxonomy.json), practice, Quiz me and the tutor are untouched until it's switched over.

The 16 existing concept names are kept: they're given to the model as "existing concepts" to reuse, and
added back with their links if the model leaves them out, so current scores stay attached.

  python scripts/build_concept_graph_preview.py               # generate -> app/data/concept_graph_preview.json
  python scripts/build_concept_graph_preview.py --review      # one pass per course over all links (fix directions)
  python scripts/build_concept_graph_preview.py --apply       # write that file to the preview collections + views
"""
import argparse
import asyncio
import json
import re
import sys
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

DATA = Path(__file__).resolve().parents[1] / "app" / "data"
OUT = DATA / "concept_graph_preview.json"
REL_TYPES = {"prerequisite_of", "part_of", "related_to"}
# Links checked by hand, always applied on --apply (the model doesn't reliably draw every obvious one).
MANUAL_LINKS = {
    "javascript-deep-dive": [
        {"source": "call-stack", "target": "event-loop", "type": "prerequisite_of"},
    ],
}
PER_LECTURE_CHARS = 4500

SYSTEM = """You build the concept map for one chapter of a programming course, from its lecture transcripts.
Return JSON: {"concepts": [{"name": "...", "description": "...", "lectures": ["..."]}],
              "relationships": [{"source": "...", "target": "...", "type": "prerequisite_of|part_of|related_to"}]}

Concepts:
- 2-5 concepts: the specific technical ideas a student must understand from this chapter
  (e.g. "call-stack", "microtask-queue", "closure-scope"). Not chapter labels like "introduction",
  "overview", "what we will build". An intro or wrap-up chapter may have 0-2.
- name: lowercase kebab-case, 1-4 words.
- If an idea is one of the EXISTING CONCEPTS, use that exact name. Don't make a near-duplicate.
- description: one plain sentence, at most 25 words, true to the transcript.
- lectures: the exact lecture titles from this chapter that teach it.

Relationships, between this chapter's concepts and the EXISTING ones:
- prerequisite_of: A must be understood before B makes sense. part_of: A is a component of B.
  related_to: closely connected, neither needed first.
- Link every new concept to at least one other concept when a real dependency exists. Only real ones."""


def slug(name: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", (name or "").lower()).strip("-")[:48]


def _creates_cycle(edges: set[tuple[str, str]], src: str, tgt: str) -> bool:
    """Would src -> tgt close a loop among prerequisite edges (i.e. can tgt already reach src)?"""
    nxt = defaultdict(list)
    for a, b in edges:
        nxt[a].append(b)
    stack, seen = [tgt], set()
    while stack:
        n = stack.pop()
        if n == src:
            return True
        if n not in seen:
            seen.add(n)
            stack.extend(nxt[n])
    return False


def clean_relationships(rels: list[dict], names: set[str], chapter: dict[str, int] | None = None) -> list[dict]:
    """Keep links whose ends exist, drop self-links, duplicates, unknown types, and prerequisite loops. With
    `chapter` (concept -> chapter index), also drop a prerequisite taught in a later chapter than what needs it."""
    out, seen, prereq = [], set(), set()
    for r in rels:
        s, t, typ = slug(r.get("source", "")), slug(r.get("target", "")), r.get("type")
        if s not in names or t not in names or s == t or typ not in REL_TYPES:
            continue
        if typ == "prerequisite_of" and chapter and (chapter.get(s) or 0) > (chapter.get(t) or 0):
            continue
        key = (s, t) if typ != "related_to" else tuple(sorted((s, t)))
        if (key, typ) in seen:
            continue
        if typ == "prerequisite_of" and _creates_cycle(prereq, s, t):
            continue
        seen.add((key, typ))
        if typ == "prerequisite_of":
            prereq.add((s, t))
        out.append({"source": s, "target": t, "type": typ})
    return out


def _chapter_text(lectures: list[str], chunks_by_lecture: dict) -> str:
    parts = []
    for title in lectures:
        text = " ".join(chunks_by_lecture.get(title, []))
        if text:
            parts.append(f"### {title}\n{text[:PER_LECTURE_CHARS]}")
    return "\n\n".join(parts)


def build_course(course: dict, chunks_by_lecture: dict, seed: dict | None, bank: list[dict]) -> dict:
    from app.services.lab.llm import _chat_json

    concepts: dict[str, dict] = {}
    rels: list[dict] = []
    seed_lectures = defaultdict(set)
    for q in bank:
        seed_lectures[q["concept"]].add(q.get("lecture", ""))
    for c in (seed or {}).get("concepts", []):
        concepts[c["name"]] = {"name": c["name"], "description": c["description"], "lectures": [],
                               "chapter_index": None, "chapter": None, "origin": "existing"}

    for ci, ch in enumerate(course["chapters"]):
        text = _chapter_text(ch["subchapters"], chunks_by_lecture)
        if not text:
            continue
        existing = "\n".join(f"- {n}: {c['description']}" for n, c in concepts.items()) or "(none yet)"
        user = (f"COURSE: {course['title']}\nCHAPTER: {ch['name']}\nLECTURES: {'; '.join(ch['subchapters'])}\n\n"
                f"EXISTING CONCEPTS:\n{existing}\n\nTRANSCRIPTS:\n{text}")
        data = _chat_json(SYSTEM, user, max_tokens=1600) or {}
        valid_lectures = set(ch["subchapters"])
        for c in data.get("concepts", [])[:5]:
            name = slug(c.get("name", ""))
            if not name:
                continue
            lectures = [t for t in c.get("lectures", []) if t in valid_lectures]
            cur = concepts.setdefault(name, {"name": name, "description": (c.get("description") or "").strip(),
                                             "lectures": [], "chapter_index": ci, "chapter": ch["name"],
                                             "origin": "generated"})
            if cur["chapter_index"] is None:      # an existing concept: place it where it's first taught
                cur["chapter_index"], cur["chapter"] = ci, ch["name"]
            cur["lectures"] = sorted(set(cur["lectures"]) | set(lectures))
        rels += data.get("relationships", [])
        print(f"  {course['slug']} ch{ci + 1}: {len(concepts)} concepts so far", flush=True)

    # Existing concepts the model never placed: put them where their bank questions are taught.
    for name, c in concepts.items():
        if c["chapter_index"] is None:
            lec = sorted(t for t in seed_lectures.get(name, []) if t)
            for ci, ch in enumerate(course["chapters"]):
                if lec and lec[0] in ch["subchapters"]:
                    c["chapter_index"], c["chapter"], c["lectures"] = ci, ch["name"], lec
                    break
    rels = (seed or {}).get("relationships", []) + rels      # existing links first, so they're always kept
    return {"title": course["title"],
            "concepts": sorted(concepts.values(), key=lambda c: (c["chapter_index"] if c["chapter_index"] is not None else 99, c["name"])),
            "relationships": clean_relationships(rels, set(concepts))}


async def generate() -> None:
    catalog = json.loads((DATA / "catalog.json").read_text())
    taxonomy = json.loads((DATA / "demo" / "taxonomy.json").read_text())["courses"]
    banks = json.loads((DATA / "demo" / "question_banks.json").read_text())
    by_course = defaultdict(lambda: defaultdict(list))
    for c in sorted(json.loads((DATA / "seed_transcripts.json").read_text()), key=lambda c: c.get("start_time", 0)):
        by_course[c["course_id"]][c["lecture_title"]].append(c["text"])

    def bank_for(slug_: str) -> list[dict]:
        b = banks.get(slug_) or []
        return b.get("questions", []) if isinstance(b, dict) else b

    results = await asyncio.gather(*(asyncio.to_thread(build_course, c, by_course[c["slug"]], taxonomy.get(c["slug"]),
                                                       bank_for(c["slug"])) for c in catalog))
    out = {"generated_at": datetime.now(timezone.utc).isoformat(), "courses": {c["slug"]: r for c, r in zip(catalog, results)}}
    OUT.write_text(json.dumps(out, indent=1, ensure_ascii=False))
    n_c = sum(len(r["concepts"]) for r in results)
    n_r = sum(len(r["relationships"]) for r in results)
    print(f"\nwrote {OUT} — {n_c} concepts, {n_r} links across {len(results)} courses")


REVIEW_MODEL = "gpt-4.1"   # link direction is where the small model slips; 10 calls, so use the stronger one

REVIEW = """You draw the links of a programming course's concept map. You get every concept in teaching order
(chapter number first), each with a one-line description. Return JSON:
{"learn_first": [{"first": "<concept>", "then": "<concept>"}],
 "parts":       [{"part": "<concept>", "of": "<concept>"}],
 "related":     [{"a": "<concept>", "b": "<concept>"}]}

- learn_first: you cannot understand "then" without first understanding "first". Ask for each pair: which one
  does a student need first? Examples: {"first": "call-stack", "then": "event-loop"},
  {"first": "microtask-queue", "then": "async-await-mechanism"} (await resumes as a microtask),
  {"first": "lexical-scope", "then": "closure"}, {"first": "v8-hidden-classes", "then": "inline-caches"}.
  Basics from earlier chapters usually come first. A bug or exercise that uses an idea comes AFTER the idea.
- parts: "part" is a component inside "of". Example: {"part": "microtask-queue", "of": "event-loop"}.
- related: connected, but neither is needed first.
- Every concept should have at least one link. Only real links. Use only the listed concept names."""


def review_course(g: dict) -> list[dict]:
    from openai import OpenAI

    lines = "\n".join(f"- ch{(c['chapter_index'] or 0) + 1} {c['name']}: {c['description']}" for c in g["concepts"])
    resp = OpenAI(timeout=180).chat.completions.create(
        model=REVIEW_MODEL, temperature=0.1, response_format={"type": "json_object"}, max_tokens=6000,
        messages=[{"role": "system", "content": REVIEW},
                  {"role": "user", "content": f"COURSE: {g['title']}\n\nCONCEPTS:\n{lines}"}])
    try:
        data = json.loads(resp.choices[0].message.content or "{}")
    except json.JSONDecodeError:
        return g["relationships"]
    reviewed = ([{"source": x.get("first"), "target": x.get("then"), "type": "prerequisite_of"} for x in data.get("learn_first", [])]
                + [{"source": x.get("part"), "target": x.get("of"), "type": "part_of"} for x in data.get("parts", [])]
                + [{"source": x.get("a"), "target": x.get("b"), "type": "related_to"} for x in data.get("related", [])])
    return reviewed if len(reviewed) >= len(g["relationships"]) // 2 else g["relationships"]   # a bad reply keeps the old


async def review() -> None:
    taxonomy = json.loads((DATA / "demo" / "taxonomy.json").read_text())["courses"]
    data = json.loads(OUT.read_text())
    slugs = list(data["courses"])
    results = await asyncio.gather(*(asyncio.to_thread(review_course, data["courses"][s]) for s in slugs))
    for s, rels in zip(slugs, results):
        g = data["courses"][s]
        seed = [r for r in taxonomy.get(s, {}).get("relationships", [])]
        before = len(g["relationships"])
        g["relationships"] = clean_relationships(seed + rels, {c["name"] for c in g["concepts"]},
                                                 {c["name"]: c["chapter_index"] or 0 for c in g["concepts"]})
        print(f"  {s}: {before} -> {len(g['relationships'])} links")
    data["reviewed_at"] = datetime.now(timezone.utc).isoformat()
    OUT.write_text(json.dumps(data, indent=1, ensure_ascii=False))


VIEWS = [
    """create or replace view concepts_preview_v as
    select data->>'course' as course, (data->>'chapter_index')::int + 1 as chapter_no, data->>'chapter' as chapter,
           data->>'name' as concept, data->>'description' as description,
           array_to_string(array(select jsonb_array_elements_text(data->'lectures')), ' | ') as taught_in,
           data->>'origin' as origin
    from docs where collection = 'concepts_preview'
    order by data->>'course', (data->>'chapter_index')::int, data->>'name'""",
    """create or replace view knowledge_graph_preview_v as
    select data->>'course' as course, data->>'source' as from_concept, data->>'type' as relation,
           data->>'target' as to_concept
    from docs where collection = 'concept_relationships_preview'
    order by data->>'course', data->>'type', data->>'source'""",
    """create or replace view demo_student_skill_graph_preview_v as
    select c.course, c.chapter_no, c.chapter, c.concept,
           coalesce((p.data->>'correct')::int, 0) as correct, coalesce((p.data->>'attempts')::int, 0) as attempts,
           round(100 * coalesce((p.data->>'accuracy')::numeric, 0)) as score_pct,
           case when coalesce((p.data->>'attempts')::int, 0) = 0 then 'not tried'
                when (p.data->>'accuracy')::numeric >= 0.8 then 'solid' else 'shaky' end as level,
           p.data->>'chat_confidence_note' as tutor_note,
           (select string_agg(r.from_concept, ', ') from knowledge_graph_preview_v r
             where r.course = c.course and r.to_concept = c.concept and r.relation = 'prerequisite_of') as prerequisites
    from concepts_preview_v c
    left join docs p on p.collection = 'concept_performance'
                    and p.doc_id = 'x94FcfXU7KRrobyOA4UHDukbRoC2__' || c.concept
    order by c.course, c.chapter_no, c.concept""",
]


async def apply() -> None:
    import os
    import asyncpg

    data = json.loads(OUT.read_text())
    c = await asyncpg.connect(os.environ["DATABASE_URL"])
    async with c.transaction():
        await c.execute("delete from docs where collection in ('concepts_preview', 'concept_relationships_preview')")
        rows = []
        for course, g in data["courses"].items():
            for k in g["concepts"]:
                rows.append(("concepts_preview", f"{course}::{k['name']}", json.dumps({**k, "course": course})))
            rels = clean_relationships(MANUAL_LINKS.get(course, []) + g["relationships"], {k["name"] for k in g["concepts"]})
            for r in rels:
                rows.append(("concept_relationships_preview", f"{course}::{r['source']}::{r['type']}::{r['target']}",
                             json.dumps({**r, "course": course})))
        await c.executemany("insert into docs (collection, doc_id, data) values ($1, $2, $3::jsonb)", rows)
        for v in VIEWS:
            await c.execute(v)
    print("preview rows:", dict(await c.fetch("select collection, count(*) from docs where collection like '%_preview' group by 1")))
    await c.close()


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true", help="write the generated file to the preview collections + views")
    ap.add_argument("--review", action="store_true", help="one pass per course over all links: fix directions, add missing")
    args = ap.parse_args()
    asyncio.run(apply() if args.apply else review() if args.review else generate())
