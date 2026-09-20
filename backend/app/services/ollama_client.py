"""
Direct streaming client for the local Ollama OpenAI-compatible endpoint (:11434).

Why this exists (an honest finding): Hermes's `/v1/chat/completions` is NOT a
transparent proxy — it runs the full agent loop (SOUL + tools), and on a small
3B model that loop reframes everything around its tools and DROPS the injected
memory + multi-turn history. Proven with an A/B: identical messages recall the
student's history correctly via Ollama-direct, and fail via Hermes.

So the reliable, memory-having tutor talks to the sovereign model directly here;
Hermes is used for the agentic tool-driving path (hermes_client), where its agent
loop is the point and where a GPU-hosted model makes it reliable. Same sovereign
guarantee either way (local model), same normalized event contract.
"""
import json
import os
from typing import AsyncIterator, Optional

import httpx

OLLAMA_URL = os.getenv("OLLAMA_URL", "http://localhost:11434")
TUTOR_MODEL = os.getenv("OLLAMA_TUTOR_MODEL", os.getenv("HERMES_MODEL_LABEL", "qwen2.5:3b"))


async def stream_chat(
    question: str,
    system: Optional[str] = None,
    history: Optional[list[dict]] = None,
) -> AsyncIterator[dict]:
    """Stream from the local model, yielding {"type": "token"|"done"|"error", ...}.

    `history` threads prior turns (multi-turn); `system` carries persona +
    injected course material + student memory.
    """
    messages = []
    if system:
        messages.append({"role": "system", "content": system})
    for turn in history or []:
        role, content = turn.get("role"), turn.get("content")
        if role in ("user", "assistant") and content:
            messages.append({"role": role, "content": content})
    messages.append({"role": "user", "content": question})

    payload = {"model": TUTOR_MODEL, "messages": messages, "stream": True}

    try:
        async with httpx.AsyncClient(timeout=180) as client:
            async with client.stream(
                "POST", f"{OLLAMA_URL}/v1/chat/completions", json=payload
            ) as resp:
                if resp.status_code != 200:
                    body = (await resp.aread()).decode("utf-8", "ignore")
                    yield {"type": "error", "message": f"Ollama {resp.status_code}: {body[:200]}"}
                    return
                async for line in resp.aiter_lines():
                    if not line.startswith("data:"):
                        continue
                    data = line[5:].strip()
                    if not data:
                        continue
                    if data == "[DONE]":
                        yield {"type": "done"}
                        return
                    try:
                        chunk = json.loads(data)
                    except json.JSONDecodeError:
                        continue
                    delta = (chunk.get("choices") or [{}])[0].get("delta", {}) or {}
                    content = delta.get("content")
                    if content:
                        yield {"type": "token", "value": content}
    except Exception as e:  # noqa: BLE001 — surface transport errors to the client
        yield {"type": "error", "message": str(e)}
