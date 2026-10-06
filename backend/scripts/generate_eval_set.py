"""Generate the retrieval eval set (spec §5): 3 questions per lecture (rotating styles) + one
navigate request, written by gpt-4.1-mini from the lecture's transcript; plus hand-written off-topic
negatives and cross-course negatives. Resumable and cached per lecture under
backend/data/cache/eval_gen/<lecture_id>.json (keyed by a hash of the lecture's text), idempotent,
and --limit N generates at most N new lectures (trial runs).

Run from backend/ with the key inline and the database off:
  env OPENAI_API_KEY=... DATABASE_URL= .venv/bin/python scripts/generate_eval_set.py [--limit N] [--only slug] [--force]
"""
import argparse
import asyncio
import hashlib
import json
import os
import re
import sys
from pathlib import Path
from typing import Optional

BACKEND = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND))

SEED = BACKEND / "app" / "data" / "seed_transcripts.json"
GOLDEN = BACKEND / "app" / "eval" / "golden_set.json"
CACHE_DIR = BACKEND / "data" / "cache" / "eval_gen"
OUT = BACKEND / "eval" / "retrieval" / "generated_set.json"
STYLES = ["direct", "casual", "keyword", "how_do_i"]
NAV_TEMPLATES = ["take me to the part about {p}", "jump to where {p} is explained",
                 "show me where the video covers {p}"]
MAX_PROMPT_CHARS = 12000
BANNED = re.compile(r"\b(lecture|video|instructor|this course|chapter|this system|this library|how do i understand)\b", re.I)
CROSS_PAIRS = [("programming-language", "react-perf"), ("react-perf", "programming-language"),
               ("real-time", "custom-library"), ("state-management", "js-engine"),
               ("web-apis", "programming-language")]
CROSS_PER_PAIR = 8
OFF_TOPIC = [  # not taught anywhere in the library (JS/web/React/compilers/npm): other stacks + non-programming
    "how do I write a SQL join across three tables?", "what is the Rust borrow checker?",
    "how do Python decorators work?", "what are Kubernetes pods?", "how do I set up a Django model?",
    "what is a Go goroutine?", "how do I configure nginx as a reverse proxy?", "what is a Docker volume?",
    "how does garbage collection work in Java?", "how do I train a linear regression model?",
    "what is the CAP theorem?", "how do I write a bash for loop?", "what is a Terraform module?",
    "how do Swift optionals work?", "how do I index a MongoDB collection?", "what is a Kafka consumer group?",
    "how do I use pandas groupby?", "what is a C++ virtual destructor?", "how do I write a Spring Boot controller?",
    "what does git rebase do?",
    "how do I bake sourdough bread?", "what is the capital of Australia?", "how do I improve my running pace?",
    "what causes the seasons on Earth?", "how do I care for a succulent?", "who wrote Pride and Prejudice?",
    "how do I make cold brew coffee?", "what is compound interest?", "how many bones are in the human body?",
    "how do I tie a bowline knot?",
]

SYSTEM = """You write evaluation questions for a course-search system. You are given one lecture's transcript, split into passages with ids. Write questions a student might type into a tutor chat that THIS lecture answers.

Rules:
- Write exactly 3 questions, one per requested style, in the order given.
  - direct: a clear, complete question ("What does the np package do when publishing?")
  - casual: lowercase, informal, possibly imprecise ("wait how do i stop npm from publishing my test files")
  - keyword: a short query built around a technical term, acronym or command from the passages ("IIFE scope", "npm link")
  - how_do_i: starts with "How do I" and asks for a procedure the lecture shows; if the lecture is purely conceptual, ask how to do a concrete task it touches on, never "How do I understand ..."
- Each question must be answerable from the transcript and make sense on its own: never mention "the lecture", "the video", "the instructor", "this course", lecture numbers or chapter names.
- Don't copy the lecture title word for word; use the words a student would use.
- gold_chunk_id: the id of the single passage that best answers the question, or null if the answer is spread over the lecture.
- navigate_phrase: 2 to 6 words naming the most specific thing the lecture shows (a command, function, pattern or term), as a student would say it after "take me to the part about".

Return only JSON: {"questions": [{"style": "...", "question": "...", "gold_chunk_id": "... or null"}], "navigate_phrase": "..."}"""


