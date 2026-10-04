"""Demo-account seed (scripts/seed_demo_account.py) — in-memory store, no network.

The seed must make every surface tell one story: the dashboard, adaptive
practice, course insight and the chat tools all read the SAME tags, and graded
performance is derived from the seeded sessions (never typed separately)."""
import json
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from app.services import journey_service, knowledge_graph_service, skill_graph_service
from app.services.store import InMemoryStore
from scripts import seed_demo_account as seed

DEMO_DIR = Path(__file__).resolve().parent.parent / "app" / "data" / "demo"
TRANSCRIPTS = Path(__file__).resolve().parent.parent / "app" / "data" / "seed_transcripts.json"
UID = "x94FcfXU7KRrobyOA4UHDukbRoC2"
# 00:10 UTC on purpose: the "today" session must still land today AND in the past.
NOW = datetime(2026, 10, 4, 0, 10, tzinfo=timezone.utc)
SLUGS = ["react-perf", "javascript-deep-dive", "web-apis", "custom-library"]


def _load(name):
    return json.loads((DEMO_DIR / name).read_text())


@pytest.fixture
def seeded(monkeypatch):
    st = InMemoryStore()
    for mod in (journey_service, knowledge_graph_service, skill_graph_service):
        monkeypatch.setattr(mod, "store", st)
    monkeypatch.setattr(journey_service, "_today", lambda: NOW.date())
    return st


async def _seed(st):
    await seed.write_all(st, seed.build_docs(UID, NOW))
    return st


# ---- fixtures are mutually consistent --------------------------------------

def test_taxonomy_banks_and_sessions_share_one_tag_set():
    tax = _load("taxonomy.json")["courses"]
    banks = _load("question_banks.json")
    student = _load("demo_student.json")
    assert sorted(tax) == sorted(SLUGS) == sorted(banks)
    for slug, course in tax.items():
        tags = {c["name"] for c in course["concepts"]}
        for r in course["relationships"]:
            assert r["source"] in tags and r["target"] in tags, (slug, r)
        assert {q["concept"] for q in banks[slug]["questions"]} == tags, slug
    for s in student["sessions"]:
        tags = {c["name"] for c in tax[s["course_slug"]]["concepts"]}
        for c in s["concepts"]:
            assert c["concept"] in tags, (s, c)
            assert 0 <= c["correct"] <= c["total"] and c["total"] > 0
    for o in student["chat_observations"]:
        assert o["concept"] in {c["name"] for c in tax[o["course_slug"]]["concepts"]}


def test_required_prerequisite_edges_present():
    tax = _load("taxonomy.json")["courses"]
    edges = {(slug, r["source"], r["target"]) for slug, c in tax.items()
             for r in c["relationships"] if r["type"] == "prerequisite_of"}
    for e in [
        ("javascript-deep-dive", "event-loop", "microtask-queue"),
        ("web-apis", "http-upgrade", "websocket-handshake"),
        ("web-apis", "websocket-handshake", "polling-vs-websockets"),
        ("web-apis", "long-polling", "polling-vs-websockets"),
        ("custom-library", "global-symlinks", "npm-link"),
        ("custom-library", "npm-link", "local-package-testing"),
        ("react-perf", "shallow-equality", "react-memo"),
        ("react-perf", "use-callback", "react-memo"),
        ("javascript-deep-dive", "prototype-inheritance", "class-syntax-sugar"),
    ]:
        assert e in edges, e


def test_every_bank_question_is_valid():
    tax = _load("taxonomy.json")["courses"]
    banks = _load("question_banks.json")
    chunks = json.loads(TRANSCRIPTS.read_text())
    for slug, bank in banks.items():
        assert bank["course_id"] == slug and bank["course_title"] == tax[slug]["title"]
        lectures = {c["lecture_title"] for c in chunks if c["course_id"] == slug}
        per = defaultdict(int)
        for n, q in enumerate(bank["questions"], start=1):
            assert q["id"] == f"{slug}-q{n}"
            assert q["question"].strip() and q["explanation"].strip()
            assert len(q["options"]) == 4 and len({o.strip().lower() for o in q["options"]}) == 4
            assert isinstance(q["correct_index"], int) and 0 <= q["correct_index"] <= 3
            assert q["difficulty"] in ("easy", "medium", "hard")
            assert q["lecture"] in lectures, (slug, q["lecture"])
            per[(q["concept"], q["difficulty"])] += 1
        tags = [c["name"] for c in tax[slug]["concepts"]]
        assert per == {(t, d): 2 for t in tags for d in ("easy", "medium", "hard")}, slug


# ---- built docs ------------------------------------------------------------

