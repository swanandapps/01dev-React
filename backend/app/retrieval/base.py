"""Retriever contract + Reciprocal Rank Fusion (spec §2.3, §4). Backends implement only the two
searches; fusion, caps and limits live here once, so Memory and Pg can't drift apart."""
from dataclasses import dataclass
from typing import Optional, Protocol, Sequence, runtime_checkable

from app.models import TranscriptChunk

RRF_K = 60


@dataclass
class Candidate:
    chunk: TranscriptChunk
    vec_rank: Optional[int] = None
    lex_rank: Optional[int] = None
    vec_score: Optional[float] = None
    lex_score: Optional[float] = None
    fused: float = 0.0


@runtime_checkable
class Retriever(Protocol):
    name: str

    async def vector_search(self, embedding: list[float], scope: Sequence[str], k: int,
                            lecture_id: Optional[str] = None) -> list[tuple[TranscriptChunk, float]]: ...

    async def lexical_search(self, tokens: list[str], scope: Sequence[str], k: int,
                             lecture_id: Optional[str] = None) -> list[tuple[TranscriptChunk, float]]: ...


def rrf_fuse(vec_lists, lex_lists, *, limit: int = 12, per_lecture: Optional[int] = 3,
             k: int = RRF_K) -> list[Candidate]:
    """fused = Σ 1 / (k + rank) over every list a chunk appears in (rank is 1-based). Sorted by fused,
    then best vector rank, then chunk id; then at most `per_lecture` chunks per lecture, `limit` in all."""
    by_id: dict[str, Candidate] = {}
    for lists, kind in ((vec_lists, "vec"), (lex_lists, "lex")):
        for lst in lists:
            for rank, (chunk, score) in enumerate(lst, 1):
                cand = by_id.setdefault(chunk.chunk_id, Candidate(chunk=chunk))
                cand.fused += 1.0 / (k + rank)
                if kind == "vec":
                    if cand.vec_rank is None or rank < cand.vec_rank:
                        cand.vec_rank = rank
                    cand.vec_score = score if cand.vec_score is None else max(cand.vec_score, score)
                else:
                    if cand.lex_rank is None or rank < cand.lex_rank:
                        cand.lex_rank = rank
                    cand.lex_score = score if cand.lex_score is None else max(cand.lex_score, score)
    ordered = sorted(by_id.values(),
                     key=lambda c: (-c.fused, c.vec_rank if c.vec_rank is not None else 10 ** 9, c.chunk.chunk_id))
    out, per = [], {}
    for cand in ordered:
        lid = cand.chunk.lecture_id
        if per_lecture is not None and per.get(lid, 0) >= per_lecture:
            continue
        per[lid] = per.get(lid, 0) + 1
        out.append(cand)
        if len(out) == limit:
            break
    return out
