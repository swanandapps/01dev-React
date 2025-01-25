import os
import math
from typing import List


class EmbeddingService:
    def __init__(self):
        self.api_key = os.getenv("OPENAI_API_KEY")
        self.use_openai = bool(self.api_key)
        self.client = None
        if self.use_openai:
            try:
                from openai import AsyncOpenAI
                self.client = AsyncOpenAI(api_key=self.api_key)
                print("EmbeddingService: using OpenAI text-embedding-3-small")
            except ImportError:
                self.use_openai = False
                print("EmbeddingService: openai package not found, using local fallback")
        else:
            print("EmbeddingService: no OPENAI_API_KEY, using local hash embedding")

    async def embed(self, text: str) -> List[float]:
        if self.use_openai and self.client:
            return await self._openai_embed(text)
        return self._local_embed(text)

    async def _openai_embed(self, text: str) -> List[float]:
        response = await self.client.embeddings.create(
            model="text-embedding-3-small",
            input=text[:8000],
        )
        return response.data[0].embedding

    def _local_embed(self, text: str) -> List[float]:
        """
        Deterministic 256-dim hash-based bag-of-words embedding.
        Good enough for keyword-rich demo queries without external deps.
        """
        DIM = 256
        words = text.lower().split()
        vec = [0.0] * DIM
        for word in words:
            clean = "".join(c for c in word if c.isalnum())
            if clean:
                idx = abs(hash(clean)) % DIM
                vec[idx] += 1.0
        norm = math.sqrt(sum(v * v for v in vec))
        if norm > 0:
            vec = [v / norm for v in vec]
        return vec


embedding_service = EmbeddingService()
