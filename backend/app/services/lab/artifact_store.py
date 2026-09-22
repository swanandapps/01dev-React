"""
The student's library of generated artifacts.

This module IS the store — it does not decide when writes happen. The caller
(the route that runs the fan-out graph, see artifacts_graph.py) awaits `save`
for each artifact once the fan-out joins, before handing off to the
interactive quiz tail.
"""
import uuid
from datetime import datetime, timezone

from app.services.store import store

COLLECTION = "lab_artifacts"


async def save(student_id: str, doc_id: str, doc_title: str,
               artifact_type: str, content) -> str:
    """Persist one artifact. Anonymous sessions save nothing rather than
    creating rows keyed on an empty student id."""
    if not student_id:
        return ""
    artifact_id = uuid.uuid4().hex[:12]
    await store.set(COLLECTION, artifact_id, {
        "artifact_id": artifact_id,
        "student_id": student_id,
        "doc_id": doc_id,
        "doc_title": doc_title,
        "artifact_type": artifact_type,
        "content": content,
        "created_at": datetime.now(timezone.utc).isoformat(),
    })
    return artifact_id


async def get(artifact_id: str) -> dict | None:
    return await store.get(COLLECTION, artifact_id)


async def library(student_id: str, limit: int = 50) -> list[dict]:
    rows = await store.query(COLLECTION, "student_id", student_id)
    rows.sort(key=lambda r: (r.get("created_at", ""), r.get("artifact_id", "")), reverse=True)
    return rows[:limit]
