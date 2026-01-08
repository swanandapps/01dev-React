"""
Shared OpenAI client + a structured-JSON generation helper used by the
content-generation features (study guides, questions, concepts, recommendations).

Falls back gracefully when no OPENAI_API_KEY is configured: callers should check
`llm.available` and handle the no-LLM case.
"""

import json
import os
from typing import Optional

GEN_MODEL = "gpt-4.1-mini"


class LLM:
    def __init__(self):
        self.api_key = os.getenv("OPENAI_API_KEY")
        self.client = None
        if self.api_key:
            try:
                from openai import AsyncOpenAI
                self.client = AsyncOpenAI(api_key=self.api_key)
            except ImportError:
                print("LLM: openai package not found.")

    @property
    def available(self) -> bool:
        return self.client is not None

    async def generate_json(
        self, system: str, user: str, temperature: float = 0.3, max_tokens: int = 1500
    ) -> Optional[dict]:
        """Return parsed JSON object from the model, or None on failure."""
        if not self.client:
            return None
        resp = await self.client.chat.completions.create(
            model=GEN_MODEL,
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            temperature=temperature,
            max_tokens=max_tokens,
            response_format={"type": "json_object"},
        )
        content = resp.choices[0].message.content
        try:
            return json.loads(content)
        except (json.JSONDecodeError, TypeError):
            return None


llm = LLM()
