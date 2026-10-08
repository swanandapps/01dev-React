"""
Seed the demo student's account so every surface tells ONE consistent story:
the dashboard (/api/ai/journey), adaptive practice, course insight and the chat
tools (get_learning_metrics / get_learning_strengths / weak_concepts_for_course /
search_history) — and so the course-level data (question banks + concept maps)
uses the SAME concept tags as the student's performance rows.

Inputs (all reviewable, committed data — nothing is invented here):
  app/data/demo/taxonomy.json        fixed concept tags + prerequisite edges per course
  app/data/demo/question_banks.json  tag-locked banks (scripts/build_demo_question_banks.py)
  app/data/demo/demo_student.json    the story: session plan, chat turns, chat observations

concept_performance is NEVER typed: it's aggregated from the generated sessions'
answers (attempts/correct/accuracy/last_seen), so the dashboard and the session
history can't disagree. No timestamp is ever in the future.

Modes:
  --dry-run (default)  forces an in-memory store (DATABASE_URL / Firebase / OpenAI
                       blanked BEFORE app modules load), seeds, and prints what the
                       app will show. Touches nothing outside this process.
  --apply --yes        against the real store from backend/.env (Postgres only):
                       1. BACKUP every doc it will delete or overwrite to
                          backend/data/demo_backups/{uid}-{utc-ts}.json, re-read and verify
                          it, then print the path + planned write/delete counts
                       2. UPSERT every fresh doc (write FIRST, so the shared questions /
                          concepts docs are never missing on a live store)
                       3. DELETE stale docs in scope that the fresh set doesn't reuse:
                          the uid's concept_performance, quiz_sessions, adaptive_sessions,
                          student_turns, student_profile, recommendations cache, and the 4
                          demo courses' questions / concepts / concept_relationships
                       4. VERIFY each demo course's bank + graph tags equal taxonomy.json.
                       On a failure mid-way it prints the backup path and how to recover.
                       Never touches enrollments, audit_log, lab_artifacts,
                       chat_citations, or any other student. Idempotent.
  --restore FILE --yes put a backup back (Postgres only): set every backed-up doc, then
                       delete seed-written docs the backup doesn't contain.
  --apply / --restore without --yes refuse (exit 2).

Run: cd backend && .venv/bin/python scripts/seed_demo_account.py --dry-run
"""
import argparse
import asyncio
import json
import os
import sys
from collections import Counter, defaultdict
from datetime import datetime, time, timedelta, timezone
from pathlib import Path

BACKEND = Path(__file__).resolve().parent.parent
DEMO_DIR = BACKEND / "app" / "data" / "demo"
BACKUP_DIR = BACKEND / "data" / "demo_backups"
DEMO_UID = "x94FcfXU7KRrobyOA4UHDukbRoC2"

# adaptive_service's accuracy bands — the difficulty a real run would have served
_BAND_MS = {"easy": 21000, "medium": 33000, "hard": 46000}
WRITE_ORDER = [
    "questions", "concepts", "concept_relationships",
    "quiz_sessions", "concept_performance", "student_turns", "student_profile",
]


# ---------------------------------------------------------------- fixtures

GRAPH = "demo"   # --graph full: the whole concept graph (app/data/full/, scripts/build_full_question_banks.py)


def load_fixtures() -> dict:
    load = lambda name: json.loads((DEMO_DIR / name).read_text())  # noqa: E731
    graph_dir = DEMO_DIR if GRAPH == "demo" else DEMO_DIR.parent / "full"
    return {
        "taxonomy": json.loads((graph_dir / "taxonomy.json").read_text())["courses"],
        "banks": json.loads((graph_dir / "question_banks.json").read_text()),
        "student": load("demo_student.json"),
    }


