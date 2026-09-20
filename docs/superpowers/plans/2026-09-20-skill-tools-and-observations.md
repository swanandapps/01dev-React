# Prerequisite-Aware Tools + Skill Observations

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make the three highest-value, already-designed-but-unbuilt pieces
real: (1) expose the already-built `get_prerequisite_view` as a tool Hermes
can actually call, (2) give the agent a narrow, safe way to log an
observation about a student mid-conversation (not a graded score — a
read/reflect, not raw SQL), (3) make sure the skill-graph data those two
things depend on actually exists for a student who only chats, not just
one who uses the adaptive-quiz feature.

**Scope:** Single learner (`beingswanand@gmail.com`), matching every prior
slice this session.

**Architecture:** All three land in the same two files that already own
this concern — `backend/app/services/skill_graph_service.py` (the
functions) and `backend/app/mcp/the01dev_tools.py` (the thin MCP wrappers
Hermes calls) — plus one small, surgical addition to
`backend/app/main.py`'s existing `hermes_chat` handler.

**Tech Stack:** Same as the rest of this backend — Python 3.10+, `store`
abstraction, pytest.

**Spec:** This session's conversation. Key decisions, and why:

- **A real, pre-existing bug gets fixed as part of Task 1, not worked
  around.** `search_history` (already deployed, already registered as a
  tool) takes `student_id` as a parameter the MODEL must supply — but
  `student_id` is never written into the system prompt anywhere. The tool
  has never been genuinely callable. The two new tools in this plan need
  the same two identifiers (`student_id`, `course_id`), so fixing this
  once, for all three tools, is the correct move — not duplicating the
  same broken pattern a third time.
- **The write tool never touches `attempts`/`correct`/`accuracy`.** Those
  three fields mean one specific thing today — graded-event results — and
  4 existing services (`journey_service`, `course_insight_service`,
  `recommendation_service`, `tutor_service`) trust that meaning. A
  chat-inferred "this student seems shaky on X" is a real, useful signal,
  but it is not a graded score, and conflating the two would corrupt data
  those 4 services already depend on. It lands in new, separate fields on
  the same row instead.
- **No raw SQL, ever, for the write path** — matches the "narrow typed
  tool, not a SQL string" decision from earlier in this session. The tool
  takes `concept`, `confidence` (an enum: `weak`/`developing`/`strong`),
  and `note` (free text) — nothing that could be misused as a query.
- **Pre-population now fires from chat too**, using the exact same
  `ensure_populated` function `adaptive_service.start()` already calls —
  not a second implementation, the same one, from a second call site.

## Global Constraints

- Do not modify `journey_service.py`, `course_insight_service.py`,
  `recommendation_service.py`, or `tutor_service.py` — additive only,
  exactly as the prior skill-graph slice required.
- Do not add or change `attempts`, `correct`, or `accuracy` semantics on
  `concept_performance` rows. New fields only.
- The two new MCP tools follow the same parameter pattern already
  established by `search_history` (`student_id`/`course_id` as explicit,
  model-supplied parameters) — not a new identity mechanism.
- `ensure_populated` calls from the chat path must be non-fatal (wrapped
  in try/except, matching how `adaptive_service.start()` already calls it)
  — a back-fill failure must never break a student's chat turn.

---

### Task 1: Inject identity context into the system prompt

