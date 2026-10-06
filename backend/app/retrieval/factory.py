"""Which Retriever serves this process. Memory by default; Task 23's init_retriever() switches prod
(DATABASE_URL set) to PgRetriever at startup."""
from typing import Optional

from app.retrieval.base import Retriever

_retriever: Optional[Retriever] = None


def set_retriever(r: Optional[Retriever]) -> None:
    global _retriever
    _retriever = r


def get_retriever() -> Retriever:
    global _retriever
    if _retriever is None:
        from app.retrieval.memory import MemoryRetriever
        _retriever = MemoryRetriever()
    return _retriever
