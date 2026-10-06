"""Look a question up in the01.dev's course library, for this student, before the
tutor answers — in code, every turn, so a demo can't fail because the model
skipped a search.

Searches lecture transcripts and the catalog index, labels each hit enrolled /
not enrolled, and decides one of three cases the grounding prompt has a rule for.
"""
import asyncio
import math
import time
import re
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional

from app.models import TranscriptChunk
from app.services import catalog_index, catalog_service, enrollment_service
from app.services.embeddings import embedding_service
from app.services.vector_store import vector_store

# Set from measured data by scripts/calibrate_lookup.py (Task 9) — see spec §4.3.
# Calibrated for OpenAI embeddings; the no-key keyword/hash fallback (local dev) is not comparable.
# calibrated 2026-10-04 on 23 labelled questions (scripts/calibrate_lookup.py): transcript acc 100%, catalog acc 100%
# Each value is the midpoint of its max-accuracy range: transcript 0.48–0.60, catalog 0.21–0.46.
TRANSCRIPT_THRESHOLD = 0.54
CATALOG_THRESHOLD = 0.34
MAX_HITS = 5
# Player only (spec §3.2 as amended by amendment-relevance.md). Relevance is scored on the
# BARE question (a lecture-title prefix makes the title dominate and inflates every score).
# STRONG = bare chunk score >= TRANSCRIPT_THRESHOLD, or the lecture's title matches the
# question (>= TITLE_THRESHOLD). WEAK = RELATED_THRESHOLD <= score < TRANSCRIPT_THRESHOLD.
# Measured 2026-10-06 on the 340 custom-library chunks (scripts/calibrate_in_course.py):
# real matches as low as 0.42 (ES modules), off-topic up to 0.45 (React reconciliation), so no
# single cutoff separates them; the title signal separates them (true >= 0.64, off-topic <= 0.34).
RELATED_THRESHOLD = 0.40
TITLE_THRESHOLD = 0.60
MOMENT_THRESHOLD = 0.46   # find_moment auto-jumps only above this (stricter than RELATED: a wrong jump is worse)
# find_moment ranks lectures by max(best chunk, title - TITLE_OFFSET). Measured on real embeddings
# (27 phrasings, Build a Custom Library): 26/27 correct vs 21/27 for "title >= 0.60 wins outright"
# (generic "npm" pulled 8.1/8.2 titles over 11.1's stronger chunks); demo margin >= 0.042.
TITLE_OFFSET = 0.10
# Agreement rule (F4). find_moment only runs on an explicit "take me to ..." request, so a lecture
# whose title AND best chunk both lean toward the phrase is a safe jump even when neither signal
# clears its own cutoff ("virtualize the table" -> 5.1: chunk 0.41-0.43 < 0.46). Found when the
# SAME lecture has title >= AGREE_TITLE and chunk >= AGREE_CHUNK. Measured 2026-10-06 with real
# embeddings (scripts: scratch qa/f4/cal.py; winner lecture, chunk / title):
#   positives                                              chunk  title  found by
#   react-perf   "virtualize the table"          5.1       0.412  0.755  title (>= 0.60), agreement
#   react-perf   "virtualizing the 5000 row table" 5.1     0.473  0.895  title, chunk
#   state-mgmt   "undo and redo"                 7.2       0.607  0.753  title, chunk
#   custom-lib   "npm publish command"           11.1      0.653  0.467  chunk
#   custom-lib   "commands for publishing the npm library" 11.1  0.689  0.439  chunk
#   custom-lib   "ES modules"                    10.1      0.474  0.735  title, chunk
#   prog-lang    "tokenizer loop"                8.3/6.2   0.508/0.452  0.506/0.540  chunk; 6.2 agrees (0.45, 0.54)
#   negatives (lecture ranked first; none may be found)    chunk  title
#   custom-lib "event loop" 6.1 0.369/0.218 | "React reconciliation" 6.5 0.436/0.212 |
#              "SQL join" 6.2 0.190/0.138   | "Kubernetes pods" 12.1 0.285/0.168
#   react-perf "event loop" 6.1 0.322/0.162 | "SQL join" 2.2 0.222/0.094 | "Kubernetes pods" 5.1 0.248/0.190
#   (react-perf "React reconciliation" is found at 0.500 by the existing chunk rule: that course is
#    about re-rendering, so it is not a false positive and not caused by this rule.)
# Every positive title is >= 0.54 where chunk < 0.46; every negative title is <= 0.22 (worst
# off-topic title seen anywhere: 0.34, CSS box model). So the title floor sits in the wide gap
# (0.34..0.54) at 0.50 and the chunk floor at RELATED_THRESHOLD's 0.40.
AGREE_TITLE = 0.50
AGREE_CHUNK = 0.40
MOMENT_LECTURE_FLOOR = 0.30  # if the winning lecture's best chunk is below this, jump to its start (0) instead
IN_COURSE_K = 3
CURRENT_PASSAGES = 3         # player: passages of the watched lecture given as context
CURRENT_CONTEXT_CHARS = 1500  # ... capped in total
DESCRIPTION_CHARS = 600  # longest catalog description is 546; product-engineering's project sits near char 430
TITLE_EMBED_TIMEOUT = 5.0   # seconds for the batched title-embedding call
TITLE_PREWARM_TIMEOUT = 30.0  # startup batch for every course
TITLE_COOLDOWN = 60.0       # after a failure, use word overlap for this long before retrying


