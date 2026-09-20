"""
EU AI Act audit log for the tutoring agent.

Every agent interaction is recorded with the metadata a regulator (or an
incident review) needs: who, what, when, which model/provider answered, and the
SHA of the SOUL.md identity that was active. Rides on the existing document
store (Firestore in prod, in-memory locally) — same pattern as the rest of the app.
"""

import hashlib
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from app.services.store import store

_SOUL_PATH = Path(os.path.expanduser("~/.hermes/SOUL.md"))
_AUDIT_COLLECTION = "audit_log"


def soul_hash() -> str:
    """Short SHA-256 of the active SOUL.md — pins which agent identity answered."""
    try:
        return hashlib.sha256(_SOUL_PATH.read_bytes()).hexdigest()[:12]
    except OSError:
        return "unknown"


async def log_event(
    student_id: str,
    course_slug: str,
    question: str,
    model: str,
    provider: str,
    risk_level: str = "low",
    outcome: Optional[str] = None,
) -> str:
    """Write one audit record and return its id."""
    ts = datetime.now(timezone.utc).isoformat()
    doc_id = f"{student_id}__{ts}"
    await store.set(
        _AUDIT_COLLECTION,
        doc_id,
        {
            "student_id": student_id,
            "course_slug": course_slug,
            "action": "tutor_chat",
            "question": question[:500],
            "model": model,
            "provider": provider,
            "soul_md_hash": soul_hash(),
            "risk_level": risk_level,
            "outcome": outcome,
            "created_at": ts,
        },
    )
    return doc_id


async def recent(limit: int = 20) -> list[dict]:
    """Most recent audit records (for an admin/compliance view)."""
    rows = await store.list_all(_AUDIT_COLLECTION)
    rows.sort(key=lambda r: r.get("created_at", ""), reverse=True)
    return rows[:limit]
