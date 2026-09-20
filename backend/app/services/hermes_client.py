"""
HTTP client for the Hermes agent runtime's OpenAI-compatible API server.

The FastAPI governance layer proxies student questions through here to Hermes,
which runs the agent loop — SOUL identity, memory, and our MCP tools
(`search_course_content` / `search_history`) — on the profile's configured
model (the01dev profile: gpt-4.1-mini via OpenAI).

Protocol: POST /v1/chat/completions (OpenAI Chat Completions format, SSE
streaming), started via `hermes gateway run` with API_SERVER_ENABLED=true.
Requires the target profile's config.yaml to set
`platform_toolsets.api_server` to a restricted list — the unrestricted
default exposes terminal/file/browser tools over this endpoint.

Emits the same normalized events as the other tutor clients:
    {"type":"token","value":...} / {"type":"done"} / {"type":"error","message":...}
"""
import json
import os
from typing import AsyncIterator, Optional

import httpx

HERMES_URL = os.getenv("HERMES_URL", "http://127.0.0.1:8642")
HERMES_API_KEY = os.getenv("HERMES_API_KEY", "")
HERMES_MODEL = os.getenv("HERMES_MODEL_LABEL", "gpt-4.1-mini")


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

    url = f"{HERMES_URL.rstrip('/')}/v1/chat/completions"
    headers = {"Authorization": f"Bearer {HERMES_API_KEY}", "Content-Type": "application/json"}
    payload = {"model": HERMES_MODEL, "messages": messages, "stream": True}

    try:
        async with httpx.AsyncClient(timeout=httpx.Timeout(180.0, connect=20.0)) as client:
            async with client.stream("POST", url, headers=headers, json=payload) as resp:
                if resp.status_code != 200:
                    body = await resp.aread()
                    yield {"type": "error", "message": f"hermes api: HTTP {resp.status_code}: {body[:300]!r}"}
                    return
                async for line in resp.aiter_lines():
                    if not line.startswith("data:"):
                        continue
                    data = line[len("data:"):].strip()
                    if data == "[DONE]":
                        break
                    try:
                        chunk = json.loads(data)
                    except json.JSONDecodeError:
                        continue
                    choices = chunk.get("choices") or []
                    if not choices:
                        continue
                    text = (choices[0].get("delta") or {}).get("content")
                    if text:
                        yield {"type": "token", "value": text}
        yield {"type": "done"}
    except httpx.HTTPError as e:
        yield {"type": "error", "message": f"hermes api: {e}"}
