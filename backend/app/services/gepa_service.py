"""
GEPA — reflective prompt evolution for the tutor.

The self-evolution loop the JD asks for, done honestly:
  1. score the current SOUL over the eval set            (eval_service)
  2. reflect on the weakest cases                        (LLM)
  3. propose an improved SOUL                             (LLM — the "mutation")
  4. re-score the candidate                               (eval_service)
  5. select it only if it improves without regressing    (Pareto-flavored)
  6. surface it for HUMAN review — nothing auto-applies
  7. on approval, write the evolved SOUL

The SOUL is the agent's identity, and the audit log fingerprints it — so the
tutor improving itself leaves a tamper-evident trail.
"""
import os
import uuid
from datetime import datetime, timezone
from pathlib import Path

from app.services import eval_service
from app.services.eval_llm import eval_client_and_model

_client, _MODEL = eval_client_and_model()
_SOUL = Path(os.path.expanduser("~/.hermes/SOUL.md"))
_FALLBACK_SOUL = (
    "You are Dev, a concise, encouraging tutor for the01.dev. Answer only from the course "
    "material you are given, cite the lecture, and never guess."
)
_PROPOSALS: dict[str, dict] = {}


def read_soul() -> str:
    try:
        return _SOUL.read_text().strip() or _FALLBACK_SOUL
    except OSError:
        return _FALLBACK_SOUL


async def _propose(current: str, weak_cases: list[dict]) -> str:
    critique = "\n".join(
        f"- Q: {c['question']}\n  scored {c['score']}/5 — {c['feedback']}" for c in weak_cases
    )
    sys = (
        "You improve a course tutor's system prompt (its SOUL). Given the current SOUL and its "
        "weakest graded cases, rewrite the SOUL so those weaknesses improve. Keep it a concise "
        "identity plus clear instructions to answer ONLY from the provided course material, cite "
        "the lecture, and decline when it isn't covered. Return ONLY the new SOUL text — no preamble."
    )
    user = f"CURRENT SOUL:\n{current}\n\nWEAKEST CASES:\n{critique}"
    resp = await _client.chat.completions.create(
        model=_MODEL, temperature=0.5, max_tokens=500,
        messages=[{"role": "system", "content": sys}, {"role": "user", "content": user}],
    )
    return (resp.choices[0].message.content or "").strip()


async def run_round() -> dict:
    """One evolution round → a human-reviewable proposal (does NOT apply anything)."""
    current = read_soul()
    baseline = await eval_service.run_eval(current)
    weak = sorted(baseline["cases"], key=lambda c: c["score"])[:3]

    candidate = await _propose(current, weak)
    cand_eval = await eval_service.run_eval(candidate)

    # Pareto-flavored acceptance: average must improve AND no case may regress into failure
    # (protects the critical behaviors — grounding and correct declining).
    improved = (
        cand_eval["avg"] > baseline["avg"]
        and all(c["score"] >= 2 for c in cand_eval["cases"])
    )

    pid = uuid.uuid4().hex[:8]
    proposal = {
        "id": pid,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "baseline_avg": baseline["avg"],
        "candidate_avg": cand_eval["avg"],
        "improved": improved,
        "recommendation": "apply" if improved else "reject",
        "current_soul": current,
        "candidate_soul": candidate,
        "baseline_cases": baseline["cases"],
        "candidate_cases": cand_eval["cases"],
        "applied": False,
    }
    _PROPOSALS[pid] = proposal
    try:  # persist the round so improvement can be tracked over time
        from app.eval.results_store import record
        record("gepa", {"baseline_avg": baseline["avg"], "candidate_avg": cand_eval["avg"],
                        "improved": improved}, {"proposal_id": pid})
    except Exception:  # noqa: BLE001 — never fail a round over logging
        pass
    return proposal


async def approve(proposal_id: str) -> dict:
    """HUMAN gate — write the approved SOUL (with a backup). This is the only path that mutates."""
    p = _PROPOSALS.get(proposal_id)
    if not p:
        return {"error": "unknown proposal_id"}
    try:
        if _SOUL.exists():
            _SOUL.with_suffix(".md.bak").write_text(_SOUL.read_text())
        _SOUL.parent.mkdir(parents=True, exist_ok=True)
        _SOUL.write_text(p["candidate_soul"] + "\n")
        p["applied"] = True
        try:  # record the applied improvement
            from app.eval.results_store import record
            record("gepa_apply", {"baseline_avg": p["baseline_avg"],
                                  "candidate_avg": p["candidate_avg"]}, {"proposal_id": proposal_id})
        except Exception:  # noqa: BLE001
            pass
        return {"applied": True, "proposal_id": proposal_id,
                "baseline_avg": p["baseline_avg"], "candidate_avg": p["candidate_avg"]}
    except OSError as e:  # noqa: BLE001
        return {"error": str(e)}


def proposals() -> list[dict]:
    """List proposals (without the bulky per-case detail)."""
    return [
        {k: v for k, v in p.items() if k not in ("baseline_cases", "candidate_cases",
                                                  "current_soul", "candidate_soul")}
        for p in _PROPOSALS.values()
    ]
