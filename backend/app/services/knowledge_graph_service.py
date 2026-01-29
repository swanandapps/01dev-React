"""
Feature 6 — Knowledge graph (per course).

A lightweight per-course concept graph: concept nodes (name + description) and
typed relationships (prerequisite_of / part_of / related_to). It's not shown to
students directly; it powers smarter RAG retrieval and prerequisite-aware
adaptive practice.

Because it spans the whole course, the graph can now express CROSS-LECTURE
prerequisites (e.g. a concept from an early lecture is a prerequisite of a
concept from a later one). It's built over the SAME concept tags the question
bank uses so per-concept performance and prerequisite gating line up.

Two collections:
  - concepts:              {course_id, name, description}
  - concept_relationships: {course_id, source, target, type}
"""

import asyncio
from typing import List

from app.services.llm import llm
from app.services.store import store
from app.services import question_service
from app.services.vector_store import vector_store

CONCEPTS = "concepts"
RELATIONSHIPS = "concept_relationships"
REL_TYPES = {"prerequisite_of", "part_of", "related_to"}

_in_progress: set[str] = set()

SYSTEM_PROMPT = """You map the concept structure of a COURSE for the 0.1% Dev platform.
You are given the course's lecture transcripts (sections marked [Lecture: ...]) and the
list of concept tags used in its quiz. For EACH given concept, write a one-sentence
description grounded in the transcripts, and identify relationships BETWEEN the concepts —
including cross-lecture prerequisites.

Return a JSON object with EXACTLY this shape:
{
  "concepts": [ {"name": "<one of the given concepts>", "description": "one sentence"} ],
  "relationships": [
    {"source": "<concept>", "target": "<concept>", "type": "prerequisite_of"}
  ]
}
Relationship types (use only these):
  - "prerequisite_of": source must be understood before target
  - "part_of": source is a sub-part of target
  - "related_to": loosely related
Only use the concept names provided. Keep relationships meaningful, not exhaustive."""


def _concept_id(course_id: str, name: str) -> str:
    return f"{course_id}::{name}"


async def get_graph(course_id: str) -> dict:
    concepts = await store.query(CONCEPTS, "course_id", course_id)
    rels = await store.query(RELATIONSHIPS, "course_id", course_id)
    return {"course_id": course_id, "concepts": concepts, "relationships": rels}


async def has_graph(course_id: str) -> bool:
    return len(await store.query(CONCEPTS, "course_id", course_id)) > 0


async def ensure_built(course_id: str) -> dict:
    if await has_graph(course_id):
        return {"status": "ready"}
    if course_id not in _in_progress:
        _in_progress.add(course_id)
        asyncio.create_task(_build(course_id))
    return {"status": "generating"}


async def get_prerequisites(course_id: str, concept: str) -> List[str]:
    """Concepts that are a prerequisite_of `concept` in this course."""
    rels = await store.query(RELATIONSHIPS, "course_id", course_id)
    return [r["source"] for r in rels if r.get("type") == "prerequisite_of" and r.get("target") == concept]


async def _build(course_id: str) -> None:
    try:
        meta = vector_store.get_course_meta(course_id)
        transcript = vector_store.get_course_transcript(course_id)
        if not meta or not transcript:
            return

        # Need the question concept tags to align the graph with tracked performance.
        qdoc = await store.get("questions", course_id)
        if not qdoc:
            await question_service.ensure_generated(course_id)
            for _ in range(25):
                await asyncio.sleep(2)
                qdoc = await store.get("questions", course_id)
                if qdoc:
                    break
        if not qdoc:
            return

        concept_tags = sorted({q["concept"] for q in qdoc["questions"]})

        data = await llm.generate_json(
            SYSTEM_PROMPT,
            f"Course: {meta['course_title']}\n\n"
            f"Concept tags: {', '.join(concept_tags)}\n\n"
            f"Transcripts:\n{transcript}",
            max_tokens=1400,
        )
        if not data:
            return

        valid = set(concept_tags)
        descriptions = {c.get("name"): c.get("description", "") for c in data.get("concepts", [])}

        for name in concept_tags:
            await store.set(
                CONCEPTS,
                _concept_id(course_id, name),
                {"course_id": course_id, "name": name, "description": descriptions.get(name, "")},
            )

        for i, r in enumerate(data.get("relationships", [])):
            src, tgt, typ = r.get("source"), r.get("target"), r.get("type")
            if src in valid and tgt in valid and src != tgt and typ in REL_TYPES:
                await store.set(
                    RELATIONSHIPS,
                    f"{course_id}::rel{i}",
                    {"course_id": course_id, "source": src, "target": tgt, "type": typ},
                )
    except Exception as e:  # noqa: BLE001
        print(f"knowledge_graph: build failed for {course_id}: {e}")
    finally:
        _in_progress.discard(course_id)
