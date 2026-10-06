"""MemoryRetriever: the Retriever contract over the in-process vector_store (local runs, tests,
DATABASE_URL blank). Cosine over precomputed norms + BM25 over lexical_doc, both scope-filtered
BEFORE scoring, so another course's chunk is never scored, let alone returned."""
import math
from typing import Optional, Sequence

from app.models import TranscriptChunk
from app.retrieval.bm25 import BM25Index
from app.retrieval.text import lexical_doc


class MemoryRetriever:
    name = "memory"

    def __init__(self, store=None):
        if store is None:
            from app.services.vector_store import vector_store as store
        self.store = store
        self._bm25: Optional[BM25Index] = None
        self._bm25_key: tuple = ()

    def _scoped(self, scope: Sequence[str], lecture_id: Optional[str]) -> list[int]:
        self.store._ensure_index()
        idx = [i for slug in dict.fromkeys(scope) for i in self.store._course_idx.get(slug, [])]
        if lecture_id:
            idx = [i for i in idx if self.store.chunks[i].lecture_id == lecture_id]
        return idx

    def _index(self) -> BM25Index:
        self.store._ensure_index()
        key = self.store._indexed_for   # same invalidation signal as the store's norms/course index
        if self._bm25 is None or self._bm25_key != key:
            self._bm25 = BM25Index([lexical_doc(c) for c in self.store.chunks])
            self._bm25_key = key
        return self._bm25

    async def vector_search(self, embedding: list[float], scope: Sequence[str], k: int,
                            lecture_id: Optional[str] = None) -> list[tuple[TranscriptChunk, float]]:
        if not scope or not embedding:
            return []
        pos = self._scoped(scope, lecture_id)
        qn = math.sqrt(sum(x * x for x in embedding))
        embs, norms, n = self.store._embeddings, self.store._norms, len(self.store._embeddings)
        if not qn:
            return []
        scored = [(i, sum(x * y for x, y in zip(embedding, embs[i])) / (qn * norms[i]))
                  for i in pos if i < n and norms[i]]
        scored.sort(key=lambda t: (-t[1], t[0]))
        return [(self.store.chunks[i], s) for i, s in scored[:k]]

    async def lexical_search(self, tokens: list[str], scope: Sequence[str], k: int,
                             lecture_id: Optional[str] = None) -> list[tuple[TranscriptChunk, float]]:
        if not scope or not tokens:
            return []
        allowed = set(self._scoped(scope, lecture_id))
        if not allowed:
            return []
        return [(self.store.chunks[i], s) for i, s in self._index().search(tokens, allowed, k)]
