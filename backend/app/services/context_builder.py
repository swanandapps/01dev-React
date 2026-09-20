"""
Context Builder — the RESOLVE step for /chat's working memory.

Given the assembled prompt parts + the model's context limit, fit them into the
window so a (local) model never *silently* truncates — the usual cause of dropped
memory. Policy: keep the essentials (persona + course material + the question) and
trim the OLDEST conversation turns first, reporting exactly what was dropped so the
cut is visible (OTel), never silent.

This is deliberately simple + offline (uses the char-based estimator). It's the
"selection, not dumping" idea made into a real step.
"""
from app.services.context_meter import estimate_tokens


def build(system: str, history: list[dict], question: str, limit: int, min_turns: int = 1) -> tuple[list[dict], dict]:
    """Fit system + history + question into `limit` tokens by trimming oldest turns.

    Returns (fitted_history, report). Never trims system/question — only conversation
    turns, keeping at least `min_turns` recent ones when possible. `over_limit` is
    True only if the essentials alone already exceed the window (history trimming
    can't help — that would need shorter material, flagged for the caller).
    """
    reserved = estimate_tokens(system) + estimate_tokens(question)
    budget = max(0, limit - reserved)

    kept: list[dict] = []
    used = 0
    for turn in reversed(history):            # newest → oldest
        t = estimate_tokens(turn.get("content", ""))
        if used + t > budget and len(kept) >= min_turns:
            break
        kept.append(turn)
        used += t
    kept.reverse()

    total = reserved + used
    return kept, {
        "limit": limit,
        "prompt_tokens_est": total,
        "fill_pct": round(100.0 * total / limit, 1) if limit else 0.0,
        "dropped_turns": len(history) - len(kept),
        "over_limit": total > limit,
    }
