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
import math
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
try:
    from app.services.llm import GEN_MODEL as MODEL
except Exception:  # noqa: BLE001 — the script must still import when settings are unavailable
    MODEL = "gpt-4.1-mini"
PROMPT_VERSION = "v2"  # bump when SYSTEM / BANNED / validation change: it is part of every cache key
STYLES = ["direct", "casual", "keyword", "how_do_i"]
NAV_TEMPLATES = ["take me to the part about {p}", "jump to where {p} comes up", "show me where {p} is covered",
                 "take me to {p}"]
MAX_PROMPT_CHARS = 12000
BANNED = re.compile(r"\b(lecture|video|instructor|this course|chapter|this system|this library|how do i understand)\b",
                    re.I)
CODEISH = re.compile(r"""[()\[\]{}'"=/\\<>;`$@#_]|--""")  # things a student does not say out loud
OUTRO_RE = re.compile(r"where from here|summary|finale|recap", re.I)
INTRO_RE = re.compile(r"what we will build|what will we build|what is this course", re.I)
PROJECT_RE = re.compile(r"\b(Ember|statekit|Pulse|Tern|mini-runtime)\b", re.I)
STOP_WORDS = set("a an the of to in on and or is are was be it its for with as at by from this that how what why "
                 "do does did i you we my me can so just about into than then when which who your our not vs "
                 "if get got there their they them these those have has had would should could will".split())
GENERIC_TITLE_WORDS = {"react", "javascript", "js", "course", "code", "node", "nodejs", "using", "use", "build",
                       "building", "writing", "scratch", "intro", "introduction", "part", "complete", "real",
                       "world", "library", "app", "system"}
VAGUE = re.compile(r"real-time system|derived (data|state)|managing state|state management|main components|"
                   r"main challenges|what is state", re.I)
RELABEL_MIN_SCORE, RELABEL_MARGIN = 6.0, 1.2
# "what should I do next" questions are about the outro itself, not about a topic a body lecture teaches
NEXT_STEPS = re.compile(r"\b(next|what else|keep learning|improv\w*|extend\w*|project ideas|suggested projects|"
                        r"new (language )?features|recommended|we (built|made|created)|after (finishing|completing|building|learning))\b", re.I)
RELABEL_STATS = {"relabeled": 0, "dropped": 0}
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
- The lecture title is context only. Never reuse two or more consecutive words of the title, and avoid its other distinctive words: say it the way a student who has not seen the title would. Prefer generic wording ("the language", "the library") over the project's own name unless a student would naturally use it.
- gold_chunk_id: the id of the single passage that best answers the question, or null if the answer is spread over the lecture.
- navigate_phrase: 2 to 5 words of plain spoken English naming the most specific thing the lecture shows, as a student would say it out loud after "take me to the part about" (for example "the np publish command" or "virtualizing the table"). No code, flags, parentheses, quotes or underscores.

