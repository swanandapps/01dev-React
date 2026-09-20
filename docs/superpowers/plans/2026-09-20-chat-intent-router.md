# Chat Intent Router (first slice) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Give `/api/hermes/chat` a real, backend-owned intent classifier instead of a
client-supplied `agentic` flag; make quiz requests do something correct
(hand off to QuizMe) instead of silently falling through to course-RAG or a
declined answer; and make progress questions ("what's my progress?") call
the real, already-built `journey_service.get_journey()` instead of also
falling through to course-RAG, where it currently gets an ungrounded or
declined non-answer.

**Architecture:** A pure, rule-based classifier (`app/routing/intent.py`)
runs once per request, right after PII scrubbing. `QUIZ_GENERATE` short-circuits
into a new hand-off response before any retrieval/model call happens.
Everything else (`COURSE_QUESTION`, and the existing agentic/grounded/decline
branching) is untouched — this is a pre-filter inserted into the existing
handler, not a rewrite. No new endpoint, no new directory tree for a single
route — `contracts/`/`orchestration/` from `PRIMARY_REPO_MIGRATION_PLAN.md`
only earns its keep once there's a second route to share it with.

**Tech Stack:** Python 3.10+, FastAPI, Pydantic v2 (already in use), pytest +
pytest-asyncio (new dev dependencies — this backend has zero test
infrastructure today).

**Spec:** `PRIMARY_REPO_MIGRATION_PLAN.md` §5 (router design) and §12
(recommended first implementation slice) — this plan implements a narrower,
codebase-grounded version of that slice. Deviations from the spec, and why:
- No `/api/chat` endpoint yet — `/api/hermes/chat` already has PII scrub,
  audit, memory, grounding, tracing; duplicating it behind a new route before
  there's a second consumer would violate DRY for no current benefit.
- `quiz_generate` does not route into `lesson_service`'s LangGraph graph —
  that graph's contract (`POST /upload-text` → `POST /lessons {docId}`)
  requires uploaded notes, not a bare topic string ("quiz me on closures").
  Faking a call to it would either error or silently produce a quiz from no
  material. The correct behavior today is a clear, honest hand-off telling
  the student to use QuizMe with their notes — not a fake pipeline.
