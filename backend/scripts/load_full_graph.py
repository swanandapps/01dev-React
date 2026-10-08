"""
Load the full concept graph (app/data/full/) into the live store: course concepts, their links and the question
banks. Touches ONLY those three course-level collections; never student data (scores, quizzes, chats, memory).
Concepts a student's own material created (course_id = null) are left alone.

  python scripts/load_full_graph.py                    # dry run: what would change, nothing written
  python scripts/load_full_graph.py --apply --yes      # back up the current graph, then load (one transaction)
  python scripts/load_full_graph.py --revert FILE --yes  # put a backup back (one transaction)

Postgres only for --apply / --revert (DATABASE_URL).
"""
import argparse
import asyncio
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

BACKEND = Path(__file__).resolve().parent.parent
FULL = BACKEND / "app" / "data" / "full"
COLLECTIONS = ("concepts", "concept_relationships", "questions")
BACKUP_DIR = Path.home() / "Backups"


def build_docs() -> dict:
    """{collection: {doc_id: data}} for the full graph, same shapes and ids as scripts/seed_demo_account.py."""
    tax = json.loads((FULL / "taxonomy.json").read_text())["courses"]
    banks = json.loads((FULL / "question_banks.json").read_text())
    docs = {c: {} for c in COLLECTIONS}
    for slug, course in tax.items():
        docs["questions"][slug] = banks[slug]
        for c in course["concepts"]:
            docs["concepts"][f"{slug}::{c['name']}"] = {
                "course_id": slug, "name": c["name"], "description": c["description"],
                **{k: c[k] for k in ("chapter", "lectures") if c.get(k)}}
        for r in course["relationships"]:
            docs["concept_relationships"][f"{slug}::{r['source']}->{r['target']}::{r['type']}"] = {
                "course_id": slug, "source": r["source"], "target": r["target"], "type": r["type"]}
    return docs


def stale_ids(current: dict, new: dict) -> dict:
    """Course-graph docs that exist now but not in the new graph (old link ids, retired names). Only docs that
    belong to a course (course_id set); a student's own concepts (course_id null) are never stale."""
    courses = {d["course_id"] for d in new["concepts"].values()}
    out = {}
    for col in ("concepts", "concept_relationships"):
        out[col] = sorted(i for i, d in current[col].items() if d.get("course_id") in courses and i not in new[col])
    out["questions"] = []          # banks are replaced per course by upsert
    return out


async def apply_to_store(store, new: dict) -> dict:
    """In-memory / generic store path (tests): delete stale, upsert new. Returns counts."""
    current = {col: dict(await store.list_all_with_ids(col)) for col in COLLECTIONS}
    stale = stale_ids(current, new)
    for col, ids in stale.items():
        for i in ids:
            await store.delete(col, i)
    for col, items in new.items():
        for i, d in items.items():
            await store.set(col, i, d)
    return {col: {"upserted": len(new[col]), "removed": len(stale[col])} for col in COLLECTIONS}


async def _pg():
    import asyncpg
    return await asyncpg.connect(os.environ["DATABASE_URL"])


async def _read_current(c) -> dict:
    rows = await c.fetch("select collection, doc_id, data from docs where collection = any($1::text[])", list(COLLECTIONS))
    cur = {col: {} for col in COLLECTIONS}
    for r in rows:
        cur[r["collection"]][r["doc_id"]] = json.loads(r["data"])
    return cur


async def dry_run() -> None:
    new = build_docs()
    if not os.getenv("DATABASE_URL"):
        print("no DATABASE_URL: showing the new graph only")
        print({col: len(v) for col, v in new.items()})
        return
    c = await _pg()
    cur = await _read_current(c)
    await c.close()
    stale = stale_ids(cur, new)
    for col in COLLECTIONS:
        added = len(set(new[col]) - set(cur[col]))
        print(f"{col:22} now {len(cur[col]):5} -> after {len(cur[col]) - len(stale[col]) + added:5} "
              f"(new {added}, replaced {len(set(new[col]) & set(cur[col]))}, removed {len(stale[col])})")


async def apply() -> None:
    new = build_docs()
    c = await _pg()
    cur = await _read_current(c)
    BACKUP_DIR.mkdir(exist_ok=True)
    path = BACKUP_DIR / f"graph-backup-{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}.json"
    path.write_text(json.dumps(cur))
    print("backup:", path, {col: len(v) for col, v in cur.items()})
    stale = stale_ids(cur, new)
    async with c.transaction():
        for col, ids in stale.items():
            if ids:
                await c.execute("delete from docs where collection = $1 and doc_id = any($2::text[])", col, ids)
        await c.executemany(
            "insert into docs (collection, doc_id, data) values ($1, $2, $3::jsonb) "
            "on conflict (collection, doc_id) do update set data = excluded.data, updated_at = now()",
            [(col, i, json.dumps(d)) for col, items in new.items() for i, d in items.items()])
    after = await _read_current(c)
    await c.close()
    print("loaded:", {col: len(v) for col, v in after.items()})
    print(f"to undo: python scripts/load_full_graph.py --revert {path} --yes")


async def revert(path: Path) -> None:
    backup = json.loads(path.read_text())
    new = build_docs()
    c = await _pg()
    async with c.transaction():
        for col in COLLECTIONS:
            ids = sorted(set(new[col]) - set(backup[col]))   # what the load added
            if ids:
                await c.execute("delete from docs where collection = $1 and doc_id = any($2::text[])", col, ids)
        await c.executemany(
            "insert into docs (collection, doc_id, data) values ($1, $2, $3::jsonb) "
            "on conflict (collection, doc_id) do update set data = excluded.data, updated_at = now()",
            [(col, i, json.dumps(d)) for col, items in backup.items() for i, d in items.items()])
    after = await _read_current(c)
    await c.close()
    print("restored:", {col: len(v) for col, v in after.items()})


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    g = ap.add_mutually_exclusive_group()
    g.add_argument("--apply", action="store_true")
    g.add_argument("--revert", metavar="BACKUP_JSON")
    ap.add_argument("--yes", action="store_true")
    a = ap.parse_args()
    if (a.apply or a.revert) and not a.yes:
        raise SystemExit("add --yes to write to the database")
    asyncio.run(apply() if a.apply else revert(Path(a.revert)) if a.revert else dry_run())