def _at(now: datetime, days_ago: int, hour: int, minute: int) -> datetime:
    """UTC timestamp `days_ago` days before now's UTC date at hh:mm — clamped so
    it is never later than now - 30 min, and a days_ago=0 event stays today."""
    now = now.astimezone(timezone.utc)
    day = now.date() - timedelta(days=days_ago)
    t = datetime.combine(day, time(hour, minute), tzinfo=timezone.utc)
    limit = now - timedelta(minutes=30)
    if t > limit:
        midnight = datetime.combine(now.date(), time(0), tzinfo=timezone.utc)
        t = limit if limit >= midnight or days_ago > 0 else midnight + (now - midnight) / 2
    return t


def _band(accuracy):
    if accuracy is None or accuracy < 0.5:
        return "easy"
    return "medium" if accuracy < 0.8 else "hard"


# ---------------------------------------------------------------- build (pure)

def build_docs(uid: str, now: datetime, fixtures: dict | None = None) -> dict:
    """Every doc the seed writes, as {collection: {doc_id: data}}. Pure."""
    fx = fixtures or load_fixtures()
    tax, banks, student = fx["taxonomy"], fx["banks"], fx["student"]
    docs: dict = {c: {} for c in WRITE_ORDER}

    # course-level: banks + knowledge graph on the fixed tags
    lecture_for: dict = {}
    for slug, course in tax.items():
        docs["questions"][slug] = banks[slug]
        for q in banks[slug]["questions"]:
            lecture_for.setdefault((slug, q["concept"], q["difficulty"]), q["lecture"])
        for c in course["concepts"]:
            docs["concepts"][f"{slug}::{c['name']}"] = {
                "course_id": slug, "name": c["name"], "description": c["description"],
                **{k: c[k] for k in ("chapter", "lectures") if c.get(k)}}     # full graph: where it's taught
        for r in course["relationships"]:
            docs["concept_relationships"][f"{slug}::{r['source']}->{r['target']}::{r['type']}"] = {
                "course_id": slug, "source": r["source"], "target": r["target"], "type": r["type"]}

    # sessions, chronological; answers replay adaptive's per-answer bookkeeping
    plan = sorted(student["sessions"], key=lambda s: (-s["days_ago"], s["utc_hour"], s["utc_minute"]))
    running: dict = defaultdict(lambda: [0, 0])          # concept -> [attempts, correct]
    perf: dict = {}
    for i, s in enumerate(plan):
        slug = s["course_slug"]
        sid = f"seed-{uid}-{slug}-{i}"
        completed = _at(now, s["days_ago"], s["utc_hour"], s["utc_minute"]).isoformat()
        answers = []
        for c in s["concepts"]:
            concept, total, n_correct = c["concept"], c["total"], c["correct"]
            for n in range(total):
                correct = n >= total - n_correct          # misses first, then it clicks
                att, cor = running[concept]
                diff = _band(cor / att if att else None)
                answers.append({
                    # Deliberately NOT bank ids: the whole bank stays "unseen", so
                    # adaptive start() never triggers an LLM top_up with invented tags.
                    "question_id": f"{sid}-a{len(answers) + 1}",
                    "concept": concept,
                    "difficulty": diff,
                    "correct": correct,
                    "time_taken_ms": _BAND_MS[diff] + ((i * 7 + len(answers) * 13) % 10) * 1000,
                    "lecture": lecture_for.get((slug, concept, diff), ""),
                })
                running[concept][0] += 1
                running[concept][1] += 1 if correct else 0
                row = perf.setdefault(concept, {"course_id": slug, "last_seen": ""})
                row["last_seen"] = max(row["last_seen"], completed)
        agg: dict = defaultdict(lambda: [0, 0])
        for a in answers:
            agg[a["concept"]][0] += 1
            agg[a["concept"]][1] += 1 if a["correct"] else 0
        breakdown = sorted(
            ({"concept": c, "attempts": a, "correct": k, "accuracy": round(k / a, 3)} for c, (a, k) in agg.items()),
            key=lambda b: b["accuracy"],
        )
        docs["quiz_sessions"][sid] = {
            "session_id": sid, "user_id": uid, "course_id": slug,
            "course_title": tax[slug]["title"],
            "score": sum(1 for a in answers if a["correct"]), "total": len(answers),
            "answers": answers, "concept_breakdown": breakdown, "completed_at": completed,
        }

    for concept, (att, cor) in running.items():
        docs["concept_performance"][f"{uid}__{concept}"] = {
            "user_id": uid, "concept": concept, "attempts": att, "correct": cor,
            "accuracy": round(cor / att, 3), "last_seen": perf[concept]["last_seen"],
            "course_id": perf[concept]["course_id"],
        }

    # chat observations: the same fields skill_graph_service.record_observation writes
    for o in student.get("chat_observations", []):
        doc_id = f"{uid}__{o['concept']}"
        row = docs["concept_performance"].get(doc_id) or {
            "user_id": uid, "concept": o["concept"], "attempts": 0, "correct": 0, "accuracy": 0.0,
            "course_id": o["course_slug"], "created_by": "chat_observation"}
        row.update({
            "chat_confidence": o["confidence"],
            "chat_confidence_note": o["note"],
            "chat_confidence_updated_at": _at(now, o["days_ago"], o["utc_hour"], o["utc_minute"]).isoformat(),
        })
        docs["concept_performance"][doc_id] = row

    # chat memory: turns + a profile consistent with them (memory_service shapes)
    turns = sorted(
        ({**t, "ts": _at(now, t["days_ago"], t["utc_hour"], t["utc_minute"]).isoformat()} for t in student["chat_turns"]),
        key=lambda t: t["ts"],
    )
    for t in turns:
        docs["student_turns"][f"{uid}__{t['ts']}"] = {
            "student_id": uid, "course_slug": t["course_slug"],
            "question": t["question"][:500], "answer": t["answer"][:1500],
            "created_at": t["ts"], "pii_redacted": [],
        }
    if turns:
        docs["student_profile"][uid] = {
            "student_id": uid, "first_seen": turns[0]["ts"], "last_seen": turns[-1]["ts"],
            "turn_count": len(turns), "topics": [t["question"][:80] for t in turns][-8:],
        }
    return docs


