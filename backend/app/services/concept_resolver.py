"""
One concept space, resolved rather than siloed.

Every concept write goes through here — the graded course quiz
(adaptive_service), Hermes's chat observations (skill_graph_service
.record_observation), and Lab quizzes built from a student's own material.

The product requirement this serves: a student studying closures from their own
notes should move the *existing* `closures` weights, while a student studying
Kubernetes — which no course covers — should get a new concept node rather than
having their work discarded or forced into our vocabulary.

Resolution order: exact slug match (free) → embedding cosine >= 0.64 → create.

On the threshold: 0.64 is the midpoint of an empty band measured across 31
pairs. True matches sat at 0.709-0.755 (`React.memo`/`react-memo` = 0.755,
`useCallback hook`/`use-callback` = 0.709); false matches capped at 0.578
(`Event Delegation`/`event-loop`). Short concept NAMES do not score like
sentences — unrelated short strings share a noise floor around 0.33-0.38, and a
0.9 threshold merges nothing at all. Expect this to need RAISING as the concept
pool grows: with 9 concepts there are 9 chances to draw a spurious high score,
with 500 there are 500.

Never rewrites existing rows. `adaptive_service._perf_id` is
f"{user_id}__{concept}", so changing a concept's spelling changes its doc id
and would orphan the row.

Fix-round-1 additions (all defend against things found against the LIVE pool):

- knowledge_graph_service writes {course_id, name, description} with no
  `embedding` field at all — that's every node in production today. The
  embedding branch used to silently skip any node without one, making it
  reachable only by exact slug match. Now a pool node found without a usable
  embedding is embedded from its `name` and persisted back onto the SAME
  document (via `store.list_all_with_ids`, not a reconstructed id — the id
  scheme knowledge_graph_service uses, `f"{course_id}::{name}"` with the RAW
  name, differs from the `scope::slug` scheme this module uses for nodes it
  creates itself). Bounded per call — see MAX_BACKFILL_PER_RESOLVE.
- `slugify` used to strip anything non-ASCII-alphanumeric, so `C++`, `C#` and
  `C` all collapsed to `"c"` and a student's C# notes would silently move
  their C++ mastery. Distinguishing symbols are spelled out before stripping,
  and unicode letters/digits are kept (not deleted), so non-Latin names slug
  to themselves rather than to nothing.
- A candidate that STILL slugifies to nothing (emoji-only, punctuation-only)
  no longer returns `""` — a blank canonical name would collide every such
  candidate onto the same `concept_performance` row
  (`f"{user_id}__{concept}"`). It falls back to a stable hash of the original
  text, logged as such.
- `_cosine` used to zip mismatched-length vectors and silently truncate,
  which is reachable in practice: `embeddings.py` embeds at 256 dims locally
  (no API key) and 1536 via OpenAI, and a node's stored vector doesn't change
  dimension just because the service that will read it next does. A
  dimension mismatch is now treated the same as "no usable embedding" — the
  node gets re-embedded (and its stored dimension/model updated), never
  compared truncated.
"""
import hashlib
import re
import unicodedata
from datetime import datetime, timezone

from app.services.embeddings import embedding_service
from app.services.store import store

CONCEPTS = "concepts"
RESOLUTIONS = "concept_resolutions"
SIMILARITY_THRESHOLD = 0.64

# Doc-id scope for a concept that belongs to no course. The `course_id` FIELD
# stays None — a sentinel string there would surface in get_concept_confidence
# and read to the model as a real course name.
_SELF_STUDY_SCOPE = "self-study"

# Symbols that distinguish otherwise-identical short names and must survive
# slugify rather than being stripped to nothing (`C++`, `C#`, `C` must not
# all become "c"). Order matters only in that longer tokens should be mapped
# before any substrings of them would be.
_SYMBOL_WORDS = {
    "+": "plus",
    "#": "sharp",
}

# Bound on how many pool nodes without a usable embedding get backfilled
# during a single resolve() call. The live pool had 9 concept nodes and NONE
# carried an embedding at the time this was found, so a cold pool needs this
# to be more than a token amount — 5 clears most or all of a pool that size
# in one call and the rest within two or three more, without making one
# student's request pay for embedding an unbounded backlog synchronously.
MAX_BACKFILL_PER_RESOLVE = 5


def slugify(name: str) -> str:
    """'React.memo' -> 'react-memo'. Lowercase; symbols that distinguish
    otherwise-identical names (C++ / C# / C) are spelled out rather than
    stripped; unicode letters/digits are kept, not deleted, so non-Latin
    names slug to themselves instead of to nothing."""
    s = str(name or "")
    for sym, word in _SYMBOL_WORDS.items():
        s = s.replace(sym, f"-{word}-")
    s = unicodedata.normalize("NFKC", s).lower()
    out = [ch if ch.isalnum() else "-" for ch in s]
    s = re.sub(r"-+", "-", "".join(out))
    return s.strip("-")