class LookupCase(str, Enum):
    ENROLLED_MATCH = "enrolled_match"
    NOT_ENROLLED_MATCH = "not_enrolled_match"
    NO_MATCH = "no_match"
    # Player tutor only (ChatScope.in_player) — this course's transcripts, nothing else.
    IN_COURSE_MATCH = "in_course_match"
    IN_COURSE_RELATED = "in_course_related"
    IN_COURSE_NONE = "in_course_none"


@dataclass(frozen=True)
class ChatScope:
    course_slug: Optional[str] = None    # None = all courses (Ask page)
    lecture_title: Optional[str] = None  # set by the video player
    # True only on the player route (/api/ai/tutor/stream). The Ask page's course filter
    # also sets course_slug, so a course being set is NOT the trigger.
    in_player: bool = False


@dataclass
class Hit:
    source: str                    # "transcript" | "catalog"
    course_id: Optional[int]       # numeric catalog id (enrollment id space)
    course_slug: Optional[str]
    course_title: str
    title: str                     # lecture title, module title, or course title
    score: float
    enrolled: bool
    text: str = ""
    lecture_id: Optional[str] = None
    start_time: int = 0
    end_time: int = 0
    url: Optional[str] = None
    via_title: bool = False        # player: surfaced because the lecture title matched the question


@dataclass
class CourseLookup:
    case: LookupCase
    hits: list[Hit]
    enrolled_titles: list[str]
    # player only: best chunk of the lecture being watched, as context for "this"/"here"
    current_excerpt: Optional[Hit] = None
    # player only: the best CURRENT_PASSAGES chunks of that lecture for the question, in time order
    current_passages: list[Hit] = field(default_factory=list)


def _norm(s: str) -> str:
    """Compare titles loosely: the player's names use backticks ("The `npm link` command")
    where transcripts don't, and spacing/case drift between the two."""
    return " ".join(s.replace("`", "").split()).casefold()


def _mmss(seconds: int) -> str:
    m, s = divmod(int(seconds), 60)
    return f"{m:02d}:{s:02d}"


async def _transcript_hits(question: str, top_k: int = 8):
    if not vector_store.chunks:
        await vector_store.initialize()
    emb = await embedding_service.embed(question)
    return [(r.chunk, r.score) for r in vector_store.search(emb, top_k=top_k, threshold=0.0, query_text=question)]


async def search_in_course(query: str, course_slug: str, top_k: Optional[int] = 8) -> list[tuple[TranscriptChunk, float]]:
    """Best-first transcript chunks of ONE course. Scores only this course's chunks,
    so another course's chunk can never stand in for this course's. top_k=None means every chunk."""
    if not vector_store.chunks:
        await vector_store.initialize()
    emb = await embedding_service.embed(query)
    results = vector_store.search(emb, top_k=len(vector_store.chunks), threshold=0.0, query_text=query,
                                  course_id=course_slug)
    return [(r.chunk, r.score) for r in results][:top_k]


_TITLE_STOPWORDS = {"the", "and", "for", "with", "what", "are", "how", "does", "why", "our", "your", "that",
                    "this", "from", "into", "using", "use", "can", "you", "its", "was", "were", "who", "when"}
_title_cache: dict[str, tuple[list[str], list[list[float]]]] = {}


def _bare_title(title: str) -> str:
    """"8.1 - The `npm link` command" -> "The npm link command"."""
    return re.sub(r"^\s*\d+(\.\d+)*\s*-\s*", "", title).replace("`", "").strip()


