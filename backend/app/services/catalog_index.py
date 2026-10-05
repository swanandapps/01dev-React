"""Embedding index over the course catalog: one entry per course and per module.

Lets course_lookup recommend courses that have no lecture transcripts yet (7 of
10 today). ~60 short texts, embedded once per process and held in memory.
"""
import asyncio
import math
from dataclasses import dataclass
from typing import Optional

from app.services import catalog_service
from app.services.embeddings import embedding_service


@dataclass(frozen=True)
class CatalogEntry:
    course_id: int
    course_slug: Optional[str]
    course_title: str
    module_title: Optional[str]  # None = the course as a whole
    text: str


_entries: list[CatalogEntry] = []
_vectors: list[list[float]] = []


def build_entries() -> list[CatalogEntry]:
    entries: list[CatalogEntry] = []
    for c in catalog_service.all_courses():
        entries.append(CatalogEntry(c["id"], c["slug"], c["title"], None, f"{c['title']}. {c['description']}"))
        for m in c["modules"]:
            entries.append(CatalogEntry(
                c["id"], c["slug"], c["title"], m["title"], f"{c['title']}: {m['title']}. {m['description']}",
            ))
    return entries


async def ensure_built() -> None:
    global _entries, _vectors
    if _entries:
        return
    entries = build_entries()
    sem = asyncio.Semaphore(8)  # stay well under embedding rate limits

    async def embed(text: str) -> list[float]:
        async with sem:
            return await embedding_service.embed(text)

    vectors = await asyncio.gather(*(embed(e.text) for e in entries))
    _entries, _vectors = entries, list(vectors)


def _cosine(a: list[float], b: list[float]) -> float:
    dot = sum(x * y for x, y in zip(a, b))
    na, nb = math.sqrt(sum(x * x for x in a)), math.sqrt(sum(y * y for y in b))
    return dot / (na * nb) if na and nb else 0.0


async def search(query: str, top_k: int = 5) -> list[tuple[CatalogEntry, float]]:
    await ensure_built()
    q = await embedding_service.embed(query)
    scored = sorted(((e, _cosine(q, v)) for e, v in zip(_entries, _vectors)), key=lambda x: x[1], reverse=True)
    return scored[:top_k]


def reset() -> None:
    global _entries, _vectors
    _entries, _vectors = [], []
