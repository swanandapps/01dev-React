"""Look a question up in the01.dev's course library, for this student, before the
tutor answers — in code, every turn, so a demo can't fail because the model
skipped a search.

Searches lecture transcripts and the catalog index, labels each hit enrolled /
not enrolled, and decides one of three cases the grounding prompt has a rule for.
"""
from dataclasses import dataclass
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
# Player only (spec §3.2): below TRANSCRIPT_THRESHOLD but at least this → "this course
# touches on it". calibrated 2026-10-06 on 15 labelled custom-library questions
# (scripts/calibrate_in_course.py): none max 0.45, related min 0.39 (no clean split) →
# 0.46, just above the best "none": a missed "related" falls back to a plain general answer,
# a false one would cite an unrelated lecture.
RELATED_THRESHOLD = 0.46


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


@dataclass
class CourseLookup:
    case: LookupCase
    hits: list[Hit]
    enrolled_titles: list[str]


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


async def search_in_course(query: str, course_slug: str, top_k: int = 8) -> list[tuple[TranscriptChunk, float]]:
    """Best-first transcript chunks of ONE course. Ranks the whole store, then filters,
    so another course's chunk can never stand in for this course's."""
    if not vector_store.chunks:
        await vector_store.initialize()
    emb = await embedding_service.embed(query)
    results = vector_store.search(emb, top_k=len(vector_store.chunks), threshold=0.0, query_text=query)
    return [(r.chunk, r.score) for r in results if r.chunk.course_id == course_slug][:top_k]


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
        course = catalog_service.by_slug(chunk.course_id)
        cid = course["id"] if course else None
        hits.append(Hit(
            source="transcript", course_id=cid, course_slug=chunk.course_id, course_title=chunk.course_title,
            title=chunk.lecture_title, score=score, enrolled=cid in enrolled_ids, text=chunk.text,
            lecture_id=chunk.lecture_id, start_time=chunk.start_time, end_time=chunk.end_time,
            url=course["url"] if course else None,
        ))

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

    hits.sort(key=rank, reverse=True)
    hits = hits[:MAX_HITS]

    if not hits:
        case = LookupCase.NO_MATCH
    elif hits[0].enrolled:  # the best-ranked hit decides (spec §4.3)
        case = LookupCase.ENROLLED_MATCH
    else:
        case = LookupCase.NOT_ENROLLED_MATCH
    return CourseLookup(case=case, hits=hits, enrolled_titles=enrolled_titles)


async def _in_course_lookup(question: str, scope: ChatScope, enrolled_ids: set[int],
                            enrolled_titles: list[str]) -> CourseLookup:
    """Player tutor (spec §3.2): this course's transcripts only — no catalog search, no
    other course. The case comes from the best in-course score."""
    slug = scope.course_slug or ""
    course = catalog_service.by_slug(slug)
    cid = course["id"] if course else None
    # The lecture title still steers the transcript search (4b02cc1).
    transcript_q = f"{scope.lecture_title} {question}" if scope.lecture_title else question
    scored = [(c, s) for c, s in await search_in_course(transcript_q, slug) if c.course_id == slug]
    best = max((s for _, s in scored), default=0.0)
    if best >= TRANSCRIPT_THRESHOLD:
        case, floor = LookupCase.IN_COURSE_MATCH, TRANSCRIPT_THRESHOLD
    elif best >= RELATED_THRESHOLD:
        case, floor = LookupCase.IN_COURSE_RELATED, RELATED_THRESHOLD
    else:
        return CourseLookup(case=LookupCase.IN_COURSE_NONE, hits=[], enrolled_titles=enrolled_titles)
    hits = [Hit(source="transcript", course_id=cid, course_slug=slug, course_title=c.course_title,
                title=c.lecture_title, score=s, enrolled=cid in enrolled_ids, text=c.text,
                lecture_id=c.lecture_id, start_time=c.start_time, end_time=c.end_time,
                url=course["url"] if course else None)
            for c, s in scored if s >= floor]
    here = _norm(scope.lecture_title or "")
    hits.sort(key=lambda h: (bool(here) and _norm(h.title) == here, h.score), reverse=True)
    return CourseLookup(case=case, hits=hits[:MAX_HITS], enrolled_titles=enrolled_titles)


def _has_lecture_excerpt(lookup: CourseLookup, scope: ChatScope) -> bool:
    return any(h.source == "transcript" and h.course_slug == scope.course_slug
               and _norm(h.title) == _norm(scope.lecture_title or "") for h in lookup.hits)


def _course_outline(course: dict, lecture_title: str) -> list[str]:
    """What the course page says, for a lecture we hold no transcript of — so a vague
    in-lecture question ("Give me an example") is answered on the course's topic
    instead of with "what kind of example do you mean?"."""
    lines = ["No transcript excerpt for this lecture. What the course page says about it:",
             f"  Course: {course['title']} — {course.get('description', '').strip()}"]
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
    else:
        lines = [
            "COURSE FACTS (looked up in the01.dev's course library for this question):",
            f"CASE: {lookup.case.name}",
            "Student is enrolled in: " + (", ".join(lookup.enrolled_titles) or "no courses yet"),
        ]
    if scope.lecture_title:
        course = catalog_service.by_slug(scope.course_slug or "")
        where = f" in {course['title']}" if course else ""
        lines.append(f'MODE: in-lecture — the student is watching "{scope.lecture_title}"{where} right now.')
        if course and not _has_lecture_excerpt(lookup, scope):
            lines.extend(_course_outline(course, scope.lecture_title))
    if weak_concepts:
        lines.append("Weak concepts in this course: " + ", ".join(weak_concepts))
    if lookup.hits:
        lines.append("Matches:")
        for i, h in enumerate(lookup.hits, 1):
            if scope.in_player:
                lines.append(f"{i}. [THIS COURSE] {h.title} @ {_mmss(h.start_time)} (score {h.score:.2f})")
            else:
                label = "ENROLLED" if h.enrolled else "NOT ENROLLED"
                where = f"{h.title} @ {_mmss(h.start_time)}" if h.source == "transcript" else h.title
                page = f" — course page: the01.dev{h.url}" if h.url else ""
                lines.append(f"{i}. [{label}] {h.course_title} → {where} ({h.source}, score {h.score:.2f}){page}")
            lines.append(f'   "{h.text[:600]}"')
    return "\n".join(lines)


def to_cards(lookup: CourseLookup) -> list[dict]:
    """SourceCard-shaped dicts for the frontend (RagSourceCard deep-links via course_id slug)."""
    cards = []
    for h in lookup.hits:
        cards.append({
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
