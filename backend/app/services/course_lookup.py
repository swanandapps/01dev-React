"""Look a question up in the01.dev's course library, for this student, before the
tutor answers — in code, every turn, so a demo can't fail because the model
skipped a search.

Searches lecture transcripts and the catalog index, labels each hit enrolled /
not enrolled, and decides one of three cases the grounding prompt has a rule for.
"""
from dataclasses import dataclass
from enum import Enum
from typing import Optional

from app.services import catalog_index, catalog_service, enrollment_service
from app.services.embeddings import embedding_service
from app.services.vector_store import vector_store

# Set from measured data by scripts/calibrate_lookup.py (Task 9) — see spec §4.3.
# Calibrated for OpenAI embeddings; the no-key keyword/hash fallback (local dev) is not comparable.
TRANSCRIPT_THRESHOLD = 0.35
CATALOG_THRESHOLD = 0.35
MAX_HITS = 5


class LookupCase(str, Enum):
    ENROLLED_MATCH = "enrolled_match"
    NOT_ENROLLED_MATCH = "not_enrolled_match"
    NO_MATCH = "no_match"


@dataclass(frozen=True)
class ChatScope:
    course_slug: Optional[str] = None    # None = all courses (Ask page)
    lecture_title: Optional[str] = None  # set by the video player


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


def _mmss(seconds: int) -> str:
    m, s = divmod(int(seconds), 60)
    return f"{m:02d}:{s:02d}"


async def _transcript_hits(question: str, top_k: int = 8):
    if not vector_store.chunks:
        await vector_store.initialize()
    emb = await embedding_service.embed(question)
    return [(r.chunk, r.score) for r in vector_store.search(emb, top_k=top_k, threshold=0.0, query_text=question)]


async def _enrollments(student_id: str) -> tuple[set[int], list[str]]:
    try:
        courses = await enrollment_service.get_enrolled_courses(student_id)
        return {c["id"] for c in courses}, [c["title"] for c in courses]
    except Exception as e:  # noqa: BLE001 — unknown enrollment = not enrolled; never fail the turn
        print(f"[course_lookup] enrollment lookup failed: {e!r}")
        return set(), []


async def course_lookup(question: str, student_id: str, scope: ChatScope = ChatScope()) -> CourseLookup:
    enrolled_ids, enrolled_titles = await _enrollments(student_id)
    hits: list[Hit] = []

    for chunk, score in await _transcript_hits(question):
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
        in_lecture = in_course and bool(scope.lecture_title) and h.title == scope.lecture_title
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


def render_facts(lookup: CourseLookup, scope: ChatScope, weak_concepts: Optional[list[str]] = None) -> str:
    lines = [
        "COURSE FACTS (looked up in the01.dev's course library for this question):",
        f"CASE: {lookup.case.name}",
        "Student is enrolled in: " + (", ".join(lookup.enrolled_titles) or "no courses yet"),
    ]
    if scope.lecture_title:
        course = catalog_service.by_slug(scope.course_slug or "")
        where = f" in {course['title']}" if course else ""
        lines.append(f'MODE: in-lecture — the student is watching "{scope.lecture_title}"{where} right now.')
    if weak_concepts:
        lines.append("Weak concepts in this course: " + ", ".join(weak_concepts))
    if lookup.hits:
        lines.append("Matches:")
        for i, h in enumerate(lookup.hits, 1):
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