Return only JSON: {"questions": [{"style": "...", "question": "...", "gold_chunk_id": "... or null"}], "navigate_phrase": "..."}"""


async def _complete(system: str, user: str) -> Optional[dict]:
    from app.services.llm import llm
    return await llm.generate_json(system, user, temperature=0.4, max_tokens=700)


def styles_for(i: int) -> list[str]:
    return [STYLES[(i + j) % len(STYLES)] for j in range(3)]


def lecture_kind(title: str, first_in_course: bool) -> str:
    if OUTRO_RE.search(title):
        return "outro"
    if first_in_course or INTRO_RE.search(title):
        return "intro"
    return "body"


def lectures_from_seed(chunks: list[dict]) -> list[dict]:
    out: dict[str, dict] = {}
    seen_courses: set[str] = set()
    for c in chunks:
        if c["lecture_id"] not in out:
            first = c["course_id"] not in seen_courses
            seen_courses.add(c["course_id"])
            out[c["lecture_id"]] = {"lecture_id": c["lecture_id"], "course_id": c["course_id"],
                                    "course_title": c["course_title"], "lecture_title": c["lecture_title"],
                                    "kind": lecture_kind(c["lecture_title"], first), "chunks": []}
        out[c["lecture_id"]]["chunks"].append({"chunk_id": c["chunk_id"], "text": c["text"]})
    return list(out.values())


def lecture_sha(lecture: dict) -> str:
    body = "\n".join(f"{c['chunk_id']}\t{c['text']}" for c in lecture["chunks"])
    key = f"{PROMPT_VERSION}|{MODEL}|{BANNED.pattern}\n{body}"
    return hashlib.sha256(key.encode()).hexdigest()[:16]


def _title_tokens(title: str) -> list[str]:
    return re.findall(r"[a-z0-9]+", re.sub(r"^\s*[\d.]+\s*-\s*", "", title).lower())


def leaks_title(question: str, title: str) -> bool:
    """The question contains a title bigram, or at least two distinct content words of the title."""
    t, q = _title_tokens(title), re.findall(r"[a-z0-9]+", question.lower())
    qs = " " + " ".join(q) + " "
    for a, b in zip(t, t[1:]):
        if (a not in STOP_WORDS or b not in STOP_WORDS) and f" {a} {b} " in qs:
            return True
    content = {w for w in t if w not in STOP_WORDS and w not in GENERIC_TITLE_WORDS and len(w) > 1}
    return len(content & set(q)) >= 2


def leaks_project(question: str) -> bool:
    return bool(PROJECT_RE.search(question))


def _passages(lecture: dict) -> str:
    chunks = lecture["chunks"]
    total = sum(len(c["text"]) for c in chunks)
    if total > MAX_PROMPT_CHARS:  # evenly spaced passages, ids kept, so gold ids stay real
        keep = max(1, int(len(chunks) * MAX_PROMPT_CHARS / total))
        step = len(chunks) / keep
        chunks = [chunks[int(i * step)] for i in range(keep)]
    return "\n".join(f"[{c['chunk_id']}] {c['text']}" for c in chunks)


def _user(lecture: dict, styles: list[str], feedback: str = "") -> str:
    return (f"Course: {lecture['course_title']}\nLecture: {lecture['lecture_title']}\n"
            f"Styles, in order: {', '.join(styles)}\n\nPassages:\n{_passages(lecture)}"
            + (f"\n\n{feedback}" if feedback else ""))


def _check(raw: Optional[dict], chunk_ids: set[str], styles: list[str]) -> tuple[Optional[dict], str]:
    """(generation, "") when valid, else (None, a sentence naming the offending phrase for the retry)."""
    if not isinstance(raw, dict):
        return None, "the reply was not a JSON object"
    qs = raw.get("questions")
    phrase = str(raw.get("navigate_phrase") or "").strip()
    if not isinstance(qs, list) or len(qs) != 3:
        return None, "write exactly 3 questions"
    if not phrase:
        return None, "navigate_phrase is missing"
    if CODEISH.search(phrase) or len(phrase.split()) > 7:
        return None, f'navigate_phrase "{phrase}" is code-like or too long; say it in 2 to 5 plain spoken words'
    out = []
    for q, style in zip(qs, styles):
        text = str((q or {}).get("question") or "").strip()
        if not text:
            return None, "a question was empty"
        m = BANNED.search(text)
        if m:
            return None, f'the question "{text}" contains the forbidden phrase "{m.group(0)}"'
        gold = (q or {}).get("gold_chunk_id")
        out.append({"style": style, "question": text, "gold_chunk_id": gold if gold in chunk_ids else None})
    return {"questions": out, "navigate_phrase": phrase}, ""


def validate_generation(raw: Optional[dict], chunk_ids: set[str], styles: list[str]) -> Optional[dict]:
    return _check(raw, chunk_ids, styles)[0]


def _tags(question: str, lecture: dict) -> dict:
    return {"lecture_kind": lecture.get("kind", "body"), "leaks_title": leaks_title(question, lecture["lecture_title"]),
            "leaks_project": leaks_project(question)}


def rows_for_lecture(lecture: dict, i: int, gen: dict) -> list[dict]:
    lid, slug = lecture["lecture_id"], lecture["course_id"]
    rows = [{"id": f"gen-{lid}-q{n}", "question": q["question"], "scope_course": slug, "expect": "covered",
             "gold_lecture_ids": [lid], "gold_chunk_ids": [q["gold_chunk_id"]] if q["gold_chunk_id"] else [],
             "style": q["style"], "intent": "explain", "source": "generated", **_tags(q["question"], lecture)}
            for n, q in enumerate(gen["questions"], 1)]
    phrase = re.sub(r"\s+(is |are )?(explained|covered|shown|taught|discussed)$", "", gen["navigate_phrase"].strip(), flags=re.I)
    question = NAV_TEMPLATES[i % len(NAV_TEMPLATES)].format(p=phrase)
    rows.append({"id": f"gen-{lid}-nav", "question": question, "scope_course": slug, "expect": "covered",
                 "gold_lecture_ids": [lid], "gold_chunk_ids": [], "style": "navigate", "intent": "navigate",
                 "navigate_phrase": phrase, "source": "generated", **_tags(question, lecture)})
    return rows


# ---- tiny BM25 over a course's chunks (outro relabelling and cross-course checks) ----
_TOK = re.compile(r"[a-z0-9]+")


def _toks(text: str) -> list[str]:
    return [w for w in _TOK.findall(text.lower()) if w not in STOP_WORDS and len(w) > 1]


class _Bm25:
    def __init__(self, docs: list[list[str]], k1: float = 1.5, b: float = 0.75):
        self.docs, self.k1, self.b = docs, k1, b
        self.avg = sum(map(len, docs)) / max(1, len(docs))
        df: dict[str, int] = {}
        for d in docs:
            for w in set(d):
                df[w] = df.get(w, 0) + 1
        n = len(docs)
        self.idf = {w: math.log(1 + (n - c + 0.5) / (c + 0.5)) for w, c in df.items()}

    def scores(self, query: list[str]) -> list[float]:
        out = []
        for d in self.docs:
            tf: dict[str, int] = {}
            for w in d:
                tf[w] = tf.get(w, 0) + 1
            sc = 0.0
            for w in set(query):
                f = tf.get(w, 0)
                if f:
                    sc += self.idf.get(w, 0) * f * (self.k1 + 1) / (f + self.k1 * (1 - self.b + self.b * len(d) / self.avg))
            out.append(sc)
        return out


def relabel_outros(rows: list[dict], lectures: list[dict]) -> list[dict]:
    """Outro lectures (Where from Here / Summary) recap other lectures, so a positive whose only gold is an outro
    is mislabelled. Find the lecture in the same course that really teaches the topic (BM25 over its non-outro
    chunks, with a score floor and a margin over the runner-up) and make it the gold, keeping the outro as an
    extra acceptable gold. Rows that cannot be placed confidently are dropped."""
    by_course: dict[str, list[tuple[str, dict]]] = {}
    for lec in lectures:
        if lec.get("kind") != "outro":
            by_course.setdefault(lec["course_id"], []).extend((lec["lecture_id"], c) for c in lec["chunks"])
    index = {slug: (items, _Bm25([_toks(c["text"]) for _, c in items])) for slug, items in by_course.items()}
    out = []
    for r in rows:
        if r.get("lecture_kind") != "outro" or r["expect"] != "covered":
            out.append(r)
            continue
        items, bm = index[r["scope_course"]]
        text = r.get("navigate_phrase") or r["question"]
        if NEXT_STEPS.search(text):
            RELABEL_STATS["dropped"] += 1
            continue
        query = _toks(text)
        sc = bm.scores(query)
        best: dict[str, tuple[float, int]] = {}
        for n, (lid, _c) in enumerate(items):
            if lid not in best or sc[n] > best[lid][0]:
                best[lid] = (sc[n], n)
        ranked = sorted(best.items(), key=lambda kv: -kv[1][0])
        top = ranked[0]
        runner = ranked[1][1][0] if len(ranked) > 1 else 0.0
        if top[1][0] < RELABEL_MIN_SCORE or top[1][0] < RELABEL_MARGIN * runner:
            RELABEL_STATS["dropped"] += 1
            continue
        RELABEL_STATS["relabeled"] += 1
        chunk_id = items[top[1][1]][1]["chunk_id"]
        out.append({**r, "gold_lecture_ids": [top[0]] + r["gold_lecture_ids"],
                    "gold_chunk_ids": [chunk_id] if r["intent"] == "explain" else []})
    return out


def negative_rows(course_slugs: list[str]) -> list[dict]:
    return [{"id": f"neg-{n:02d}", "question": q, "scope_course": course_slugs[n % len(course_slugs)],
             "expect": "not_covered", "gold_lecture_ids": [], "style": "off_topic", "intent": "explain",
             "source": "generated"} for n, q in enumerate(OFF_TOPIC)]


def cross_course_rows(rows: list[dict], lectures: Optional[list[dict]] = None) -> list[dict]:
    """Questions from a source course asked inside a destination course that does not teach them. Sources are
    spread across the whole course (one per lecture, evenly spaced). With `lectures`, a question must also carry
    a term that is distinctive in its own course (<= 3 lectures) and absent from the destination's transcripts."""
    df: dict[str, dict[str, int]] = {}
    if lectures:
        for lec in lectures:
            seen = {w for c in lec["chunks"] for w in _toks(c["text"])}
            for w in seen:
                d = df.setdefault(lec["course_id"], {})
                d[w] = d.get(w, 0) + 1

    def distinctive(q: str, src: str, dst: str) -> bool:
        if not lectures:
            return True
        return any(1 <= df.get(src, {}).get(w, 0) <= 3 and df.get(dst, {}).get(w, 0) == 0 for w in set(_toks(q)))

    out = []
    for src, dst in CROSS_PAIRS:
        cands, seen_lec = [], set()
        for r in rows:
            lid = (r.get("gold_lecture_ids") or [None])[0]
            if (r["scope_course"] != src or r.get("intent") != "explain" or r["style"] not in ("keyword", "direct")
                    or r.get("lecture_kind", "body") != "body" or r.get("leaks_project") or lid in seen_lec
                    or VAGUE.search(r["question"]) or not distinctive(r["question"], src, dst)):
                continue
            seen_lec.add(lid)
            cands.append(r)
        picked = [cands[int(k * len(cands) / CROSS_PER_PAIR)] for k in range(CROSS_PER_PAIR)] \
            if len(cands) > CROSS_PER_PAIR else cands
        out += [{"id": f"cross-{r['id'].removeprefix('gen-')}-in-{dst}", "question": r["question"],
                 "scope_course": dst, "expect": "not_covered", "gold_lecture_ids": [], "style": "cross_course",
                 "intent": "explain", "source": "generated"} for r in picked]
    return out


