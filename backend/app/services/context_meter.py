"""
Context-window fill tracking for /chat.

Measures how much of the model's context window the assembled prompt (SOUL +
memory + material + history + question) is consuming, so you can SEE when it's
close to overflowing — past that point the oldest context gets cut (the usual
cause of "dropped memory").

Estimate-only + offline: no tokenizer download, no network, no storage. A
char/4 heuristic is plenty for a "how full is it" gauge; the model's exact
prompt_tokens (from its usage response) is the source of truth when available.
"""
def estimate_tokens(text: str) -> int:
    """~4 chars/token heuristic (English). Dependency-free + offline."""
    return max(0, len(text or "") // 4)
