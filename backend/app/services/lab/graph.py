"""The Lab quiz flow as a LangGraph StateGraph.

How it is built:
  each step             → graph node
  human-in-the-loop     → interrupt() + Command(resume=…) with a checkpointer
  model call            → node calling the model (see llm.py)
  lesson state          → StateGraph channels (durable via the checkpointer)

Flow:
  plan_objectives → await_approval(HITL) → generate_quiz → await_submit(HITL)
                                                 ▲                    │
                                                 └──── more objectives┘
                                                            │ else
                                                        summarize → END

Nodes are synchronous (langgraph 1.2.x only propagates the interrupt config
context on the sync path); the service runs the graph in a threadpool.
"""
import operator
from typing import Annotated, TypedDict

from langgraph.graph import StateGraph, START, END
from langgraph.checkpoint.memory import MemorySaver
from langgraph.types import interrupt

from .llm import gen_objectives, gen_quiz, gen_summary


class LessonState(TypedDict, total=False):
    doc: str
    doc_id: str
    course_id: str | None                   # set when the doc is a course lecture
    student_id: str | None                  # verified uid of the lesson owner, if signed in
    title: str
    proposed_objectives: list[dict]
    objectives: list[dict]
    questions_per_quiz: int
    objective_index: int
    current_objective: dict
    quiz: dict                              # {"questions": [...]}
    results: Annotated[list, operator.add]  # appended one Result per objective
    summary: dict
    status: str                             # awaiting_approval | quizzing | complete


# ── Nodes ────────────────────────────────────────────────────────────────────
def plan_objectives(state: LessonState) -> dict:
    """Planner: draft objectives from the material."""
    proposed = gen_objectives(state["doc"], state.get("title"))
    return {"proposed_objectives": proposed, "status": "awaiting_approval"}


def await_approval(state: LessonState) -> dict:
    """HITL gate: suspend until the human approves/edits the objective list."""
    decision = interrupt({"phase": "approval",
                          "proposed_objectives": state["proposed_objectives"]})
    objectives = decision.get("objectives") if isinstance(decision, dict) else None
    objectives = objectives or state["proposed_objectives"]
    n = decision.get("questionsPerQuiz", 3) if isinstance(decision, dict) else 3
    return {
        "objectives": objectives,
        "questions_per_quiz": max(1, min(10, int(n or 3))),
        "objective_index": 0,
        "status": "quizzing",
    }


def generate_quiz(state: LessonState) -> dict:
    """Specialized generator: build the quiz for the current objective."""
    idx = state["objective_index"]
    obj = state["objectives"][idx]
    questions = gen_quiz(state["doc"], obj, state.get("questions_per_quiz", 3))
    return {"quiz": {"questions": questions}, "current_objective": obj, "status": "quizzing"}


def await_submit(state: LessonState) -> dict:
    """HITL gate: suspend with the quiz shown; resume records the score, advances."""
    submitted = interrupt({"phase": "quiz", "objective_index": state["objective_index"]})
    obj = state["current_objective"]
    score = int(submitted.get("score", 0)) if isinstance(submitted, dict) else 0
    total = int(submitted.get("total", 0)) if isinstance(submitted, dict) else 0
    result = {
        "objectiveId": obj["id"],
        "objectiveTitle": obj["title"],
        "score": score,
        "total": total,
    }
    return {"results": [result], "objective_index": state["objective_index"] + 1}


def route_after_submit(state: LessonState) -> str:
    """More objectives → next quiz; otherwise → wrap up."""
    return "generate_quiz" if state["objective_index"] < len(state["objectives"]) else "summarize"


def summarize(state: LessonState) -> dict:
    summary = gen_summary(state["doc"], state["objectives"], state.get("results", []))
    return {"summary": summary, "status": "complete"}


def build_graph():
    b = StateGraph(LessonState)
    b.add_node("plan_objectives", plan_objectives)
    b.add_node("await_approval", await_approval)
    b.add_node("generate_quiz", generate_quiz)
    b.add_node("await_submit", await_submit)
    b.add_node("summarize", summarize)

    b.add_edge(START, "plan_objectives")
    b.add_edge("plan_objectives", "await_approval")
    b.add_edge("await_approval", "generate_quiz")
    b.add_edge("generate_quiz", "await_submit")
    b.add_conditional_edges("await_submit", route_after_submit,
                            ["generate_quiz", "summarize"])
    b.add_edge("summarize", END)

    # MemorySaver keeps each lesson's state by thread_id across the suspend/resume
    # calls. Production: Postgres checkpointer (same interface) survives restarts.
    return b.compile(checkpointer=MemorySaver())
