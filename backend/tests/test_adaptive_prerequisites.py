"""Which concept practice works on, once a course has a full concept graph: the weakest concept the student
has actually tried, but if a prerequisite of it is weak or untried, that prerequisite first (struggling with
the microtask queue -> the event loop it builds on -> the call stack under that). A concept with no answers
yet is "not tried", never "0%": the zeroed rows the skill graph back-fills must not outrank real weak spots."""
import pytest

from app.models import MCQQuestion
from app.services import adaptive_service as ad
from app.services import knowledge_graph_service
from app.services.store import store

COURSE = "prereq-course"


def _q(concept, n):
    return MCQQuestion(id=f"{concept}-{n}", question=f"{concept} q{n}?", options=["a", "b", "c", "d"],
                       correct_index=0, explanation="e", concept=concept, difficulty="easy", lecture="L")


BANK = [_q(c, n) for c in ("tokenizer", "call-stack", "event-loop", "microtask-queue", "closure") for n in (1, 2)]


async def _perf(uid, concept, correct, attempts):
    await store.set(ad.PERF_COLLECTION, ad._perf_id(uid, concept),
                    {"user_id": uid, "concept": concept, "attempts": attempts, "correct": correct,
                     "accuracy": round(correct / attempts, 3) if attempts else 0.0})


@pytest.fixture
def graph(monkeypatch):
    edges = {"microtask-queue": ["event-loop"], "event-loop": ["call-stack"]}   # target -> its prerequisites

    async def prereqs(course_id, concept):
        return edges.get(concept, [])
    monkeypatch.setattr(knowledge_graph_service, "get_prerequisites", prereqs)
    return edges


@pytest.mark.asyncio
async def test_untried_rows_are_not_zero_percent(graph):
    uid = "prq-untried"
    await _perf(uid, "closure", 3, 10)                    # really weak, no prerequisites
    for c in ("tokenizer", "call-stack", "event-loop", "microtask-queue"):
        await _perf(uid, c, 0, 0)                         # back-filled "not tried" rows (accuracy 0.0)
    q = await ad._pick_next(uid, COURSE, BANK, [], set())
    assert q.concept == "closure"


@pytest.mark.asyncio
async def test_a_weak_concept_sends_practice_down_its_prerequisite_chain(graph):
    uid = "prq-chain"
    await _perf(uid, "microtask-queue", 3, 10)            # weakest tried
    await _perf(uid, "event-loop", 5, 11)                 # its prerequisite: weak (45%)
    await _perf(uid, "call-stack", 0, 0)                  # and that one's prerequisite: not tried
    q = await ad._pick_next(uid, COURSE, BANK, [], set())
    assert q.concept == "call-stack"


@pytest.mark.asyncio
async def test_solid_prerequisites_keep_practice_on_the_weak_concept(graph):
    uid = "prq-solid"
    await _perf(uid, "microtask-queue", 3, 10)
    await _perf(uid, "event-loop", 9, 10)                 # solid, so no step back
    q = await ad._pick_next(uid, COURSE, BANK, [], set())
    assert q.concept == "microtask-queue"


@pytest.mark.asyncio
async def test_with_nothing_tried_practice_starts_at_the_beginning_of_the_course(graph):
    q = await ad._pick_next("prq-new", COURSE, BANK, [], set())
    assert q.concept == "tokenizer"                       # first in teaching (bank) order
