"""The full course catalog, including courses with no transcripts yet.

Generated from frontend/src/data/tracks.ts (the source of truth) by
frontend/scripts/export-catalog.mjs; tests/test_catalog.py fails if this copy
drifts. Bridges the two id spaces: numeric `id` (enrollments, course pages) and
`slug` (transcript chunks' course_id).
"""
import json
from functools import lru_cache
from pathlib import Path
from typing import Optional

_PATH = Path(__file__).resolve().parents[1] / "data" / "catalog.json"


@lru_cache(maxsize=1)
def all_courses() -> list[dict]:
    return json.loads(_PATH.read_text())


def get(course_id: int) -> Optional[dict]:
    return next((c for c in all_courses() if c["id"] == course_id), None)


def by_slug(slug: str) -> Optional[dict]:
    return next((c for c in all_courses() if c["slug"] == slug), None)