# ---------------------------------------------------------------- store I/O

async def write_all(st, docs: dict) -> dict:
    counts = {}
    for col in WRITE_ORDER:
        for doc_id, data in docs.get(col, {}).items():
            await st.set(col, doc_id, data)
        counts[col] = len(docs.get(col, {}))
    return counts


async def _docs_where(st, col: str, field: str | None = None, value=None, prefix: str | None = None) -> dict:
    """{doc_id: data} matching data[field] == value, or doc_id starting with prefix.
    The store interface doesn't expose doc ids, so this reads them per backend."""
    from app.services.store import InMemoryStore, PostgresStore

    if isinstance(st, InMemoryStore):
        items = st._db.get(col, {}).items()
        if prefix is not None:
            return {k: v for k, v in items if k.startswith(prefix)}
        return {k: v for k, v in items if v.get(field) == value}
    if isinstance(st, PostgresStore):
        from app.services.db import get_pool

        pool = await get_pool()
        if prefix is not None:
            rows = await pool.fetch(
                "select doc_id, data from docs where collection=$1 and left(doc_id, length($2::text)) = $2::text",
                col, prefix)
        else:
            rows = await pool.fetch(
                "select doc_id, data from docs where collection=$1 and data->>$2 = $3", col, field, str(value))
        return {r["doc_id"]: r["data"] for r in rows}
    raise RuntimeError(f"unsupported store backend for --apply: {type(st).__name__}")


