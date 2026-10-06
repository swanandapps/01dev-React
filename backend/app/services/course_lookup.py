"""Look a question up in the01.dev's course library, for this student, before the
tutor answers — in code, every turn, so a demo can't fail because the model
skipped a search.

Searches lecture transcripts and the catalog index, labels each hit enrolled /
not enrolled, and decides one of the cases the grounding prompt has a rule for.
Coverage is decided by the retrieval pipeline's reranker (app/retrieval), not by score thresholds.
"""
import asyncio
import re
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional, Sequence

from app.models import TranscriptChunk
from app.retrieval import pipeline
from app.retrieval.rerank import Graded, Outcome, decide
from app.retrieval.text import norm_title
from app.services import catalog_index, catalog_service, enrollment_service
from app.services.vector_store import vector_store

CATALOG_THRESHOLD = 0.34  # catalog entries of in-scope courses with NO transcripts only (see _catalog_hits)
MAX_HITS = 5
IN_COURSE_K = 3
CURRENT_PASSAGES = 3         # player: passages of the watched lecture given as context
CURRENT_CONTEXT_CHARS = 1500  # ... capped in total
DESCRIPTION_CHARS = 600  # longest catalog description is 546; product-engineering's project sits near char 430


class LookupCase(str, Enum):
    ENROLLED_MATCH = "enrolled_match"
    ENROLLED_RELATED = "enrolled_related"   # Ask: a launched+owned course only touches on it (graded partial)
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
    grade: str = ""                # reranker grade: "answers" | "partial" ("" = catalog hit or context passage)
    reason: str = ""               # reranker's one-line reason, shown to the model as "why:"


@dataclass
class CourseLookup:
    case: LookupCase
    hits: list[Hit]
    enrolled_titles: list[str]
    # player only: best chunk of the lecture being watched, as context for "this"/"here"
    current_excerpt: Optional[Hit] = None
    # player only: the best CURRENT_PASSAGES chunks of that lecture for the question, in time order
    current_passages: list[Hit] = field(default_factory=list)


_norm = norm_title


def _mmss(seconds: int) -> str:
    m, s = divmod(int(seconds), 60)
    return f"{m:02d}:{s:02d}"


def _pairs(cands) -> list[tuple[TranscriptChunk, float]]:
    """(chunk, cosine) in the hybrid search's fused order (0.0 only when a candidate's embedding is unknown)."""
    return [(c.chunk, c.cosine if c.cosine is not None else (c.vec_score or 0.0)) for c in cands]


async def search_in_lecture(query: str, course_slug: str, lecture_title: str) -> list[tuple[TranscriptChunk, float]]:
    """Chunks of ONE lecture for the query, fused order; [] when that lecture has no transcript."""
    lid = pipeline.lecture_id_for(course_slug, lecture_title)
    if not lid:
        return []
    return _pairs(await pipeline.search(query, [course_slug], lecture_id=lid,
                                        limit=pipeline.VEC_K + pipeline.LEX_K, per_lecture=None))


async def _enrollments(student_id: str) -> tuple[set[int], list[str]]:
    try:
        courses = await enrollment_service.get_enrolled_courses(student_id)
        return {c["id"] for c in courses}, [c["title"] for c in courses]
    except Exception as e:  # noqa: BLE001 — unknown enrollment = not enrolled; never fail the turn
        print(f"[course_lookup] enrollment lookup failed: {e!r}")
        return set(), []


async def course_lookup(question: str, student_id: str, scope: ChatScope = ChatScope(),
                        history: Sequence[dict] = ()) -> CourseLookup:
    enrolled_ids, enrolled_titles = await _enrollments(student_id)
    if scope.in_player:
        return await _in_course_lookup(question, scope, enrolled_ids, enrolled_titles, history)
    scope_slugs = pipeline.ask_scope(enrolled_ids)
    if not scope_slugs:  # F1: nothing launched AND owned -> nothing to search, rerank or cite
        return CourseLookup(case=LookupCase.NO_MATCH, hits=[], enrolled_titles=[])
    # The bare question is the evidence query; the lecture being watched and the history are context
    # for query understanding (Task 18), never folded into what the reranker judges.
    result = await pipeline.graded_search(question, scope_slugs, history=history, lecture_title=scope.lecture_title)
    hits = [graded_hit(g, enrolled_ids) for g in result.cited()]
    if result.outcome == Outcome.NOT_COVERED:
        hits = await _catalog_hits(question, scope_slugs, enrolled_ids)
    # Ask citation policy (user decision 2026-10-06, F1): cite only courses that are launched AND owned.
    hits = [h for h in hits if ask_citable(h)]

    def rank(h: Hit):
        in_course = bool(scope.course_slug) and h.course_slug == scope.course_slug
        in_lecture = in_course and bool(scope.lecture_title) and _norm(h.title) == _norm(scope.lecture_title)
        return (_GRADE_RANK.get(h.grade, 2), not in_lecture, not in_course)

    hits = sorted(hits, key=rank)[:MAX_HITS]          # stable: fused order is kept within a rank
    # The case follows the grades of the hits that SURVIVE the citation policy, not the raw outcome.
    if any(h.grade == "answers" for h in hits):
        case = LookupCase.ENROLLED_MATCH
    elif any(h.grade == "partial" for h in hits):
        case = LookupCase.ENROLLED_RELATED
    elif hits:                       # catalog-only course pointers
        case = LookupCase.ENROLLED_MATCH
    else:
        case = LookupCase.NO_MATCH
    owned_titles = [c["title"] for i in sorted(enrolled_ids) if (c := catalog_service.get(i)) and c.get("launched")]
    return CourseLookup(case=case, hits=hits, enrolled_titles=owned_titles)


