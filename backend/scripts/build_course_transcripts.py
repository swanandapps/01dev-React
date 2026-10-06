"""
Validate and merge spoken-lecture transcripts for the 9 non-custom-library courses.

Writers produce staging files  backend/data/course_src/<slug>.json  (a JSON list of
TranscriptChunk dicts). This script checks them against the curriculum in
app/data/catalog.json and merges them into app/data/seed_transcripts.json.

Usage (from backend/):
  python scripts/build_course_transcripts.py --check [slug ...]   # exit 1 on any problem
  python scripts/build_course_transcripts.py --merge              # all 9 must be valid
  python scripts/build_course_transcripts.py --snapshot-anchors   # write _anchors.json once

custom-library (340 real chunks) is never touched.
"""
import argparse
import json
import os
import re
import sys
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[1]
CATALOG = BACKEND / "app" / "data" / "catalog.json"
SEED = BACKEND / "app" / "data" / "seed_transcripts.json"
SRC_DIR = BACKEND / "data" / "course_src"
ANCHORS = SRC_DIR / "_anchors.json"

CUSTOM = "custom-library"
ANCHOR_LECTURE_PREFIXES = (
    "js-deep-4-1", "js-deep-5-1", "js-deep-6-1",
    "web-apis-2-2", "web-apis-3-1", "react-perf-3-2", "react-perf-4-1",
)
FIELDS = ["chunk_id", "course_id", "course_title", "lecture_id", "lecture_title",
          "text", "start_time", "end_time", "embedding"]
MD_RE = re.compile(r"(^\s*#)|```|(^\s*[-*]\s)|\*\*", re.MULTILINE)


def _catalog(path=CATALOG):
    return json.loads(Path(path).read_text())


def load_curriculum(path=CATALOG):
    """slug -> {"title", "lectures": [(lecture_id, lecture_title)]}, custom-library excluded."""
    out = {}
    for c in _catalog(path):
        if c["slug"] == CUSTOM:
            continue
        lectures = []
        for ci, ch in enumerate(c["chapters"]):
            for si, name in enumerate(ch["subchapters"]):
                lectures.append((f"{c['slug']}-{ci}-{si}", name))
        out[c["slug"]] = {"title": c["title"], "lectures": lectures}
    return out


def snapshot_anchors(seed_path=SEED, out_path=ANCHORS):
    """lecture_title -> [passage text]. Creates the file; refuses to overwrite one."""
    out_path = Path(out_path)
    if out_path.exists():
        raise FileExistsError(f"{out_path} already exists; refusing to overwrite the anchor snapshot")
    anchors = {}
    for c in json.loads(Path(seed_path).read_text()):
        if c["lecture_id"].startswith(ANCHOR_LECTURE_PREFIXES):
            anchors.setdefault(c["lecture_title"], []).append(c["text"])
    if not anchors:
        raise ValueError("no hand-written anchor chunks found in the seed; nothing to snapshot")
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(anchors, indent=2, ensure_ascii=False) + "\n")
    return anchors


def load_anchors(path=ANCHORS):
    """Existing snapshot only. Raises if missing or empty (never regenerates)."""
    path = Path(path)
    if not path.exists():
        raise FileNotFoundError(f"{path} missing; run --snapshot-anchors on a seed that still has the hand-written chunks")
    data = json.loads(path.read_text())
    if not data:
        raise ValueError(f"{path} is empty")
    return data


def _whole(v):
    return isinstance(v, int) and not isinstance(v, bool)


def validate_course(slug, chunks, curriculum, anchors):
    try:
        return _validate_course(slug, chunks, curriculum, anchors)
    except Exception as e:  # malformed input must be reported, never crash
        return [f"malformed input: {type(e).__name__}: {e}"]