async def find_targets(st, uid: str, slugs: list[str]) -> dict:
    """Every existing doc the reset will delete: uid-scoped + the demo courses' docs."""
    t: dict = defaultdict(dict)
    t["concept_performance"].update(await _docs_where(st, "concept_performance", "user_id", uid))
    t["concept_performance"].update(await _docs_where(st, "concept_performance", prefix=f"{uid}__"))
    t["quiz_sessions"].update(await _docs_where(st, "quiz_sessions", "user_id", uid))
    t["adaptive_sessions"].update(await _docs_where(st, "adaptive_sessions", "user_id", uid))
    t["student_turns"].update(await _docs_where(st, "student_turns", "student_id", uid))
    t["student_turns"].update(await _docs_where(st, "student_turns", prefix=f"{uid}__"))
    for col in ("student_profile", "recommendations"):
        doc = await st.get(col, uid)
        if doc is not None:
            t[col][uid] = doc
    for slug in slugs:
        doc = await st.get("questions", slug)
        if doc is not None:
            t["questions"][slug] = doc
        t["concepts"].update(await _docs_where(st, "concepts", "course_id", slug))
        t["concept_relationships"].update(await _docs_where(st, "concept_relationships", "course_id", slug))
    return {col: docs for col, docs in t.items() if docs}


async def find_overwrites(st, docs: dict, already: dict) -> dict:
    """Existing docs at a FRESH doc id that the scoped queries didn't catch (e.g. a
    legacy doc without course_id) — the upsert will overwrite them, so back them up."""
    found: dict = defaultdict(dict)
    for col, items in docs.items():
        for doc_id in items:
            if doc_id in already.get(col, {}):
                continue
            existing = await st.get(col, doc_id)
            if existing is not None:
                found[col][doc_id] = existing
    return dict(found)


def _merge(*parts: dict) -> dict:
    out: dict = defaultdict(dict)
    for part in parts:
        for col, items in part.items():
            out[col].update(items)
    return {c: d for c, d in out.items() if d}


def _write_backup(backup_dir: Path, uid: str, seed_now: datetime, backed_up: dict) -> Path:
    backup_dir.mkdir(parents=True, exist_ok=True)
    ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
    path = backup_dir / f"{uid}-{ts}.json"
    n = 1
    while path.exists():
        path = backup_dir / f"{uid}-{ts}-{n}.json"
        n += 1
    payload = {
        "uid": uid, "created_at": datetime.now(timezone.utc).isoformat(),
        # the `now` the seed was built with — restore recomputes the exact fresh set from it
        "seed_now": seed_now.isoformat(),
        "counts": {c: len(d) for c, d in backed_up.items()}, "docs": backed_up,
    }
    path.write_text(json.dumps(payload, indent=1, ensure_ascii=False))
    return path


def _verify_backup(path: Path, backed_up: dict) -> None:
    loaded = json.loads(path.read_text())
    if loaded.get("docs") != json.loads(json.dumps(backed_up)):
        raise RuntimeError(f"backup {path} does not round-trip — aborting before any write or delete")


def _keys(docs: dict) -> set:
    return {(c, d) for c, items in docs.items() for d in items}


async def verify_course_docs(st, taxonomy: dict) -> dict:
    """Re-read each demo course's bank + graph and check its tags/edges equal taxonomy.json."""
    ok = {}
    for slug, course in taxonomy.items():
        tags = {c["name"] for c in course["concepts"]}
        edges = {(r["source"], r["target"], r["type"]) for r in course["relationships"]}
        bank = await st.get("questions", slug) or {}
        bank_tags = {q.get("concept") for q in bank.get("questions", [])}
        graph_tags = {c.get("name") for c in await st.query("concepts", "course_id", slug)}
        graph_edges = {(r.get("source"), r.get("target"), r.get("type"))
                       for r in await st.query("concept_relationships", "course_id", slug)}
        ok[slug] = bank_tags == tags and graph_tags == tags and graph_edges == edges
    return ok


def _restore_hint(path: Path) -> str:
    return (f"originals are in {path}; re-running `--apply --yes` is safe; "
            f"or restore with `--restore {path} --yes`")


