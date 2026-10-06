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

EMBED_BATCH = 100


def _fmt_vec(v: List[float]) -> str:
    """List -> pgvector text literal, e.g. '[0.1,0.2]'."""
    return "[" + ",".join(repr(float(x)) for x in v) + "]"


def _parse_vec(s: str) -> List[float]:
    """pgvector text literal -> list."""
    return [float(x) for x in s.strip("[]").split(",")] if s else []


class InMemoryVectorStore:
    """
    RAG store. Chunk metadata is held in memory (small, deterministic seed set);
    embeddings are persisted to Postgres/pgvector when DATABASE_URL is set, so they
    survive restarts and aren't recomputed (and cost re-paid) on every boot.

    search() stays synchronous (in-process cosine) so callers are unchanged; the
    pgvector table is the durable cache + basis for SQL-side search at larger scale.
    """

    def __init__(self):
        self.chunks: List[TranscriptChunk] = []
        self._embeddings: List[List[float]] = []

    async def initialize(self):
        seed_path = os.path.join(os.path.dirname(__file__), "../data/seed_transcripts.json")
        with open(seed_path, "r") as f:
            data = json.load(f)

        self.chunks = [TranscriptChunk(**item) for item in data]
        self._embeddings = []

        if os.getenv("DATABASE_URL") and embedding_service.use_openai:
            try:
                await self._init_with_pgvector()
                return
            except Exception as e:  # noqa: BLE001 — DB/driver missing (e.g. in the MCP venv) → degrade
                print(f"Vector store: pgvector path unavailable ({e}); using in-memory embeddings.")
                self._embeddings = []

        print(f"Computing embeddings for {len(self.chunks)} transcript chunks (in-memory)...")
        self._embeddings = await embedding_service.embed_many([c.text for c in self.chunks])
        print(f"Vector store ready — {len(self.chunks)} chunks indexed (in-memory).")

    async def _init_with_pgvector(self):
        """Reuse persisted embeddings; only embed (and store) chunks not yet cached."""
        from app.services.db import get_pool

        pool = await get_pool()
        rows = await pool.fetch(
            "select chunk_id, embedding::text as emb from rag_chunks where embedding is not null"
        )
        cached = {r["chunk_id"]: _parse_vec(r["emb"]) for r in rows}

        missing = [c for c in self.chunks if c.chunk_id not in cached]
        for i in range(0, len(missing), EMBED_BATCH):
            batch = missing[i:i + EMBED_BATCH]
            embs = await embedding_service.embed_many([c.text for c in batch])
            await pool.executemany(
                """insert into rag_chunks (chunk_id, text, meta, embedding)
                   values ($1, $2, $3, $4::vector)
                   on conflict (chunk_id)
                   do update set text = $2, meta = $3, embedding = $4::vector""",
                [
                    (c.chunk_id, c.text, c.model_dump(exclude={"embedding"}), _fmt_vec(e))
                    for c, e in zip(batch, embs)
                ],
            )
            for c, e in zip(batch, embs):
                cached[c.chunk_id] = e
        newly = len(missing)
        self._embeddings = [cached[c.chunk_id] for c in self.chunks]

        print(f"Vector store ready — {len(self.chunks)} chunks "
              f"({newly} newly embedded, {len(self.chunks) - newly} from pgvector cache).")

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

    def get_course_lectures(self, course_id: str) -> List[dict]:
        """Distinct lectures within a course, in time/seed order."""
        seen: dict = {}
        for chunk in self.chunks:
            if chunk.course_id == course_id and chunk.lecture_id not in seen:
                seen[chunk.lecture_id] = {
                    "lecture_id": chunk.lecture_id,
                    "lecture_title": chunk.lecture_title,
                }
        return list(seen.values())

    def get_course_meta(self, course_id: str) -> Optional[dict]:
        lectures = self.get_course_lectures(course_id)
        if not lectures:
            return None
        title = next(c.course_title for c in self.chunks if c.course_id == course_id)
        return {
            "course_id": course_id,
            "course_title": title,
            "lecture_count": len(lectures),
            "lectures": lectures,
        }

    def get_course_transcript(self, course_id: str) -> str:
        """Whole-course transcript: every lecture's chunks, with lecture headers
        so generation stays lecture-aware (concepts can reference a lecture)."""
        chunks = [c for c in self.chunks if c.course_id == course_id]
        chunks.sort(key=lambda c: (c.lecture_id, c.start_time))
        parts: List[str] = []
        current_lecture = None
        for c in chunks:
            if c.lecture_id != current_lecture:
                current_lecture = c.lecture_id
                parts.append(f"\n[Lecture: {c.lecture_title}]")
            parts.append(c.text)
        return "\n\n".join(parts).strip()

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