def _validate_course(slug, chunks, curriculum, anchors):
    cur = curriculum[slug]
    problems = []
    valid_pairs = dict(cur["lectures"])  # id -> title
    by_lecture = {}
    clean = []
    for i, c in enumerate(chunks):
        if not isinstance(c, dict):
            problems.append(f"#{i}: chunk is not an object")
            continue
        tag = c.get("chunk_id", f"#{i}")
        text = c.get("text")
        if not isinstance(text, str):
            problems.append(f"{tag}: text must be a string")
            continue
        lid = c.get("lecture_id")
        if not isinstance(lid, str):
            problems.append(f"{tag}: lecture_id must be a string")
            continue
        if c.get("course_id") != slug:
            problems.append(f"{tag}: course_id {c.get('course_id')!r} != {slug!r}")
        if c.get("course_title") != cur["title"]:
            problems.append(f"{tag}: course_title {c.get('course_title')!r} != {cur['title']!r}")
        if valid_pairs.get(lid) != c.get("lecture_title"):
            problems.append(f"{tag}: lecture_title {c.get('lecture_title')!r} does not match curriculum for {lid!r}")
        if c.get("embedding") != []:
            problems.append(f"{tag}: embedding must be []")
        if MD_RE.search(text):
            problems.append(f"{tag}: markdown in text")
        by_lecture.setdefault(lid, []).append(c)
        clean.append(c)

    seen = {}
    for c in clean:
        t = c["text"]
        if t in seen:
            problems.append(f"{c.get('chunk_id')}: duplicate text of {seen[t]}")
        else:
            seen[t] = c.get("chunk_id")

    for lid, title in cur["lectures"]:
        group = by_lecture.get(lid)
        if not group:
            problems.append(f"{lid} ({title}): no chunks")
            continue
        prev_end = 0
        for n, c in enumerate(group):
            tag = c.get("chunk_id")
            if tag != f"{lid}-{n}":
                problems.append(f"{tag}: chunk_id should be {lid}-{n}")
            s, e = c.get("start_time"), c.get("end_time")
            if not (_whole(s) and _whole(e)):
                problems.append(f"{tag}: times must be whole integers")
                continue
            if n == 0 and s != 0:
                problems.append(f"{tag}: first passage must start at 0")
            if n > 0 and s != prev_end:
                problems.append(f"{tag}: not contiguous (start {s} != previous end {prev_end})")
            dur = e - s
            last = n == len(group) - 1
            lo = 20 if last and len(group) > 1 else 45
            if not (lo <= dur <= 75):
                kind = "last passage " if lo == 20 else ""
                problems.append(f"{tag}: {kind}duration {dur}s outside {lo}-75 s")
            if dur > 0:
                wpm = len(c["text"].split()) * 60 / dur
                if not (100 <= wpm <= 180):
                    problems.append(f"{tag}: {wpm:.0f} wpm outside 100-180")
            prev_end = e
        if not (240 <= prev_end <= 720):
            problems.append(f"{lid}: lecture total {prev_end}s outside 240-720 s")
        for text in anchors.get(title, []):
            if not any(text in c["text"] for c in group):
                problems.append(f"{lid}: anchor passage missing verbatim: {text[:50]!r}...")
    for lid in by_lecture:
        if lid not in valid_pairs:
            problems.append(f"unknown lecture_id {lid!r}")
    return problems


def _load_staging(slug, src_dir):
    p = Path(src_dir) / f"{slug}.json"
    if not p.exists():
        return None, [f"{slug}: staging file {p.name} missing"]
    try:
        data = json.loads(p.read_text())
    except json.JSONDecodeError as e:
        return None, [f"{slug}: invalid JSON ({e})"]
    if not isinstance(data, list):
        return None, [f"{slug}: staging file must be a JSON list"]
    return data, []


def check(slugs, curriculum, src_dir, anch):
    problems = []
    all_titles = {t for c in curriculum.values() for _lid, t in c["lectures"]}
    for key in anch:
        if key not in all_titles:
            problems.append(f"anchor {key!r} is not a lecture title in the curriculum")
    for slug in slugs:
        if slug not in curriculum:
            problems.append(f"{slug}: unknown course slug")
            continue
        data, errs = _load_staging(slug, src_dir)
        if errs:
            problems += errs
            continue
        problems += [f"{slug}: {p}" for p in validate_course(slug, data, curriculum, anch)]
    return problems


def merge(catalog_path, seed_path, src_dir, anch):
    """Returns problems; writes the seed only if there are none."""
    curriculum = load_curriculum(catalog_path)
    problems = check(list(curriculum), curriculum, src_dir, anch)
    if problems:
        return problems
    custom = [c for c in json.loads(Path(seed_path).read_text()) if c["course_id"] == CUSTOM]
    if not custom:
        return ["old seed has no custom-library chunks; refusing to merge"]
    merged = []
    for course in _catalog(catalog_path):
        slug = course["slug"]
        if slug == CUSTOM:
            merged += custom
        else:
            data, _ = _load_staging(slug, src_dir)
            order = {lid: i for i, (lid, _t) in enumerate(curriculum[slug]["lectures"])}
            data = sorted(data, key=lambda c: (order[c["lecture_id"]],
                                               int(c["chunk_id"].rsplit("-", 1)[1])))
            merged += [{k: c[k] for k in FIELDS} for c in data]
    seed_path = Path(seed_path)
    tmp = seed_path.with_name(seed_path.name + ".tmp")
    tmp.write_text(json.dumps(merged, indent=2))  # no trailing newline, like the current seed
    os.replace(tmp, seed_path)
    return []


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--check", nargs="*", metavar="slug", help="validate staging files (all 9 if none given)")
    ap.add_argument("--merge", action="store_true", help="validate all 9, then write the seed")
    ap.add_argument("--snapshot-anchors", action="store_true")
    a = ap.parse_args(argv)
    if a.snapshot_anchors:
        try:
            anch = snapshot_anchors(SEED, ANCHORS)
        except (FileExistsError, ValueError) as e:
            print(f"ERROR: {e}")
            return 1
        print(f"anchors: {sum(len(v) for v in anch.values())} passages in {len(anch)} lectures -> {ANCHORS}")
        return 0
    if a.check is None and not a.merge:
        return 0
    try:
        anch = load_anchors(ANCHORS)
    except (OSError, ValueError) as e:
        print(f"ERROR: {e}")
        return 1
    if a.check is not None:
        cur = load_curriculum()
        problems = check(a.check or list(cur), cur, SRC_DIR, anch)
        for p in problems:
            print(p)
        print("OK" if not problems else f"{len(problems)} problem(s)")
        return 1 if problems else 0
    problems = merge(CATALOG, SEED, SRC_DIR, anch)
    for p in problems:
        print(p)
    print("merged" if not problems else f"REFUSED: {len(problems)} problem(s)")
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
