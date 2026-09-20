# Skill Graph & Learner Memory — Data Schema and First Slice

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Turn the existing, disconnected per-student data (a flat topics list,
an adaptive-quiz-only performance table) into one coherent picture: what a
student knows (tied to the course's real concept graph, not a flat list),
how to talk to them (a slow-moving personality profile, separate from what
they know), and a bounded window of raw conversation (not unlimited
retention). This slice implements the piece that's fully specified — skill
graph pre-population tied to the existing course concept graph. Personality
narrative, retention windows, and the periodic reflection job are scoped as
explicit Future work, not built here.

**Scope:** Single learner only — `beingswanand@gmail.com` — per explicit
instruction. No multi-tenant/auth work in this slice.

**Architecture:** Reuses two things that already exist rather than building
new ones: `knowledge_graph_service`'s per-course concept graph (nodes =
`concepts` collection, edges = `concept_relationships` — real
`prerequisite_of`/`part_of`/`related_to` typed relationships, already built
from lecture transcripts + quiz concept tags) supplies the *structure*.
`adaptive_service`'s `concept_performance` collection supplies the
*per-student values* already sitting on that structure, today
disconnected from it. This slice connects them: when a student's first
graded event for a course happens, every concept in that course's graph
gets a zeroed `concept_performance` row up front, not created ad hoc one at
a time. The collection name and its three core fields (`concept`,
`accuracy`, `attempts`) are kept exactly as-is — four existing services
(`journey_service`, `course_insight_service`, `recommendation_service`,
`tutor_service`) read them directly and must not need to change.

**Tech Stack:** Python 3.10+, existing `store` abstraction (Postgres via
the `docs` jsonb table), pytest (already set up).

**Spec:** This session's conversation is the spec — no external doc. Key
decisions, and why:
- **Not a rename.** `concept_performance` stays `concept_performance`.
  Renaming to `skill_graph` would require touching 4 existing readers for a
  cosmetic win. Extending its shape in place is zero-risk to them (verified
  by reading all 4 call sites — they only ever read `concept`, `accuracy`,
  `attempts`, `last_seen`).
- **The graph is course-level, shared, not per-student.** A student's
  "skill graph" isn't a separate graph object — it's their values attached
  to nodes of the ONE course graph everyone shares. Building a graph
  structure per student would duplicate the same edges for every learner
  for no benefit.
- **Pre-population is lazy, not tied to a real "enrollment" event.** This
  backend has no enrollment endpoint — enrollment currently only exists as
  an `arrayUnion` write in Firestore, not read by this backend at all. So
  "when a student starts a course" is approximated as "the first
  request (chat, quiz, or adaptive) this backend sees for this
  (student_id, course_slug) pair" — checked and back-filled idempotently,
  not a new onboarding flow.
- **No chat-driven exposure tracking in this slice.** A quiz answer has an
  obvious correct/incorrect signal; a chat question doesn't. Correctly
  tagging which concept(s) an arbitrary chat question touches is a real
  matching problem on its own (keyword match? embedding similarity against
  concept names? ask Hermes to report it back?) — not something to guess at
  under this scope. `attempts`/`correct`/`accuracy` stay driven by graded
  events only, exactly as today. Tracked as Future work below.
- **If the course has no concept graph built yet, pre-population is a
  no-op**, not a trigger to auto-build one. Building a graph is an existing,
  separate, LLM-driven operation (`POST /api/ai/knowledge-graph/{course_id}/build`)
  that a human/admin already triggers deliberately — this slice doesn't
  change when that happens.

## Future work (explicitly not in this plan)

- **`student_personality`** — a slow-moving narrative (tone, pace,
  explanation style preference) separate from the skill graph, refreshed
  periodically (not per-turn) by an LLM call. Distinct from *what* the
  skill graph tracks (what to teach) — this is *how* to teach it.
- **Retention window on `student_turns`** — currently stored forever, no
  expiry. Real privacy gap; needs a bounded window (e.g. 30-90 days) with
  automatic cleanup, keeping only the distilled skill-graph/personality
  state past that window, not the raw text.
- **Session-end reflection job** — one LLM call, triggered when a session
  ends (idle gap or explicit signal, not every single turn — an LLM call
  per message is both wasteful and unnecessary since the skill graph
  already updates instantly and deterministically), that decides whether
  the personality narrative needs updating based on what happened.
