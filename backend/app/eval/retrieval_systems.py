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


def _ms(t0: float) -> float:
    return round((time.perf_counter() - t0) * 1000, 1)


class V2System:
    """Phase 4+: graded_search (understand || hybrid -> rerank -> decision); navigation through find_moment's locator.
    simulate_lecture: in player mode the row is asked while watching `watched_lecture(row)` (an explicit title, else a
    deterministic NON-gold lecture), so query understanding runs as it does in the real player."""
    name = "v2"

    def __init__(self, simulate_lecture: bool = False):
        self.simulate_lecture = simulate_lecture

    async def predict(self, row: Row, mode: str, rank: bool = True) -> Prediction:
        from app.retrieval import pipeline
        from app.services import tutor_agent
        t0 = time.perf_counter()
        if row.intent == "navigate":
            hit = await tutor_agent._locate_moment(row.navigate_phrase or row.question, row.scope_course)
            return Prediction(row.id, mode, [], NOT_COVERED, None,
                              moment_lecture=hit[0].lecture_id if hit else None, latency_ms=_ms(t0))
        if mode == "player":
            scope = [row.scope_course]
        else:   # production Ask policy: launched AND owned (own_every_course enrollments, launched predicate patched in ask_all)
            from app.services import course_lookup as cl
            enrolled, _ = await cl._enrollments(EVAL_STUDENT)
            scope = list(pipeline.ask_scope(enrolled))
        res = await pipeline.graded_search(row.question, scope, history=list(row.history),
                                           lecture_title=(watched_lecture(row) if self.simulate_lecture else row.lecture_title)
                                           if mode == "player" else None)
        ms = _ms(t0)
        best = res.best()
        case = (f"fallback:{res.rerank_error}" if res.fallback
                else f"{res.outcome.value}:salvaged" if res.rerank_error else res.outcome.value)
        return Prediction(row.id, mode, await self._ranking(row.question, scope, res) if rank else [],
                          res.outcome.value, best.candidate.chunk.lecture_id if best else None, latency_ms=ms,
                          shown_lectures=list(dict.fromkeys(g.candidate.chunk.lecture_id for g in res.cited())),
                          fallback=res.fallback, lookup_case=case)

    @staticmethod
    async def _ranking(question: str, scope, res) -> list[str]:
        """The full scoped ranking: graded candidates first (best grade first), then the rest of the scope's
        hybrid ranking, so recall@k sees every lecture the mode may cite."""
        from app.retrieval import pipeline
        graded = [g.candidate.chunk.lecture_id for g in res.graded]
        rest = await pipeline.search(question, scope, limit=pipeline.VEC_K + pipeline.LEX_K)
        return list(dict.fromkeys(graded + [c.chunk.lecture_id for c in rest]))
