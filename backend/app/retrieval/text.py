"""Text helpers shared by enrichment, BM25 and the Postgres full-text columns."""
import re


def norm_title(s: str) -> str:
    """Compare lecture titles loosely: backticks, spacing and case drift between player and transcripts."""
    return " ".join(s.replace("`", "").split()).casefold()


_SENTENCE_END = re.compile(r"(?<=[.!?])\s+")


def last_sentence(text: str, max_chars: int = 200, max_words: int = 25) -> str:
    """The last sentence; for unpunctuated (Whisper) text, at most the last max_words whole words.
    Never starts mid-word (unless a single word alone exceeds max_chars)."""
    parts = [p for p in _SENTENCE_END.split(text.strip()) if p.strip()]
    tail = parts[-1].strip() if parts else ""
    words = tail.split()
    if len(words) > max_words:
        words = words[-max_words:]
    while len(words) > 1 and len(" ".join(words)) > max_chars:
        words = words[1:]
    tail = " ".join(words)
    return tail[-max_chars:]
