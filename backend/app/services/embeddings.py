import os
import math
from typing import List

EMBED_MODEL = "text-embedding-3-small"


class EmbeddingService:
    def __init__(self):
        self.api_key = os.getenv("OPENAI_API_KEY")
        self.use_openai = bool(self.api_key)
        self.client = None
        if self.use_openai:
            try:
                from openai import AsyncOpenAI
                from app.services.tracing import maybe_trace
                # timeout + bounded exponential-backoff retries (SDK-native)
                self.client = maybe_trace(AsyncOpenAI(api_key=self.api_key, timeout=30.0, max_retries=3))
                print("EmbeddingService: using OpenAI {EMBED_MODEL}")
            except ImportError:
                self.use_openai = False
                print("EmbeddingService: openai package not found, using local fallback")
        else:
            print("EmbeddingService: no OPENAI_API_KEY, using local hash embedding")

    async def embed(self, text: str) -> List[float]:
        if self.use_openai and self.client:
            return await self._openai_embed(text)
        return self._local_embed(text)

    async def embed_many(self, texts: List[str], batch_size: int = 100) -> List[List[float]]:
        """Embed texts in order, one embeddings.create call per batch when OpenAI is on."""
        if not (self.use_openai and self.client):
            return [self._local_embed(t) for t in texts]
        out: List[List[float]] = []
        for i in range(0, len(texts), batch_size):
            batch = texts[i:i + batch_size]
            response = await self.client.embeddings.create(
                model=EMBED_MODEL,
                input=[t[:8000] for t in batch],
            )
            if len(response.data) != len(batch):
                raise RuntimeError(
                    f"embeddings response size mismatch: got {len(response.data)}, expected {len(batch)}"
                )
            out.extend(d.embedding for d in sorted(response.data, key=lambda d: d.index))
        return out

    async def _openai_embed(self, text: str) -> List[float]:
        response = await self.client.embeddings.create(
            model=EMBED_MODEL,
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