- **Chat-driven concept exposure** — tagging which concept(s) an ordinary
  chat question touches, so `last_seen`/exposure (never `accuracy` — no
  correctness signal exists in plain chat) can reflect chat engagement too,
  not just graded quiz events.
- **Student-specific edges** (e.g. "struggled with X right after Y" as a
  personal connection, on top of the course's shared structure) — this
  session deliberately scoped to course-structure-only edges for now.

## Global Constraints

- Do not rename the `concept_performance` collection, and do not remove or
  rename its existing fields (`user_id`, `concept`, `attempts`, `correct`,
  `accuracy`, `last_seen`) — 4 existing services read these directly and
  must keep working unmodified.
- Do not modify `journey_service.py`, `course_insight_service.py`,
  `recommendation_service.py`, or `tutor_service.py` — this slice is additive
  only (new fields, a new pre-population path); nothing about how those 4
  files read `concept_performance` changes.
- Pre-population must be idempotent — calling it twice for the same
  (student_id, course_id) must not duplicate or reset existing rows with
  real attempts/accuracy data.
- If `knowledge_graph_service.has_graph(course_id)` is `False`, pre-population
  is a silent no-op — never trigger graph building as a side effect of this
  path.

---

### Task 1: Skill-graph pre-population

**Files:**
- Create: `backend/app/services/skill_graph_service.py`
- Create: `backend/tests/test_skill_graph_service.py`
- Modify: `backend/app/services/adaptive_service.py` — call the new
  pre-population function at the point a session starts (see Step 3 below
  for the exact insertion point).

**Interfaces:**
- Consumes: `app.services.knowledge_graph_service.has_graph(course_id: str) -> bool`
  and `get_graph(course_id: str) -> dict` (already exist — `get_graph`
  returns `{"course_id": ..., "concepts": [{"course_id", "name",
  "description"}, ...], "relationships": [...]}`).
- Consumes: `app.services.store.store` (`.get`, `.set` — already used
  identically by `adaptive_service._get_perf`/`_update_perf`).
- Produces: `app.services.skill_graph_service.ensure_populated(user_id: str, course_id: str) -> int`
  (async) — returns the number of concept rows it created (0 if already
  populated or no graph exists yet). Other tasks/services can call this the
  same way `adaptive_service` does.

- [ ] **Step 1: Write the failing tests**

```python
# backend/tests/test_skill_graph_service.py
import pytest

from app.services import skill_graph_service


@pytest.mark.asyncio
async def test_populates_a_zeroed_row_per_concept(monkeypatch):
    from app.services import knowledge_graph_service

    async def fake_has_graph(course_id):
        assert course_id == "js-fundamentals"
        return True

    async def fake_get_graph(course_id):
        return {
            "course_id": course_id,
            "concepts": [
                {"course_id": course_id, "name": "closures", "description": "..."},
                {"course_id": course_id, "name": "hoisting", "description": "..."},
            ],
            "relationships": [
                {"course_id": course_id, "source": "hoisting", "target": "closures", "type": "prerequisite_of"},
            ],
        }

    written: dict[str, dict] = {}

    async def fake_get(collection, doc_id):
        return written.get(doc_id)

    async def fake_set(collection, doc_id, data):
        assert collection == "concept_performance"
        written[doc_id] = data

    monkeypatch.setattr(knowledge_graph_service, "has_graph", fake_has_graph)
    monkeypatch.setattr(knowledge_graph_service, "get_graph", fake_get_graph)
    monkeypatch.setattr(skill_graph_service.store, "get", fake_get)
    monkeypatch.setattr(skill_graph_service.store, "set", fake_set)

    created = await skill_graph_service.ensure_populated("student-1", "js-fundamentals")

    assert created == 2
    row = written["student-1__closures"]
    assert row == {
        "user_id": "student-1", "concept": "closures",
        "attempts": 0, "correct": 0, "accuracy": 0.0,
        "course_id": "js-fundamentals", "source": "pre_populated",
    }


@pytest.mark.asyncio
async def test_is_idempotent_and_never_overwrites_real_progress(monkeypatch):
    from app.services import knowledge_graph_service

    async def fake_has_graph(course_id):
        return True

    async def fake_get_graph(course_id):
        return {
            "course_id": course_id,
            "concepts": [{"course_id": course_id, "name": "closures", "description": "..."}],
            "relationships": [],
        }

    existing_row = {
        "user_id": "student-1", "concept": "closures",
        "attempts": 5, "correct": 4, "accuracy": 0.8,
        "course_id": "js-fundamentals", "last_seen": "2026-09-01T00:00:00+00:00",
    }
    written = {"student-1__closures": existing_row}

    async def fake_get(collection, doc_id):
        return written.get(doc_id)

    async def fake_set(collection, doc_id, data):
        written[doc_id] = data

    monkeypatch.setattr(knowledge_graph_service, "has_graph", fake_has_graph)
    monkeypatch.setattr(knowledge_graph_service, "get_graph", fake_get_graph)
    monkeypatch.setattr(skill_graph_service.store, "get", fake_get)
    monkeypatch.setattr(skill_graph_service.store, "set", fake_set)

    created = await skill_graph_service.ensure_populated("student-1", "js-fundamentals")

    assert created == 0
    assert written["student-1__closures"] == existing_row  # untouched


@pytest.mark.asyncio
async def test_no_graph_yet_is_a_silent_noop(monkeypatch):
    from app.services import knowledge_graph_service

    async def fake_has_graph(course_id):
        return False

    async def fail_if_called(course_id):
        raise AssertionError("get_graph must not be called when has_graph is False")

    monkeypatch.setattr(knowledge_graph_service, "has_graph", fake_has_graph)
    monkeypatch.setattr(knowledge_graph_service, "get_graph", fail_if_called)

    created = await skill_graph_service.ensure_populated("student-1", "js-fundamentals")

    assert created == 0
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd backend && .venv/bin/pytest tests/test_skill_graph_service.py -v`
Expected: `ModuleNotFoundError: No module named 'app.services.skill_graph_service'`

- [ ] **Step 3: Write the implementation**

```python
# backend/app/services/skill_graph_service.py
"""
Ties the per-student `concept_performance` table (already written by
adaptive_service on graded quiz answers) to the per-COURSE concept graph
that already exists (knowledge_graph_service: concepts + prerequisite/
part-of/related-to edges, shared by every student).

`concept_performance` itself is not a graph — it's a flat set of per-
(student, concept) values. This module is what makes those values sit ON
the shared graph's nodes: the moment a student's first graded event for a
course happens, every concept node in that course's graph gets a zeroed
row up front, instead of rows appearing one at a time as concepts happen
to come up. Collection name and field shape (concept/attempts/correct/
accuracy/last_seen) are unchanged — journey_service, course_insight_service,
recommendation_service, and tutor_service all read this collection directly
and must keep working without modification.
"""
from app.services import knowledge_graph_service
from app.services.store import store

PERF_COLLECTION = "concept_performance"


def _perf_id(user_id: str, concept: str) -> str:
    return f"{user_id}__{concept}"


async def ensure_populated(user_id: str, course_id: str) -> int:
    """Back-fill a zeroed concept_performance row for every concept in this
    course's graph that this student doesn't already have a row for.
    Idempotent: never touches a row that already exists (real progress is
    never reset). Silent no-op if the course has no graph built yet —
    building one is a separate, deliberately-triggered operation."""
    if not await knowledge_graph_service.has_graph(course_id):
        return 0

    graph = await knowledge_graph_service.get_graph(course_id)
    created = 0
    for concept in graph["concepts"]:
        name = concept["name"]
        doc_id = _perf_id(user_id, name)
        if await store.get(PERF_COLLECTION, doc_id):
            continue
        await store.set(PERF_COLLECTION, doc_id, {
            "user_id": user_id,
            "concept": name,
            "attempts": 0,
            "correct": 0,
            "accuracy": 0.0,
            "course_id": course_id,
            "source": "pre_populated",
        })
        created += 1
    return created
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd backend && .venv/bin/pytest tests/test_skill_graph_service.py -v`
Expected: all 3 PASS

- [ ] **Step 5: Wire it into `adaptive_service.start()`**

Read `backend/app/services/adaptive_service.py`'s `start()` function (the
handler behind `POST /api/ai/adaptive/start`) to find its exact first
lines, then insert a call at the very top, before anything else runs:

```python
from app.services import skill_graph_service
# ... inside start(), as its first line:
    await skill_graph_service.ensure_populated(user_id, course_id)
```

(Use whatever the function's actual parameter names are — confirm by
reading the function signature directly rather than assuming `user_id`/
`course_id` match exactly.) This is the one existing entry point that
already represents "a student is engaging with graded practice for this
course" — the natural, lowest-risk place to back-fill from, since it runs
before any quiz question is served either way.

- [ ] **Step 6: Run the full test suite to confirm nothing else broke**

Run: `cd backend && .venv/bin/pytest tests -v`
Expected: all PASS (31 existing + 3 new = 34)

- [ ] **Step 7: Commit**

```bash
git add backend/app/services/skill_graph_service.py backend/tests/test_skill_graph_service.py backend/app/services/adaptive_service.py
git commit -m "feat: pre-populate concept_performance from the course's existing concept graph"
```

---

### Task 2: Weighted prerequisite view (no N+1)

**Files:**
- Modify: `backend/app/services/skill_graph_service.py` — add a new
  function alongside `ensure_populated` (same file: tightly coupled to the
  same collection and concept model, not worth a second module).
- Modify: `backend/tests/test_skill_graph_service.py` — add tests
  alongside the existing 3.

**Interfaces:**
- Consumes: `app.services.knowledge_graph_service.get_prerequisites(course_id: str, concept: str) -> list[str]`
  (already exists — returns concept names that are `prerequisite_of` the
  given concept, one query).
