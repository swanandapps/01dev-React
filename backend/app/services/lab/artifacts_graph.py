"""Document → artifacts, as a LangGraph planner-executor with HITL approval.

A **planner** proposes which artifacts to produce (notes / summary / quiz /
flashcards), a human **approves/edits** the plan (interrupt), then the graph
**fans out** to specialized generator nodes in parallel and assembles the result.
Same orchestration shape as the QuizMe lesson, applied to one-shot generation.

Sync nodes + run_in_threadpool (langgraph 1.2.x only propagates the interrupt
config context on the sync path).
"""
from typing import Annotated, TypedDict

from langgraph.graph import StateGraph, START, END
from langgraph.checkpoint.memory import MemorySaver
from langgraph.types import interrupt, Send

from .llm import gen_artifact, ARTIFACT_TYPES


def _merge(a: dict, b: dict) -> dict:
    return {**(a or {}), **(b or {})}


class ArtifactState(TypedDict, total=False):
    document: str
    requested: list[str]
    plan: list[str]
    approved: bool
    outputs: Annotated[dict, _merge]   # artifact_type -> text
    status: str


def planner(state: ArtifactState) -> dict:
    """Decide which artifacts to generate (requested subset, or all four)."""
    req = [t for t in (state.get("requested") or []) if t in ARTIFACT_TYPES]
    return {"plan": req or list(ARTIFACT_TYPES), "status": "awaiting_approval"}


def approve(state: ArtifactState) -> dict:
    """HITL gate — suspend until a human approves/edits the artifact plan."""
    decision = interrupt({"phase": "approval", "proposed_plan": state["plan"]})
    if isinstance(decision, dict):
        if decision.get("approved") is False:
            return {"approved": False, "status": "rejected"}
        plan = [t for t in (decision.get("plan") or []) if t in ARTIFACT_TYPES]
        return {"approved": True, "plan": plan or state["plan"], "status": "generating"}
    return {"approved": True, "status": "generating"}


def route(state: ArtifactState):
    if not state.get("approved"):
        return END
    return [Send(f"gen_{t}", state) for t in state["plan"]]


def _make_generator(artifact_type: str):
    def _gen(state: ArtifactState) -> dict:
        return {"outputs": {artifact_type: gen_artifact(artifact_type, state["document"])}}

    _gen.__name__ = f"gen_{artifact_type}"
    return _gen


def assemble(state: ArtifactState) -> dict:
    return {"status": "complete"}


def build_artifacts_graph():
    b = StateGraph(ArtifactState)
    b.add_node("planner", planner)
    b.add_node("approve", approve)
    for t in ARTIFACT_TYPES:
        b.add_node(f"gen_{t}", _make_generator(t))
    b.add_node("assemble", assemble)

    b.add_edge(START, "planner")
    b.add_edge("planner", "approve")
    b.add_conditional_edges("approve", route, [f"gen_{t}" for t in ARTIFACT_TYPES] + [END])
    for t in ARTIFACT_TYPES:
        b.add_edge(f"gen_{t}", "assemble")
    b.add_edge("assemble", END)
    return b.compile(checkpointer=MemorySaver())
