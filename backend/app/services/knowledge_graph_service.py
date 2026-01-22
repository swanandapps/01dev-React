"""
Feature 6 — Knowledge graph.

A lightweight per-lecture concept graph: concept nodes (name + description) and
typed relationships (prerequisite_of / part_of / related_to). It's not shown to
students directly; it powers smarter RAG retrieval and prerequisite-aware
adaptive practice.

To keep it aligned with the rest of the system, the graph is built over the
SAME concept tags the question bank uses (so per-concept performance and
prerequisite gating line up), with descriptions and relationships grounded in
the transcript via GPT.

Two collections (the "two tables" from the spec):
  - concepts:              {lecture_id, name, description, course_id}
  - concept_relationships: {lecture_id, source, target, type}
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

SYSTEM_PROMPT = """You map the concept structure of a single lecture for the 0.1% Dev platform.
You are given the lecture transcript and the list of concept tags used in its quiz.
For EACH given concept, write a one-sentence description grounded in the transcript,
and identify relationships BETWEEN the given concepts.

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


def _concept_id(lecture_id: str, name: str) -> str:
    return f"{lecture_id}::{name}"


async def get_graph(lecture_id: str) -> dict:
    concepts = await store.query(CONCEPTS, "lecture_id", lecture_id)
    rels = await store.query(RELATIONSHIPS, "lecture_id", lecture_id)
    return {"lecture_id": lecture_id, "concepts": concepts, "relationships": rels}


async def has_graph(lecture_id: str) -> bool:
    return len(await store.query(CONCEPTS, "lecture_id", lecture_id)) > 0


async def ensure_built(lecture_id: str) -> dict:
    if await has_graph(lecture_id):
        return {"status": "ready"}
    if lecture_id not in _in_progress:
        _in_progress.add(lecture_id)
        asyncio.create_task(_build(lecture_id))
    return {"status": "generating"}


async def get_prerequisites(lecture_id: str, concept: str) -> List[str]:
    """Concepts that are a prerequisite_of `concept` in this lecture."""
    rels = await store.query(RELATIONSHIPS, "lecture_id", lecture_id)
    return [r["source"] for r in rels if r.get("type") == "prerequisite_of" and r.get("target") == concept]


async def _build(lecture_id: str) -> None:
    try:
        meta = vector_store.get_lecture_meta(lecture_id)
        transcript = vector_store.get_lecture_transcript(lecture_id)
        if not meta or not transcript:
            return

        # Need the question concept tags to align the graph with tracked performance.
        qdoc = await store.get("questions", lecture_id)
        if not qdoc:
            await question_service.ensure_generated(lecture_id)
            # Retry shortly once questions exist.
            for _ in range(20):
                await asyncio.sleep(2)
                qdoc = await store.get("questions", lecture_id)
                if qdoc:
                    break
        if not qdoc:
            return

        concept_tags = sorted({q["concept"] for q in qdoc["questions"]})

        data = await llm.generate_json(
            SYSTEM_PROMPT,
            f"Lecture: {meta['lecture_title']} (course: {meta['course_title']})\n\n"
            f"Concept tags: {', '.join(concept_tags)}\n\n"
            f"Transcript:\n{transcript}",
            max_tokens=1200,
        )
        if not data:
            return

        valid = set(concept_tags)
        descriptions = {c.get("name"): c.get("description", "") for c in data.get("concepts", [])}

        for name in concept_tags:
            await store.set(
                CONCEPTS,
                _concept_id(lecture_id, name),
                {
                    "lecture_id": lecture_id,
                    "course_id": meta["course_id"],
                    "name": name,
                    "description": descriptions.get(name, ""),
                },
            )

        for i, r in enumerate(data.get("relationships", [])):
            src, tgt, typ = r.get("source"), r.get("target"), r.get("type")
            if src in valid and tgt in valid and src != tgt and typ in REL_TYPES:
                await store.set(
                    RELATIONSHIPS,
                    f"{lecture_id}::rel{i}",
                    {"lecture_id": lecture_id, "source": src, "target": tgt, "type": typ},
                )
    except Exception as e:  # noqa: BLE001
        print(f"knowledge_graph: build failed for {lecture_id}: {e}")
    finally:
        _in_progress.discard(lecture_id)