def _lecture_titles(slug: str) -> list[str]:
    course = catalog_service.by_slug(slug)
    return [t for ch in (course or {}).get("chapters", []) for t in ch.get("subchapters", [])]


def _cosine(a: list[float], b: list[float]) -> float:
    na, nb = math.sqrt(sum(x * x for x in a)), math.sqrt(sum(x * x for x in b))
    return sum(x * y for x, y in zip(a, b)) / (na * nb) if na and nb else 0.0


def _words(text: str) -> set[str]:
    return {w for w in re.findall(r"[a-z0-9]+", text.casefold()) if len(w) > 2 and w not in _TITLE_STOPWORDS}


def _overlap_title_scores(question: str, titles: list[str]) -> dict[str, float]:
    """No-embedding fallback: 1.0 when at least half of a title's content words are in the
    question, else 0.0 (so the TITLE_THRESHOLD test still reads the same)."""
    q = _words(question)
    out = {}
    for t in titles:
        w = _words(_bare_title(t))
        out[t] = 1.0 if w and len(w & q) / len(w) >= 0.5 else 0.0
    return out


_title_failed_until: dict[str, float] = {}


async def _embed_titles(slug: str, titles: list[str]) -> list[list[float]]:
    """One batched embed call per course, cached for the process."""
    cached = _title_cache.get(slug)
    if cached and cached[0] == titles:
        return cached[1]
    texts = [_bare_title(t) for t in titles]
    resp = await asyncio.wait_for(
        embedding_service.client.embeddings.create(model="text-embedding-3-small", input=texts),
        timeout=TITLE_EMBED_TIMEOUT)
    vecs = [d.embedding for d in resp.data]
    _title_cache[slug] = (titles, vecs)
    return vecs


async def prewarm_titles() -> tuple[int, int]:
    """Embed every launched-or-not catalog course's lecture titles in ONE batched call and fill
    _title_cache, so the first player turn never pays (or fails) the build. Returns (titles, courses).
    Raises on failure; deliberately never touches _title_failed_until (the lazy path stays a backup)."""
    if not (embedding_service.use_openai and embedding_service.client):
        raise RuntimeError("OpenAI embeddings unavailable")
    per_course = {}
    for course in catalog_service.all_courses():
        slug = course.get("slug")
        titles = _lecture_titles(slug) if slug else []
        if titles:
            per_course[slug] = titles
    texts = [_bare_title(t) for ts in per_course.values() for t in ts]
    if not texts:
        return 0, 0
    resp = await asyncio.wait_for(
        embedding_service.client.embeddings.create(model="text-embedding-3-small", input=texts),
        timeout=TITLE_PREWARM_TIMEOUT)
    vecs = [d.embedding for d in resp.data]
    i = 0
    for slug, ts in per_course.items():
        _title_cache[slug] = (ts, vecs[i:i + len(ts)])
        i += len(ts)
    return len(texts), len(per_course)


async def _title_scores(question: str, slug: str) -> dict[str, float]:
    """Bare question vs each of the course's lecture titles (numbering and backticks stripped).
    Keys are the titles exactly as the course lists them. Falls back to word overlap when
    embeddings are unavailable; after a failure the fallback is used for TITLE_COOLDOWN
    seconds so an outage can't stall every turn. Reused by Task D's find_moment."""
    titles = _lecture_titles(slug)
    if not titles:
        return {}
    if (embedding_service.use_openai and embedding_service.client
            and time.monotonic() >= _title_failed_until.get(slug, 0.0)):
        try:
            vecs = await _embed_titles(slug, titles)
        except Exception as e:  # noqa: BLE001 — title signal is best-effort
            _title_failed_until[slug] = time.monotonic() + TITLE_COOLDOWN
            print(f"[course_lookup] title embedding failed, word overlap for {TITLE_COOLDOWN:.0f}s: {e!r}")
        else:
            # The question embed is outside the cooldown: a transient failure here must not
            # disable titles for the slug (it just fails this turn's lookup like any other embed).
            try:
                q = await embedding_service.embed(question)
            except Exception as e:  # noqa: BLE001
                print(f"[course_lookup] question embed failed, word overlap this turn: {e!r}")
            else:
                return {t: _cosine(q, v) for t, v in zip(titles, vecs)}
    return _overlap_title_scores(question, titles)


