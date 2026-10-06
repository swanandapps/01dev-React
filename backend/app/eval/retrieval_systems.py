"""Eval adapters (spec §5): run one labelled Row through a retrieval system, in one mode, and say
what it did. "player" = scope is the row's course; "ask" = scope is every course, decided by the real
course_lookup with the production F1 policy (cite only launched AND owned courses); the eval student
owns every course (own_every_course), so "launched" is what limits Ask to the launched courses.
Latency covers the decision call only (not the extra ranking call made for recall/MRR)."""
import time

from app.eval.retrieval_metrics import COVERED, NOT_COVERED, PARTIAL, Prediction, Row

EVAL_STUDENT = "eval-student"


async def own_every_course() -> None:
    """Make the eval student own every catalog course (call once, from the runner). Replaces only the
    enrollment DB lookup; every decision rule stays the production code."""
    from app.services import catalog_service, course_lookup as cl

    async def _all(student_id: str):
        courses = catalog_service.all_courses()
        return {c["id"] for c in courses}, [c["title"] for c in courses]

    cl._enrollments = _all


def _lecture_order(pairs) -> list[str]:
    """(chunk, score) best-first -> distinct lecture ids, best first."""
    return list(dict.fromkeys(c.lecture_id for c, _ in pairs))


def _ms(t0: float) -> float:
    return round((time.perf_counter() - t0) * 1000, 1)


class LegacySystem:
    """Phases 1-3: the threshold-based code paths exactly as they are (course_lookup, find_moment)."""
    name = "legacy"

    async def predict(self, row: Row, mode: str) -> Prediction:
        from app.services import course_lookup as cl, tutor_agent
        t0 = time.perf_counter()
        if row.intent == "navigate":
            hit = await tutor_agent._locate_moment(row.navigate_phrase or row.question, row.scope_course)
            return Prediction(row.id, mode, [], NOT_COVERED, None,
                              moment_lecture=hit[0].lecture_id if hit else None, latency_ms=_ms(t0))
        if mode == "player":
            scope = cl.ChatScope(course_slug=row.scope_course, lecture_title=row.lecture_title, in_player=True)
            lk = await cl.course_lookup(row.question, EVAL_STUDENT, scope)
            ms = _ms(t0)
            ranked = _lecture_order(await cl.search_in_course(row.question, row.scope_course, top_k=None))
            outcome = {cl.LookupCase.IN_COURSE_MATCH: COVERED,
                       cl.LookupCase.IN_COURSE_RELATED: PARTIAL}.get(lk.case, NOT_COVERED)
            cited = lk.hits[0].lecture_id if lk.hits else None
            return Prediction(row.id, mode, ranked, outcome, cited, latency_ms=ms)
        lk = await cl.course_lookup(row.question, EVAL_STUDENT, cl.ChatScope())
        ms = _ms(t0)
        ranked = _lecture_order(await cl._transcript_hits(row.question))
        cited = next((h.lecture_id for h in lk.hits if h.source == "transcript"), None)  # catalog hits are course pointers
        return Prediction(row.id, mode, ranked, COVERED if cited else NOT_COVERED, cited, latency_ms=ms)