async def apply(st, uid: str, now: datetime, backup_dir: Path = BACKUP_DIR, fixtures: dict | None = None) -> dict:
    """BACKUP (verified) -> UPSERT every fresh doc -> DELETE stale docs not in the fresh
    set -> VERIFY course tags. Writing first means the shared questions/concepts docs
    are never missing on a live store (a request in that gap would start a background
    LLM build that could overwrite the tag-locked bank). Nothing is mutated if the
    backup can't be written and read back."""
    fx = fixtures or load_fixtures()
    docs = build_docs(uid, now, fx)
    fresh = _keys(docs)
    targets = await find_targets(st, uid, list(fx["taxonomy"]))
    backed_up = _merge(targets, await find_overwrites(st, docs, targets))
    path = _write_backup(backup_dir, uid, now, backed_up)
    _verify_backup(path, backed_up)

    stale = {(c, d) for c, d in _keys(targets) if (c, d) not in fresh}
    print(f"backup:  {path} (verified)")
    print("planned writes:  " + ", ".join(f"{c}={len(d)}" for c, d in docs.items()))
    print("planned deletes: " + (", ".join(f"{c}={n}" for c, n in sorted(Counter(c for c, _ in stale).items())) or "none"))

    try:
        counts = await write_all(st, docs)
        deleted: Counter = Counter()
        for col, doc_id in sorted(stale):
            await st.delete(col, doc_id)
            deleted[col] += 1
        verify = await verify_course_docs(st, fx["taxonomy"])
    except BaseException:
        print(f"FAILED mid-apply — {_restore_hint(path)}")
        raise
    print("verify course tags vs taxonomy.json: "
          + ", ".join(f"{s}={'OK' if v else 'FAIL'}" for s, v in verify.items()))
    return {"backup_path": str(path), "deleted": dict(deleted), "counts": counts, "verify": verify}


async def restore(st, backup_path: Path, fixtures: dict | None = None) -> dict:
    """Put a backup back: `set` every backed-up doc, then delete the docs the seed
    wrote (fresh set recomputed from the fixtures + the backup's seed_now) that the
    backup doesn't contain. Docs outside the seed's scope are never touched."""
    payload = json.loads(Path(backup_path).read_text())
    uid, seed_now = payload["uid"], datetime.fromisoformat(payload["seed_now"])
    backed_up = payload["docs"]
    written = 0
    for col, items in backed_up.items():
        for doc_id, data in items.items():
            await st.set(col, doc_id, data)
            written += 1
    have = _keys(backed_up)
    removed = 0
    for col, doc_id in sorted(_keys(build_docs(uid, seed_now, fixtures)) - have):
        await st.delete(col, doc_id)
        removed += 1
    return {"restored": written, "removed_seed_docs": removed}


# ---------------------------------------------------------------- report

def _pct(x) -> str:
    return "n/a" if x is None else f"{round(x * 100)}%"


def _p(line: str = "") -> None:
    print(line)