def _fallback_slug(original: str) -> str:
    """Deterministic slug for a name that slugifies to nothing (emoji-only,
    punctuation-only, or empty). Uses hashlib — NOT Python's built-in
    hash(), which is randomised per process for strings and would mint a
    new node for the same odd name on every restart — so the fallback is
    stable across calls and processes."""
    digest = hashlib.sha256(str(original or "").encode("utf-8")).hexdigest()[:10]
    return f"concept-{digest}"


def _cosine(a: list[float], b: list[float]) -> float:
    dot = sum(x * y for x, y in zip(a, b))
    na = sum(x * x for x in a) ** 0.5
    nb = sum(y * y for y in b) ** 0.5
    if na == 0 or nb == 0:
        return 0.0
    return dot / (na * nb)


def _current_embedding_model() -> str:
    # Read-only mirror of embeddings.py's own choice (never modify that
    # file). Purely descriptive metadata; the actual reuse/backfill decision
    # below is driven by comparing vector LENGTHS, not this string, so a
    # stale or missing value here can't cause a wrong comparison.
    return "text-embedding-3-small" if getattr(embedding_service, "use_openai", False) else "local-hash-256"


async def _log(candidate: str, resolved_to: str, method: str, score, **extra) -> None:
    ts = datetime.now(timezone.utc).isoformat()
    entry = {
        "candidate": candidate,
        "resolved_to": resolved_to,
        "method": method,           # slug | embedding | created | backfill
        "score": round(score, 3) if score is not None else None,
        "at": ts,
    }
    entry.update(extra)
    await store.set(RESOLUTIONS, f"{slugify(candidate) or 'x'}__{ts}", entry)


async def _log_backfill(node_name: str, doc_id: str) -> None:
    """Audit trail for a pool node embedded on read-miss — distinct from a
    resolution decision, but still logged, per the requirement that a
    decision that isn't logged is a merge nobody can contest. This isn't a
    merge decision about a candidate; it's infrastructure self-healing that a
    later tuning pass should be able to see happened."""
    ts = datetime.now(timezone.utc).isoformat()
    await store.set(RESOLUTIONS, f"backfill__{slugify(node_name) or 'x'}__{ts}", {
        "candidate": node_name,
        "resolved_to": node_name,
        "method": "backfill",
        "score": None,
        "doc_id": doc_id,
        "at": ts,
    })


async def resolve(candidate: str, course_id: str | None = None) -> str:
    """Canonical concept name to key concept_performance on. Never returns "".

    `course_id` is the INGEST SOURCE's course, not a filter — the search pool is
    always every known concept, because a self-study concept resolving onto a
    course concept is the whole point. It only affects a newly created node: a
    concept first seen in a course lecture attaches to that course; one from an
    uploaded PDF attaches to nothing.
    """
    slug = slugify(candidate)
    used_fallback_slug = slug == ""
    if used_fallback_slug:
        slug = _fallback_slug(candidate)

    known = await store.list_all_with_ids(CONCEPTS)

    # 1. exact slug match — free, no API call
    for _doc_id, c in known:
        if slugify(c.get("name", "")) == slug:
            await _log(candidate, c["name"], "slug", 1.0, used_fallback_slug=used_fallback_slug)
            return c["name"]

    # 2. embedding compare against cached concept embeddings. Pool nodes with
    # no embedding, or one of a stale dimension, are backfilled in place
    # (bounded) rather than skipped or truncate-compared.
    candidate_vec = await embedding_service.embed(candidate)
    candidate_dim = len(candidate_vec)
    best_name, best_score = None, 0.0
    backfilled = 0
    for doc_id, c in known:
        vec = c.get("embedding")
        if not vec or len(vec) != candidate_dim:
            if backfilled >= MAX_BACKFILL_PER_RESOLVE:
                continue  # leave it for a later resolve() call; don't block this request
            vec = await embedding_service.embed(c.get("name", ""))
            await store.set(CONCEPTS, doc_id, {
                **c,
                "embedding": vec,
                "embedding_dim": len(vec),
                "embedding_model": _current_embedding_model(),
            })
            await _log_backfill(c.get("name", ""), doc_id)
            backfilled += 1

        score = _cosine(candidate_vec, vec)
        if score > best_score:
            best_name, best_score = c.get("name"), score

    if best_name is not None and best_score >= SIMILARITY_THRESHOLD:
        await _log(candidate, best_name, "embedding", best_score, used_fallback_slug=used_fallback_slug)
        return best_name

    # 3. create a new node — the graph grows to fit the student
    scope = course_id or _SELF_STUDY_SCOPE
    await store.set(CONCEPTS, f"{scope}::{slug}", {
        "course_id": course_id,     # None for self-study, deliberately not a string
        "name": slug,
        "description": "",
        "created_by": "student_content",
        "embedding": candidate_vec,  # cached so the pool is never re-embedded
        "embedding_dim": candidate_dim,
        "embedding_model": _current_embedding_model(),
        "created_at": datetime.now(timezone.utc).isoformat(),
    })
    await _log(candidate, slug, "created", best_score, used_fallback_slug=used_fallback_slug)
    return slug
