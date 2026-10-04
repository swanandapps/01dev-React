"""
Shared LLM selection for the eval / self-improvement tools (GEPA, eval_service,
accuracy). Uses OpenAI — the same model family the product ships on — so the
eval suite runs anywhere (CI, cloud).

  EVAL_MODEL=gpt-4.1-mini       (the judge / generator model)
"""
import os


def eval_client_and_model():
    """Return (AsyncOpenAI client, model_name) for the eval tools."""
    from openai import AsyncOpenAI

    # "" (not None) when the key is unset: callers build this at import time, and
    # AsyncOpenAI raises on a missing key — a keyless import must not crash main.
    client = AsyncOpenAI(api_key=os.getenv("OPENAI_API_KEY", ""), timeout=60.0, max_retries=3)
    return client, os.getenv("EVAL_MODEL", "gpt-4.1-mini")
