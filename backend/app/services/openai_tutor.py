"""
OpenAI-backed streaming tutor client — the production path.

Same event contract as ollama_client.stream_chat ({"type": "token"|"done"|"error"}),
so the governance layer in main.py is provider-agnostic. Used when TUTOR_PROVIDER is
"openai" (the default whenever OPENAI_API_KEY is set), since managed hosting has no
local Ollama. Timeout + bounded retries come from the SDK; any hard failure degrades
to a single graceful message instead of a 500.
"""
import os
from typing import AsyncIterator, Optional

TUTOR_MODEL = os.getenv("TUTOR_MODEL", "gpt-4.1-mini")
_client = None


def _get_client():
    global _client
    if _client is None:
        from openai import AsyncOpenAI
        from app.services.tracing import maybe_trace
        _client = maybe_trace(AsyncOpenAI(api_key=os.getenv("OPENAI_API_KEY"), timeout=60.0, max_retries=3))
    return _client


async def stream_chat(
    question: str,
    system: Optional[str] = None,
    history: Optional[list[dict]] = None,
) -> AsyncIterator[dict]:
    messages: list[dict] = []
    if system:
        messages.append({"role": "system", "content": system})
    for turn in history or []:
        role, content = turn.get("role"), turn.get("content")
        if role in ("user", "assistant") and content:
            messages.append({"role": role, "content": content})
    messages.append({"role": "user", "content": question})

    try:
        stream = await _get_client().chat.completions.create(
            model=TUTOR_MODEL,
            messages=messages,
            temperature=0.3,
            max_tokens=800,
            stream=True,
            stream_options={"include_usage": True},  # so LangSmith gets token/cost
        )
        async for chunk in stream:
            delta = chunk.choices[0].delta.content if chunk.choices else None
            if delta:
                yield {"type": "token", "value": delta}
        yield {"type": "done"}
    except Exception as e:  # noqa: BLE001 — degrade gracefully, log the real cause
        print(f"[openai_tutor] stream failed: {e}")
        yield {"type": "token", "value": "The tutor is temporarily unavailable. Please try again in a moment."}
        yield {"type": "done"}
