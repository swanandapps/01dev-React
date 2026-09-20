"""
LangSmith observability — traces + token + cost + latency for every LLM call.

Wiring is opt-in via env, so it's a clean no-op until a key is present:
  LANGCHAIN_TRACING_V2=true
  LANGCHAIN_API_KEY=ls__...
  LANGCHAIN_PROJECT=the01dev        (optional; groups the traces)

`maybe_trace(client)` wraps an OpenAI client so its calls show up in LangSmith
when tracing is enabled, and returns the client untouched otherwise. QuizMe
(LangGraph) auto-traces from the same env vars — no code change needed there.
"""
import os


def tracing_enabled() -> bool:
    return bool(
        os.getenv("LANGCHAIN_TRACING_V2") or os.getenv("LANGSMITH_TRACING")
    ) and bool(os.getenv("LANGCHAIN_API_KEY") or os.getenv("LANGSMITH_API_KEY"))


def maybe_trace(client):
    """Return a LangSmith-wrapped OpenAI client if tracing is on, else the client."""
    if not tracing_enabled():
        return client
    try:
        from langsmith.wrappers import wrap_openai
        return wrap_openai(client)
    except Exception as e:  # noqa: BLE001 — never let observability break inference
        print(f"[tracing] LangSmith unavailable, continuing untraced: {e}")
        return client
