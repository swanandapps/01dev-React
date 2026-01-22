import os
from typing import AsyncIterator, List, Tuple

from app.models import SearchResult
from app.prompts import SYSTEM_PROMPT


class AnswerGenerator:
    def __init__(self):
        self.api_key = os.getenv("OPENAI_API_KEY")
        self.client = None
        if self.api_key:
            try:
                from openai import AsyncOpenAI
                self.client = AsyncOpenAI(api_key=self.api_key)
                print("AnswerGenerator: using gpt-4.1-mini")
            except ImportError:
                print("AnswerGenerator: openai package not found, using local fallback")
        else:
            print("AnswerGenerator: no OPENAI_API_KEY, using local fallback")

    @property
    def model_name(self) -> str:
        return "text-embedding-3-small + gpt-4.1-mini" if self.client else "local-fallback"

    async def generate(
        self, question: str, results: List[SearchResult], extra_context: str = ""
    ) -> Tuple[str, str]:
        context = self._build_context(results) + extra_context
        if self.client:
            return await self._openai_generate(question, context)
        return self._local_generate(question, results), "local-fallback"

    async def generate_stream(
        self, question: str, results: List[SearchResult], extra_context: str = ""
    ) -> AsyncIterator[str]:
        """Yield answer tokens as they are produced."""
        context = self._build_context(results) + extra_context
        if self.client:
            stream = await self.client.chat.completions.create(
                model="gpt-4.1-mini",
                messages=[
                    {"role": "system", "content": SYSTEM_PROMPT},
                    {
                        "role": "user",
                        "content": f"Educational context:\n\n{context}\n\nStudent question: {question}",
                    },
                ],
                temperature=0.3,
                max_tokens=800,
                stream=True,
            )
            async for chunk in stream:
                delta = chunk.choices[0].delta.content
                if delta:
                    yield delta
        else:
            # Local fallback: emit the excerpt word-by-word so the UI still streams.
            text = self._local_generate(question, results)
            for word in text.split(" "):
                yield word + " "

    def _build_context(self, results: List[SearchResult]) -> str:
        parts = []
        for r in results:
            parts.append(
                f"[Source: {r.chunk.course_title} — {r.chunk.lecture_title} "
                f"@ {_fmt_time(r.chunk.start_time)}]\n{r.chunk.text}"
            )
        return "\n\n---\n\n".join(parts)

    async def _openai_generate(self, question: str, context: str) -> Tuple[str, str]:
        response = await self.client.chat.completions.create(
            model="gpt-4.1-mini",
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {
                    "role": "user",
                    "content": f"Educational context:\n\n{context}\n\nStudent question: {question}",
                },
            ],
            temperature=0.3,
            max_tokens=800,
        )
        return response.choices[0].message.content, "text-embedding-3-small + gpt-4.1-mini"

    def _local_generate(self, question: str, results: List[SearchResult]) -> str:
        top = results[0].chunk
        excerpt = top.text[:400] + ("..." if len(top.text) > 400 else "")
        return (
            f"Based on \"{top.course_title}\" — {top.lecture_title}:\n\n"
            f"{excerpt}\n\n"
            f"(OpenAI API key not configured. Set OPENAI_API_KEY for full AI-generated answers.)"
        )


def _fmt_time(seconds: int) -> str:
    m, s = divmod(seconds, 60)
    return f"{m:02d}:{s:02d}"


answer_generator = AnswerGenerator()