async def _complete(system: str, user: str) -> Optional[dict]:
    from app.services.llm import llm
    return await llm.generate_json(system, user, temperature=0.4, max_tokens=700)


def styles_for(i: int) -> list[str]:
    return [STYLES[(i + j) % len(STYLES)] for j in range(3)]


def lectures_from_seed(chunks: list[dict]) -> list[dict]:
    out: dict[str, dict] = {}
    for c in chunks:
        lec = out.setdefault(c["lecture_id"], {"lecture_id": c["lecture_id"], "course_id": c["course_id"],
                                               "course_title": c["course_title"],
                                               "lecture_title": c["lecture_title"], "chunks": []})
        lec["chunks"].append({"chunk_id": c["chunk_id"], "text": c["text"]})
    return list(out.values())


def lecture_sha(lecture: dict) -> str:
    body = "\n".join(f"{c['chunk_id']}\t{c['text']}" for c in lecture["chunks"])
    return hashlib.sha256(body.encode()).hexdigest()[:16]


def _passages(lecture: dict) -> str:
    chunks = lecture["chunks"]
    total = sum(len(c["text"]) for c in chunks)
    if total > MAX_PROMPT_CHARS:  # evenly spaced passages, ids kept, so gold ids stay real
        keep = max(1, int(len(chunks) * MAX_PROMPT_CHARS / total))
        step = len(chunks) / keep
        chunks = [chunks[int(i * step)] for i in range(keep)]
    return "\n".join(f"[{c['chunk_id']}] {c['text']}" for c in chunks)


def _user(lecture: dict, styles: list[str]) -> str:
    return (f"Course: {lecture['course_title']}\nLecture: {lecture['lecture_title']}\n"
            f"Styles, in order: {', '.join(styles)}\n\nPassages:\n{_passages(lecture)}")


def validate_generation(raw: Optional[dict], chunk_ids: set[str], styles: list[str]) -> Optional[dict]:
    if not isinstance(raw, dict):
        return None
    qs = raw.get("questions")
    phrase = str(raw.get("navigate_phrase") or "").strip()
    if not isinstance(qs, list) or len(qs) != 3 or not phrase:
        return None
    out = []
    for q, style in zip(qs, styles):
        text = str((q or {}).get("question") or "").strip()
        if not text or BANNED.search(text):
            return None
        gold = (q or {}).get("gold_chunk_id")
        out.append({"style": style, "question": text, "gold_chunk_id": gold if gold in chunk_ids else None})
    return {"questions": out, "navigate_phrase": phrase}


def rows_for_lecture(lecture: dict, i: int, gen: dict) -> list[dict]:
    lid, slug = lecture["lecture_id"], lecture["course_id"]
    rows = [{"id": f"gen-{lid}-q{n}", "question": q["question"], "scope_course": slug, "expect": "covered",
             "gold_lecture_ids": [lid], "gold_chunk_ids": [q["gold_chunk_id"]] if q["gold_chunk_id"] else [],
             "style": q["style"], "intent": "explain", "source": "generated"}
            for n, q in enumerate(gen["questions"], 1)]
    phrase = gen["navigate_phrase"]
    rows.append({"id": f"gen-{lid}-nav", "question": NAV_TEMPLATES[i % len(NAV_TEMPLATES)].format(p=phrase),
                 "scope_course": slug, "expect": "covered", "gold_lecture_ids": [lid], "gold_chunk_ids": [],
                 "style": "navigate", "intent": "navigate", "navigate_phrase": phrase, "source": "generated"})
    return rows


def negative_rows(course_slugs: list[str]) -> list[dict]:
    return [{"id": f"neg-{n:02d}", "question": q, "scope_course": course_slugs[n % len(course_slugs)],
             "expect": "not_covered", "gold_lecture_ids": [], "style": "off_topic", "intent": "explain",
             "source": "generated"} for n, q in enumerate(OFF_TOPIC)]


def cross_course_rows(rows: list[dict]) -> list[dict]:
    out = []
    for src, dst in CROSS_PAIRS:
        picked = [r for r in rows if r["scope_course"] == src and r["intent"] == "explain"
                  and r["style"] in ("keyword", "direct")][:CROSS_PER_PAIR]
        out += [{"id": f"cross-{r['id'].removeprefix('gen-')}-in-{dst}", "question": r["question"],
                 "scope_course": dst, "expect": "not_covered", "gold_lecture_ids": [], "style": "cross_course",
                 "intent": "explain", "source": "generated"} for r in picked]
    return out


