import json
import math
import os
from typing import List, Optional

from app.models import TranscriptChunk, SearchResult
from app.services.embeddings import embedding_service

_STOP_WORDS = {
    "the","a","an","is","it","this","that","what","why","how","does","do",
    "i","to","of","in","and","or","for","with","not","be","are","was","were",
    "has","have","had","will","can","could","would","should","may","might",
    "did","which","who","when","where","if","then","there","here","we","they",
    "he","she","you","me","my","our","their","its","but","just","also","so",
    "about","from","at","by","as","on","up","out","into","over","after",
    "explain","simply","help","create","make","use","used","using","means",
    "tell","show","give","let","get","put","run","work","works","something",
}


class InMemoryVectorStore:
    """
    In-memory RAG store for MVP. Drop-in replaceable with pgvector:
    swap search() to use pg vector_cosine_ops index and initialize()
    to INSERT chunks into PostgreSQL instead of a list.
    """

    def __init__(self):
        self.chunks: List[TranscriptChunk] = []
        self._embeddings: List[List[float]] = []

    async def initialize(self):
        seed_path = os.path.join(os.path.dirname(__file__), "../data/seed_transcripts.json")
        with open(seed_path, "r") as f:
            data = json.load(f)

        self.chunks = [TranscriptChunk(**item) for item in data]
        print(f"Computing embeddings for {len(self.chunks)} transcript chunks...")

        for chunk in self.chunks:
            emb = await embedding_service.embed(chunk.text)
            self._embeddings.append(emb)

        print(f"Vector store ready — {len(self.chunks)} chunks indexed.")

    def search(
        self,
        query_embedding: List[float],
        top_k: int = 5,
        threshold: float = 0.25,
        query_text: str = "",
    ) -> List[SearchResult]:
        if not embedding_service.use_openai and query_text:
            return self._keyword_search(query_text, top_k, threshold)
        return self._embedding_search(query_embedding, top_k, threshold)

    def _embedding_search(
        self,
        query_embedding: List[float],
        top_k: int,
        threshold: float,
    ) -> List[SearchResult]:
        scores = [
            (i, self._cosine_sim(query_embedding, emb))
            for i, emb in enumerate(self._embeddings)
        ]
        scores.sort(key=lambda x: x[1], reverse=True)

        results = []
        for i, score in scores[:top_k]:
            if score < threshold:
                break
            results.append(SearchResult(chunk=self.chunks[i], score=score))

        return results

    def _keyword_search(
        self,
        query_text: str,
        top_k: int,
        threshold: float,
    ) -> List[SearchResult]:
        """BM25-inspired keyword overlap for local (no-API) mode."""
        query_words = {
            w.lower().strip(".,?!")
            for w in query_text.split()
            if w.lower().strip(".,?!") not in _STOP_WORDS and len(w) > 2
        }

        if not query_words:
            return []

        scored = []
        for i, chunk in enumerate(self.chunks):
            chunk_tokens = {
                w.lower().strip(".,?!")
                for w in chunk.text.split()
                if w.isalnum()
            }
            overlap = len(query_words & chunk_tokens)
            if overlap == 0:
                continue
            score = overlap / (len(query_words) + 1)
            scored.append((i, min(score, 1.0)))

        scored.sort(key=lambda x: x[1], reverse=True)

        results = []
        for i, score in scored[:top_k]:
            if score < threshold:
                break
            results.append(SearchResult(chunk=self.chunks[i], score=score))

        return results

    def list_lectures(self) -> List[dict]:
        """Distinct lectures that have transcripts, in seed order."""
        seen: dict = {}
        for chunk in self.chunks:
            if chunk.lecture_id not in seen:
                seen[chunk.lecture_id] = {
                    "lecture_id": chunk.lecture_id,
                    "lecture_title": chunk.lecture_title,
                    "course_id": chunk.course_id,
                    "course_title": chunk.course_title,
                }
        return list(seen.values())

    def get_lecture_chunks(self, lecture_id: str) -> List[TranscriptChunk]:
        return [c for c in self.chunks if c.lecture_id == lecture_id]

    def get_lecture_transcript(self, lecture_id: str) -> str:
        """Full lecture text, chunks concatenated in time order."""
        chunks = sorted(self.get_lecture_chunks(lecture_id), key=lambda c: c.start_time)
        return "\n\n".join(c.text for c in chunks)

    def get_lecture_meta(self, lecture_id: str) -> Optional[dict]:
        for chunk in self.chunks:
            if chunk.lecture_id == lecture_id:
                return {
                    "lecture_id": chunk.lecture_id,
                    "lecture_title": chunk.lecture_title,
                    "course_id": chunk.course_id,
                    "course_title": chunk.course_title,
                }
        return None

    def get_all_courses(self):
        seen: dict = {}
        for chunk in self.chunks:
            cid = chunk.course_id
            if cid not in seen:
                seen[cid] = {"course_id": cid, "title": chunk.course_title, "lectures": set()}
            seen[cid]["lectures"].add(chunk.lecture_id)
        return [
            {"course_id": v["course_id"], "title": v["title"], "lecture_count": len(v["lectures"])}
            for v in seen.values()
        ]

    @staticmethod
    def _cosine_sim(a: List[float], b: List[float]) -> float:
        dot = sum(x * y for x, y in zip(a, b))
        norm_a = math.sqrt(sum(x * x for x in a))
        norm_b = math.sqrt(sum(x * x for x in b))
        if norm_a == 0 or norm_b == 0:
            return 0.0
        return dot / (norm_a * norm_b)


vector_store = InMemoryVectorStore()
