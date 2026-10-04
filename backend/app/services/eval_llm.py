"""
Shared LLM selection for the eval tools (eval_service, accuracy). Uses OpenAI — the same model family the product ships on — so the
eval suite runs anywhere (CI, cloud).

  EVAL_MODEL=gpt-4.1-mini       (the judge / generator model)
"""
import os


def eval_client_and_model():
    """Return (AsyncOpenAI client, model_name) for the eval tools."""
    from openai import AsyncOpenAI

    # Callers build this at import time, and a keyless import must not crash main.
    # openai>=3 rejects a missing OR empty key at construction (1.x accepted ""),
    # so when the key is unset pass a key *provider* instead: construction
    # succeeds and the missing key only surfaces if a call is actually made.
    async def _key_at_call_time() -> str:
        return os.getenv("OPENAI_API_KEY", "")

    api_key = os.getenv("OPENAI_API_KEY") or _key_at_call_time
    client = AsyncOpenAI(api_key=api_key, timeout=60.0, max_retries=3)
    return client, os.getenv("EVAL_MODEL", "gpt-4.1-mini")
