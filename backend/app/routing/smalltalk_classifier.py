"""
Embedding-based small-talk detector — narrow and biased toward letting
things through to Hermes, not a general off-topic/trivia filter. Gating on
"low similarity to our course content" would reject legitimate general-
knowledge questions the course library doesn't happen to cover (e.g. "what
are cgroups and namespaces in Linux") — the opposite of the decision this
platform made (see SOUL.md's "Avoid" section). This only asks "does this
look like a greeting/pleasantry," nothing broader.

Only runs on short messages (<= _MAX_WORDS words) — a real technical
question is essentially never this short, so the common case (an actual
question) pays zero extra latency or embedding cost; only the rare short
message pays one embedding call.

Ships in OBSERVE-ONLY mode by default (SMALLTALK_BLOCK_ENABLED unset/false):
the similarity score is always computed and returned for logging, but
`should_block` stays False regardless of the score until that env var is
flipped on. There's no labeled data yet on where real greetings vs. real
short questions actually cluster — same "high-precision rules first,
upgrade once there's a labeled log" approach as intent.py's own docstring.
Flip SMALLTALK_BLOCK_ENABLED=true only after reviewing real similarity
scores from production traffic and confirming the threshold is safe.
"""
import os

from app.services.embeddings import embedding_service

_MAX_WORDS = int(os.getenv("SMALLTALK_MAX_WORDS", "6"))
_THRESHOLD = float(os.getenv("SMALLTALK_SIMILARITY_THRESHOLD", "0.85"))
_BLOCK_ENABLED = os.getenv("SMALLTALK_BLOCK_ENABLED", "false").strip().lower() == "true"

# Deliberately narrow: greetings/pleasantries only, not general trivia.
_EXAMPLES = [
    "hi", "hello", "hey", "hey there", "good morning", "good evening",
    "how are you", "how's it going", "what's up",
    "thanks", "thank you", "thanks a lot", "ok thanks", "great, thanks",
    "bye", "goodbye", "see you", "ok cool", "nice", "sounds good",
]

_example_embeddings: list[list[float]] | None = None


def _cosine(a: list[float], b: list[float]) -> float:
    dot = sum(x * y for x, y in zip(a, b))
    norm_a = sum(x * x for x in a) ** 0.5
    norm_b = sum(y * y for y in b) ** 0.5
    if norm_a == 0 or norm_b == 0:
        return 0.0
    return dot / (norm_a * norm_b)


async def _ensure_examples_embedded() -> list[list[float]]:
    global _example_embeddings
    if _example_embeddings is None:
        _example_embeddings = [await embedding_service.embed(e) for e in _EXAMPLES]
    return _example_embeddings


async def check(question: str) -> dict:
    """Returns {"checked": bool, "similarity": float, "should_block": bool}.
    `checked` is False (similarity 0.0, should_block False) for anything
    over _MAX_WORDS — the length gate short-circuits before any embedding
    call. `should_block` is always False unless SMALLTALK_BLOCK_ENABLED."""
    words = question.split()
    if len(words) > _MAX_WORDS:
        return {"checked": False, "similarity": 0.0, "should_block": False}

    examples = await _ensure_examples_embedded()
    q_embedding = await embedding_service.embed(question)
    similarity = round(max(_cosine(q_embedding, e) for e in examples), 3)

    should_block = _BLOCK_ENABLED and similarity >= _THRESHOLD
    return {"checked": True, "similarity": similarity, "should_block": should_block}