async def print_report(uid: str, docs: dict) -> None:
    """Print what the app's own read paths return for the seeded data."""
    from app.models import MCQQuestion
    from app.services import adaptive_service, journey_service

    m = await journey_service.get_metrics(uid)
    _p("== get_metrics (dashboard tiles / get_learning_metrics) ==")
    for k, v in m.items():
        _p(f"  {k:26s} {v}")

    sessions = sorted(docs["quiz_sessions"].values(), key=lambda s: s["completed_at"])
    ratio = lambda xs: sum(s["score"] for s in xs) / max(sum(s["total"] for s in xs), 1)  # noqa: E731
    half = len(sessions) // 2
    _p(f"  score trend (journey's halves)  {_pct(ratio(sessions[:half]))} -> {_pct(ratio(sessions[half:]))}"
       f"   first 3: {_pct(ratio(sessions[:3]))}   last 5: {_pct(ratio(sessions[-5:]))}")
    hours = Counter(datetime.fromisoformat(s["completed_at"]).hour for s in sessions)
    _p(f"  session UTC hours  {dict(sorted(hours.items()))}  (journey labels part-of-day from the UTC hour)")

    j = await journey_service.get_journey(uid)
    active = [h for h in j["heatmap"] if h["count"]]
    _p(f"  heatmap: {len(active)} active day(s) in the last {len(j['heatmap'])}; "
       f"first {active[0]['date'] if active else '-'}, last {active[-1]['date'] if active else '-'}")
    _p("  last 14 days: " + "".join("#" if h["count"] else "." for h in j["heatmap"][-14:]) + "  (rightmost = today)")

    sw = await journey_service.get_strengths_weaknesses(uid)
    _p("\n== get_strengths_weaknesses ==")
    _p("  strengths:  " + ", ".join(f"{s['concept']} {_pct(s['accuracy'])} ({s['attempts']})" for s in sw["strengths"]))
    _p("  weaknesses: " + ", ".join(f"{w['concept']} {_pct(w['accuracy'])} ({w['attempts']})" for w in sw["weaknesses"]))
    _p(f"  concepts_attempted: {sw['concepts_attempted']}")

    rep = await journey_service.get_strengths_report(uid)
    _p("\n== get_strengths_report (get_learning_strengths: weak + prerequisites) ==")
    for w in rep["weaknesses"]:
        pre = ", ".join(
            f"{p['concept']} {_pct(p['accuracy'])}" + (f" [chat: {p['chat_confidence']}]" if p.get("chat_confidence") else "")
            for p in w["prerequisites"]) or "none"
        _p(f"  {w['concept']:24s} {_pct(w['accuracy']):>4s}  course={w['course_id']}  prerequisites: {pre}")

    _p("\n== weak_concepts_for_course (chat hint, accuracy < 70%) ==")
    for slug in docs["questions"]:
        _p(f"  {slug:22s} {await journey_service.weak_concepts_for_course(uid, slug)}")

    _p("\n== course insight signals (concept_performance filtered by the bank's tags) ==")
    perf = {p["concept"]: p for p in docs["concept_performance"].values()}
    for slug, bank in docs["questions"].items():
        tags = sorted({q["concept"] for q in bank["questions"]})
        cs = [s for s in sessions if s["course_id"] == slug]
        avg = sum(s["score"] / max(s["total"], 1) for s in cs) / len(cs) if cs else None
        strong = [f"{c} {_pct(perf[c]['accuracy'])}" for c in tags if c in perf and perf[c]["accuracy"] >= 0.8]
        weak = [f"{c} {_pct(perf[c]['accuracy'])}" for c in tags if c in perf and perf[c]["accuracy"] < 0.8]
        _p(f"  {slug}: {len(cs)} session(s), avg {_pct(avg)} | strong: {', '.join(strong) or '-'} | weak: {', '.join(weak) or '-'}")

    _p("\n== question banks + adaptive practice first pick ==")
    for slug, bank in docs["questions"].items():
        qs = [MCQQuestion(**q) for q in bank["questions"]]
        seen = await adaptive_service._seen_question_ids(uid, slug)
        unseen = len([q for q in qs if q.id not in seen])
        first = await adaptive_service._pick_next(uid, slug, qs, [], seen)
        by_tag = Counter(q.concept for q in qs)
        _p(f"  {slug:22s} {len(qs)} questions {dict(by_tag)}")
        _p(f"  {'':22s} unseen {unseen}/{len(qs)} (top_up fires below {adaptive_service.LOW_UNSEEN}); "
           f"first pick: {first.concept} / {first.difficulty}")

    turns = sorted(docs["student_turns"].values(), key=lambda t: t["created_at"])
    prof = docs["student_profile"].get(uid, {})
    _p("\n== chat memory ==")
    _p(f"  student_turns: {len(turns)}   profile.turn_count: {prof.get('turn_count')}   "
       f"first_seen {prof.get('first_seen', '')[:10]}  last_seen {prof.get('last_seen', '')[:10]}")
    for t in turns:
        _p(f"  {t['created_at'][:16]}  [{t['course_slug']}] {t['question'][:70]}")
    kitchen = next((t for t in turns if "restaurant" in t["answer"].lower()), None)
    if kitchen:
        _p(f"  restaurant-kitchen analogy turn: {kitchen['created_at'][:10]} ({kitchen['course_slug']})")
    obs = [p for p in docs["concept_performance"].values() if p.get("chat_confidence")]
    for o in obs:
        _p(f"  chat observation: {o['concept']} = {o['chat_confidence']} — \"{o['chat_confidence_note']}\"")
    _p("  (search_history is Postgres full-text search — not exercised by --dry-run)")

    _p("\n== docs written (in-memory) ==")
    _p("  " + ", ".join(f"{c}={len(d)}" for c, d in docs.items()))