- Consumes: `app.services.store.store.query(collection, field, value) -> list[dict]`
  (already the established pattern in `journey_service`/
  `course_insight_service`/`recommendation_service` — fetch ALL of this
  student's `concept_performance` rows in one query, filter in memory,
  rather than one query per concept).
- Produces: `app.services.skill_graph_service.get_prerequisite_view(user_id: str, course_id: str, concept: str) -> dict`
  (async).

- [ ] **Step 1: Write the failing tests**

```python
# append to backend/tests/test_skill_graph_service.py

@pytest.mark.asyncio
async def test_prerequisite_view_combines_target_and_prereqs_in_two_queries(monkeypatch):
    from app.services import knowledge_graph_service

    query_calls = []

    async def fake_get_prerequisites(course_id, concept):
        assert (course_id, concept) == ("js-fundamentals", "closures")
        return ["scope", "functions"]

    async def fake_query(collection, field, value):
        query_calls.append((collection, field, value))
        assert collection == "concept_performance"
        assert (field, value) == ("user_id", "student-1")
        return [
            {"user_id": "student-1", "concept": "closures", "attempts": 5, "correct": 3, "accuracy": 0.6},
            {"user_id": "student-1", "concept": "scope", "attempts": 2, "correct": 0, "accuracy": 0.0},
            # "functions" deliberately has NO row — never attempted at all.
        ]

    monkeypatch.setattr(knowledge_graph_service, "get_prerequisites", fake_get_prerequisites)
    monkeypatch.setattr(skill_graph_service.store, "query", fake_query)

    view = await skill_graph_service.get_prerequisite_view("student-1", "js-fundamentals", "closures")

    # Exactly one query for prerequisites (via get_prerequisites) + one
    # store.query for ALL this student's performance — never one query
    # per prerequisite, no matter how many prerequisites there are.
    assert len(query_calls) == 1

    assert view["concept"] == "closures"
    assert view["accuracy"] == 0.6
    assert view["attempted"] is True

    prereqs = {p["concept"]: p for p in view["prerequisites"]}
    assert prereqs["scope"]["accuracy"] == 0.0
    assert prereqs["scope"]["attempted"] is True  # 2 attempts, genuinely scored 0%
    assert prereqs["functions"]["accuracy"] is None  # never attempted — NOT a fake 0.0
    assert prereqs["functions"]["attempted"] is False

    # Weakest prerequisite must only consider ones actually attempted —
    # "functions" has no real score to compare, so "scope" wins even
    # though its accuracy (0.0) looks "worse" than functions' None.
    assert view["weakest_prerequisite"]["concept"] == "scope"


@pytest.mark.asyncio
async def test_prerequisite_view_handles_no_attempted_prerequisites(monkeypatch):
    from app.services import knowledge_graph_service

    async def fake_get_prerequisites(course_id, concept):
        return ["scope"]

    async def fake_query(collection, field, value):
        return []  # nothing attempted yet at all, including the target concept

    monkeypatch.setattr(knowledge_graph_service, "get_prerequisites", fake_get_prerequisites)
    monkeypatch.setattr(skill_graph_service.store, "query", fake_query)

    view = await skill_graph_service.get_prerequisite_view("student-1", "js-fundamentals", "closures")

    assert view["accuracy"] is None
    assert view["attempted"] is False
    assert view["weakest_prerequisite"] is None
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd backend && .venv/bin/pytest tests/test_skill_graph_service.py -v`
Expected: `AttributeError: module 'app.services.skill_graph_service' has no attribute 'get_prerequisite_view'`

