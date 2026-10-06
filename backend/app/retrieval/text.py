"""Text helpers shared by enrichment, BM25 and the Postgres full-text columns."""
import re


def norm_title(s: str) -> str:
    """Compare lecture titles loosely: backticks, spacing and case drift between player and transcripts."""
    return " ".join(s.replace("`", "").split()).casefold()


_SENTENCE_END = re.compile(r"(?<=[.!?])\s+")


def last_sentence(text: str, max_chars: int = 200) -> str:
    parts = [p for p in _SENTENCE_END.split(text.strip()) if p.strip()]
    tail = parts[-1].strip() if parts else ""
    return tail[-max_chars:]