def test_concept_performance_is_the_aggregation_of_session_answers():
    docs = seed.build_docs(UID, NOW)
    agg = defaultdict(lambda: {"attempts": 0, "correct": 0, "last_seen": ""})
    for s in docs["quiz_sessions"].values():
        assert s["score"] == sum(a["correct"] for a in s["answers"])
        assert s["total"] == len(s["answers"])
        for a in s["answers"]:
            g = agg[a["concept"]]
            g["attempts"] += 1
            g["correct"] += 1 if a["correct"] else 0
            g["last_seen"] = max(g["last_seen"], s["completed_at"])
    perf = docs["concept_performance"]
    assert set(perf) == {f"{UID}__{c}" for c in agg}
    for c, g in agg.items():
        row = perf[f"{UID}__{c}"]
        assert row["user_id"] == UID and row["concept"] == c
        assert (row["attempts"], row["correct"], row["last_seen"]) == (g["attempts"], g["correct"], g["last_seen"])
        assert row["accuracy"] == round(g["correct"] / g["attempts"], 3)


def test_session_answer_ids_never_collide_with_bank_ids():
    """Seeded history must leave the whole bank 'unseen', otherwise adaptive
    start() calls question_service.top_up and the LLM invents new tags."""
    docs = seed.build_docs(UID, NOW)
    bank_ids = {q["id"] for b in docs["questions"].values() for q in b["questions"]}
    answer_ids = [a["question_id"] for s in docs["quiz_sessions"].values() for a in s["answers"]]
    assert len(answer_ids) == len(set(answer_ids))
    assert not bank_ids & set(answer_ids)


def test_no_future_timestamps_and_today_session_is_today():
    docs = seed.build_docs(UID, NOW)
    stamps = [s["completed_at"] for s in docs["quiz_sessions"].values()]
    stamps += [t["created_at"] for t in docs["student_turns"].values()]
    stamps += [p["last_seen"] for p in docs["concept_performance"].values()]
    stamps += [p["chat_confidence_updated_at"] for p in docs["concept_performance"].values()
               if "chat_confidence_updated_at" in p]
    prof = docs["student_profile"][UID]
    stamps += [prof["first_seen"], prof["last_seen"]]
    parsed = [datetime.fromisoformat(s) for s in stamps]
    assert all(p <= NOW for p in parsed)
    assert NOW.date() in {datetime.fromisoformat(s).date() for s in
                          (x["completed_at"] for x in docs["quiz_sessions"].values())}


def test_turns_and_profile_are_consistent():
    docs = seed.build_docs(UID, NOW)
    turns = sorted(docs["student_turns"].values(), key=lambda t: t["created_at"])
    assert 6 <= len(turns) <= 10
    for doc_id, t in docs["student_turns"].items():
        assert doc_id == f"{UID}__{t['created_at']}" and t["student_id"] == UID
    prof = docs["student_profile"][UID]
    assert prof["turn_count"] == len(turns)
    assert prof["first_seen"] == turns[0]["created_at"] and prof["last_seen"] == turns[-1]["created_at"]
    assert prof["topics"] == [t["question"][:80] for t in turns][-8:]
    kitchen = [t for t in turns if "restaurant" in t["answer"].lower()]
    assert len(kitchen) == 1
    age = NOW - datetime.fromisoformat(kitchen[0]["created_at"])
    assert timedelta(days=8) < age < timedelta(days=12)
    for word in ("chef", "call stack", "ticket", "head waiter", "microtask"):
        assert word in kitchen[0]["answer"].lower(), word


def test_event_loop_carries_the_chat_observation():
    row = seed.build_docs(UID, NOW)["concept_performance"][f"{UID}__event-loop"]
    assert row["chat_confidence"] == "developing"
    assert row["chat_confidence_note"] == (
        "explained the call stack correctly but mixed up setTimeout vs Promise ordering")
    assert row["attempts"] > 0  # graded fields still come from sessions


# ---- what the app shows ----------------------------------------------------

async def test_story_targets_hold_through_the_real_services(seeded):
    await _seed(seeded)
    m = await journey_service.get_metrics(UID)
    assert m["streak"] >= 5
    assert 18 <= m["quizzes"] <= 22
    sw = await journey_service.get_strengths_weaknesses(UID)
    strong = {s["concept"] for s in sw["strengths"]}
    weak = {w["concept"] for w in sw["weaknesses"]}
    assert "react-memo" in strong
    assert {"event-loop", "microtask-queue"} <= weak

    report = await journey_service.get_strengths_report(UID)
    micro = next(w for w in report["weaknesses"] if w["concept"] == "microtask-queue")
    assert micro["course_id"] == "javascript-deep-dive"
    assert [p["concept"] for p in micro["prerequisites"]] == ["event-loop"]
    assert micro["prerequisites"][0]["chat_confidence"] == "developing"

    js_weak = await journey_service.weak_concepts_for_course(UID, "javascript-deep-dive")
    assert js_weak and js_weak[0].startswith("microtask-queue")