def transcript_hit(chunk: TranscriptChunk, score: float, enrolled_ids: set[int], grade: str = "",
                   reason: str = "") -> Hit:
    course = catalog_service.by_slug(chunk.course_id)
    cid = course["id"] if course else None
    return Hit(
        source="transcript", course_id=cid, course_slug=chunk.course_id, course_title=chunk.course_title,
        title=chunk.lecture_title, score=score, enrolled=cid in enrolled_ids, text=chunk.text_clean or chunk.text,
        lecture_id=chunk.lecture_id, start_time=chunk.start_time, end_time=chunk.end_time,
        url=course["url"] if course else None, grade=grade, reason=reason,
    )


def graded_hit(g: Graded, enrolled_ids: set[int]) -> Hit:
    c = g.candidate
    return transcript_hit(c.chunk, c.cosine if c.cosine is not None else (c.vec_score or 0.0), enrolled_ids,
                          g.grade, g.reason)


_GRADE_RANK = {"answers": 0, "": 0, "partial": 1}


async def _catalog_hits(question: str, scope_slugs: Sequence[str], enrolled_ids: set[int]) -> list[Hit]:
    """Catalog text is evidence only for an in-scope course we hold NO transcript of; for every other
    course the reranker's judgement of its transcripts decides (a vague catalog blurb must not cite)."""
    bare = set(scope_slugs) - {c.course_id for c in vector_store.chunks}
    if not bare:
        return []
    out: list[Hit] = []
    for entry, score in await catalog_index.search(question, top_k=5):
        if entry.course_slug not in bare or score < CATALOG_THRESHOLD or any(h.course_id == entry.course_id for h in out):
            continue
        course = catalog_service.get(entry.course_id)
        out.append(Hit(source="catalog", course_id=entry.course_id, course_slug=entry.course_slug,
                       course_title=entry.course_title, title=entry.module_title or entry.course_title, score=score,
                       enrolled=entry.course_id in enrolled_ids, text=entry.text,
                       url=course["url"] if course else None))
    return out


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


async def _in_course_lookup(question: str, scope: ChatScope, enrolled_ids: set[int], enrolled_titles: list[str],
                            history: Sequence[dict] = ()) -> CourseLookup:
    """Player tutor (spec §3.2): this course's transcripts only. The reranker judges the BARE question;
    the lecture being watched is context (passages for "this"/"here"), not evidence."""
    slug = scope.course_slug or ""
    course = catalog_service.by_slug(slug)
    cid = course["id"] if course else None

    def to_hit(c: TranscriptChunk, s: float, grade: str = "", reason: str = "") -> Hit:
        return Hit(source="transcript", course_id=cid, course_slug=slug, course_title=c.course_title,
                   title=c.lecture_title, score=s, enrolled=cid in enrolled_ids, text=c.text_clean or c.text,
                   lecture_id=c.lecture_id, start_time=c.start_time, end_time=c.end_time,
                   url=course["url"] if course else None, grade=grade, reason=reason)

    async def context():
        if not scope.lecture_title:
            return []
        return await search_in_lecture(f"{scope.lecture_title} {question}", slug, scope.lecture_title)

    result, ctx = await asyncio.gather(
        pipeline.graded_search(question, [slug], history=history, lecture_title=scope.lecture_title), context())
    # the pipeline is already scoped to this course; filter again so another course can never decide the case
    outcome, graded = decide([g for g in result.graded if g.candidate.chunk.course_id == slug])
    case = {Outcome.COVERED: LookupCase.IN_COURSE_MATCH,
            Outcome.PARTIAL: LookupCase.IN_COURSE_RELATED}.get(outcome, LookupCase.IN_COURSE_NONE)
    want = {LookupCase.IN_COURSE_MATCH: "answers", LookupCase.IN_COURSE_RELATED: "partial"}.get(case)
    hits, seen = [], set()
    for g in graded:
        ch, key = g.candidate.chunk, _norm(g.candidate.chunk.lecture_title)
        if g.grade != want or key in seen:
            continue
        seen.add(key)
        c = g.candidate
        hits.append(to_hit(ch, c.cosine if c.cosine is not None else (c.vec_score or 0.0), g.grade, g.reason))
        if len(hits) == IN_COURSE_K:
            break
    current, passages = None, []
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
                band = "STRONG" if h.grade == "answers" else "WEAK"
                lines.append(f"{i}. [THIS COURSE · {band}] {h.title} @ {_mmss(h.start_time)}")
            else:
                label = ("ENROLLED" if h.enrolled else "NOT ENROLLED") + (" · PARTIAL" if h.grade == "partial" else "")
                where = f"{h.title} @ {_mmss(h.start_time)}" if h.source == "transcript" else h.title
                link = deep_link(h)
                page = f" — link: the01.dev{link}" if link else ""
                lines.append(f"{i}. [{label}] {h.course_title} → {where} ({h.source}){page}")
            if h.reason and not h.reason.startswith("fallback:"):   # hide fallback mechanics from the model
                lines.append(f"   why: {h.reason}")
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
