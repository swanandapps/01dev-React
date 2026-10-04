import shutil
import subprocess
from pathlib import Path

import pytest

from app.services import catalog_service

REPO = Path(__file__).resolve().parents[2]


def test_catalog_has_every_course_with_ids_and_slugs():
    courses = catalog_service.all_courses()
    assert len(courses) == 10
    assert all(isinstance(c["id"], int) and c["url"] == f"/course/{c['id']}" for c in courses)


def test_lookup_by_numeric_id_and_by_transcript_slug_agree():
    lib = catalog_service.get(2)
    assert lib["title"] == "Build a Custom Library"
    assert catalog_service.by_slug("custom-library") == lib
    assert any(m["title"] == "NPM Package Development" for m in lib["modules"])


def test_unknown_ids_return_none():
    assert catalog_service.get(999) is None
    assert catalog_service.by_slug("nope") is None


@pytest.mark.skipif(shutil.which("node") is None, reason="node not installed")
def test_catalog_json_matches_tracks_ts():
    result = subprocess.run(
        ["node", "frontend/scripts/export-catalog.mjs", "--check"],
        cwd=REPO, capture_output=True, text=True,
    )
    assert result.returncode == 0, result.stderr