async def test_accuracy_targets(seeded):
    await _seed(seeded)
    acc = {p["concept"]: p["accuracy"] for p in await seeded.query("concept_performance", "user_id", UID)}
    for c in ("react-memo", "use-memo", "use-callback", "prototype-inheritance", "npm-link"):
        assert acc[c] >= 0.85, c
    assert 0.75 <= acc["shallow-equality"] <= 0.85
    assert 0.65 <= acc["class-syntax-sugar"] <= 0.75
    assert 0.6 <= acc["v8-hidden-classes"] <= 0.7
    assert 0.4 <= acc["event-loop"] <= 0.5
    assert 0.25 <= acc["microtask-queue"] <= 0.35
    assert 0.45 <= acc["polling-vs-websockets"] <= 0.55
    assert acc["http-upgrade"] >= 0.75 and acc["websocket-handshake"] >= 0.75


async def test_dashboard_score_trend_reads_improving(seeded, monkeypatch):
    """Drive the dashboard's own path (get_journey -> _ai_insights) and read the
    trend line it hands the narrative model: must be "improving", by >= 8 points."""
    import re

    captured = {}

    async def fake_generate_json(system, user, **kwargs):
        captured["user"] = user
        return None

    monkeypatch.setattr(journey_service.llm, "generate_json", fake_generate_json)
    await _seed(seeded)
    await journey_service.get_journey(UID)
    m = re.search(r"Score trend: (\w+) \((\d+)% → (\d+)%\)", captured["user"])
    assert m, captured["user"]
    label, early, late = m.group(1), int(m.group(2)), int(m.group(3))
    assert label == "improving"
    assert late - early >= 8, (early, late)


def test_event_loop_improves_across_sessions():
    docs = seed.build_docs(UID, NOW)
    chron = sorted(docs["quiz_sessions"].values(), key=lambda s: s["completed_at"])
    accs = [b["accuracy"] for s in chron for b in s["concept_breakdown"] if b["concept"] == "event-loop"]
    assert len(accs) >= 3 and accs[-1] > accs[0]


# ---- apply: backup -> reset -> write ---------------------------------------

class RecordingStore(InMemoryStore):
    """Records mutations; delete() asserts a backup file already exists."""

    def __init__(self, backup_dir: Path):
        super().__init__()
        self.backup_dir = backup_dir
        self.calls: list = []

    async def set(self, collection, doc_id, data):
        self.calls.append(("set", collection, doc_id))
        await super().set(collection, doc_id, data)

    async def delete(self, collection, doc_id):
        assert list(self.backup_dir.glob("*.json")), "delete before backup was written"
        self.calls.append(("delete", collection, doc_id))
        await super().delete(collection, doc_id)


async def _populate_other_data(st):
    """Data that must survive: another student, another course, untouched collections."""
    other = {
        ("concept_performance", "other__event-loop"): {"user_id": "other", "concept": "event-loop", "attempts": 3, "correct": 1, "accuracy": 0.333},
        ("quiz_sessions", "q-other"): {"session_id": "q-other", "user_id": "other", "course_id": "react-perf", "score": 1, "total": 2, "answers": [], "completed_at": "2026-09-01T10:00:00+00:00"},
        ("student_turns", "other__2026-09-01T10:00:00+00:00"): {"student_id": "other", "course_slug": "react-perf", "question": "q", "answer": "a", "created_at": "2026-09-01T10:00:00+00:00"},
        ("student_profile", "other"): {"student_id": "other", "turn_count": 1, "topics": ["q"]},
        ("questions", "programming-language"): {"course_id": "programming-language", "questions": []},
        ("concepts", "programming-language::parsing"): {"course_id": "programming-language", "name": "parsing", "description": ""},
        ("concept_relationships", "programming-language::rel0"): {"course_id": "programming-language", "source": "a", "target": "b", "type": "prerequisite_of"},
        ("enrollments", UID): {"PrevCourses": [11, 9, 10, 2]},
        ("audit_log", "a1"): {"student_id": UID},
        ("lab_artifacts", "l1"): {"student_id": UID},
        ("chat_citations", "c1"): {"student_id": UID},
    }
    for (col, doc_id), data in other.items():
        await InMemoryStore.set(st, col, doc_id, data)
    return other