async def search_in_lecture(query: str, course_slug: str, lecture_title: str) -> list[tuple[TranscriptChunk, float]]:
    """Chunks of ONE lecture scored against the query, best first — scores only that
    lecture's chunks instead of ranking the whole store."""
    if not vector_store.chunks:
        await vector_store.initialize()
    here = _norm(lecture_title)
    idx = [i for i, c in enumerate(vector_store.chunks)
           if c.course_id == course_slug and _norm(c.lecture_title) == here]
    if not idx:
        return []
    if not (embedding_service.use_openai and len(vector_store._embeddings) == len(vector_store.chunks)):
        # keyword/hash dev fallback has no comparable per-chunk vectors: use the normal search
        return [(c, s) for c, s in await search_in_course(query, course_slug, top_k=None)
                if _norm(c.lecture_title) == here]
    emb = await embedding_service.embed(query)
    out = [(vector_store.chunks[i], vector_store._cosine_sim(emb, vector_store._embeddings[i])) for i in idx]
    return sorted(out, key=lambda t: t[1], reverse=True)


async def _enrollments(student_id: str) -> tuple[set[int], list[str]]:
    try:
        courses = await enrollment_service.get_enrolled_courses(student_id)
        return {c["id"] for c in courses}, [c["title"] for c in courses]
    except Exception as e:  # noqa: BLE001 — unknown enrollment = not enrolled; never fail the turn
        print(f"[course_lookup] enrollment lookup failed: {e!r}")
        return set(), []


async def course_lookup(question: str, student_id: str, scope: ChatScope = ChatScope()) -> CourseLookup:
    enrolled_ids, enrolled_titles = await _enrollments(student_id)
    if scope.in_player:
        return await _in_course_lookup(question, scope, enrolled_ids, enrolled_titles)
    hits: list[Hit] = []

    # In the player, vague questions ("Give me an example") only find the right
    # transcript when the lecture title rides along. The catalog search keeps the bare
    # question: a generic title ("1.1 - What is this course") matches other courses'
    # overviews and turned a vague question into a pointer to an unrelated course.
    transcript_q = f"{scope.lecture_title} {question}" if scope.lecture_title else question
    for chunk, score in await _transcript_hits(transcript_q):
        if score < TRANSCRIPT_THRESHOLD:
            continue
        hits.append(transcript_hit(chunk, score, enrolled_ids))

    covered = {h.course_id for h in hits}
    for entry, score in await catalog_index.search(question, top_k=5):
        if score < CATALOG_THRESHOLD or entry.course_id in covered:
            continue
        covered.add(entry.course_id)
        course = catalog_service.get(entry.course_id)
        hits.append(Hit(
            source="catalog", course_id=entry.course_id, course_slug=entry.course_slug,
            course_title=entry.course_title, title=entry.module_title or entry.course_title, score=score,
            enrolled=entry.course_id in enrolled_ids, text=entry.text, url=course["url"] if course else None,
        ))

    def rank(h: Hit):
        in_course = bool(scope.course_slug) and h.course_slug == scope.course_slug
        in_lecture = in_course and bool(scope.lecture_title) and _norm(h.title) == _norm(scope.lecture_title)
        return (in_lecture, in_course, h.enrolled, h.score)

    # Ask citation policy (user decision 2026-10-06): cite only courses that are launched AND
    # the student owns. Never point at an unowned or unreleased course, so NOT_ENROLLED_MATCH
    # is not produced here (the enum member stays for the in-player path / prompt history).
    hits = [h for h in hits if ask_citable(h)]
    hits.sort(key=rank, reverse=True)
    hits = hits[:MAX_HITS]
    owned_titles = [c["title"] for i in sorted(enrolled_ids) if (c := catalog_service.get(i)) and c.get("launched")]
    return CourseLookup(case=LookupCase.ENROLLED_MATCH if hits else LookupCase.NO_MATCH,
                        hits=hits, enrolled_titles=owned_titles)


def transcript_hit(chunk: TranscriptChunk, score: float, enrolled_ids: set[int]) -> Hit:
    course = catalog_service.by_slug(chunk.course_id)
    cid = course["id"] if course else None
    return Hit(
        source="transcript", course_id=cid, course_slug=chunk.course_id, course_title=chunk.course_title,
        title=chunk.lecture_title, score=score, enrolled=cid in enrolled_ids, text=chunk.text,
        lecture_id=chunk.lecture_id, start_time=chunk.start_time, end_time=chunk.end_time,
        url=course["url"] if course else None,
    )


def ask_citable(h: Hit) -> bool:
    """The Ask citation policy, in one place: only launched AND enrolled courses may be cited
    (course_lookup's hits and the agent's search_course_content tool both use it)."""
    return h.enrolled and _is_launched(h.course_id)


