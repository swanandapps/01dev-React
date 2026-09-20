"""Trajectory evaluation of the01.dev's Hermes AGENT — the tool-path equivalent of
ragas_eval.py (which scores the answer-path / retrieval).

Where RAGAS asks "was the ANSWER good?", this asks "did the agent call the RIGHT
TOOLS?". It reads the tool-call sequence the Hermes agent actually produced (from
the gateway's own session store, :9119) and scores it with RAGAS's own agent metric
**ToolCallAccuracy** against a reference tool sequence per question.

Scope: this measures tool SELECTION (which tools, in what order) — argument-level
correctness is a separate axis we deliberately don't score here, because the query
text is free-form. So both actual and reference tool calls are compared name-only
(args normalised to {}), which makes ToolCallAccuracy a pure selection score:
    right tool  → 1.0     wrong / extra / missing tool → penalised toward 0.0

No LLM and no local model are used — ToolCallAccuracy is deterministic (ExactMatch),
so this runs instantly even under load. Records to the same history.jsonl trend.

Run (isolated venv):  .ragas-venv/bin/python trajectory_eval.py
"""
import asyncio
import json
import os
import sys
import urllib.request
from pathlib import Path

# make the (stdlib-only) results store importable from this isolated venv
sys.path.insert(0, str(Path(__file__).resolve().parent / "app" / "eval"))

from ragas.metrics import ToolCallAccuracy
from ragas.dataset_schema import MultiTurnSample
from ragas.messages import HumanMessage, AIMessage, ToolMessage, ToolCall

HERMES = os.getenv("HERMES_HTTP", "http://localhost:9119")
TOKEN = os.getenv("HERMES_SESSION_TOKEN", "the01dev-local")
_TRAJ_SET = Path(__file__).resolve().parent / "app" / "eval" / "trajectory_set.json"
_TOOL_PREFIX = "mcp__the01dev_tools__"


def _get(path: str) -> dict:
    req = urllib.request.Request(HERMES + path, headers={"X-Hermes-Session-Token": TOKEN})
    return json.load(urllib.request.urlopen(req, timeout=8))


def _short(name: str) -> str:
    """Strip the MCP namespace so 'mcp__the01dev_tools__search_course_content' → 'search_course_content'."""
    return name.split("__")[-1] if name else name


def _session_tool_names(session_id: str) -> list[str]:
    """The ordered tool names the agent called in this session (from assistant tool_calls)."""
    msgs = _get(f"/api/sessions/{session_id}/messages").get("messages", [])
    names: list[str] = []
    for m in msgs:
        if m.get("role") == "assistant":
            for tc in m.get("tool_calls") or []:
                name = (tc.get("function") or {}).get("name") or tc.get("name")
                if name:
                    names.append(_short(name))
    return names


def _first_user_question(session_id: str) -> str:
    for m in _get(f"/api/sessions/{session_id}/messages").get("messages", []):
        if m.get("role") == "user":
            return (m.get("content") or "").strip().lower()
    return ""


def _build_sample(question: str, actual_tools: list[str], reference_tools: list[str]) -> MultiTurnSample:
    """One agent turn as a RAGAS MultiTurnSample — name-only tool calls (args normalised)."""
    ui = [HumanMessage(content=question)]
    for name in actual_tools:
        ui.append(AIMessage(content="", tool_calls=[ToolCall(name=name, args={})]))
        ui.append(ToolMessage(content="(result)"))
    return MultiTurnSample(
        user_input=ui,
        reference_tool_calls=[ToolCall(name=n, args={}) for n in reference_tools],
    )


async def main() -> None:
    golden = json.loads(_TRAJ_SET.read_text())

    # index the most-recent Hermes session per question
    sessions = _get("/api/sessions?limit=40").get("sessions", [])
    by_question: dict[str, str] = {}
    for s in sessions:                      # newest first → first match wins per question
        q = _first_user_question(s["id"])
        if q and q not in by_question:
            by_question[q] = s["id"]

    metric = ToolCallAccuracy()
    print(f"Scoring agent trajectories with RAGAS ToolCallAccuracy — {len(golden)} reference case(s)\n")

    scored = []
    for item in golden:
        q = item["question"].strip().lower()
        ref = item["reference_tools"]
        sid = by_question.get(q)
        if not sid:
            print(f"  · no captured session for: {item['question']!r} — run it through the agent first")
            continue
        actual = _session_tool_names(sid)
        sample = _build_sample(item["question"], actual, ref)
        score = await metric.multi_turn_ascore(sample) if actual or ref else 1.0
        scored.append(score)
        verdict = "✅ right path" if score == 1.0 else "❌ wrong tools"
        print(f"  {verdict}  score={score:.2f}")
        print(f"      q        : {item['question']}")
        print(f"      expected : {ref}")
        print(f"      actual   : {actual or '(no tool calls)'}\n")

    if not scored:
        print("No trajectories scored — no matching agent sessions found.")
        return

    avg = round(sum(scored) / len(scored), 3)
    print(f"=== ToolCallAccuracy (tool-selection) — avg over {len(scored)} trajectory(ies): {avg} ===")
    try:
        import results_store
        results_store.record("trajectory", {"tool_call_accuracy": avg},
                             {"metric": "ToolCallAccuracy", "n": len(scored), "source": "hermes_sessions"})
        print("(recorded → data/eval_results/history.jsonl)")
    except Exception as e:  # noqa: BLE001
        print("(could not record trajectory result:", e, ")")


if __name__ == "__main__":
    asyncio.run(main())