**Files:**
- Modify: `backend/app/main.py` — the `persona`/`system` construction in
  `hermes_chat` (currently around the `persona = gepa_service.read_soul() + ...`
  line — read the current exact line numbers before editing, this plan's
  earlier tasks have already shifted this file's line numbers twice).
- Create: `backend/tests/test_hermes_chat_identity_context.py`

**Interfaces:**
- Produces: no new function — this is a string-construction change to the
  existing `system` prompt variable inside `hermes_chat`. The two new MCP
  tools in Task 2/3 depend on the model actually having `student_id` and
  `course_id` values available to pass as tool arguments.

- [ ] **Step 1: Write the failing test**

```python
# backend/tests/test_hermes_chat_identity_context.py
from app.services import hermes_client
from fastapi.testclient import TestClient

from app.main import app


def test_system_prompt_includes_student_and_course_ids(monkeypatch):
    from app.services import audit_service, memory_service

    captured = {}

    async def _capture_stream_chat(question, system=None, history=None):
        captured["system"] = system
        yield {"type": "done"}

    async def _noop_log_event(**kwargs):
        return None

    async def _empty_memory_context(*args, **kwargs):
        return ""

    async def _empty_recent_turns(*args, **kwargs):
        return []

    async def _noop_record_turn(*args, **kwargs):
        return None

    monkeypatch.setattr(hermes_client, "stream_chat", _capture_stream_chat)
    monkeypatch.setattr(audit_service, "log_event", _noop_log_event)
    monkeypatch.setattr(memory_service, "memory_context", _empty_memory_context)
    monkeypatch.setattr(memory_service, "recent_turns", _empty_recent_turns)
    monkeypatch.setattr(memory_service, "record_turn", _noop_record_turn)

    client = TestClient(app)
    resp = client.post(
        "/api/hermes/chat",
        json={
            "question": "What is a closure?",
            "user_id": "identity-test-student",
            "course_slug": "js-fundamentals",
        },
    )
    assert resp.status_code == 200
    assert "identity-test-student" in captured["system"]
    assert "js-fundamentals" in captured["system"]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && .venv/bin/pytest tests/test_hermes_chat_identity_context.py -v`
Expected: FAIL — `AssertionError` (the ids aren't in the system prompt yet)

- [ ] **Step 3: Add the identity line to the system prompt**

Open `backend/app/main.py` and find the existing line:

```python
    persona = gepa_service.read_soul() + f"\nYou are tutoring the '{course_slug}' course on the01.dev. "
```

Change it to also state the literal ids tools need (insert this directly
after that line, still before `memory_block` is used):

```python
    persona = gepa_service.read_soul() + f"\nYou are tutoring the '{course_slug}' course on the01.dev. "
    persona += (
        f"\nFor any tool that takes student_id or course_id, use exactly "
        f"student_id=\"{student_id}\" and course_id=\"{course_slug}\" — never guess or ask the "
        f"student for these, you already have them."
    )
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd backend && .venv/bin/pytest tests/test_hermes_chat_identity_context.py -v`
Expected: PASS

- [ ] **Step 5: Run the full suite**

Run: `cd backend && .venv/bin/pytest tests -v`
Expected: all PASS (46 existing + 1 new = 47)

- [ ] **Step 6: Commit**

```bash
git add backend/app/main.py backend/tests/test_hermes_chat_identity_context.py
git commit -m "fix: give Hermes the actual student_id/course_id to pass to identity-scoped tools"
```

---

### Task 2: `get_concept_confidence` MCP tool

**Files:**
- Modify: `backend/app/mcp/the01dev_tools.py` — add one new `@mcp.tool()`
  function alongside the existing ones.
- Create: `backend/tests/test_mcp_get_concept_confidence.py`

**Interfaces:**
- Consumes: `app.services.skill_graph_service.get_prerequisite_view(user_id, course_id, concept) -> dict`
  (already exists, already tested — Task 1 of the prior skill-graph plan).
- Produces: `get_concept_confidence` tool, callable by Hermes with
  `(concept: str, course_id: str, student_id: str)`.

- [ ] **Step 1: Write the failing test**

```python
# backend/tests/test_mcp_get_concept_confidence.py
import pytest


@pytest.mark.asyncio
async def test_get_concept_confidence_wraps_get_prerequisite_view(monkeypatch):
    from app.mcp import the01dev_tools

    async def fake_get_prerequisite_view(user_id, course_id, concept):
        assert (user_id, course_id, concept) == ("student-1", "js-fundamentals", "closures")
        return {
            "concept": "closures", "accuracy": 0.6, "attempts": 5, "attempted": True,
            "prerequisites": [
                {"concept": "scope", "accuracy": 0.3, "attempts": 2, "attempted": True},
            ],
            "weakest_prerequisite": {"concept": "scope", "accuracy": 0.3, "attempts": 2, "attempted": True},
        }

    monkeypatch.setattr(the01dev_tools, "get_prerequisite_view", fake_get_prerequisite_view)

    result = await the01dev_tools.get_concept_confidence(
        concept="closures", course_id="js-fundamentals", student_id="student-1",
    )

    assert result["concept"] == "closures"
    assert result["weakest_prerequisite"]["concept"] == "scope"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && .venv/bin/pytest tests/test_mcp_get_concept_confidence.py -v`
Expected: FAIL — `AttributeError` (function doesn't exist yet)

- [ ] **Step 3: Add the tool**

Add this to `backend/app/mcp/the01dev_tools.py`, in the imports block
(alongside the existing `from app.services import grounding, content,
memory_service` line) add `skill_graph_service`:

```python
with contextlib.redirect_stdout(sys.stderr):
    from app.services.vector_store import vector_store
    from app.services.embeddings import embedding_service
    from app.services import grounding, content, memory_service, skill_graph_service
```

Then add, near `search_history` (same "cross-session" section makes
sense, or its own section — your call, keep it adjacent to
`search_history` since both take `student_id`):

```python
from app.services.skill_graph_service import get_prerequisite_view


# ── Prerequisite-aware confidence (thin wrapper over skill_graph_service) ─────
@mcp.tool()
async def get_concept_confidence(concept: str, course_id: str, student_id: str) -> dict:
    """Check how confident this student is on a concept AND on everything that
    concept depends on, in one call — use this BEFORE teaching something that has
    prerequisites, so you can address a shaky prerequisite instead of teaching on
    top of a gap the student doesn't know they have.

    Returns the target concept's accuracy/attempts, a list of its prerequisites
    with the same shape, and `weakest_prerequisite` (the lowest-accuracy
    prerequisite that has actually been attempted — `null` if none have been).
    `accuracy: null` on any entry means the student has never been graded on it
    yet, not that they scored zero — do not treat null as a bad score.

    Args:
        concept: The concept to check (must match a concept tag used in this course).
        course_id: The course's id/slug — use the exact value you were given for
            this conversation.
        student_id: This student's id — use the exact value you were given for
            this conversation, never a different one.
    """
    return await get_prerequisite_view(student_id, course_id, concept)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd backend && .venv/bin/pytest tests/test_mcp_get_concept_confidence.py -v`
Expected: PASS

- [ ] **Step 5: Run the full suite**

Run: `cd backend && .venv/bin/pytest tests -v`
Expected: all PASS

- [ ] **Step 6: Commit**

```bash
git add backend/app/mcp/the01dev_tools.py backend/tests/test_mcp_get_concept_confidence.py
git commit -m "feat: expose get_prerequisite_view to Hermes as get_concept_confidence"
```

---

### Task 3: `record_skill_observation` write tool + chat-side pre-population

**Files:**
- Modify: `backend/app/services/skill_graph_service.py` — add
  `record_observation(...)`.
- Modify: `backend/app/mcp/the01dev_tools.py` — add the
  `record_skill_observation` tool.
- Modify: `backend/app/main.py` — call `ensure_populated` from the chat
  path too.
- Create/modify: `backend/tests/test_skill_graph_service.py` (append),
  `backend/tests/test_mcp_record_skill_observation.py` (new),
  `backend/tests/test_hermes_chat_routing.py` (append one test).

**Interfaces:**
- Produces:
  `app.services.skill_graph_service.record_observation(user_id: str, course_id: str, concept: str, confidence: str, note: str) -> dict`
  (async) — writes `chat_confidence`, `chat_confidence_note`,
  `chat_confidence_updated_at` onto the SAME `concept_performance` row
  `ensure_populated`/`_update_perf` already use (creating a pre-populated
  row first via `ensure_populated`-style upsert if none exists), never
  touching `attempts`/`correct`/`accuracy`. Returns the updated row.
- Produces: `record_skill_observation` MCP tool wrapping it, callable with
  `(concept: str, course_id: str, student_id: str, confidence: str, note: str)`.

- [ ] **Step 1: Write the failing tests for `record_observation`**

Append to `backend/tests/test_skill_graph_service.py`:

```python
@pytest.mark.asyncio
async def test_record_observation_adds_fields_without_touching_graded_data():
    from app.services import skill_graph_service

    written = {
        "student-1__closures": {
            "user_id": "student-1", "concept": "closures",
            "attempts": 5, "correct": 4, "accuracy": 0.8,
            "course_id": "js-fundamentals",
        }
    }

    async def fake_get(collection, doc_id):
        return written.get(doc_id)

    async def fake_set(collection, doc_id, data):
        written[doc_id] = data

    import unittest.mock as mock
    with mock.patch.object(skill_graph_service.store, "get", fake_get), \
         mock.patch.object(skill_graph_service.store, "set", fake_set):
        result = await skill_graph_service.record_observation(
            "student-1", "js-fundamentals", "closures", "weak",
            "Struggled to explain closures in their own words.",
        )

    row = written["student-1__closures"]
    # Graded fields untouched.
    assert row["attempts"] == 5
    assert row["correct"] == 4
    assert row["accuracy"] == 0.8
    # New observational fields present.
    assert row["chat_confidence"] == "weak"
    assert row["chat_confidence_note"] == "Struggled to explain closures in their own words."
    assert "chat_confidence_updated_at" in row
    assert result == row


@pytest.mark.asyncio
async def test_record_observation_creates_row_if_none_exists():
    from app.services import skill_graph_service

    written: dict = {}

    async def fake_get(collection, doc_id):
        return written.get(doc_id)

    async def fake_set(collection, doc_id, data):
        written[doc_id] = data

    import unittest.mock as mock
    with mock.patch.object(skill_graph_service.store, "get", fake_get), \
         mock.patch.object(skill_graph_service.store, "set", fake_set):
        await skill_graph_service.record_observation(
            "student-2", "js-fundamentals", "hoisting", "strong", "Explained it correctly unprompted.",
        )

    row = written["student-2__hoisting"]
    assert row["attempts"] == 0
    assert row["chat_confidence"] == "strong"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd backend && .venv/bin/pytest tests/test_skill_graph_service.py -v -k record_observation`
Expected: FAIL — `AttributeError`

- [ ] **Step 3: Implement `record_observation`**

Append to `backend/app/services/skill_graph_service.py`:

```python
from datetime import datetime, timezone

_VALID_CONFIDENCE = {"weak", "developing", "strong"}


async def record_observation(
    user_id: str, course_id: str, concept: str, confidence: str, note: str,
) -> dict:
    """Log a chat-inferred observation about a student's grasp of a concept —
    NOT a graded score. Writes to separate chat_confidence* fields on the same
    concept_performance row ensure_populated/_update_perf use; attempts/correct/
    accuracy (the graded-event fields 4 other services depend on) are never
    touched here. Creates a zeroed row first if this student has no row for
    this concept yet, so an observation can happen before any graded event."""
    if confidence not in _VALID_CONFIDENCE:
        raise ValueError(f"confidence must be one of {sorted(_VALID_CONFIDENCE)}, got {confidence!r}")

    doc_id = _perf_id(user_id, concept)
    row = await store.get(PERF_COLLECTION, doc_id) or {
        "user_id": user_id, "concept": concept,
        "attempts": 0, "correct": 0, "accuracy": 0.0,
        "course_id": course_id,
    }
    row["chat_confidence"] = confidence
    row["chat_confidence_note"] = note
    row["chat_confidence_updated_at"] = datetime.now(timezone.utc).isoformat()
    await store.set(PERF_COLLECTION, doc_id, row)
    return row
```

Note: this file currently imports `_perf_id` from `adaptive_service`
(function-local import inside `ensure_populated`, added in the prior
slice's final-review fix round) — reuse that same import inside
`record_observation` rather than importing it again at module level,
matching how `ensure_populated` already does it (avoids the same
circular-import hazard documented there).

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd backend && .venv/bin/pytest tests/test_skill_graph_service.py -v`
Expected: all PASS

- [ ] **Step 5: Write the failing MCP tool test**

```python
# backend/tests/test_mcp_record_skill_observation.py
import pytest


@pytest.mark.asyncio
async def test_record_skill_observation_wraps_record_observation(monkeypatch):
    from app.mcp import the01dev_tools

    async def fake_record_observation(user_id, course_id, concept, confidence, note):
        assert (user_id, course_id, concept, confidence, note) == (
            "student-1", "js-fundamentals", "closures", "weak", "some note",
        )
        return {"concept": "closures", "chat_confidence": "weak"}

    monkeypatch.setattr(the01dev_tools, "record_observation", fake_record_observation)

    result = await the01dev_tools.record_skill_observation(
        concept="closures", course_id="js-fundamentals", student_id="student-1",
        confidence="weak", note="some note",
    )

    assert result == {"concept": "closures", "chat_confidence": "weak"}


@pytest.mark.asyncio
async def test_record_skill_observation_rejects_bad_confidence_without_crashing():
    from app.mcp import the01dev_tools

    result = await the01dev_tools.record_skill_observation(
        concept="closures", course_id="js-fundamentals", student_id="student-1",
        confidence="super-duper-good", note="x",
    )
    assert "error" in result
```

- [ ] **Step 6: Run test to verify it fails**

Run: `cd backend && .venv/bin/pytest tests/test_mcp_record_skill_observation.py -v`
Expected: FAIL — `AttributeError`

- [ ] **Step 7: Add the tool**

Add to `backend/app/mcp/the01dev_tools.py`, alongside
`get_concept_confidence`:

```python
from app.services.skill_graph_service import record_observation


# ── Skill observation write (thin wrapper over skill_graph_service.record_observation) ─
@mcp.tool()
async def record_skill_observation(
    concept: str, course_id: str, student_id: str, confidence: str, note: str,
) -> dict:
    """Log what you've noticed about this student's grasp of a concept from the
    conversation — NOT a quiz score. Call this whenever the conversation makes
    their understanding clear either way (they explained it correctly unprompted,
    or they were clearly confused/wrong about it) — you don't need to ask
    permission, this is internal bookkeeping, not a consequential action.

    confidence must be exactly one of: "weak", "developing", "strong".
    Do not call this for vague or ambiguous signals — only when the
    conversation actually showed you something concrete.

    Args:
        concept: The concept this observation is about.
        course_id: The course's id/slug — use the exact value you were given
            for this conversation.
        student_id: This student's id — use the exact value you were given
            for this conversation, never a different one.
        confidence: "weak" | "developing" | "strong".
        note: One sentence — what you actually observed, in plain language.
    """
    try:
        return await record_observation(student_id, course_id, concept, confidence, note)
    except ValueError as e:
        return {"error": str(e)}
```

- [ ] **Step 8: Run test to verify it passes**

Run: `cd backend && .venv/bin/pytest tests/test_mcp_record_skill_observation.py -v`
Expected: PASS

- [ ] **Step 9: Wire `ensure_populated` into the chat path**

In `backend/app/main.py`, inside `hermes_chat`, find where `intent =
classify(question)` is called (read the current file to confirm the exact
surrounding lines — this file has been edited by every task in this
session, confirm before assuming line numbers). Immediately after
classifying the intent, before the `QUIZ_GENERATE`/`PROGRESS_LOOKUP`
short-circuit, add:

```python
    try:
        await skill_graph_service.ensure_populated(student_id, course_slug)
    except Exception as e:  # noqa: BLE001 — back-fill is never allowed to break a chat turn
        print(f"[hermes_chat] ensure_populated failed for {student_id}/{course_slug}: {e}")
```

Add the import near the other local imports:

```python
from app.services import skill_graph_service
```

(Check whether `app.services` is already imported as a namespace or via
individual names in this file's existing import block — match whatever
pattern is already there rather than introducing a new import style.)

- [ ] **Step 10: Write the failing integration test**

Append to `backend/tests/test_hermes_chat_routing.py`:

```python
def test_course_question_backfills_skill_graph(client, monkeypatch):
    from app.services import hermes_client, skill_graph_service

    calls = []

    async def fake_ensure_populated(user_id, course_id):
        calls.append((user_id, course_id))
        return 0

    async def _fake_stream_chat(question, system=None, history=None):
        yield {"type": "token", "value": "ok"}
        yield {"type": "done"}

    monkeypatch.setattr(skill_graph_service, "ensure_populated", fake_ensure_populated)
    monkeypatch.setattr(hermes_client, "stream_chat", _fake_stream_chat)

    resp = client.post(
        "/api/hermes/chat",
        json={"question": "What is a closure?", "user_id": "backfill-test", "course_slug": "js-fundamentals"},
    )
    assert resp.status_code == 200
    assert ("backfill-test", "js-fundamentals") in calls


def test_backfill_failure_does_not_break_chat(client, monkeypatch):
    from app.services import hermes_client, skill_graph_service

    async def fake_ensure_populated(user_id, course_id):
        raise RuntimeError("skill graph service is down")

    async def _fake_stream_chat(question, system=None, history=None):
        yield {"type": "token", "value": "ok"}
        yield {"type": "done"}

    monkeypatch.setattr(skill_graph_service, "ensure_populated", fake_ensure_populated)
    monkeypatch.setattr(hermes_client, "stream_chat", _fake_stream_chat)

    resp = client.post(
        "/api/hermes/chat",
        json={"question": "What is a closure?", "user_id": "backfill-fail-test", "course_slug": "js-fundamentals"},
    )
    assert resp.status_code == 200
```

- [ ] **Step 11: Run tests to verify they fail, then pass after Step 9's edit**

Run: `cd backend && .venv/bin/pytest tests/test_hermes_chat_routing.py -v`
Expected: FAIL before Step 9's edit is in place, PASS after.

- [ ] **Step 12: Run the full suite**

Run: `cd backend && .venv/bin/pytest tests -v`
Expected: all PASS

- [ ] **Step 13: Manual smoke test against the real running app + real Hermes**

Same pattern as every prior slice this session: run `hermes gateway run`
locally, run this backend locally against it, and send one real request
that should trigger BOTH new tools in a single turn, e.g.:

```bash
curl -sN -X POST http://127.0.0.1:8099/api/hermes/chat \
  -H "Content-Type: application/json" \
  -d '{"question":"Check my confidence on closures and its prerequisites, then note that I seem weak on scope based on this conversation.","user_id":"smoke-test","course_slug":"js-fundamentals"}'
```

Paste the actual raw output into the report — this is the first time
either new tool has ever been exercised against a real Hermes instance,
and per this session's established practice, that must be observed, not
assumed from the unit tests alone.

- [ ] **Step 14: Commit**

```bash
git add backend/app/services/skill_graph_service.py backend/app/mcp/the01dev_tools.py backend/app/main.py backend/tests/test_skill_graph_service.py backend/tests/test_mcp_record_skill_observation.py backend/tests/test_hermes_chat_routing.py
git commit -m "feat: add record_skill_observation write tool, back-fill skill graph from chat"
```

---

## Self-Review

1. **Spec coverage:** all 3 prioritized items from this session's ranking
   are covered — Task 2 = "wire up get_prerequisite_view", Task 3 =
   "narrow write tool" + "fire pre-population from chat too" (bundled
   since the write tool needs a row to exist, same dependency Task 3
   documents). Task 1 is a genuine pre-existing bug found while designing
   Task 2 (search_history's parameter was never satisfiable) — fixed once,
   shared by all three tools, not silently worked around per-tool.
2. **Placeholder scan:** no TBD/TODO; every step has real code.
3. **Type consistency:** `get_prerequisite_view(user_id, course_id, concept)`
   used identically between its existing definition and Task 2's tool
   wrapper. `record_observation(user_id, course_id, concept, confidence, note)`
   used identically between Task 3's definition, its tests, and the MCP
   tool wrapper. `ensure_populated(user_id, course_id)` used identically
   between its existing definition (prior slice), `adaptive_service.start()`'s
   existing call, and Task 3's new call from `hermes_chat`.
