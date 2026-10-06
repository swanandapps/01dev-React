"""Lecture-title signal (retrieval side): cached title vectors, prewarm, and scores of a question against the
titles of every lecture in a scope. Scoring uses an ALREADY COMPUTED question embedding (never embeds the
question); word overlap is the fallback when title vectors are unavailable. course_lookup's legacy
_title_scores/prewarm_titles delegate here."""
import asyncio
import math
import re
import time
from typing import Optional, Sequence

from app.services import catalog_service
from app.services.embeddings import embedding_service

TITLE_THRESHOLD = 0.60      # a title at/above this matches the question (see course_lookup's calibration notes)
TITLE_EMBED_TIMEOUT = 5.0   # seconds for the batched title-embedding call
TITLE_PREWARM_TIMEOUT = 30.0  # startup batch for every course
TITLE_COOLDOWN = 60.0       # after a failure, use word overlap for this long before retrying

_STOPWORDS = {"the", "and", "for", "with", "what", "are", "how", "does", "why", "our", "your", "that",
              "this", "from", "into", "using", "use", "can", "you", "its", "was", "were", "who", "when"}
_cache: dict[str, tuple[list[str], list[list[float]]]] = {}
_failed_until: dict[str, float] = {}


def bare_title(title: str) -> str:
    """"8.1 - The `npm link` command" -> "The npm link command"."""
    return re.sub(r"^\s*\d+(\.\d+)*\s*-\s*", "", title).replace("`", "").strip()


def lecture_titles(slug: str) -> list[str]:
    course = catalog_service.by_slug(slug)
    return [t for ch in (course or {}).get("chapters", []) for t in ch.get("subchapters", [])]


def _cosine(a: list[float], b: list[float]) -> float:
    na, nb = math.sqrt(sum(x * x for x in a)), math.sqrt(sum(x * x for x in b))
    return sum(x * y for x, y in zip(a, b)) / (na * nb) if na and nb else 0.0


def _words(text: str) -> set[str]:
    return {w for w in re.findall(r"[a-z0-9]+", text.casefold()) if len(w) > 2 and w not in _STOPWORDS}


def overlap_scores(question: str, titles: list[str]) -> dict[str, float]:
    """No-embedding fallback: 1.0 when at least half of a title's content words are in the question, else 0.0."""
    q = _words(question)
    out = {}
    for t in titles:
        w = _words(bare_title(t))
        out[t] = 1.0 if w and len(w & q) / len(w) >= 0.5 else 0.0
    return out


async def _embed_titles(slug: str, titles: list[str]) -> list[list[float]]:
    """One batched embed call per course, cached for the process."""
    cached = _cache.get(slug)
    if cached and cached[0] == titles:
        return cached[1]
    resp = await asyncio.wait_for(
        embedding_service.client.embeddings.create(model="text-embedding-3-small",
                                                   input=[bare_title(t) for t in titles]),
        timeout=TITLE_EMBED_TIMEOUT)
    vecs = [d.embedding for d in resp.data]
    _cache[slug] = (titles, vecs)
    return vecs


async def vectors(slug: str) -> Optional[list[list[float]]]:
    """The course's title vectors (cached; built lazily as a backup to prewarm), or None when unavailable
    (no embeddings, no titles, or cooling down after a failure)."""
    titles = lecture_titles(slug)
    if not titles or not (embedding_service.use_openai and embedding_service.client):
        return None
    if time.monotonic() < _failed_until.get(slug, 0.0):
        return None
    try:
        return await _embed_titles(slug, titles)
    except Exception as e:  # noqa: BLE001 — title signal is best-effort
        _failed_until[slug] = time.monotonic() + TITLE_COOLDOWN
        print(f"[titles] title embedding failed, word overlap for {TITLE_COOLDOWN:.0f}s: {e!r}")
        return None


async def title_scores(question_embedding: Optional[list[float]], slugs: Sequence[str], *,
                       question: str = "") -> dict[tuple[str, str], float]:
    """{(slug, lecture title as the course lists it): score} for every lecture of every slug. Cosine of the
    given question embedding to the cached title vectors; word overlap against `question` for a slug whose
    vectors are unavailable or when no embedding was given. Never embeds the question."""
    out: dict[tuple[str, str], float] = {}
    for slug in dict.fromkeys(slugs):
        titles = lecture_titles(slug)
        vecs = await vectors(slug) if question_embedding else None
        scores = ({t: _cosine(question_embedding, v) for t, v in zip(titles, vecs)} if vecs
                  else overlap_scores(question, titles))
        out.update({(slug, t): s for t, s in scores.items()})
    return out


async def prewarm() -> tuple[int, int]:
    """Embed every catalog course's lecture titles in ONE batched call and fill the cache, so the first turn
    never pays (or fails) the build. Returns (titles, courses). Raises on failure (callers treat it as
    non-fatal); deliberately never touches _failed_until (the lazy path stays a backup)."""
    if not (embedding_service.use_openai and embedding_service.client):
        raise RuntimeError("OpenAI embeddings unavailable")
    per_course = {}
    for course in catalog_service.all_courses():
        slug = course.get("slug")
        titles = lecture_titles(slug) if slug else []
        if titles:
            per_course[slug] = titles
    texts = [bare_title(t) for ts in per_course.values() for t in ts]
    if not texts:
        return 0, 0
    resp = await asyncio.wait_for(
        embedding_service.client.embeddings.create(model="text-embedding-3-small", input=texts),
        timeout=TITLE_PREWARM_TIMEOUT)
    vecs = [d.embedding for d in resp.data]
    i = 0
    for slug, ts in per_course.items():
        _cache[slug] = (ts, vecs[i:i + len(ts)])
        i += len(ts)
    return len(texts), len(per_course)