def _is_launched(course_id: Optional[int]) -> bool:
    course = catalog_service.get(course_id) if course_id is not None else None
    return bool(course and course.get("launched"))


def deep_link(h: Hit) -> Optional[str]:
    """Path that opens the player at this hit's lecture and second: /course/<id>?chapter=&sub=&t=.
    chapter/sub are the 0-indexed positions encoded in a position-based lecture_id "<slug>-<c>-<s>"
    (CoursePlayerPage reads them 0-indexed). Catalog hits have no lecture: the plain course page."""
    if not h.url:
        return None
    m = re.search(r"-(\d+)-(\d+)$", h.lecture_id or "") if h.source == "transcript" else None
    if not m:
        return h.url
    return f"{h.url}?chapter={m.group(1)}&sub={m.group(2)}&t={int(h.start_time)}"


def _best_per_lecture(scored) -> dict[str, tuple[TranscriptChunk, float]]:
    best: dict[str, tuple[TranscriptChunk, float]] = {}
    for c, sc in scored:
        k = _norm(c.lecture_title)
        if k not in best or sc > best[k][1]:
            best[k] = (c, sc)
    return best


async def _in_course_lookup(question: str, scope: ChatScope, enrolled_ids: set[int],
                            enrolled_titles: list[str]) -> CourseLookup:
    """Player tutor (spec §3.2 + amendment-relevance.md): this course's transcripts only.
    Relevance comes from the BARE question; the lecture being watched is context, not evidence."""
    slug = scope.course_slug or ""
    course = catalog_service.by_slug(slug)
    cid = course["id"] if course else None

    def to_hit(c: TranscriptChunk, s: float, via_title: bool = False) -> Hit:
        return Hit(source="transcript", course_id=cid, course_slug=slug, course_title=c.course_title,
                   title=c.lecture_title, score=s, enrolled=cid in enrolled_ids, text=c.text,
                   lecture_id=c.lecture_id, start_time=c.start_time, end_time=c.end_time,
                   url=course["url"] if course else None, via_title=via_title)

    scored = [(c, s) for c, s in await search_in_course(question, slug, top_k=None) if c.course_id == slug]
    best = _best_per_lecture(scored)
    titled = {_norm(t) for t, sc in (await _title_scores(question, slug)).items() if sc >= TITLE_THRESHOLD}

    strong = [(c, s, k in titled) for k, (c, s) in best.items()
              if s >= TRANSCRIPT_THRESHOLD or k in titled]
    weak = [(c, s, False) for k, (c, s) in best.items()
            if RELATED_THRESHOLD <= s < TRANSCRIPT_THRESHOLD and k not in titled]
    if strong:
        case, picked = LookupCase.IN_COURSE_MATCH, strong
    elif weak:
        case, picked = LookupCase.IN_COURSE_RELATED, weak
    else:
        case, picked = LookupCase.IN_COURSE_NONE, []
    picked.sort(key=lambda t: t[1], reverse=True)
    hits = [to_hit(c, s, v) for c, s, v in picked[:IN_COURSE_K]]

    current, passages = None, []
    if scope.lecture_title:
        ctx = await search_in_lecture(f"{scope.lecture_title} {question}", slug, scope.lecture_title)
        if ctx:
            c, s = max(ctx, key=lambda t: t[1])
            current = to_hit(c, s)
            top = sorted(ctx, key=lambda t: t[1], reverse=True)[:CURRENT_PASSAGES]
            passages = [to_hit(c, s) for c, s in sorted(top, key=lambda t: t[0].start_time)]
    return CourseLookup(case=case, hits=hits, enrolled_titles=enrolled_titles, current_excerpt=current,
                        current_passages=passages)


def _has_lecture_excerpt(lookup: CourseLookup, scope: ChatScope) -> bool:
    return any(h.source == "transcript" and h.course_slug == scope.course_slug
               and _norm(h.title) == _norm(scope.lecture_title or "") for h in lookup.hits)


def _course_outline(course: dict, lecture_title: str, with_description: bool = True) -> list[str]:
    """What the course page says, for a lecture we hold no transcript of — so a vague
    in-lecture question ("Give me an example") is answered on the course's topic
    instead of with "what kind of example do you mean?"."""
    lines = ["No transcript excerpt for this lecture. What the course page says about it:",
             f"  Course: {course['title']}"
             + (f" — {course.get('description', '').strip()}" if with_description else "")]
    for chapter in course.get("chapters", []):
        subs = chapter.get("subchapters", [])
        if any(_norm(t) == _norm(lecture_title) for t in subs):
            lines.append(f"  This lecture is in {chapter['name']}: {'; '.join(subs)}")
            break
    return lines