def golden_rows(chunks: list[dict]) -> list[dict]:
    by_id = {c["chunk_id"]: c for c in chunks}
    lecs = {lec["lecture_id"]: lec for lec in lectures_from_seed(chunks)}
    out = []
    for n, item in enumerate(json.loads(GOLDEN.read_text())):
        gold = [by_id[c] for c in item["gold_chunk_ids"] if c in by_id]
        if not gold:
            continue
        lectures = list(dict.fromkeys(c["lecture_id"] for c in gold))
        out.append({"id": f"golden-{n:02d}", "question": item["question"], "scope_course": gold[0]["course_id"],
                    "expect": "covered", "gold_lecture_ids": lectures, "gold_chunk_ids": item["gold_chunk_ids"],
                    "style": "direct", "intent": "explain", "source": "hand",
                    **_tags(item["question"], lecs[lectures[0]])})
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


def _leak_count(gen: dict, lecture: dict) -> int:
    return sum(leaks_title(q["question"], lecture["lecture_title"]) for q in gen["questions"])


async def _generate(lecture: dict, styles: list[str]) -> Optional[dict]:
    """Up to 3 attempts, each told what was wrong with the last (a banned phrase, code-like navigate phrase, or
    questions that copy title words). If that fails and there is a how_do_i slot, one more attempt with direct in
    its place (purely conceptual lectures). Title leakage that survives the retries is kept: some is natural."""
    ids = {c["chunk_id"] for c in lecture["chunks"]}
    plan = [styles] * 3 + ([["direct" if s == "how_do_i" else s for s in styles]] if "how_do_i" in styles else [])
    feedback, best = "", None
    for attempt, st in enumerate(plan):
        try:
            gen, problem = _check(await _complete(SYSTEM, _user(lecture, st, feedback)), ids, st)
        except Exception as e:  # noqa: BLE001 — one lecture failing must not stop the run
            print(f"  {lecture['lecture_id']}: {e!r}")
            gen, problem = None, "the request failed"
        if gen:
            n = _leak_count(gen, lecture)
            if best is None or n < best[0]:
                best = (n, gen)
            if n == 0:
                break
            copied = [q["question"] for q in gen["questions"] if leaks_title(q["question"], lecture["lecture_title"])]
            feedback = (f"These questions reuse words from the lecture title: {copied}. Rewrite them in your own "
                        f"words, with no two consecutive title words and at most one other title word.")
            if attempt >= 1:
                break  # leakage: two tries are enough, keep the best
        else:
            feedback = f"Your previous attempt was rejected: {problem}."
    if best is None:
        print(f"  {lecture['lecture_id']}: no valid generation, skipped ({feedback})")
        return None
    return best[1]


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
    return relabel_outros(rows, lectures)


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
    rows += cross_course_rows(rows, lectures) + negative_rows(slugs) + golden_rows(chunks)
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(rows, indent=1, ensure_ascii=False) + "\n")
    cached = sum(_read_cache(CACHE_DIR, lec) is not None for lec in lectures)
    print(f"outro rows: {RELABEL_STATS['relabeled']} relabelled, {RELABEL_STATS['dropped']} dropped")
    print(f"{len(rows)} rows ({cached}/{len(lectures)} lectures generated) -> {OUT}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
