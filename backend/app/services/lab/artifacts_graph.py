"""
The Lab graph — the student's selection drives a fan-out, then the quiz tail.

    START
      → fan_out          Send() per requested artifact, driven straight by the
                         student's selection. NO approval gate: they already
                         chose in the UI; interrupting to confirm what they just
                         said is a wasted click.
      → join             fan-out result assembled in state (no I/O here — see
                         below); sets status=complete on the artifacts-only path
      → quiz requested?  no  → END
                         yes → hand off to the objectives/quiz tail, which keeps
                               its HITL gate (reviewing what you'll be tested on
                               IS worth a gate)

Artifacts are sequenced BEFORE the quiz rather than run as a sibling branch: a
branch that interrupts inside the same superstep as the generators would make
the durability of their writes depend on LangGraph's pending-write semantics.
Sequencing removes the question entirely.

Persistence is deliberately NOT done inside `_gen`. This package's nodes are
sync on purpose (langgraph 1.2.x only propagates the interrupt()/HITL config
context on the sync path, which the live quiz tail depends on), but
`artifact_store.save` is async and talks to a process-wide asyncpg pool
(`app.services.db.get_pool`) that is bound to the event loop that created it.
Bridging with `asyncio.run(...)` inside a sync node creates a NEW loop on every
call, so any save after the first hits the pool from a foreign loop —
`InterfaceError: cannot perform operation: another operation is in progress`
against real Postgres (confirmed by reproduction against Neon; the in-memory
test store masks it because `InMemoryStore.set` is a plain dict write with no
loop affinity at all). So `_gen` returns generated content only; the async
route that owns the graph invocation awaits `artifact_store.save` directly on
its own already-running loop, once the fan-out joins and before the quiz
tail begins. That still satisfies the "don't hold finished artifacts hostage
behind a long quiz tail" rationale — the join happens before that tail.
"""
from typing import Annotated, TypedDict

from langgraph.graph import StateGraph, START, END
from langgraph.checkpoint.memory import MemorySaver
from langgraph.types import Send

from app.services.lab.generators import ARTIFACT_TYPES, generate


def _merge(a: dict, b: dict) -> dict:
    return {**(a or {}), **(b or {})}


class LabState(TypedDict, total=False):
    document: str
    doc_id: str
    doc_title: str
    student_id: str
    outputs_requested: list[str]
    artifacts: Annotated[dict, _merge]   # artifact_type -> content
    status: str                          # complete | awaiting_objectives


def fan_out(state: LabState):
    """One Send per requested artifact. Quiz is not an artifact — it's the tail."""
    wanted = [t for t in (state.get("outputs_requested") or []) if t in ARTIFACT_TYPES]
    if not wanted:
        return "join"                     # empty passthrough (e.g. quiz-only)
    return [Send(f"gen_{t}", state) for t in wanted]


def _make_generator(artifact_type: str):
    # Sync node, not async: langgraph 1.2.x's sync `.invoke()` requires a
    # synchronous function per node (an async-only node raises "No
    # synchronous function provided"), matching every other node in this
    # package (see graph.py).
    #
    # No I/O here on purpose. `artifact_store.save` is async and owns a
    # process-wide asyncpg pool bound to whichever event loop created it;
    # bridging into it with asyncio.run() from this sync node would hand it
    # a brand-new loop on every call and break the pool the moment a second
    # generator (or a later request) touches it — see the module docstring.
    # The caller (the async route that invokes this graph) awaits
    # artifact_store.save directly on its own loop once the fan-out joins.
    def _gen(state: LabState) -> dict:
        content = generate(artifact_type, state["document"])
        return {"artifacts": {artifact_type: content}}

    _gen.__name__ = f"gen_{artifact_type}"
    return _gen


def join(state: LabState) -> dict:
    if "quiz" in (state.get("outputs_requested") or []):
        return {}
    return {"status": "complete"}


def route_after_join(state: LabState) -> str:
    if "quiz" in (state.get("outputs_requested") or []):
        return "quiz_tail"
    return END


def quiz_tail(state: LabState) -> dict:
    """Marker node: the endpoint hands off to the lesson graph from here.

    The objectives→approve→quiz→summarize flow stays in graph.py, unchanged and
    already parity-verified. Duplicating it here would fork a working
    implementation for no gain.
    """
    return {"status": "awaiting_objectives"}


def build_lab_graph():
    b = StateGraph(LabState)
    b.add_node("join", join)
    b.add_node("quiz_tail", quiz_tail)
    for t in ARTIFACT_TYPES:
        b.add_node(f"gen_{t}", _make_generator(t))

    b.add_conditional_edges(
        START, fan_out, [f"gen_{t}" for t in ARTIFACT_TYPES] + ["join"],
    )
    for t in ARTIFACT_TYPES:
        b.add_edge(f"gen_{t}", "join")
    b.add_conditional_edges("join", route_after_join, ["quiz_tail", END])
    b.add_edge("quiz_tail", END)
    return b.compile(checkpointer=MemorySaver())
