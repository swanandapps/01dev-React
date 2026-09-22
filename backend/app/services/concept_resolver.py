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
"""
import re
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


def slugify(name: str) -> str:
    """'React.memo' -> 'react-memo'. Lowercase, non-alphanumerics to hyphens."""
    s = re.sub(r"[^a-z0-9]+", "-", str(name or "").lower())
    return s.strip("-")


def _cosine(a: list[float], b: list[float]) -> float:
    dot = sum(x * y for x, y in zip(a, b))
    na = sum(x * x for x in a) ** 0.5
    nb = sum(y * y for y in b) ** 0.5
    if na == 0 or nb == 0:
        return 0.0
    return dot / (na * nb)


async def _log(candidate: str, resolved_to: str, method: str, score: float) -> None:
    ts = datetime.now(timezone.utc).isoformat()
    await store.set(RESOLUTIONS, f"{slugify(candidate)}__{ts}", {
        "candidate": candidate,
        "resolved_to": resolved_to,
        "method": method,           # slug | embedding | created
        "score": round(score, 3),
        "at": ts,
    })


async def resolve(candidate: str, course_id: str | None = None) -> str:
    """Canonical concept name to key concept_performance on.

    `course_id` is the INGEST SOURCE's course, not a filter — the search pool is
    always every known concept, because a self-study concept resolving onto a
    course concept is the whole point. It only affects a newly created node: a
    concept first seen in a course lecture attaches to that course; one from an
    uploaded PDF attaches to nothing.
    """
    slug = slugify(candidate)
    if not slug:
        return ""

    known = await store.list_all(CONCEPTS)

    # 1. exact slug match — free, no API call
    for c in known:
        if slugify(c.get("name", "")) == slug:
            await _log(candidate, c["name"], "slug", 1.0)
            return c["name"]

    # 2. embedding compare against cached concept embeddings
    candidate_vec = await embedding_service.embed(candidate)
    best_name, best_score = None, 0.0
    for c in known:
        vec = c.get("embedding")
        if not vec:
            continue
        score = _cosine(candidate_vec, vec)
        if score > best_score:
            best_name, best_score = c.get("name"), score

    if best_name is not None and best_score >= SIMILARITY_THRESHOLD:
        await _log(candidate, best_name, "embedding", best_score)
        return best_name

    # 3. create a new node — the graph grows to fit the student
    scope = course_id or _SELF_STUDY_SCOPE
    await store.set(CONCEPTS, f"{scope}::{slug}", {
        "course_id": course_id,     # None for self-study, deliberately not a string
        "name": slug,
        "description": "",
        "created_by": "student_content",
        "embedding": candidate_vec,  # cached so the pool is never re-embedded
        "created_at": datetime.now(timezone.utc).isoformat(),
    })
    await _log(candidate, slug, "created", best_score)
    return slug
