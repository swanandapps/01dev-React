import json
from collections import Counter
from pathlib import Path

DATA = Path(__file__).resolve().parents[1] / "app" / "data"


def _load():
    catalog = json.loads((DATA / "catalog.json").read_text())
    seed = json.loads((DATA / "seed_transcripts.json").read_text())
    return catalog, seed


def test_every_lecture_has_a_transcript():
    catalog, seed = _load()
    have = {(c["course_id"], c["lecture_title"]) for c in seed}
    missing = [(c["slug"], name) for c in catalog for ch in c["chapters"]
               for name in ch["subchapters"] if (c["slug"], name) not in have]
    assert not missing, f"lectures without transcript chunks: {missing}"


def test_every_chunk_belongs_to_a_catalog_lecture():
    catalog, seed = _load()
    known = {(c["slug"], name) for c in catalog for ch in c["chapters"] for name in ch["subchapters"]}
    stray = sorted({(c["course_id"], c["lecture_title"]) for c in seed} - known)
    assert not stray, f"chunks pointing at lectures not in the catalog: {stray}"


def test_no_duplicate_chunk_ids():
    _, seed = _load()
    dupes = [k for k, v in Counter(c["chunk_id"] for c in seed).items() if v > 1]
    assert not dupes, f"duplicate chunk ids: {dupes[:10]}"
