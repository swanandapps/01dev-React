"""Eval adapters (spec §5): run one labelled Row through a retrieval system, in one mode, and say
what it did.

Modes: "player" = scope is the row's course, with a FIXED watched lecture (watched_lecture); "ask" = scope is
every course the student owns AND that is launched (production F1 policy, via ask_citable); "ask_all" = the
same code with every course treated as launched (all_courses_launched), to measure retrieval across the library.
The eval student owns every course (own_every_course). The decision is always the real production code.

Contract for every system: `ranked_lectures` is the FULL, uncapped ranking of the mode's scope (for Ask: launched
AND owned lectures only); `shown_lectures` are the lectures the student is actually shown; `predict(..., rank=False)`
skips the ranking so latency covers the decision only.
"""
import hashlib
import time
from contextlib import contextmanager
from typing import Optional

from app.eval.retrieval_metrics import COVERED, NOT_COVERED, PARTIAL, Prediction, Row

EVAL_STUDENT = "eval-student"
ASK_MODES = ("ask", "ask_all")


async def own_every_course() -> None:
    """Make the eval student own every catalog course (call once, from the runner). Replaces only the
    enrollment DB lookup; every decision rule stays the production code."""
    from app.services import catalog_service, course_lookup as cl

    async def _all(student_id: str):
        courses = catalog_service.all_courses()
        return {c["id"] for c in courses}, [c["title"] for c in courses]

    cl._enrollments = _all


@contextmanager
def all_courses_launched():
    """ask_all: treat every catalog course as launched, by replacing the launched predicate production uses
    (course_lookup._is_launched), exactly as own_every_course replaces enrollments."""
    from app.services import catalog_service, course_lookup as cl
    orig = cl._is_launched
    cl._is_launched = lambda course_id: course_id is not None and catalog_service.get(course_id) is not None
    try:
        yield
    finally:
        cl._is_launched = orig


def launched_slugs(mode: str) -> list[str]:
    """Course slugs a mode's scope may cite (player scope is the row's own course, so: all)."""
    from app.services import catalog_service, course_lookup as cl
    return sorted(c["slug"] for c in catalog_service.all_courses()
                  if mode != "ask" or cl._is_launched(c["id"]))


def watched_lecture(row: Row) -> Optional[str]:
    """The lecture the eval pretends the student is watching in the player: the row's explicit lecture_title,
    else a deterministic (sha1 of the row id) lecture of the same course that is NOT a gold lecture. Fixed so every
    phase and system sees the same player context, and nothing about the gold leaks."""
    if row.lecture_title:
        return row.lecture_title
    from app.services.vector_store import vector_store
    lectures = sorted({(c.lecture_id, c.lecture_title) for c in vector_store.chunks
                       if c.course_id == row.scope_course and c.lecture_id not in row.gold_lecture_ids})
    if not lectures:
        return None
    return lectures[int(hashlib.sha1(row.id.encode()).hexdigest(), 16) % len(lectures)][1]


def _lecture_order(pairs) -> list[str]:
    """(chunk, score) best-first -> distinct lecture ids, best first."""
    return list(dict.fromkeys(c.lecture_id for c, _ in pairs))


def _ms(t0: float) -> float:
    return round((time.perf_counter() - t0) * 1000, 1)


class LegacySystem:
    """Phases 1-3: the threshold-based code paths exactly as they are (course_lookup, find_moment)."""
    name = "legacy"

    async def predict(self, row: Row, mode: str, rank: bool = True) -> Prediction:
        from app.services import course_lookup as cl, tutor_agent
        t0 = time.perf_counter()
        if row.intent == "navigate":
            hit = await tutor_agent._locate_moment(row.navigate_phrase or row.question, row.scope_course)
            return Prediction(row.id, mode, [], NOT_COVERED, None,
                              moment_lecture=hit[0].lecture_id if hit else None, latency_ms=_ms(t0))
        if mode == "player":
            scope = cl.ChatScope(course_slug=row.scope_course, lecture_title=watched_lecture(row), in_player=True)
            lk = await cl.course_lookup(row.question, EVAL_STUDENT, scope)
            ms = _ms(t0)
            ranked = _lecture_order(await cl.search_in_course(row.question, row.scope_course, top_k=None)) if rank else []
            outcome = {cl.LookupCase.IN_COURSE_MATCH: COVERED,
                       cl.LookupCase.IN_COURSE_RELATED: PARTIAL}.get(lk.case, NOT_COVERED)
            return Prediction(row.id, mode, ranked, outcome, lk.hits[0].lecture_id if lk.hits else None,
                              latency_ms=ms, shown_lectures=[h.lecture_id for h in lk.hits],
                              lookup_case=lk.case.value)
        lk = await cl.course_lookup(row.question, EVAL_STUDENT, cl.ChatScope())
        ms = _ms(t0)
        ranked = await self._ask_ranking(row.question) if rank else []
        shown = [h.lecture_id for h in lk.hits if h.source == "transcript"]
        # a catalog-only match shows the student a course-pointer card: partial, naming no lecture
        outcome = COVERED if shown else (PARTIAL if lk.hits else NOT_COVERED)
        return Prediction(row.id, mode, ranked, outcome, shown[0] if shown else None, latency_ms=ms,
                          shown_lectures=shown, lookup_case=lk.case.value)

    @staticmethod
    async def _ask_ranking(question: str) -> list[str]:
        """Every lecture the Ask page may cite (launched AND owned, via the real ask_citable), best first."""
        from app.services import course_lookup as cl
        from app.services.vector_store import vector_store
        enrolled, _ = await cl._enrollments(EVAL_STUDENT)
        pairs = await cl._transcript_hits(question, top_k=len(vector_store.chunks))
        return _lecture_order((c, s) for c, s in pairs if cl.ask_citable(cl.transcript_hit(c, s, enrolled)))
