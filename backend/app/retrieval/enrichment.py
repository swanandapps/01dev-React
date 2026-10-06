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
import os
import re
from pathlib import Path
from typing import Optional

from app.models import TranscriptChunk
from app.retrieval.text import last_sentence

BACKEND = Path(__file__).resolve().parents[2]
ENRICH_DIR = BACKEND / "data" / "enrichment"
GLOSSARY_DIR = BACKEND / "data" / "glossary"
EMBED_MODEL = "text-embedding-3-small"
EMBED_TEXT_CHARS = 8000  # embeddings.py truncates input at 8000 chars too


def text_sha(text: str) -> str:
    return hashlib.sha256(text.encode()).hexdigest()[:16]


def load_glossary(slug: str, glossary_dir: Path = GLOSSARY_DIR) -> list[tuple[re.Pattern, str]]:
    p = Path(glossary_dir) / f"{slug}.json"
    if not p.exists():
        return []
    return [(re.compile(r["pattern"], re.IGNORECASE), r["replace"])
            for r in json.loads(p.read_text()).get("replacements", [])]


def clean_text(text: str, glossary: list[tuple[re.Pattern, str]]) -> str:
    for pattern, replacement in glossary:
        text = pattern.sub(replacement, text)
    return " ".join(text.split())


def load_enrichment(slug: str, enrich_dir: Path = ENRICH_DIR) -> dict[str, dict]:
    p = Path(enrich_dir) / f"{slug}.json"
    return json.loads(p.read_text()).get("chunks", {}) if p.exists() else {}


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
    prev_clean: dict[str, str] = {}   # lecture_id -> previous chunk's text_clean (seed order = time order)
    out = []
    for c in chunks:
        slug = c.course_id
        if slug not in glossaries:
            glossaries[slug] = load_glossary(slug, glossary_dir)
            entries[slug] = load_enrichment(slug, enrich_dir)
        e = entries[slug].get(c.chunk_id)
        fresh = bool(e) and e.get("text_sha") == text_sha(c.text)
        new = c.model_copy(update={
            "chapter": chapter_for(c.lecture_id, slug),
            "text_clean": clean_text(c.text, glossaries[slug]),
            "summary": (e or {}).get("summary", "") if fresh else "",
            "keywords": list((e or {}).get("keywords", [])) if fresh else [],
            "questions": list((e or {}).get("questions", [])) if fresh else [],
        })
        new.embed_text = build_embed_text(new, prev_clean.get(c.lecture_id))
        new.embed_model = EMBED_MODEL
        new.content_hash = content_hash(new.embed_text, EMBED_MODEL)
        prev_clean[c.lecture_id] = new.text_clean
        out.append(new)
    return out
