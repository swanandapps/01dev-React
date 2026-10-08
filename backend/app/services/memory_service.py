"""
Persistent, session-spanning memory for the Hermes tutor.

This is the HindSight-style capability — "the tutor remembers the student across
sessions" — implemented deterministically in the governance layer rather than
left to the model to drive through a memory tool, so recall never depends on
the model choosing to call one.

Rides on the same document store as the audit log (Firestore in prod, in-memory
locally). Two collections:
  student_profile : one doc per student — running profile (topics, counts, seen)
  student_turns   : one doc per exchange — for multi-turn threading + recall

GDPR: erase() removes everything stored for a student (right-to-erasure).
"""
import os
import re
from datetime import datetime, timezone
from typing import Optional

from app.retrieval.understand import about_the_screen
from app.services import pii
from app.services.store import store

_PROFILE = "student_profile"
_TURNS = "student_turns"
_MAX_TOPICS = 8


# Replies that carry no topic of their own: "yes", "ok thanks", "got it".
_FILLER = re.compile(r"^\W*(yes|yeah|yep|yup|no|nope|ok|okay|sure|thanks|thank you|ok thanks|cool|nice|great|"
                     r"got it|hmm+|right|done|go on|continue|more)\W*$", re.IGNORECASE)


def topic_label(question: str, lecture_title: Optional[str] = None, cited: Optional[dict] = None) -> Optional[str]:
    """What the student was working on, for the memory's topic list — never their raw filler. In the player
    it's the lecture; on Ask, the lecture the answer cited; otherwise the question if it names something.
    None means there's nothing worth remembering."""
    if lecture_title:
        return lecture_title
    if cited and cited.get("lecture_title"):
        course = cited.get("course_title")
        return f"{cited['lecture_title']} ({course})" if course else cited["lecture_title"]
    q = (question or "").strip()
    if not q or _FILLER.match(q) or about_the_screen(q):
        return None
    return q[:80]


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


async def record_turn(student_id: str, course_slug: str, question: str, answer: str,
                      topic: Optional[str] = None) -> None:
    """Persist one exchange and fold it into the student's running profile. `topic` is what the exchange was
    about (see topic_label); without one it's worked out from the question, and filler adds no topic.

    PII is scrubbed here too — the storage choke point — so nothing personal is ever
    written to the store regardless of caller. Idempotent with the request-entry scrub.
    """
    ts = _now()
    question, q_pii = pii.scrub(question)
    answer, a_pii = pii.scrub(answer)
    await store.set(_TURNS, f"{student_id}__{ts}", {
        "student_id": student_id,
        "course_slug": course_slug,
        "question": question[:500],
        "answer": (answer or "")[:1500],
        "created_at": ts,
        "pii_redacted": sorted(set(q_pii + a_pii)),  # audit trail: kinds only, never values
    })

    prof = await store.get(_PROFILE, student_id) or {"first_seen": ts, "turn_count": 0, "topics": []}
    topics = list(prof.get("topics", []))
    label = topic or topic_label(question)
    if label and (not topics or topics[-1] != label):
        topics.append(label)
    await store.set(_PROFILE, student_id, {
        "student_id": student_id,
        "first_seen": prof.get("first_seen", ts),
        "last_seen": ts,
        "turn_count": int(prof.get("turn_count", 0)) + 1,
        "topics": topics[-_MAX_TOPICS:],
    })


async def recent_turns(student_id: str, course_slug: Optional[str] = None, limit: int = 4) -> list[dict]:
    """Last `limit` exchanges (chronological) — used to thread multi-turn context."""
    rows = await store.query(_TURNS, "student_id", student_id)
    if course_slug:
        rows = [r for r in rows if r.get("course_slug") == course_slug]
    rows.sort(key=lambda r: r.get("created_at", ""))
    return rows[-limit:]


async def get_profile(student_id: str) -> Optional[dict]:
    return await store.get(_PROFILE, student_id)


async def memory_context(student_id: str, course_slug: str) -> str:
    """A compact memory block injected into the system prompt so the tutor
    'remembers' the student. Empty string for a first-time learner."""
    prof = await store.get(_PROFILE, student_id)
    if not prof or not prof.get("turn_count"):
        return ""
    topics = prof.get("topics", [])
    lines = "\n".join(f"- {t}" for t in topics[-5:])
    return (
        "=== STUDENT MEMORY (returning learner) ===\n"
        f"You have helped this student across {prof['turn_count']} prior exchange(s). "
        "Build on what they've already explored. "
        "If they revisit something, acknowledge it. Recently they asked you about:\n" + lines
    )


async def search_history(student_id: str, query: str, top_k: int = 3) -> list[dict]:
    """Cross-session memory: full-text search THIS student's past exchanges for ones
    relevant to `query`. Selection across time — returns only the top_k slice, never
    the whole history. Scoped to student_id (isolation), keyword FTS (no embeddings /
    no OpenAI). No-op ([]) unless Postgres is the backend."""
    if not os.getenv("DATABASE_URL"):
        return []
    try:
        from app.services.db import get_pool
        pool = await get_pool()
        rows = await pool.fetch(
            """
            select data,
                   ts_rank(to_tsvector('english',
                       coalesce(data->>'question','') || ' ' || coalesce(data->>'answer','')),
                       plainto_tsquery('english', $2)) as rank
            from docs
            where collection = 'student_turns'
              and data->>'student_id' = $1
              and to_tsvector('english',
                    coalesce(data->>'question','') || ' ' || coalesce(data->>'answer',''))
                  @@ plainto_tsquery('english', $2)
            order by rank desc
            limit $3
            """,
            student_id, query, top_k,
        )
        out = []
        for r in rows:
            d = r["data"]
            out.append({
                "turn_id": f"{student_id}__{d.get('created_at','')}",
                "course_slug": d.get("course_slug"),
                "question": d.get("question", ""),
                "answer": d.get("answer", ""),
                "created_at": d.get("created_at", ""),
                "rank": round(float(r["rank"]), 4),
            })
        return out
    except Exception as e:  # noqa: BLE001 — search must never break a turn
        print(f"[memory] search_history failed: {e}")
        return []


async def recall(student_id: str) -> dict:
    """The 'what does the tutor remember about me' view (transparency)."""
    prof = await store.get(_PROFILE, student_id)
    turns = await recent_turns(student_id, limit=20)
    return {
        "student_id": student_id,
        "remembered": bool(prof),
        "profile": prof,
        "recent_turns": turns,
    }


async def erase(student_id: str) -> dict:
    """GDPR right-to-erasure — delete all stored memory for a student."""
    turns = await store.query(_TURNS, "student_id", student_id)
    for t in turns:
        await store.delete(_TURNS, f"{student_id}__{t.get('created_at')}")
    await store.delete(_PROFILE, student_id)
    return {"student_id": student_id, "erased_turns": len(turns), "profile_erased": True}
