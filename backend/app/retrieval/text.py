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


_WORD = re.compile(r"[A-Za-z0-9]+")
_CAMEL_PART = re.compile(r"[A-Z]+(?=[A-Z][a-z])|[A-Z]?[a-z]+|[A-Z]+|[0-9]+")
_STOP = frozenset("""
a an the and or but if then else of to in on at by for with from as is are was were be been being it its this
that these those there here we you he she they me my our your their them his her what which who whom when where
why how do does did doing done can could would should will shall may might must not no so just also about into
over under up down out than too very more most some any all each other such only own same both few again once
let lets get got go going gonna wanna like okay ok yeah um uh""".split())


def _stem(t: str) -> str:
    if len(t) > 4 and t.endswith("ies"):
        return t[:-3] + "y"
    if len(t) > 4 and t.endswith("s") and not t.endswith(("ss", "us", "is")):
        return t[:-1]
    return t


def tokenize(text: str) -> list[str]:
    """Search tokens shared by BM25 and the Postgres search_tsv ('simple' config over these tokens).
    Acronyms and short code words survive (IIFE, np, js); camelCase identifiers that start lowercase
    (useMemo, innerHTML) are kept whole and split; PascalCase brand names (JavaScript) are not split."""
    out: list[str] = []
    for raw in _WORD.findall(text or ""):
        low = raw.lower()
        variants = [low]
        if raw[0].islower() and any(ch.isupper() for ch in raw[1:]):
            parts = [p.lower() for p in _CAMEL_PART.findall(raw)]
            if len(parts) > 1:
                variants += parts
        for tok in variants:
            if len(tok) >= 2 and tok not in _STOP:
                out.append(_stem(tok))
    return out


def lexical_fields(chunk) -> tuple[list[str], list[str], list[str]]:
    """(A, B, C) = (lecture title + keywords, summary + questions, text) — the Postgres setweight A/B/C."""
    a = tokenize(chunk.lecture_title + " " + " ".join(chunk.keywords))
    b = tokenize(chunk.summary + " " + " ".join(chunk.questions))
    c = tokenize(chunk.text_clean or chunk.text)
    return a, b, c


def lexical_doc(chunk) -> list[str]:
    a, b, c = lexical_fields(chunk)
    return a * 3 + b * 2 + c