def render_facts(lookup: CourseLookup, scope: ChatScope, weak_concepts: Optional[list[str]] = None) -> str:
    if scope.in_player:
        watched = catalog_service.by_slug(scope.course_slug or "")
        name = watched["title"] if watched else "this course"
        lines = [
            f"COURSE FACTS (looked up in {name} only — the course the student is watching):",
            f"CASE: {lookup.case.name}",
            f"COURSE: {name}. Answer from this course or general knowledge; "
            "never name, recommend or link another course.",
        ]
        desc = " ".join((watched or {}).get("description", "").split())
        if desc:  # names the course's running project (Ember, the trading dashboard ...)
            lines.append("COURSE DESCRIPTION (the course's running project): "
                         + (desc if len(desc) <= DESCRIPTION_CHARS else desc[:DESCRIPTION_CHARS].rstrip() + "…"))
    else:
        lines = [
            "COURSE FACTS (looked up in the01.dev's course library for this question):",
            f"CASE: {lookup.case.name}",
        ]
        if lookup.enrolled_titles:  # launched + owned only; when empty say nothing ("no courses yet" invited a sales line)
            lines.append("Student is enrolled in: " + ", ".join(lookup.enrolled_titles))
    if scope.lecture_title:
        course = catalog_service.by_slug(scope.course_slug or "")
        where = f" in {course['title']}" if course else ""
        lines.append(f'MODE: in-lecture — the student is watching "{scope.lecture_title}"{where} right now.')
        if scope.in_player and (lookup.current_passages or lookup.current_excerpt):
            passages = lookup.current_passages or [lookup.current_excerpt]
            each = CURRENT_CONTEXT_CHARS // len(passages) - 12  # room for the ' "" @ mm:ss ' markers
            body = " … ".join(f'"{p.text[:each]}" @ {_mmss(p.start_time)}' for p in passages)
            lines.append('CURRENT LECTURE excerpt (context for "this"/"here" questions and for building '
                         'examples — not evidence that this lecture answers the question; passages in the '
                         f'order they are taught): {body}')
        elif course and (scope.in_player or not _has_lecture_excerpt(lookup, scope)):
            lines.extend(_course_outline(course, scope.lecture_title, with_description=not scope.in_player))
    if weak_concepts:
        lines.append("Weak concepts in this course: " + ", ".join(weak_concepts))
    if lookup.hits:
        lines.append("Matches:")
        for i, h in enumerate(lookup.hits, 1):
            if scope.in_player:
                band = "STRONG" if h.via_title or h.score >= TRANSCRIPT_THRESHOLD else "WEAK"
                tag = ", title match" if h.via_title else ""
                lines.append(f"{i}. [THIS COURSE · {band}] {h.title} @ {_mmss(h.start_time)} "
                             f"(score {h.score:.2f}{tag})")
            else:
                label = "ENROLLED" if h.enrolled else "NOT ENROLLED"
                where = f"{h.title} @ {_mmss(h.start_time)}" if h.source == "transcript" else h.title
                link = deep_link(h)
                page = f" — link: the01.dev{link}" if link else ""
                lines.append(f"{i}. [{label}] {h.course_title} → {where} ({h.source}, score {h.score:.2f}){page}")
            lines.append(f'   "{h.text[:600]}"')
    return "\n".join(lines)


def to_cards(lookup: CourseLookup) -> list[dict]:
    """SourceCard-shaped dicts for the frontend (RagSourceCard deep-links via course_id slug)."""
    cards = []
    for h in lookup.hits:
        m = re.search(r"-(\d+)-(\d+)$", h.lecture_id or "") if h.source == "transcript" else None
        cards.append({
            "url": deep_link(h),
            "chapter": int(m.group(1)) if m else None,
            "sub": int(m.group(2)) if m else None,
            "course_id": h.course_slug or "",
            "course_title": h.course_title,
            "lecture_id": h.lecture_id or f"catalog-{h.course_id}",
            "lecture_title": h.title,
            "timestamp": _mmss(h.start_time) if h.source == "transcript" else "",
            "start_time": h.start_time,
            "end_time": h.end_time,
            "snippet": (h.text[:220] + "…") if len(h.text) > 220 else h.text,
            "score": round(h.score, 3),
        })
    return cards
