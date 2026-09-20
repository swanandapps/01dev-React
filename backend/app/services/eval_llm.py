"""
Shared LLM selection for the eval / self-improvement tools (GEPA, eval_service,
accuracy). Mirrors the tutor: OpenAI in production/CI, local Ollama in dev.

So the eval suite judges the SAME model family the product ships on, and runs
anywhere (CI, cloud) — not only where a local Ollama happens to be up.

  EVAL_PROVIDER=openai|ollama   (default: openai when OPENAI_API_KEY is set)
  EVAL_MODEL=gpt-4.1-mini       (the judge / generator model)
"""
import os


def eval_client_and_model():
    """Return (AsyncOpenAI client, model_name) for the eval tools."""
    from openai import AsyncOpenAI

    use_openai = bool(os.getenv("OPENAI_API_KEY")) and os.getenv("EVAL_PROVIDER", "openai") != "ollama"
    if use_openai:
        client = AsyncOpenAI(api_key=os.getenv("OPENAI_API_KEY"), timeout=60.0, max_retries=3)
        return client, os.getenv("EVAL_MODEL", "gpt-4.1-mini")

    client = AsyncOpenAI(
        base_url=os.getenv("OLLAMA_URL", "http://localhost:11434/v1"),
        api_key=os.getenv("OLLAMA_KEY", "ollama"),
    )
    model = os.getenv("OLLAMA_TUTOR_MODEL", os.getenv("HERMES_MODEL_LABEL", "qwen2.5:3b"))
    return client, model