- [ ] **Step 3: Write the implementation**

Append to `backend/app/services/skill_graph_service.py`:

```python
def _view(row: dict | None) -> dict:
    """Translate a raw concept_performance row (or its absence) into an
    honest view: attempts == 0 (including a pre-populated-but-untouched
    row from Task 1) means NO real signal exists yet — report accuracy as
    None, never the stored 0.0 placeholder, which would look like a real
    (bad) score instead of "not tried"."""
    attempts = (row or {}).get("attempts", 0)
    attempted = attempts > 0
    return {
        "concept": (row or {}).get("concept"),
        "accuracy": (row or {}).get("accuracy") if attempted else None,
        "attempts": attempts,
        "attempted": attempted,
    }


async def get_prerequisite_view(user_id: str, course_id: str, concept: str) -> dict:
    """One-shot view of `concept`'s confidence plus every one of its
    prerequisites' confidence, for this student. Two queries total no
    matter how many prerequisites exist: the course's prerequisite edges
    (knowledge_graph_service, already a single query), and ALL of this
    student's concept_performance rows in one store.query — the same
    fetch-everything-then-filter-in-memory pattern journey_service and
    friends already use, not a new capability."""
    prereq_names = await knowledge_graph_service.get_prerequisites(course_id, concept)
    rows = await store.query(PERF_COLLECTION, "user_id", user_id)
    by_concept = {r["concept"]: r for r in rows}

    target = _view(by_concept.get(concept) or {"concept": concept})
    prerequisites = [_view(by_concept.get(name) or {"concept": name}) for name in prereq_names]

    attempted_prereqs = [p for p in prerequisites if p["attempted"]]
    weakest = min(attempted_prereqs, key=lambda p: p["accuracy"], default=None)

    return {**target, "prerequisites": prerequisites, "weakest_prerequisite": weakest}
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd backend && .venv/bin/pytest tests/test_skill_graph_service.py -v`
Expected: all 5 PASS

- [ ] **Step 5: Run the full suite**

Run: `cd backend && .venv/bin/pytest tests -v`
Expected: all PASS (31 existing + 5 new = 36)

- [ ] **Step 6: Commit**

```bash
git add backend/app/services/skill_graph_service.py backend/tests/test_skill_graph_service.py
git commit -m "feat: add weighted prerequisite view (no N+1) to skill_graph_service"
```

---

## Self-Review

1. **Spec coverage:** "how do we figure out concepts, do we pre-populate" →
   Task 1, using the existing course graph as the concept source, not
   inventing a new one. "Is skill graph actually a graph" → addressed
   architecturally (shared course-level edges, per-student node values),
   not by adding fake edges to `concept_performance` itself — the edges
   already exist in `concept_relationships` and are read via `get_graph`,
   not duplicated. "N+1 query problem walking prerequisites" → Task 2,
   two queries total regardless of prerequisite count, reusing
   `get_prerequisites` (already existed) and the fetch-all-then-filter
   pattern already used by 3 other services — no graph database, no new
   infrastructure. "Personality vs skill graph naming" and "keep it
   simple, real-time" → captured in Future work with the reasoning for why
   they're not in this slice (not silently dropped).
2. **Placeholder scan:** no TBD/TODO; every step has real code.
3. **Type consistency:** `ensure_populated(user_id: str, course_id: str) -> int`
   used identically in its definition, tests, and the `adaptive_service`
   call site. `get_prerequisite_view(user_id: str, course_id: str, concept: str) -> dict`
   used identically between its definition and its tests; its `_view()`
   helper's "attempted" semantics (accuracy is `None`, never the stored
   `0.0` placeholder, when `attempts == 0`) match exactly how Task 1
   writes pre-populated rows (`attempts: 0, accuracy: 0.0`) — the two
   tasks agree on what that placeholder means downstream.