def golden_rows(chunks: list[dict]) -> list[dict]:
    by_id = {c["chunk_id"]: c for c in chunks}
    out = []
    for n, item in enumerate(json.loads(GOLDEN.read_text())):
        gold = [by_id[c] for c in item["gold_chunk_ids"] if c in by_id]
        if not gold:
            continue
        lectures = list(dict.fromkeys(c["lecture_id"] for c in gold))
        out.append({"id": f"golden-{n:02d}", "question": item["question"], "scope_course": gold[0]["course_id"],
                    "expect": "covered", "gold_lecture_ids": lectures, "gold_chunk_ids": item["gold_chunk_ids"],
                    "style": "direct", "intent": "explain", "source": "hand"})
    return out


def _cache_path(cache_dir: Path, lecture_id: str) -> Path:
    return Path(cache_dir) / f"{lecture_id}.json"


def _read_cache(cache_dir: Path, lecture: dict) -> Optional[dict]:
    p = _cache_path(cache_dir, lecture["lecture_id"])
    if not p.exists():
        return None
    data = json.loads(p.read_text())
    return data["gen"] if data.get("sha") == lecture_sha(lecture) else None


def _write_cache(cache_dir: Path, lecture: dict, gen: dict) -> None:
    p = _cache_path(cache_dir, lecture["lecture_id"])
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.with_suffix(".tmp")
    tmp.write_text(json.dumps({"sha": lecture_sha(lecture), "gen": gen}, indent=1))
    os.replace(tmp, p)


async def _generate(lecture: dict, styles: list[str]) -> Optional[dict]:
    ids = {c["chunk_id"] for c in lecture["chunks"]}
    for _attempt in range(2):
        try:
            gen = validate_generation(await _complete(SYSTEM, _user(lecture, styles)), ids, styles)
        except Exception as e:  # noqa: BLE001 — one lecture failing must not stop the run
            print(f"  {lecture['lecture_id']}: {e!r}")
            gen = None
        if gen:
            return gen
    print(f"  {lecture['lecture_id']}: no valid generation, skipped")
    return None


async def build_set(lectures: list[dict], cache_dir: Path, *, limit: Optional[int] = None, force: bool = False,
                    concurrency: int = 4) -> list[dict]:
    todo = [(i, lec) for i, lec in enumerate(lectures) if force or _read_cache(cache_dir, lec) is None]
    if limit is not None:
        todo = todo[:limit]
    sem = asyncio.Semaphore(concurrency)

    async def one(i: int, lec: dict):
        async with sem:
            gen = await _generate(lec, styles_for(i))
            if gen:
                _write_cache(cache_dir, lec, gen)

    await asyncio.gather(*(one(i, lec) for i, lec in todo))
    rows = []
    for i, lec in enumerate(lectures):
        gen = _read_cache(cache_dir, lec)
        if gen:
            rows += rows_for_lecture(lec, i, gen)
    return rows


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--limit", type=int, help="generate at most N new lectures (trial run)")
    ap.add_argument("--only", help="only this course slug")
    ap.add_argument("--force", action="store_true", help="ignore the cache and regenerate")
    ap.add_argument("--concurrency", type=int, default=4)
    a = ap.parse_args(argv)
    chunks = json.loads(SEED.read_text())
    lectures = lectures_from_seed(chunks)
    if a.only:
        lectures = [lec for lec in lectures if lec["course_id"] == a.only]
    rows = asyncio.run(build_set(lectures, CACHE_DIR, limit=a.limit, force=a.force, concurrency=a.concurrency))
    slugs = list(dict.fromkeys(c["course_id"] for c in chunks))
    rows += cross_course_rows(rows) + negative_rows(slugs) + golden_rows(chunks)
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(rows, indent=1, ensure_ascii=False) + "\n")
    cached = sum(_read_cache(CACHE_DIR, lec) is not None for lec in lectures)
    print(f"{len(rows)} rows ({cached}/{len(lectures)} lectures generated) -> {OUT}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