async def _populate_stale_demo_data(st):
    """What an older seed / real usage left behind for the demo uid + demo courses."""
    stale = {
        ("concept_performance", f"{UID}__useMemo hook"): {"user_id": UID, "concept": "useMemo hook", "attempts": 2, "correct": 1, "accuracy": 0.5},
        ("quiz_sessions", "3f0c-uuid"): {"session_id": "3f0c-uuid", "user_id": UID, "course_id": "react-perf", "score": 1, "total": 2, "answers": [], "completed_at": "2026-09-30T10:00:00+00:00"},
        ("student_turns", f"{UID}__2026-09-30T10:00:00+00:00"): {"student_id": UID, "course_slug": "react-perf", "question": "old", "answer": "old", "created_at": "2026-09-30T10:00:00+00:00"},
        ("student_profile", UID): {"student_id": UID, "turn_count": 99, "topics": ["old"]},
        ("adaptive_sessions", "as-1"): {"session_id": "as-1", "user_id": UID, "course_id": "react-perf"},
        ("recommendations", UID): {"user_id": UID, "items": ["stale"]},
        ("questions", "react-perf"): {"course_id": "react-perf", "questions": [{"id": "react-perf-q1", "concept": "useMemo hook"}]},
        ("concepts", "react-perf::useMemo hook"): {"course_id": "react-perf", "name": "useMemo hook", "description": ""},
        ("concept_relationships", "react-perf::rel0"): {"course_id": "react-perf", "source": "x", "target": "y", "type": "related_to"},
    }
    for (col, doc_id), data in stale.items():
        await InMemoryStore.set(st, col, doc_id, data)
    return stale


async def test_apply_backs_up_then_resets_only_demo_scope_then_writes(tmp_path):
    st = RecordingStore(tmp_path)
    other = await _populate_other_data(st)
    stale = await _populate_stale_demo_data(st)

    result = await seed.apply(st, UID, NOW, backup_dir=tmp_path)

    # backup holds every stale doc, and is parseable
    backup = json.loads(Path(result["backup_path"]).read_text())
    for (col, doc_id), data in stale.items():
        assert backup["docs"][col][doc_id] == data
    # stale docs that the fresh write doesn't reuse are gone
    for col, doc_id in [("concept_performance", f"{UID}__useMemo hook"), ("quiz_sessions", "3f0c-uuid"),
                        ("student_turns", f"{UID}__2026-09-30T10:00:00+00:00"), ("adaptive_sessions", "as-1"),
                        ("recommendations", UID), ("concepts", "react-perf::useMemo hook"),
                        ("concept_relationships", "react-perf::rel0")]:
        assert await st.get(col, doc_id) is None, (col, doc_id)
    # everything outside the demo scope is untouched
    for (col, doc_id), data in other.items():
        assert await st.get(col, doc_id) == data, (col, doc_id)
    touched = {(c, d) for _, c, d in st.calls}
    assert not touched & set(other)
    # all deletes happen before any write
    kinds = [k for k, _, _ in st.calls]
    assert "set" in kinds and kinds.index("set") > max(i for i, k in enumerate(kinds) if k == "delete")
    # fresh data present
    assert (await st.get("questions", "react-perf"))["questions"][0]["concept"] == "shallow-equality"
    assert result["counts"]["quiz_sessions"] == len(seed.build_docs(UID, NOW)["quiz_sessions"])


async def test_apply_is_idempotent(tmp_path):
    st = RecordingStore(tmp_path)
    await _populate_other_data(st)
    first = await seed.apply(st, UID, NOW, backup_dir=tmp_path)
    snapshot = json.loads(json.dumps(st._db))
    second = await seed.apply(st, UID, NOW, backup_dir=tmp_path)
    assert first["counts"] == second["counts"]
    assert json.loads(json.dumps(st._db)) == snapshot
    # a later run (different "now") still leaves no duplicate turns or sessions
    third = await seed.apply(st, UID, NOW + timedelta(hours=5), backup_dir=tmp_path)
    assert third["counts"] == first["counts"]
    assert len(await st.query("student_turns", "student_id", UID)) == first["counts"]["student_turns"]
    assert len(await st.query("quiz_sessions", "user_id", UID)) == first["counts"]["quiz_sessions"]


async def test_apply_aborts_before_deleting_if_backup_unreadable(tmp_path, monkeypatch):
    st = RecordingStore(tmp_path)
    await _populate_stale_demo_data(st)
    monkeypatch.setattr(seed, "_verify_backup", lambda path, docs: (_ for _ in ()).throw(RuntimeError("bad backup")))
    with pytest.raises(RuntimeError):
        await seed.apply(st, UID, NOW, backup_dir=tmp_path)
    assert not [c for c in st.calls if c[0] == "delete"]


def test_apply_without_yes_refuses():
    assert seed.main(["--apply"]) == 2


def test_apply_and_dry_run_are_exclusive():
    with pytest.raises(SystemExit):
        seed.main(["--apply", "--yes", "--dry-run"])
