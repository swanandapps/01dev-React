"""Context-rich chunks (spec §3): merge the committed offline enrichment into the chunks at load time
and derive text_clean (glossary), chapter, embed_text and content_hash. Never touches text/times/ids.

Enrichment file: backend/data/enrichment/<slug>.json
  {"version": 1, "model": "gpt-4.1-mini", "chunks": {chunk_id: {"text_sha", "summary", "keywords", "questions"}}}
An entry applies only while sha256(chunk.text)[:16] == text_sha, so a transcript edit makes it inert.
Glossary file: backend/data/glossary/<slug>.json  {"replacements": [{"pattern": regex, "replace": str}]}
(case-insensitive; applied to text_clean only).
"""
import hashlib
import json
import logging
import os
import re
from pathlib import Path
from typing import Optional

from app.models import TranscriptChunk
from app.retrieval.text import last_sentence

BACKEND = Path(__file__).resolve().parents[2]
ENRICH_DIR = BACKEND / "data" / "enrichment"
GLOSSARY_DIR = BACKEND / "data" / "glossary"
from app.services.embeddings import EMBED_MODEL  # noqa: E402  single source of truth for the model name

log = logging.getLogger(__name__)
EMBED_TEXT_CHARS = 8000  # embeddings.py truncates input at 8000 chars too


def text_sha(text: str) -> str:
    return hashlib.sha256(text.encode()).hexdigest()[:16]


_BOUNDARY = re.compile(r"\\b|\(\?<[=!]|\(\?[=!]")


def load_glossary(slug: str, glossary_dir: Path = GLOSSARY_DIR) -> list[tuple[re.Pattern, str]]:
    """Entries: {"term", "replacement"} (literal, whole-word) or {"pattern", "replace"} (regex that must
    carry a word boundary or lookaround, so "np" can never rewrite "npm")."""
    p = Path(glossary_dir) / f"{slug}.json"
    if not p.exists():
        return []
    try:
        rows = json.loads(p.read_text()).get("replacements", [])
    except Exception as e:  # noqa: BLE001 — bad data must never break boot
        log.warning("glossary %s: unreadable, skipping the whole file (%s)", p, e)
        return []
    out = []
    for r in rows:
        try:
            if "term" in r:
                pat = r"(?<!\w)" + r"\s+".join(re.escape(w) for w in r["term"].split()) + r"(?!\w)"
                out.append((re.compile(pat, re.IGNORECASE), r["replacement"]))
            else:
                if not _BOUNDARY.search(r["pattern"]):
                    raise ValueError(f"regex {r['pattern']!r} needs a word boundary or lookaround")
                out.append((re.compile(r["pattern"], re.IGNORECASE), r["replace"]))
        except Exception as e:  # noqa: BLE001
            log.warning("glossary %s: skipping bad entry %r (%s)", p, r, e)
    return out


def clean_text(text: str, glossary: list[tuple[re.Pattern, str]]) -> str:
    for pattern, replacement in glossary:
        text = pattern.sub(replacement, text)
    return " ".join(text.split())


def load_enrichment(slug: str, enrich_dir: Path = ENRICH_DIR) -> dict[str, dict]:
    p = Path(enrich_dir) / f"{slug}.json"
    if not p.exists():
        return {}
    try:
        chunks = json.loads(p.read_text()).get("chunks", {})
        if not isinstance(chunks, dict):
            raise ValueError("'chunks' is not an object")
    except Exception as e:  # noqa: BLE001 — bad data must never break boot
        log.warning("enrichment %s: unreadable, skipping the whole file (%s)", p, e)
        return {}
    return {k: v for k, v in chunks.items() if isinstance(v, dict)}


def save_enrichment(slug: str, entries: dict[str, dict], model: str, enrich_dir: Path = ENRICH_DIR) -> Path:
    p = Path(enrich_dir) / f"{slug}.json"
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.with_name(p.name + ".tmp")
    body = {"version": 1, "model": model, "chunks": {k: entries[k] for k in sorted(entries)}}
    tmp.write_text(json.dumps(body, indent=1, ensure_ascii=False) + "\n")
    os.replace(tmp, p)
    return p


def chapter_for(lecture_id: str, slug: str) -> str:
    from app.services import catalog_service
    m = re.search(r"-(\d+)-(\d+)$", lecture_id)
    chapters = (catalog_service.by_slug(slug) or {}).get("chapters", [])
    if not m or int(m.group(1)) >= len(chapters):
        return ""
    return chapters[int(m.group(1))].get("name", "")


def build_embed_text(chunk: TranscriptChunk, prev_text: Optional[str]) -> str:
    header = " › ".join(p for p in (chunk.course_title, chunk.chapter, chunk.lecture_title) if p)
    parts = [header]
    if chunk.summary:
        parts.append(f"Summary: {chunk.summary}")
    if chunk.keywords:
        parts.append("Key terms: " + ", ".join(chunk.keywords))
    if prev_text:
        parts.append(f"Previously: {last_sentence(prev_text)}")
    parts.append(chunk.text_clean or chunk.text)
    return "\n".join(parts)[:EMBED_TEXT_CHARS]


def content_hash(embed_text: str, model: str = EMBED_MODEL) -> str:
    return hashlib.sha256(f"{model}\n{embed_text}".encode()).hexdigest()


def embed_input(chunk: TranscriptChunk) -> str:
    """What to embed for this chunk: embed_text once enrichment has run, else the raw text."""
    return chunk.embed_text or chunk.text


def apply_enrichment(chunks: list[TranscriptChunk], enrich_dir: Path = ENRICH_DIR,
                     glossary_dir: Path = GLOSSARY_DIR) -> list[TranscriptChunk]:
    glossaries: dict[str, list] = {}
    entries: dict[str, dict] = {}
    enriched = []
    for c in chunks:
        slug = c.course_id
        if slug not in glossaries:
            glossaries[slug] = load_glossary(slug, glossary_dir)
            entries[slug] = load_enrichment(slug, enrich_dir)
        e = entries[slug].get(c.chunk_id)
        fresh = bool(e) and e.get("text_sha") == text_sha(c.text) and isinstance(e.get("keywords", []), list) and isinstance(e.get("questions", []), list)
        enriched.append(c.model_copy(update={
            "chapter": chapter_for(c.lecture_id, slug),
            "text_clean": clean_text(c.text, glossaries[slug]),
            "summary": (e or {}).get("summary", "") if fresh else "",
            "keywords": list((e or {}).get("keywords", [])) if fresh else [],
            "questions": list((e or {}).get("questions", [])) if fresh else [],
        }))
    by_lecture: dict[str, list[TranscriptChunk]] = {}
    for c in enriched:
        by_lecture.setdefault(c.lecture_id, []).append(c)
    for group in by_lecture.values():   # overlap follows time order, whatever the input order
        prev = None
        for c in sorted(group, key=lambda x: x.start_time):
            c.embed_text = build_embed_text(c, prev)
            c.embed_model = EMBED_MODEL
            c.content_hash = content_hash(c.embed_text, EMBED_MODEL)
            prev = c.text_clean
    return enriched