- `agentic` routing (course-RAG vs. Hermes agent loop) stays client-supplied
  for this slice. Making that a backend policy decision is real, separate
  work (`PRIMARY_REPO_MIGRATION_PLAN.md`'s "Agent selection" gap) — a rule
  can't safely decide when to grant tool access; it needs the auth/authz
  work from Phase 1, which is explicitly out of scope here.
- No `schedule_lookup` intent. There is no live-class/calendar data model
  anywhere in this product (course content in `frontend/src/data/tracks.ts`
  is static, pre-recorded video, not scheduled cohorts) — adding a route
  with nothing behind it would mean building a fake answer. Not built.
- No text-to-SQL / open-ended structured-query route. This is a legitimate
  pattern for genuinely open-ended structured questions, but two
  prerequisites aren't in place yet: (1) production data lives in one
  generic `docs(collection, doc_id, data jsonb)` table (`store.py`), not the
  typed tables §9 of the spec calls for — text-to-SQL needs a documented,
  typed schema to be safe/accurate, not a JSON blob; (2) safely sandboxing
  LLM-generated SQL (read-only DB role, curated views, mandatory server-side
  identity injection, static validation of the generated query before
  execution) is a real task on its own. Tracked as explicit future work
  below, not attempted here under demo time pressure.
- Classification stays rule-based (regex/keyword), not a HuggingFace/ML
  classifier. No labeled routing data exists yet to validate thresholds
  against, and a model adds load-time latency and a new failure mode for a
  live demo. Matches the spec's own §5 guidance to start with rules and
  upgrade only once there's a routing log to evaluate against.

## Future work (explicitly not in this plan)

- **Typed data model migration** (`PRIMARY_REPO_MIGRATION_PLAN.md` §9), then
  a guarded `structured_query` intent: read-only DB role, a curated set of
  views (not raw tables), server-injected `student_id` filter (never
  trusted from model output), and static validation (e.g. via `sqlglot`)
  that the generated SQL is a single `SELECT` against an allow-listed view
  before it runs.
- A learned intent classifier (sentence-embedding + logistic regression, or
  a small HF zero-shot model) once there's a real routing log from this
  rule-based version to evaluate it against.
- `schedule_lookup`, if/when this product gains a live-class calendar
  feature to back it.
- `memory_service.record_turn(...)` is not called for quiz/progress hand-off
  turns (matches the plan's own originally-specified code) — so a student
  who gets the QuizMe hand-off and immediately asks a follow-up like "how do
  I do that?" won't have the hand-off turn in their conversation memory;
  that follow-up will be classified as a normal course question with no
  context of the hand-off.
- `agentic=true` clients are now diverted to the QUIZ_GENERATE/
  PROGRESS_LOOKUP hand-offs before reaching the Hermes agent loop, for
  those two intents specifically — this narrows the "agentic routing stays
  client-supplied" statement elsewhere in this plan; worth reconciling
  explicitly if `agentic` semantics matter for those two intents later.

## Global Constraints

- Do not modify or remove `/api/ai/ask`, `/api/ai/ask/stream`, or the
  existing grounded/decline/agentic branches inside `/api/hermes/chat` —
  only insert a classifier check before them.
- The classifier must never guess into `COURSE_QUESTION` on ambiguity in a
  way that silently changes existing behavior — default/unmatched input
  falls through to today's exact existing logic unchanged.
- No network calls in the classifier — pure function, testable without
  mocks.
- Every new module gets tests. This repo has no test runner configured yet;
  Task 1 sets that up.

---

### Task 1: Test scaffolding + intent contract + classifier

**Files:**
- Create: `backend/pytest.ini`
- Create: `backend/tests/__init__.py` (empty)
- Create: `backend/tests/routing/__init__.py` (empty)
- Create: `backend/app/routing/__init__.py` (empty)
- Create: `backend/app/routing/intent.py`
- Create: `backend/tests/routing/test_intent.py`
- Modify: `backend/requirements.txt` — add `pytest==8.3.4` and
  `pytest-asyncio==0.25.2` under a new `# --- dev/test ---` section at the
  bottom (kept in the same file since this repo has no separate
  `requirements-dev.txt`; follow that existing single-file convention).

**Interfaces:**
- Produces: `app.routing.intent.Intent` (a `str` Enum: `COURSE_QUESTION`,
  `QUIZ_GENERATE`, `PROGRESS_LOOKUP`, `OUT_OF_SCOPE`), and
  `app.routing.intent.classify(question: str) -> Intent`.

- [ ] **Step 1: Write the failing tests**

```python
# backend/tests/routing/test_intent.py
import pytest

from app.routing.intent import Intent, classify

QUIZ_EXAMPLES = [
    "Can you quiz me on closures?",
    "Make a quiz on React hooks",
    "quiz me",
    "Create a test for the useEffect lecture",
    "I want to test myself on this course",
    "give me a practice quiz about async/await",
]

PROGRESS_EXAMPLES = [
    "What's my progress so far?",
    "How am I doing in this course?",
    "show me my learning journey",
    "what are my strengths and weaknesses",
    "am I improving",
    "what's my quiz streak",
]

COURSE_QUESTION_EXAMPLES = [
    "What is a closure in JavaScript?",
    "Explain useCallback vs useMemo",
    "Can you summarize lecture 4.1?",
    "why does my component re-render every time",
    "what did we cover last week",
]

OUT_OF_SCOPE_EXAMPLES = [
    "",
    "   ",
    "asdkjaslkdj",
]


@pytest.mark.parametrize("question", QUIZ_EXAMPLES)
def test_classifies_quiz_requests(question):
    assert classify(question) == Intent.QUIZ_GENERATE


@pytest.mark.parametrize("question", PROGRESS_EXAMPLES)
def test_classifies_progress_requests(question):
    assert classify(question) == Intent.PROGRESS_LOOKUP


@pytest.mark.parametrize("question", COURSE_QUESTION_EXAMPLES)
def test_classifies_course_questions(question):
    assert classify(question) == Intent.COURSE_QUESTION


@pytest.mark.parametrize("question", OUT_OF_SCOPE_EXAMPLES)
def test_classifies_empty_or_junk_as_out_of_scope(question):
    assert classify(question) == Intent.OUT_OF_SCOPE


def test_quiz_keyword_inside_a_real_question_does_not_misfire():
    # "test" appears, but this is a course question about testing, not a
    # request to BE quizzed — the rule must key off the imperative pattern,
    # not the bare word.
    assert classify("What's the difference between unit tests and integration tests?") == Intent.COURSE_QUESTION


def test_progress_takes_priority_over_quiz_when_both_words_appear():
    # "quiz" appears, but this is asking to REVIEW past quiz performance,
    # not to be quizzed — progress rules must be checked before quiz rules.
    assert classify("how did I do on my last quiz") == Intent.PROGRESS_LOOKUP
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd backend && python -m pytest tests/routing/test_intent.py -v`
Expected: `ERROR ... ModuleNotFoundError: No module named 'app.routing'`

- [ ] **Step 3: Write `pytest.ini` so `app.*` imports resolve from `backend/`**

```ini
# backend/pytest.ini
[pytest]
pythonpath = .
testpaths = tests
asyncio_mode = auto
```

`asyncio_mode = auto` lets Task 3's `async def test_...` functions run
without an explicit `@pytest.mark.asyncio` on each one — pytest-asyncio
handles them automatically.

- [ ] **Step 4: Write the classifier**

```python
# backend/app/routing/intent.py
"""
Deterministic, rule-based intent classification for the chat endpoint.

No ML here on purpose — PRIMARY_REPO_MIGRATION_PLAN.md §5 explicitly says
not to block the router contract on training infrastructure. High-precision
rules first; a learned classifier is a drop-in replacement behind the same
`classify(question) -> Intent` signature later, once there's a labeled
routing log to train it on.
"""
import re
from enum import Enum


class Intent(str, Enum):
    COURSE_QUESTION = "course_question"
    QUIZ_GENERATE = "quiz_generate"
    PROGRESS_LOOKUP = "progress_lookup"
    OUT_OF_SCOPE = "out_of_scope"


# Checked FIRST: "how did I do on my last quiz" mentions "quiz" but is a
# review of past performance, not a request to be quizzed. Progress rules
# must win that overlap, so they're matched before the quiz rules below.
_PROGRESS_PATTERNS = [
    re.compile(r"\bmy\s+(progress|journey|streak|strengths?|weakness(es)?)\b", re.I),
    re.compile(r"\bhow\s+(am\s+i|did\s+i)\s+(doing|do)\b", re.I),
    re.compile(r"\bam\s+i\s+(improving|getting\s+better)\b", re.I),
    re.compile(r"\bshow\s+me\s+my\s+(progress|journey|stats)\b", re.I),
]

# Imperative "quiz/test me" patterns — deliberately narrow so a course
# question that merely mentions "test" (e.g. "unit tests vs integration
# tests") doesn't misfire into QUIZ_GENERATE.
_QUIZ_PATTERNS = [
    re.compile(r"\bquiz\s+me\b", re.I),
    re.compile(r"\b(make|create|give|build|generate)\s+(me\s+)?(a\s+)?(quick\s+)?(quiz|practice\s+quiz|test)\b", re.I),
    re.compile(r"\btest\s+(myself|me)\b", re.I),
    re.compile(r"\bcan\s+you\s+quiz\s+me\b", re.I),
]


def classify(question: str) -> Intent:
    q = (question or "").strip()
    if not q or not re.search(r"[a-zA-Z0-9]", q):
        return Intent.OUT_OF_SCOPE
    for pattern in _PROGRESS_PATTERNS:
        if pattern.search(q):
            return Intent.PROGRESS_LOOKUP
    for pattern in _QUIZ_PATTERNS:
        if pattern.search(q):
            return Intent.QUIZ_GENERATE
    return Intent.COURSE_QUESTION
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `cd backend && python -m pytest tests/routing/test_intent.py -v`
Expected: all PASS

- [ ] **Step 6: Commit**

```bash
git add backend/pytest.ini backend/tests backend/app/routing backend/requirements.txt
git commit -m "feat: add rule-based chat intent classifier"
```

---

### Task 2: Quiz hand-off response

**Files:**
- Create: `backend/app/routing/quiz_handoff.py`
- Create: `backend/tests/routing/test_quiz_handoff.py`

**Interfaces:**
- Consumes: nothing (pure).
- Produces: `app.routing.quiz_handoff.build_handoff_message(course_slug: str) -> str`
  — a single user-facing sentence, used by Task 4 to build the existing SSE
  `token`/`done` event shape (no new event schema needed).

- [ ] **Step 1: Write the failing test**

```python
# backend/tests/routing/test_quiz_handoff.py
from app.routing.quiz_handoff import build_handoff_message


def test_handoff_mentions_quizme_and_the_course():
    msg = build_handoff_message("react-performance")
    assert "QuizMe" in msg
    assert "notes" in msg.lower()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && python -m pytest tests/routing/test_quiz_handoff.py -v`
Expected: FAIL — `ModuleNotFoundError`

- [ ] **Step 3: Write the implementation**

```python
# backend/app/routing/quiz_handoff.py
"""
QuizMe (lesson_service, LangGraph) only builds a quiz from uploaded notes —
it has no "quiz me on <topic>" entry point. Until that gap is closed, a chat
request classified as QUIZ_GENERATE gets an honest hand-off instead of a
fake or silently-wrong answer.
"""


def build_handoff_message(course_slug: str) -> str:
    return (
        "I can't build a quiz straight from chat yet — QuizMe needs your "
        "notes first. Head to the QuizMe tab, upload the notes you want "
        f"quizzed on from '{course_slug}', and it'll generate questions "
        "from that material."
    )
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd backend && python -m pytest tests/routing/test_quiz_handoff.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add backend/app/routing/quiz_handoff.py backend/tests/routing/test_quiz_handoff.py
git commit -m "feat: add honest QuizMe hand-off for quiz-intent chat requests"
```

---

### Task 3: Progress-lookup response

**Files:**
- Create: `backend/app/routing/progress_handoff.py`
- Create: `backend/tests/routing/test_progress_handoff.py`

**Interfaces:**
- Consumes: `app.services.journey_service.get_journey(user_id: str) -> dict`
  (already exists — returns `{"metrics": {...}, "heatmap": [...],
  "strengths": [...], "weaknesses": [...], "ai": {"narrative": str,
  "insights": [...], "focus": str}}`).
- Produces: `app.routing.progress_handoff.build_progress_message(student_id: str) -> str`
  (async), used by Task 4 the same way `build_handoff_message` is.

- [ ] **Step 1: Write the failing test**

```python
# backend/tests/routing/test_progress_handoff.py
import pytest

from app.routing.progress_handoff import build_progress_message


@pytest.mark.asyncio
async def test_progress_message_surfaces_the_existing_narrative(monkeypatch):
    from app.routing import progress_handoff

    async def fake_get_journey(user_id):
        assert user_id == "student-42"
        return {
            "metrics": {"quizzes": 3, "avg_score": 0.75},
            "heatmap": [],
            "strengths": [{"concept": "closures", "accuracy": 0.9, "attempts": 4}],
            "weaknesses": [{"concept": "async/await", "accuracy": 0.4, "attempts": 3}],
            "ai": {
                "narrative": "You've been consistent this week.",
                "insights": ["You do best in the mornings."],
                "focus": "Review async/await next.",
            },
        }

    monkeypatch.setattr(progress_handoff, "get_journey", fake_get_journey)
    msg = await build_progress_message("student-42")
    assert "You've been consistent this week." in msg
    assert "Review async/await next." in msg


@pytest.mark.asyncio
async def test_progress_message_handles_no_activity_yet(monkeypatch):
    from app.routing import progress_handoff

    async def fake_get_journey(user_id):
        return {
            "metrics": {"quizzes": 0, "avg_score": 0.0},
            "heatmap": [],
            "strengths": [],
            "weaknesses": [],
            "ai": {"narrative": "No activity yet.", "insights": [], "focus": "Take your first quiz to start tracking."},
        }

    monkeypatch.setattr(progress_handoff, "get_journey", fake_get_journey)
    msg = await build_progress_message("new-student")
    assert "No activity yet." in msg
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd backend && python -m pytest tests/routing/test_progress_handoff.py -v`
Expected: FAIL — `ModuleNotFoundError`

- [ ] **Step 3: Write the implementation**

```python
# backend/app/routing/progress_handoff.py
"""
Turns the existing `journey_service.get_journey()` payload (already built
for the dashboard) into one chat-friendly message, so PROGRESS_LOOKUP
requests reuse the real analytics instead of getting an ungrounded or
declined non-answer from the RAG path.
"""
from app.services.journey_service import get_journey


async def build_progress_message(student_id: str) -> str:
    journey = await get_journey(student_id)
    ai = journey.get("ai") or {}
    parts = [ai.get("narrative", "").strip()]
    focus = ai.get("focus", "").strip()
    if focus:
        parts.append(focus)
    return " ".join(p for p in parts if p)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd backend && python -m pytest tests/routing/test_progress_handoff.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add backend/app/routing/progress_handoff.py backend/tests/routing/test_progress_handoff.py
git commit -m "feat: surface existing journey analytics as a chat progress response"
```

---

### Task 4: Wire the classifier into `/api/hermes/chat`

**Files:**
- Modify: `backend/app/main.py:204-260` (the `hermes_chat` handler — insert
  the classifier call right after the PII scrub, before the `tutor_client`
  resolution; short-circuit `QUIZ_GENERATE` before any retrieval/model call)
- Create: `backend/tests/test_hermes_chat_routing.py`

**Interfaces:**
- Consumes: `app.routing.intent.classify` (Task 1),
  `app.routing.quiz_handoff.build_handoff_message` (Task 2),
  `app.routing.progress_handoff.build_progress_message` (Task 3).
- Produces: a new `span.set_attribute("intent", ...)` on the existing
  `hermes_chat` OTel span, and a `data: {"type":"token",...}` /
  `data: {"type":"done"}` SSE pair for the quiz/progress hand-offs — same
  event shape the client already parses, so the frontend needs no changes
  for this slice.

- [ ] **Step 1: Write the failing integration test**

```python
# backend/tests/test_hermes_chat_routing.py
import json

import pytest
from fastapi.testclient import TestClient

from app.main import app


@pytest.fixture
def client(monkeypatch):
    # Never touch Postgres/OpenAI/audit storage from this test — it's
    # asserting routing behavior, not the downstream services' correctness.
    from app.services import audit_service, memory_service

    async def _noop_log_event(**kwargs):
        return None

    async def _empty_memory_context(*args, **kwargs):
        return ""

    async def _empty_recent_turns(*args, **kwargs):
        return []

    async def _noop_record_turn(*args, **kwargs):
        return None

    monkeypatch.setattr(audit_service, "log_event", _noop_log_event)
    monkeypatch.setattr(memory_service, "memory_context", _empty_memory_context)
    monkeypatch.setattr(memory_service, "recent_turns", _empty_recent_turns)
    monkeypatch.setattr(memory_service, "record_turn", _noop_record_turn)
    return TestClient(app)


def _sse_events(raw_text: str) -> list[dict]:
    events = []
    for line in raw_text.splitlines():
        if line.startswith("data:"):
            events.append(json.loads(line[len("data:"):].strip()))
    return events


def test_quiz_intent_short_circuits_before_any_model_call(client, monkeypatch):
    # If routing is broken and this falls through to the real grounded/agentic
    # path, these would be hit and (without network) raise — the test fails
    # loudly instead of silently calling out to OpenAI/Hermes.
    from app.services import grounding

    async def _fail_if_called(*args, **kwargs):
        raise AssertionError("retrieval must not run for a QUIZ_GENERATE request")

    monkeypatch.setattr(grounding, "retrieve", _fail_if_called)

    resp = client.post(
        "/api/hermes/chat",
        json={
            "question": "Can you quiz me on closures?",
            "user_id": "test-student",
            "course_slug": "js-fundamentals",
        },
    )
    assert resp.status_code == 200
    events = _sse_events(resp.text)
    tokens = "".join(e["value"] for e in events if e.get("type") == "token")
    assert "QuizMe" in tokens
    assert any(e.get("type") == "done" for e in events)


def test_course_question_intent_is_unaffected(client, monkeypatch):
    # Not asserting the full grounded-answer path here (that's rag_service's
    # own concern) — only that a normal question is NOT diverted into the
    # quiz hand-off.
    from app.services import grounding

    async def _empty_retrieve(*args, **kwargs):
        return []

    monkeypatch.setattr(grounding, "retrieve", _empty_retrieve)

    resp = client.post(
        "/api/hermes/chat",
        json={
            "question": "What is a closure?",
            "user_id": "test-student",
            "course_slug": "js-fundamentals",
        },
    )
    assert resp.status_code == 200
    events = _sse_events(resp.text)
    tokens = "".join(e["value"] for e in events if e.get("type") == "token")
    assert "QuizMe" not in tokens


def test_progress_intent_calls_journey_service_not_the_model(client, monkeypatch):
    from app.routing import progress_handoff
    from app.services import grounding

    async def _fail_if_called(*args, **kwargs):
        raise AssertionError("retrieval must not run for a PROGRESS_LOOKUP request")

    async def _fake_get_journey(user_id):
        assert user_id == "test-student"
        return {"ai": {"narrative": "You're making steady progress.", "insights": [], "focus": "Keep it up."}}

    monkeypatch.setattr(grounding, "retrieve", _fail_if_called)
    monkeypatch.setattr(progress_handoff, "get_journey", _fake_get_journey)

    resp = client.post(
        "/api/hermes/chat",
        json={
            "question": "What's my progress so far?",
            "user_id": "test-student",
            "course_slug": "js-fundamentals",
        },
    )
    assert resp.status_code == 200
    events = _sse_events(resp.text)
    tokens = "".join(e["value"] for e in events if e.get("type") == "token")
    assert "You're making steady progress." in tokens
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd backend && python -m pytest tests/test_hermes_chat_routing.py -v`
Expected: FAIL — quiz test fails because nothing short-circuits yet (falls
into the real decline/grounded path and "QuizMe" never appears).

- [ ] **Step 3: Insert the classifier + short-circuit into `main.py`**

In `app/main.py`, add the import near the other local imports (around line
30, alongside the existing `hermes_client, ollama_client, ...` import
block):

```python
from app.routing.intent import Intent, classify
from app.routing.quiz_handoff import build_handoff_message
from app.routing.progress_handoff import build_progress_message
```

Then, immediately after the existing PII-scrub line
(`question, pii_kinds = pii.scrub(question)`) and before the OTel span
block, insert:

```python
    intent = classify(question)
```

Add the intent to the existing span attributes block (right after
`span.set_attribute("agentic", agentic)`):

```python
    span.set_attribute("intent", intent.value)
```

Then, right before the existing `# Resolve which engine answers` comment
(the `if agentic: tutor_client = hermes_client ...` block), insert the
short-circuit. Both hand-offs stream the same way, so this factors into one
inline generator taking the message and an outcome label:

```python
    if intent in (Intent.QUIZ_GENERATE, Intent.PROGRESS_LOOKUP):
        if intent == Intent.QUIZ_GENERATE:
            outcome, model_label = "quiz_handoff", "rule-based-router"
            message = build_handoff_message(course_slug)
        else:
            outcome, model_label = "progress_handoff", "rule-based-router"
            message = await build_progress_message(student_id)

        span.set_attribute("outcome", outcome)
        await audit_service.log_event(
            student_id=student_id, course_slug=course_slug, question=question,
            model=model_label, provider="none",
        )

        async def gen_handoff():
            try:
                yield f"data: {json.dumps({'type': 'sources', 'sources': [], 'insufficient_context': False, 'offer_general': False})}\n\n"
                for word in message.split(" "):
                    yield f"data: {json.dumps({'type': 'token', 'value': word + ' '})}\n\n"
                yield f"data: {json.dumps({'type': 'done'})}\n\n"
            finally:
                span.end()

        return StreamingResponse(
            gen_handoff(),
            media_type="text/event-stream",
            headers={"Cache-Control": "no-cache", "Connection": "keep-alive", "X-Accel-Buffering": "no"},
        )
```

This mirrors the existing handler's own SSE conventions and audit-logging
pattern exactly (same event shapes, same `audit_service.log_event` call
signature already used a few lines below it) — nothing new for the frontend
or the audit trail to learn.

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd backend && python -m pytest tests/ -v`
Expected: all PASS (Task 1 + 2 + 3 tests)

- [ ] **Step 5: Manual smoke test against the real running app**

Run the app (`uvicorn app.main:app --reload` from `backend/`) and:

```bash
curl -sN -X POST http://127.0.0.1:8000/api/hermes/chat \
  -H "Content-Type: application/json" \
  -d '{"question":"quiz me on closures","user_id":"smoke-test","course_slug":"js-fundamentals"}'
```

Expected: SSE stream whose `token` events assemble into the QuizMe
hand-off message, ending in `{"type":"done"}` — no OpenAI/Hermes call made
(check there's no `llm_generate` span logged/printed). Repeat with
`{"question":"what's my progress so far?", ...}` and confirm the tokens
assemble into a real narrative from `journey_service`.

- [ ] **Step 6: Commit**

```bash
git add backend/app/main.py backend/tests/test_hermes_chat_routing.py
git commit -m "feat: route quiz- and progress-intent chat requests to real handlers"
```

---

## Self-Review

1. **Spec coverage:** §5's `RouteDecision`/intent concept → implemented as
   `Intent` + `classify()` (Task 1), narrower (rules only, 4 intents) per
   §5's own "don't block on training infra" guidance. §12's "quiz_generate"
   step → implemented as a real hand-off (Task 2/4), not a fake pipeline
   call, because the underlying service's contract doesn't support a
   topic-only request yet — documented as a deviation above, not silently
   dropped. `progress_lookup` (not in §12's original 3, added per this
   session's discussion) → implemented as a real call into the existing
   `journey_service.get_journey()` (Task 3/4), not a new analytics
   computation. §12's "out_of_scope" step → already exists today via the
   grounding-threshold decline path; `Intent.OUT_OF_SCOPE` from the
   classifier is reserved for empty/junk input, a distinct, narrower case,
   to avoid the classifier fighting with the existing grounding-based
   decline logic. `course_question` → intentionally the unchanged existing
   path (no task needed — that's the point of the pre-filter design).
2. **Placeholder scan:** no TBD/TODO, no "add error handling" hand-waves —
   every step has real code or a real test.
3. **Type consistency:** `Intent` used identically across Tasks 1–4
   (`Intent.QUIZ_GENERATE`, `Intent.PROGRESS_LOOKUP`, `Intent.COURSE_QUESTION`,
   `Intent.OUT_OF_SCOPE`); `build_handoff_message(course_slug: str) -> str`
   matches between Task 2's definition and Task 4's call site;
   `build_progress_message(student_id: str) -> str` (async) matches between
   Task 3's definition and Task 4's call site.
