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

Fix-round-1 additions (defend against things found against the LIVE pool):

- knowledge_graph_service writes {course_id, name, description} with no
  `embedding` field at all — that's every node in production today. A pool
  node found without a usable embedding is embedded from its `name` and
  persisted back onto the SAME document (via `store.list_all_with_ids`, not
  a reconstructed id — the id scheme knowledge_graph_service uses,
  `f"{course_id}::{name}"` with the RAW name, differs from the
  `scope::slug` scheme this module uses for nodes it creates itself).
- `slugify` spells out distinguishing symbols (C++ / C# / C must not all
  become "c") and keeps unicode letters/digits instead of deleting them.
- A candidate that slugifies to nothing (emoji-only, punctuation-only) falls
  back to a stable hash of the original text rather than returning "" —
  "" would collide every such candidate onto one concept_performance row.
- A dimension mismatch between a stored vector and the candidate's is
  treated as "no usable embedding" (re-embed), never compared truncated —
  reachable because embeddings.py embeds at 256 dims locally vs 1536 via
  OpenAI.

Fix-round-2 additions (a bound that itself forked permanent duplicates, plus
robustness the first fix-round didn't cover):

- CRITICAL: bounding the pool-vs-candidate comparison (so one student's
  request can't pay for embedding an unbounded backlog) is only safe to do
  in front of a MERGE, never in front of a CREATE. Merging is recoverable;
  creating a node is not. So the bound now gates only the fast path: if a
  match is found while comparing the first MAX_BACKFILL_PER_RESOLVE-or-fewer
  cold nodes, return it immediately. If nothing matches within that budget,
  the *remaining* cold nodes are backfilled and compared too — unbounded —
  before a create is allowed to happen. A prior version bounded the whole
  comparison, so a 9-node cold pool with the true match at position 9 and a
  bound of 5 forked a permanent duplicate: the fork then wins the exact-slug
  branch forever, so that student's course mastery never moved again. DO NOT
  re-bound the path in front of create() — that reintroduces exactly this.
- A failed backfill embed (rate limit, outage) is caught per-node and no
  longer propagates out of resolve() — pre-round-1, a vectorless node was
  merely unreachable via the embedding branch, never a crash, and that must
  still hold. If a failure means the pool couldn't be fully compared before
  a create, the create still happens (a student's request must never hang
  or 500 on this), but the resolution log records
  `comparison_incomplete: True` and how many nodes were unreadable, so a
  possible fork is findable later instead of silent.
- The exact-slug branch deliberately does NOT trigger backfill. Repeat
  candidates for the same concept hit that branch and return immediately;
  making the cheapest, most common path also pay for pool migration would
  be exactly backwards. Coldness only matters — and only gets paid for — at
  the moment a create is about to happen, per the point above.
- `best_name` is now checked for truthiness, not `is not None` — a pool
  node with `name: ""` and a usable embedding used to be returned as the
  resolved name, and "" is exactly the value that poisons `_perf_id`.
- Symbol substitution (+/# -> plus/sharp) now only applies when the
  original string has at least one alphanumeric character. Without that
  guard, pure junk like "#" or "@#$%^&*" slugified to a plausible-looking
  word ("sharp") instead of falling back to the hash path, and could then
  merge with an unrelated real concept of that name.
- `resolve(None)` and `resolve("")`/whitespace-only no longer reach
  `embed()` at all — None used to crash before hitting the API, and a
  blank string is rejected BY the API. Both now go straight to the
  fallback-slug path.
- A persisted embedding's `embedding_model` tag is now compared too, not
  just its length — dimension alone can't tell two same-length vectors
  from different provenances apart (embeddings.py's local fallback uses
  Python's `hash()`, per-process randomised). A missing tag (data written
  before this field existed, including this module's own tests) is
  trusted rather than treated as stale; only an explicit mismatch forces
  re-embed.
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
# all become "c"). Only applied when the original has real alphanumeric
# content — see slugify().
_SYMBOL_WORDS = {
    "+": "plus",
    "#": "sharp",
}

# Bound on how many cold (unbackfilled/stale) pool nodes are compared on the
# FAST path of a single resolve() call — i.e. before we know whether we'll
# need to create. This bound must NEVER gate the comparison that happens
# immediately before a create decision: see the fix-round-2 note above. The
# live pool had 9 concept nodes and NONE carried an embedding, so a cold
# pool needs this to be more than a token amount — 5 clears most of a pool
# that size for free (no create pending) and the rest is paid for, in full,
# by whichever request would otherwise have forked a duplicate.
MAX_BACKFILL_PER_RESOLVE = 5


def slugify(name: str) -> str:
    """'React.memo' -> 'react-memo'. Lowercase; symbols that distinguish
    otherwise-identical names (C++ / C# / C) are spelled out rather than
    stripped, but only when the string has real alphanumeric content —
    otherwise pure junk like "#" would slug to a plausible word ("sharp")
    instead of falling through to the hash fallback where it belongs.
    Unicode letters/digits are kept, not deleted, so non-Latin names slug
    to themselves instead of to nothing."""
    s = str(name or "")
    if any(ch.isalnum() for ch in s):
        for sym, word in _SYMBOL_WORDS.items():
            s = s.replace(sym, f"-{word}-")
    s = unicodedata.normalize("NFKC", s).lower()
    out = [ch if ch.isalnum() else "-" for ch in s]
    s = re.sub(r"-+", "-", "".join(out))
    return s.strip("-")


def _fallback_slug(original) -> str:
    """Deterministic slug for a name that slugifies to nothing (emoji-only,
    punctuation-only, empty, or None). Uses hashlib — NOT Python's built-in
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
    # file). Used both as descriptive metadata and, since round 2, as part
    # of the staleness check alongside vector length.
    return "text-embedding-3-small" if getattr(embedding_service, "use_openai", False) else "local-hash-256"


def _node_needs_backfill(node: dict, candidate_dim: int) -> bool:
    vec = node.get("embedding")
    if not vec or len(vec) != candidate_dim:
        return True
    tag = node.get("embedding_model")
    # A missing tag is legacy/test data written before this field existed —
    # trusted rather than treated as stale. Only an explicit mismatch (the
    # service's current choice has actually changed) forces re-embed.
    return tag is not None and tag != _current_embedding_model()


async def _try_backfill(doc_id: str, node: dict):
    """Embed a pool node's name and persist the vector back onto the SAME
    document, preserving every existing field. Returns the fresh vector, or
    None if the embed or the write failed — caught here so one bad node
    (rate limit, outage, whatever) can't crash somebody else's resolve()
    call. Pre-round-1, a vectorless node was merely unreachable via the
    embedding branch, never a crash; that property must survive a failed
    backfill attempt too."""
    try:
        vec = await embedding_service.embed(node.get("name", ""))
        await store.set(CONCEPTS, doc_id, {
            **node,
            "embedding": vec,
            "embedding_dim": len(vec),
            "embedding_model": _current_embedding_model(),
        })
    except Exception:
        return None
    await _log_backfill(node.get("name", ""), doc_id)
    return vec


async def _log(candidate, resolved_to: str, method: str, score, **extra) -> None:
    ts = datetime.now(timezone.utc).isoformat()
    entry = {
        "candidate": candidate,
        "resolved_to": resolved_to,
        "method": method,           # slug | embedding | created | backfill
        "score": round(score, 3) if score is not None else None,
        "at": ts,
    }
    entry.update(extra)
    await store.set(RESOLUTIONS, f"{slugify(str(candidate or '')) or 'x'}__{ts}", entry)


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


async def resolve(candidate, course_id: str | None = None) -> str:
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

    # 1. exact slug match — free, no API call, and deliberately does no
    # backfill: this is the cheapest, most common path (repeat candidates
    # for a concept already resolved once) and must stay that way.
    for _doc_id, c in known:
        if slugify(c.get("name", "")) == slug:
            await _log(candidate, c["name"], "slug", 1.0, used_fallback_slug=used_fallback_slug)
            return c["name"]

    # Nothing to embed for None / blank-only input — None crashes embed()
    # before it even reaches the API, and a whitespace-only string is
    # rejected BY the API. A punctuation/emoji-only candidate (non-blank,
    # e.g. "!!!") still has real characters and goes through normally; only
    # truly empty input skips the embedding branch entirely.
    candidate_is_embeddable = candidate is not None and str(candidate).strip() != ""

    candidate_vec = None
    candidate_dim = None
    best_name, best_score = None, 0.0
    did_compare = False
    unreadable = 0

    if candidate_is_embeddable:
        did_compare = True
        candidate_vec = await embedding_service.embed(candidate)
        candidate_dim = len(candidate_vec)

        # 2. embedding compare against cached concept embeddings. Cold pool
        # nodes are backfilled in place, bounded — but ONLY as a fast path:
        # if that bounded pass already finds a merge, return it now. If it
        # doesn't, the bound must not be allowed to gate the decision to
        # create — see the fix-round-2 note at the top of this file.
        backfilled = 0
        pending = []  # cold nodes not yet attempted because the bound was hit
        for doc_id, c in known:
            vec = c.get("embedding")
            if _node_needs_backfill(c, candidate_dim):
                if backfilled >= MAX_BACKFILL_PER_RESOLVE:
                    pending.append((doc_id, c))
                    continue
                backfilled += 1  # counts the ATTEMPT, success or not — a
                                 # flaky node can't let a hostile candidate
                                 # spend the whole budget retrying it
                fresh = await _try_backfill(doc_id, c)
                if fresh is None:
                    unreadable += 1
                    continue
                vec = fresh

            score = _cosine(candidate_vec, vec)
            if score > best_score:
                best_name, best_score = c.get("name"), score

        if best_name and best_score >= SIMILARITY_THRESHOLD:
            await _log(candidate, best_name, "embedding", best_score, used_fallback_slug=used_fallback_slug)
            return best_name

        # No merge on the bounded pass, but the pool wasn't fully compared.
        # Creating now would risk forking a permanent duplicate over a real
        # match we simply hadn't reached the budget for — exactly what
        # forked one in production. Finish the remainder, unbounded,
        # because creating a node cannot be undone the way returning a
        # merge can.
        for doc_id, c in pending:
            fresh = await _try_backfill(doc_id, c)
            if fresh is None:
                unreadable += 1
                continue
            score = _cosine(candidate_vec, fresh)
            if score > best_score:
                best_name, best_score = c.get("name"), score

        if best_name and best_score >= SIMILARITY_THRESHOLD:
            await _log(candidate, best_name, "embedding", best_score, used_fallback_slug=used_fallback_slug)
            return best_name

    # 3. create a new node — the graph grows to fit the student
    scope = course_id or _SELF_STUDY_SCOPE
    doc = {
        "course_id": course_id,     # None for self-study, deliberately not a string
        "name": slug,
        "description": "",
        "created_by": "student_content",
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    if candidate_vec is not None:
        doc.update({
            "embedding": candidate_vec,      # cached so the pool is never re-embedded
            "embedding_dim": candidate_dim,
            "embedding_model": _current_embedding_model(),
        })
    await store.set(CONCEPTS, f"{scope}::{slug}", doc)

    extra = {"used_fallback_slug": used_fallback_slug}
    if unreadable:
        # The pool comparison could not be fully completed before this
        # create — some nodes' backfill attempts failed. A possible fork
        # from this must be findable later, since we chose to let the
        # student's request through rather than block or crash it.
        extra["comparison_incomplete"] = True
        extra["unreadable_pool_nodes"] = unreadable
    await _log(candidate, slug, "created", best_score if did_compare else None, **extra)
    return slug