# ---------------------------------------------------------------- entry points

def _force_offline_env() -> None:
    for var in ("DATABASE_URL", "FIREBASE_SERVICE_ACCOUNT_JSON", "GOOGLE_APPLICATION_CREDENTIALS", "OPENAI_API_KEY"):
        os.environ[var] = ""
    os.environ["LANGSMITH_TRACING"] = "false"


async def _dry_run(uid: str) -> int:
    from app.services.store import InMemoryStore, store

    if not isinstance(store, InMemoryStore):
        print(f"REFUSING: dry-run store is {type(store).__name__}, expected InMemoryStore.", file=sys.stderr)
        return 1
    now = datetime.now(timezone.utc)
    docs = build_docs(uid, now)
    await write_all(store, docs)
    print(f"DRY RUN — in-memory store, nothing persisted. uid={uid} now={now.isoformat(timespec='seconds')}\n")
    await print_report(uid, docs)
    return 0


def _target_label() -> str:
    """host/db of DATABASE_URL — never the user or password."""
    import urllib.parse as up

    u = up.urlsplit(os.getenv("DATABASE_URL", ""))
    return f"{u.hostname or '?'}{u.path or '/?'}"


async def _real_store():
    from app.services.store import PostgresStore, store

    if not isinstance(store, PostgresStore):
        print(f"REFUSING: needs the Postgres store (DATABASE_URL); got {type(store).__name__}.", file=sys.stderr)
        return None
    print(f"target:  postgres {_target_label()}")
    return store


async def _apply(uid: str) -> int:
    store = await _real_store()
    if store is None:
        return 1
    result = await apply(store, uid, datetime.now(timezone.utc))
    print("deleted: " + (", ".join(f"{c}={n}" for c, n in result["deleted"].items()) or "none"))
    print("written: " + ", ".join(f"{c}={n}" for c, n in result["counts"].items()))
    return 0 if all(result["verify"].values()) else 3


async def _restore(path: Path) -> int:
    payload = json.loads(path.read_text())  # fail fast on a bad file, before touching the store
    store = await _real_store()
    if store is None:
        return 1
    print(f"restoring {sum(len(d) for d in payload['docs'].values())} doc(s) from {path}")
    result = await restore(store, path)
    print(f"restored: {result['restored']}   removed seed-written docs: {result['removed_seed_docs']}")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Seed the demo student's account.")
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--dry-run", action="store_true", help="in-memory seed + report (default)")
    mode.add_argument("--apply", action="store_true", help="backup, write fresh, delete stale in the real store")
    mode.add_argument("--restore", metavar="BACKUP_JSON", help="put a --apply backup back (Postgres only)")
    parser.add_argument("--yes", action="store_true", help="confirm --apply / --restore")
    parser.add_argument("--graph", choices=("demo", "full"), default="demo",
                        help="concept graph + banks to seed: the 4 demo courses (default) or the full graph")
    args = parser.parse_args(argv)
    global GRAPH
    GRAPH = args.graph

    if (args.apply or args.restore) and not args.yes:
        what = "--apply" if args.apply else f"--restore {args.restore}"
        print(f"REFUSING: {what} rewrites the demo account in the real store; add --yes.", file=sys.stderr)
        return 2
    if args.apply or args.restore:
        from dotenv import load_dotenv

        load_dotenv(BACKEND / ".env")
        if args.apply:
            return asyncio.run(_apply(DEMO_UID))
        return asyncio.run(_restore(Path(args.restore)))
    _force_offline_env()
    return asyncio.run(_dry_run(DEMO_UID))


if __name__ == "__main__":
    sys.path.insert(0, str(BACKEND))
    if not {"--apply", "--restore"} & set(sys.argv[1:]):
        _force_offline_env()  # before ANY app module can be imported
    sys.exit(main())
