# Lab Phase 2 — Concept Resolver, Learner-Model Coupling, Explainability — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make self-study quizzing count toward one unified learner model — resolving concepts onto existing course concepts where they match, creating new graph nodes where they don't — and let a student ask *"why is this my strong topic?"* and get a truthful, sourced answer.

**Architecture:** One `concept_resolver` that every concept write goes through (course quizzes, Hermes chat observations, Lab quizzes). Resolution is slug match → embedding cosine at 0.64 → create a new node. Because resolution happens at quiz *generation* time, generated questions carry canonical concept ids and the existing grading path needs no changes. Explainability reads per-answer data that `quiz_sessions` already stores.

**Tech Stack:** FastAPI, Postgres via the `store` abstraction, OpenAI `text-embedding-3-small` via the existing `embedding_service`, LangGraph, pytest.

**Spec:** `docs/superpowers/specs/2026-09-22-lab-content-pipeline-design.md`

**Depends on:** Phase 1 plan (`2026-09-22-lab-phase0-1-merge-and-parity.md`) complete — `app/services/lab/` exists and `/api/lab/*` is live.

## Global Constraints

- **Threshold is `0.64`**, derived from 31 measured pairs. Do not change it to a "rounder" number. True matches observed at 0.709–0.755; false matches cap at 0.578. An earlier 0.9 draft would have merged nothing at all — even `React.memo` vs `react-memo` scores only 0.755.
- **Normalize and resolve on the write path only.** Never rewrite existing `concept_performance` rows. `_perf_id` is `f"{user_id}__{concept}"`, so changing a concept's spelling changes its doc id and would orphan every existing row — including the seeded demo data for `x94FcfXU7KRrobyOA4UHDukbRoC2` and `3f95EO0xaqM4TMP0g7iD1BD4z4u1`.
- **Self-study concept nodes get `course_id: None`, not a sentinel string.** A string like `"self-study"` would surface in `get_concept_confidence` output and the model would treat it as a real course name — the exact bug that produced *"you're enrolled in the course called all-courses"* earlier in this project. The doc id uses a `self-study::` prefix for uniqueness; the **field** stays `None`.
- **This phase removes Phase 1's no-writes constraint.** `tests/test_lab_routes.py::test_phase_1_writes_nothing_to_the_learner_model` must be deleted in Task 5, not left failing.
- **Every resolution decision is logged**, including near-misses. That log is the only real tuning data and it feeds the student-facing explanation.
- Tests: `bash backend/scripts/run_tests.sh`. New MCP-tool tests go in that script's `MCP_ONLY_TESTS` array (Task 7 adds one).
- Deploys: backend `railway up --service the01dev-backend`; Hermes `railway up --service the01dev-hermes` **is required whenever `app/mcp/the01dev_tools.py` changes** — that file is baked into the Hermes image at build time.

---

## File Structure

**Created:**
- `app/services/concept_resolver.py` — slugify, resolve, node creation, decision logging
- `app/services/concept_explain.py` — `explain_concept()` over `quiz_sessions`
- `backend/tests/test_concept_resolver.py`
- `backend/tests/test_concept_explain.py`
- `backend/tests/test_mcp_explain_concept.py`
- `backend/tests/test_lab_learner_model_writes.py`

**Modified:**
- `app/services/lab/llm.py` — `gen_quiz` emits `concept`
- `app/services/lab/schemas.py` — `Question` gains a `concept` field
- `app/services/lab/routes.py` — `SubmitReq` accepts per-answer results; writes the learner model
- `app/services/skill_graph_service.py` — `record_observation` resolves its concept
- `app/mcp/the01dev_tools.py` — new `explain_concept` tool
- `backend/scripts/run_tests.sh` — register the new MCP test
- `frontend/src/lib/notesQuizApiLang.ts` — `submitResult` sends per-answer results
- `frontend/src/lib/notesQuizApi.ts` — `Question` type gains optional `concept` (type source only; its functions stay unused)
- `frontend/src/components/learn/NotesQuizModal.tsx` — accumulate per-answer results
- `backend/tests/test_lab_routes.py` — delete the Phase 1 no-writes test

---

### Task 1: The concept resolver

**Files:**
- Create: `backend/app/services/concept_resolver.py`
- Test: `backend/tests/test_concept_resolver.py`

**Interfaces:**
- Consumes: `app.services.store.store`, `app.services.embeddings.embedding_service.embed`
- Produces:
  - `slugify(name: str) -> str`
  - `async resolve(candidate: str, course_id: str | None = None) -> str` — returns the canonical concept **name** to key `concept_performance` on
  - `SIMILARITY_THRESHOLD: float = 0.64`
  - `CONCEPTS = "concepts"`, `RESOLUTIONS = "concept_resolutions"`

- [ ] **Step 1: Write the failing tests**

Create `backend/tests/test_concept_resolver.py`:

```python
import pytest

from app.services import concept_resolver
from app.services.store import InMemoryStore


@pytest.mark.parametrize("raw,expected", [
    ("React.memo", "react-memo"),
    ("useCallback hook", "usecallback-hook"),
    ("  Event  Loop  ", "event-loop"),
    ("V8 Hidden Classes!", "v8-hidden-classes"),
    ("closures", "closures"),
])
def test_slugify(raw, expected):
    assert concept_resolver.slugify(raw) == expected


@pytest.fixture
def store(monkeypatch):
    s = InMemoryStore()
    monkeypatch.setattr(concept_resolver, "store", s)
    return s


def _stub_embeddings(monkeypatch, vectors: dict[str, list[float]]):
    """Map exact text -> vector; anything unmapped gets an orthogonal vector."""
    async def fake_embed(text):
        return vectors.get(text, [0.0, 0.0, 1.0])
    from app.services import embeddings
    monkeypatch.setattr(embeddings.embedding_service, "embed", fake_embed)


@pytest.mark.asyncio
async def test_exact_slug_match_resolves_without_embedding(store, monkeypatch):
    await store.set("concepts", "react-perf::react-memo",
                    {"course_id": "react-perf", "name": "react-memo"})

    async def fail_embed(text):
        raise AssertionError("must not embed when the slug matches exactly")

    from app.services import embeddings
    monkeypatch.setattr(embeddings.embedding_service, "embed", fail_embed)

    assert await concept_resolver.resolve("React.memo") == "react-memo"


@pytest.mark.asyncio
async def test_embedding_match_above_threshold_resolves_to_existing(store, monkeypatch):
    await store.set("concepts", "react-perf::use-callback", {
        "course_id": "react-perf", "name": "use-callback", "embedding": [1.0, 0.0, 0.0],
    })
    _stub_embeddings(monkeypatch, {"useCallback hook": [0.95, 0.31, 0.0]})  # cos ~0.95

    assert await concept_resolver.resolve("useCallback hook") == "use-callback"


@pytest.mark.asyncio
async def test_below_threshold_creates_a_new_node(store, monkeypatch):
    await store.set("concepts", "react-perf::event-loop", {
        "course_id": "react-perf", "name": "event-loop", "embedding": [1.0, 0.0, 0.0],
    })
    _stub_embeddings(monkeypatch, {"kubernetes": [0.0, 1.0, 0.0]})  # cos 0.0

    assert await concept_resolver.resolve("kubernetes") == "kubernetes"
    node = await store.get("concepts", "self-study::kubernetes")
    assert node is not None
    assert node["name"] == "kubernetes"
    assert node["created_by"] == "student_content"
    # MUST be None, not a sentinel string — a string would read to the model as
    # a real course name (the "all-courses" bug).
    assert node["course_id"] is None
    assert node["embedding"] == [0.0, 1.0, 0.0]


@pytest.mark.asyncio
async def test_new_node_from_a_lecture_source_attaches_to_that_course(store, monkeypatch):
    _stub_embeddings(monkeypatch, {"Fiber Architecture": [0.0, 1.0, 0.0]})

    assert await concept_resolver.resolve("Fiber Architecture", course_id="react-perf") \
        == "fiber-architecture"
    node = await store.get("concepts", "react-perf::fiber-architecture")
    assert node["course_id"] == "react-perf"


@pytest.mark.asyncio
async def test_every_decision_is_logged_with_its_score(store, monkeypatch):
    await store.set("concepts", "react-perf::use-callback", {
        "course_id": "react-perf", "name": "use-callback", "embedding": [1.0, 0.0, 0.0],
    })
    _stub_embeddings(monkeypatch, {"useCallback hook": [0.95, 0.31, 0.0]})

    await concept_resolver.resolve("useCallback hook")
    logged = await store.list_all("concept_resolutions")
    assert len(logged) == 1
    entry = logged[0]
    assert entry["candidate"] == "useCallback hook"
    assert entry["resolved_to"] == "use-callback"
    assert entry["method"] == "embedding"
    assert entry["score"] > 0.64


@pytest.mark.asyncio
async def test_a_created_concept_is_logged_as_created(store, monkeypatch):
    _stub_embeddings(monkeypatch, {"kubernetes": [0.0, 1.0, 0.0]})
    await concept_resolver.resolve("kubernetes")
    entry = (await store.list_all("concept_resolutions"))[0]
    assert entry["method"] == "created"
    assert entry["resolved_to"] == "kubernetes"


@pytest.mark.asyncio
async def test_second_resolution_of_the_same_candidate_hits_the_slug_path(store, monkeypatch):
    _stub_embeddings(monkeypatch, {"kubernetes": [0.0, 1.0, 0.0]})
    await concept_resolver.resolve("kubernetes")   # creates the node

    async def fail_embed(text):
        raise AssertionError("second resolution must hit the slug path, not embed again")

    from app.services import embeddings
    monkeypatch.setattr(embeddings.embedding_service, "embed", fail_embed)

    assert await concept_resolver.resolve("Kubernetes") == "kubernetes"
```

- [ ] **Step 2: Run the tests to verify they fail**

```bash
cd /Users/swanandkadam/Desktop/01dev-React-hermes/backend
.venv/bin/python -m pytest tests/test_concept_resolver.py -v
```

Expected: FAIL — `ModuleNotFoundError: No module named 'app.services.concept_resolver'`.

- [ ] **Step 3: Write the resolver**

Create `backend/app/services/concept_resolver.py`:

```python
"""
One concept space, resolved rather than siloed.

Every concept write goes through here — the graded course quiz
(adaptive_service), Hermes's chat observations (skill_graph_service
.record_observation), and Lab quizzes built from a student's own material.

The product requirement this serves: a student studying closures from their own
notes should move the *existing* `closures` weights, while a student studying
Kubernetes — which no course covers — should get a new concept node rather than
having their work discarded or forced into our vocabulary.

Resolution order: exact slug match (free) → embedding cosine >= 0.64 → create.

On the threshold: 0.64 is the midpoint of an empty band measured across 31
pairs. True matches sat at 0.709-0.755 (`React.memo`/`react-memo` = 0.755,
`useCallback hook`/`use-callback` = 0.709); false matches capped at 0.578
(`Event Delegation`/`event-loop`). Short concept NAMES do not score like
sentences — unrelated short strings share a noise floor around 0.33-0.38, and a
0.9 threshold merges nothing at all. Expect this to need RAISING as the concept
pool grows: with 9 concepts there are 9 chances to draw a spurious high score,
with 500 there are 500.

Never rewrites existing rows. `adaptive_service._perf_id` is
f"{user_id}__{concept}", so changing a concept's spelling changes its doc id
and would orphan the row.
"""
import re
from datetime import datetime, timezone

from app.services.embeddings import embedding_service
from app.services.store import store

CONCEPTS = "concepts"
RESOLUTIONS = "concept_resolutions"
SIMILARITY_THRESHOLD = 0.64

# Doc-id scope for a concept that belongs to no course. The `course_id` FIELD
# stays None — a sentinel string there would surface in get_concept_confidence
# and read to the model as a real course name.
_SELF_STUDY_SCOPE = "self-study"


def slugify(name: str) -> str:
    """'React.memo' -> 'react-memo'. Lowercase, non-alphanumerics to hyphens."""
    s = re.sub(r"[^a-z0-9]+", "-", str(name or "").lower())
    return s.strip("-")


def _cosine(a: list[float], b: list[float]) -> float:
    dot = sum(x * y for x, y in zip(a, b))
    na = sum(x * x for x in a) ** 0.5
    nb = sum(y * y for y in b) ** 0.5
    if na == 0 or nb == 0:
        return 0.0
    return dot / (na * nb)


async def _log(candidate: str, resolved_to: str, method: str, score: float) -> None:
    ts = datetime.now(timezone.utc).isoformat()
    await store.set(RESOLUTIONS, f"{slugify(candidate)}__{ts}", {
        "candidate": candidate,
        "resolved_to": resolved_to,
        "method": method,           # slug | embedding | created
        "score": round(score, 3),
        "at": ts,
    })


async def resolve(candidate: str, course_id: str | None = None) -> str:
    """Canonical concept name to key concept_performance on.

    `course_id` is the INGEST SOURCE's course, not a filter — the search pool is
    always every known concept, because a self-study concept resolving onto a
    course concept is the whole point. It only affects a newly created node: a
    concept first seen in a course lecture attaches to that course; one from an
    uploaded PDF attaches to nothing.
    """
    slug = slugify(candidate)
    if not slug:
        return ""

    known = await store.list_all(CONCEPTS)

    # 1. exact slug match — free, no API call
    for c in known:
        if slugify(c.get("name", "")) == slug:
            await _log(candidate, c["name"], "slug", 1.0)
            return c["name"]

    # 2. embedding compare against cached concept embeddings
    candidate_vec = await embedding_service.embed(candidate)
    best_name, best_score = None, 0.0
    for c in known:
        vec = c.get("embedding")
        if not vec:
            continue
        score = _cosine(candidate_vec, vec)
        if score > best_score:
            best_name, best_score = c.get("name"), score

    if best_name is not None and best_score >= SIMILARITY_THRESHOLD:
        await _log(candidate, best_name, "embedding", best_score)
        return best_name

    # 3. create a new node — the graph grows to fit the student
    scope = course_id or _SELF_STUDY_SCOPE
    await store.set(CONCEPTS, f"{scope}::{slug}", {
        "course_id": course_id,     # None for self-study, deliberately not a string
        "name": slug,
        "description": "",
        "created_by": "student_content",
        "embedding": candidate_vec,  # cached so the pool is never re-embedded
        "created_at": datetime.now(timezone.utc).isoformat(),
    })
    await _log(candidate, slug, "created", best_score)
    return slug
```

- [ ] **Step 4: Run the tests to verify they pass**

```bash
.venv/bin/python -m pytest tests/test_concept_resolver.py -v
```

Expected: 12 passed (5 slugify params + 7 async tests).

- [ ] **Step 5: Commit**

```bash
cd /Users/swanandkadam/Desktop/01dev-React-hermes
git add backend/app/services/concept_resolver.py backend/tests/test_concept_resolver.py
git commit -m "feat: concept resolver — one growing concept space

Slug match, then embedding cosine at 0.64, then create a new node. Notes on
a concept a course already teaches move that concept's weights; notes on
something no course covers get a new graph node instead of being discarded.

0.64 is measured, not guessed: 31 pairs put true matches at 0.709-0.755 and
false matches at or below 0.578. Self-study nodes carry course_id=None
rather than a sentinel string, which would read to the model as a real
course name."
```

---

### Task 2: `gen_quiz` emits a concept per question

Resolution runs at generation time so the grading path needs no changes — but that only works if generated questions carry a concept.

**Files:**
- Modify: `backend/app/services/lab/schemas.py` (`Question`)
- Modify: `backend/app/services/lab/llm.py` (`gen_quiz` prompt + resolution)
- Test: `backend/tests/test_lab_quiz_concepts.py`

**Interfaces:**
- Consumes: `concept_resolver.resolve`
- Produces: `gen_quiz(document, objective, n, course_id=None) -> list[dict]` where each dict now includes `concept: str` (a resolved canonical name)

- [ ] **Step 1: Write the failing test**

Create `backend/tests/test_lab_quiz_concepts.py`:

```python
import pytest

from app.services.lab import llm as lab_llm


@pytest.mark.asyncio
async def test_gen_quiz_attaches_resolved_concepts(monkeypatch):
    # gen_quiz is sync (LangGraph's interrupt context only propagates on the
    # sync path), so it resolves concepts via asyncio.run internally. Patch the
    # resolver to a deterministic stub.
    def fake_chat_json(system, user, max_tokens=900):
        assert "concept" in system, "prompt must ask the model for a concept tag"
        return {"questions": [
            {"question": "What does React.memo skip?", "options": ["a1", "b1", "c1", "d1"],
             "correctIndex": 0, "explanation": "because", "hint": "nudge",
             "concept": "React.memo"},
        ]}

    async def fake_resolve(candidate, course_id=None):
        assert candidate == "React.memo"
        return "react-memo"

    monkeypatch.setattr(lab_llm, "_chat_json", fake_chat_json)
    monkeypatch.setattr(lab_llm, "resolve_concept", fake_resolve)

    out = lab_llm.gen_quiz("material", {"title": "Memoization", "difficulty": "beginner",
                                        "focus": "memo"}, 1)
    assert out[0]["concept"] == "react-memo"
    # the interactive UI's required fields must survive
    assert out[0]["hint"] and out[0]["explanation"]
    assert out[0]["correctIndex"] == 0


@pytest.mark.asyncio
async def test_question_without_a_concept_falls_back_to_the_objective_title(monkeypatch):
    def fake_chat_json(system, user, max_tokens=900):
        return {"questions": [
            {"question": "Q?", "options": ["a", "b", "c", "d"], "correctIndex": 1,
             "explanation": "e", "hint": "h"},  # model omitted `concept`
        ]}

    seen = []

    async def fake_resolve(candidate, course_id=None):
        seen.append(candidate)
        return "memoization"

    monkeypatch.setattr(lab_llm, "_chat_json", fake_chat_json)
    monkeypatch.setattr(lab_llm, "resolve_concept", fake_resolve)

    out = lab_llm.gen_quiz("material", {"title": "Memoization", "difficulty": "beginner",
                                        "focus": "memo"}, 1)
    assert seen == ["Memoization"], "must fall back to the objective title"
    assert out[0]["concept"] == "memoization"
```

- [ ] **Step 2: Run it to verify it fails**

```bash
cd /Users/swanandkadam/Desktop/01dev-React-hermes/backend
.venv/bin/python -m pytest tests/test_lab_quiz_concepts.py -v
```

Expected: FAIL — `AttributeError: module 'app.services.lab.llm' has no attribute 'resolve_concept'`.

- [ ] **Step 3: Add `concept` to the `Question` schema**

In `backend/app/services/lab/schemas.py`, add the field to `Question` (after `hint`):

```python
    concept: str = ""
```

The existing validators are unaffected — an empty default keeps every current caller valid.

- [ ] **Step 4: Ask the model for a concept and resolve it**

In `backend/app/services/lab/llm.py`, add near the top-level imports:

```python
import asyncio

from app.services.concept_resolver import resolve as resolve_concept
```

In `gen_quiz`'s system prompt, change the JSON contract line to include a concept tag. Replace:

```python
        'correct>","hint":"<nudge that does NOT reveal the answer>"}]}'
```

with:

```python
        'correct>","hint":"<nudge that does NOT reveal the answer>",'
        '"concept":"<2-4 word name of the single concept this question tests>"}]}'
```

Then, after the existing validation loop builds `out`, resolve each question's concept. Add immediately before `gen_quiz`'s `return`:

```python
    # Resolve each question's concept to a canonical name so the grading path
    # writes to one concept space. Sync because LangGraph only propagates the
    # interrupt() context on the synchronous graph path; the FastAPI layer runs
    # the whole graph in a threadpool, so this blocking call never stalls the
    # event loop.
    for q in out:
        candidate = (q.get("concept") or "").strip() or (objective.get("title") or "")
        q["concept"] = asyncio.run(resolve_concept(candidate)) if candidate else ""
```

- [ ] **Step 5: Run the tests to verify they pass**

```bash
.venv/bin/python -m pytest tests/test_lab_quiz_concepts.py -v
```

Expected: 2 passed.

- [ ] **Step 6: Run the full suite**

```bash
bash scripts/run_tests.sh
```

Expected: `ALL PASSED`.

- [ ] **Step 7: Commit**

```bash
cd /Users/swanandkadam/Desktop/01dev-React-hermes
git add backend/app/services/lab/schemas.py backend/app/services/lab/llm.py \
        backend/tests/test_lab_quiz_concepts.py
git commit -m "feat: Lab quiz questions carry a resolved concept

The generator now asks for a concept tag per question and resolves it to a
canonical name, so resolution happens once per quiz instead of once per
answer and the grading path needs no changes. Falls back to the objective
title when the model omits the tag."
```

---

### Task 3: Carry per-answer results through the submit contract

`submitResult(lessonId, score, total)` sends only an aggregate today (`firstTry + 1, questions.length`), so no concept or per-question correctness reaches the backend. Without this, Phase 2's learner-model writes are impossible.

**Files:**
- Modify: `backend/app/services/lab/routes.py` (`SubmitReq`)
- Modify: `frontend/src/lib/notesQuizApi.ts` (`Question` type gains optional `concept`)
- Modify: `frontend/src/lib/notesQuizApiLang.ts` (`submitResult` signature)
- Modify: `frontend/src/components/learn/NotesQuizModal.tsx` (accumulate answers)
- Test: `backend/tests/test_lab_submit_answers.py`

**Interfaces:**
- Produces:
  - `SubmitReq{score: int, total: int, answers: list[dict] = []}` where each answer is `{"concept": str, "correct": bool, "question_index": int}`
  - `submitResult(id: string, score: number, total: number, answers: AnswerResult[]): Promise<LessonView>`
  - `export type AnswerResult = { concept?: string; correct: boolean; question_index: number }`

- [ ] **Step 1: Write the failing test**

Create `backend/tests/test_lab_submit_answers.py`:

```python
import pytest
from fastapi.testclient import TestClient

from app.main import app


@pytest.fixture
def client(monkeypatch):
    from app.services.lab import graph as lab_graph

    monkeypatch.setattr(lab_graph, "gen_objectives", lambda doc, title: [
        {"id": "o1", "title": "Closures", "difficulty": "beginner", "focus": "scope"},
    ])
    monkeypatch.setattr(lab_graph, "gen_quiz", lambda doc, objective, n: [
        {"question": "Q?", "options": ["a", "b", "c", "d"], "correctIndex": 0,
         "explanation": "e", "hint": "h", "concept": "closures"} for _ in range(n)
    ])
    monkeypatch.setattr(lab_graph, "gen_summary", lambda doc, objectives, results: {
        "overall": "ok", "perObjective": [], "studyTips": []})
    return TestClient(app)


def test_submit_accepts_per_answer_results(client):
    doc = client.post("/api/lab/upload-text", json={"text": "Closures."}).json()["docId"]
    lesson = client.post("/api/lab/lessons", json={"docId": doc}).json()
    lid = lesson["id"]
    client.post(f"/api/lab/lessons/{lid}/approve",
                json={"objectives": lesson["plan"]["objectives"], "questionsPerQuiz": 2})

    r = client.post(f"/api/lab/lessons/{lid}/submit", json={
        "score": 1, "total": 2,
        "answers": [
            {"concept": "closures", "correct": True, "question_index": 0},
            {"concept": "closures", "correct": False, "question_index": 1},
        ],
    })
    assert r.status_code == 200
    assert r.json()["status"] == "complete"


def test_submit_without_answers_still_works(client):
    # Backward compatible: an older client that sends only score/total must not 400.
    doc = client.post("/api/lab/upload-text", json={"text": "Closures."}).json()["docId"]
    lesson = client.post("/api/lab/lessons", json={"docId": doc}).json()
    lid = lesson["id"]
    client.post(f"/api/lab/lessons/{lid}/approve",
                json={"objectives": lesson["plan"]["objectives"], "questionsPerQuiz": 1})
    r = client.post(f"/api/lab/lessons/{lid}/submit", json={"score": 1, "total": 1})
    assert r.status_code == 200
```

- [ ] **Step 2: Run it to verify it fails**

```bash
cd /Users/swanandkadam/Desktop/01dev-React-hermes/backend
.venv/bin/python -m pytest tests/test_lab_submit_answers.py -v
```

Expected: the first test FAILS — pydantic rejects the unexpected `answers` field or silently drops it and the assertion on status still passes; confirm by checking the model. If it passes accidentally, add `assert "answers" in SubmitReq.model_fields` to force the failure.

- [ ] **Step 3: Extend `SubmitReq`**

In `backend/app/services/lab/routes.py`, replace:

```python
class SubmitReq(BaseModel):
    score: int
    total: int
```

with:

```python
class AnswerResult(BaseModel):
    concept: str = ""
    correct: bool
    question_index: int = 0


class SubmitReq(BaseModel):
    score: int
    total: int
    # Per-answer detail so the learner model can be written per concept rather
    # than per objective. Defaults to empty so an older client that sends only
    # score/total keeps working.
    answers: list[AnswerResult] = []
```

- [ ] **Step 4: Run the tests to verify they pass**

```bash
.venv/bin/python -m pytest tests/test_lab_submit_answers.py -v
```

Expected: 2 passed.

- [ ] **Step 5: Add `concept` to the frontend `Question` type**

In `frontend/src/lib/notesQuizApi.ts`, find the `Question` type and add:

```typescript
  concept?: string;
```

Also add the new result type next to it:

```typescript
export type AnswerResult = {
  concept?: string;
  correct: boolean;
  question_index: number;
};
```

- [ ] **Step 6: Send the answers from the LangGraph client**

In `frontend/src/lib/notesQuizApiLang.ts`, add `AnswerResult` to the type re-export list, then replace `submitResult`:

```typescript
export function submitResult(
  id: string,
  score: number,
  total: number,
  answers: AnswerResult[] = [],
): Promise<LessonView> {
  return post<LessonView>(`/lessons/${id}/submit`, { score, total, answers });
}
```

Add `AnswerResult` to the `import type { ... }` at the top of that file.

- [ ] **Step 7: Accumulate per-answer results in the modal**

In `frontend/src/components/learn/NotesQuizModal.tsx`:

Add state next to `firstTry` (line ~57):

```typescript
  const [answerLog, setAnswerLog] = useState<AnswerResult[]>([]);
```

Import the type on line 7's `import type { ... }` list: add `AnswerResult`.

In `resetQuizState()` (line ~92), clear it:

```typescript
    setAnswerLog([]);
```

In `handleSubmitAnswer` (line ~142), record the attempt. Replace the body:

```typescript
  async function handleSubmitAnswer() {
    if (selected === null || !lesson?.quiz) return;
    const q = lesson.quiz.questions[qIdx];
    const correct = selected === q.correctIndex;
    if (correct) setFirstTry((n) => n + 1);
    // Log only the FIRST attempt per question — a retry after a hint shouldn't
    // overwrite the fact that the first answer was wrong.
    setAnswerLog((log) =>
      log.some((a) => a.question_index === qIdx)
        ? log
        : [...log, { concept: q.concept, correct, question_index: qIdx }],
    );
    setSubmitted(true);
  }
```

In `handleNext` (line ~149), pass the log:

```typescript
        const view = await api.submitResult(
          lesson.id, firstTry + 1, lesson.quiz.questions.length, answerLog,
        );
```

Widen the `QuizApi` type (line 14-17) so the extra argument type-checks — it is `Pick<typeof quizApi, ...>`, so it follows the client automatically once Step 6 lands. No change needed there; verify with the build.

- [ ] **Step 8: Verify the frontend compiles**

```bash
cd /Users/swanandkadam/Desktop/01dev-React-hermes/frontend
npm run build
```

Expected: clean build.

- [ ] **Step 9: Commit**

```bash
cd /Users/swanandkadam/Desktop/01dev-React-hermes
git add backend/app/services/lab/routes.py backend/tests/test_lab_submit_answers.py \
        frontend/src/lib/notesQuizApi.ts frontend/src/lib/notesQuizApiLang.ts \
        frontend/src/components/learn/NotesQuizModal.tsx
git commit -m "feat: carry per-answer results through the Lab submit contract

submitResult sent only an aggregate score, so no concept or per-question
correctness reached the backend — which made per-concept learner-model
writes impossible. Answers are now logged per question (first attempt only,
so a post-hint retry doesn't erase the original miss) and sent with the
submit. The field defaults to empty, so an older client still works."
```

---

### Task 4: Lab quizzes write the learner model

**Files:**
- Modify: `backend/app/services/lab/routes.py` (write on submit)
- Test: `backend/tests/test_lab_learner_model_writes.py`
- Delete: the Phase 1 constraint test in `backend/tests/test_lab_routes.py`

**Interfaces:**
- Consumes: `adaptive_service._update_perf`, `concept_resolver`
- Produces: `concept_performance` rows (via `_update_perf`) and one `quiz_sessions` row per submitted objective, carrying `source`/`doc_id`/`doc_title`

- [ ] **Step 1: Write the failing tests**

Create `backend/tests/test_lab_learner_model_writes.py`:

```python
import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.services.store import InMemoryStore


@pytest.fixture
def client(monkeypatch):
    from app.services.lab import graph as lab_graph, routes as lab_routes
    from app.services import adaptive_service

    s = InMemoryStore()
    monkeypatch.setattr(lab_routes, "store", s, raising=False)
    monkeypatch.setattr(adaptive_service, "store", s)

    monkeypatch.setattr(lab_graph, "gen_objectives", lambda doc, title: [
        {"id": "o1", "title": "Closures", "difficulty": "beginner", "focus": "scope"},
    ])
    monkeypatch.setattr(lab_graph, "gen_quiz", lambda doc, objective, n: [
        {"question": f"Q{i}?", "options": ["a", "b", "c", "d"], "correctIndex": 0,
         "explanation": "e", "hint": "h", "concept": "closures"} for i in range(n)
    ])
    monkeypatch.setattr(lab_graph, "gen_summary", lambda doc, objectives, results: {
        "overall": "ok", "perObjective": [], "studyTips": []})
    return TestClient(app), s


def _walk_one_objective(c, answers):
    doc = c.post("/api/lab/upload-text",
                 json={"text": "Closures.", "title": "My Notes"}).json()["docId"]
    lesson = c.post("/api/lab/lessons", json={"docId": doc}).json()
    lid = lesson["id"]
    c.post(f"/api/lab/lessons/{lid}/approve",
           json={"objectives": lesson["plan"]["objectives"], "questionsPerQuiz": 2})
    c.post(f"/api/lab/lessons/{lid}/submit",
           json={"score": sum(a["correct"] for a in answers), "total": len(answers),
                 "answers": answers, "student_id": "s1"})
    return lid


@pytest.mark.asyncio
async def test_writes_concept_performance_per_concept(client):
    # async test so the InMemoryStore assertions can be awaited directly;
    # TestClient's sync calls work fine inside an async test.
    c, s = client
    _walk_one_objective(c, [
        {"concept": "closures", "correct": True, "question_index": 0},
        {"concept": "closures", "correct": False, "question_index": 1},
    ])
    row = await s.get("concept_performance", "s1__closures")
    assert row["attempts"] == 2
    assert row["correct"] == 1
    assert row["accuracy"] == 0.5


@pytest.mark.asyncio
async def test_writes_a_quiz_session_with_self_study_provenance(client):
    c, s = client
    _walk_one_objective(c, [{"concept": "closures", "correct": True, "question_index": 0}])
    sessions = await s.query("quiz_sessions", "user_id", "s1")
    assert len(sessions) == 1
    sess = sessions[0]
    assert sess["source"] == "self_study"
    assert sess["doc_title"] == "My Notes"
    assert sess["course_id"] is None
    assert sess["answers"][0]["concept"] == "closures"
    assert sess["answers"][0]["correct"] is True


@pytest.mark.asyncio
async def test_no_student_id_means_no_learner_model_write(client):
    # An anonymous session must not create orphan rows keyed on "".
    c, s = client
    doc = c.post("/api/lab/upload-text", json={"text": "Closures."}).json()["docId"]
    lesson = c.post("/api/lab/lessons", json={"docId": doc}).json()
    lid = lesson["id"]
    c.post(f"/api/lab/lessons/{lid}/approve",
           json={"objectives": lesson["plan"]["objectives"], "questionsPerQuiz": 1})
    c.post(f"/api/lab/lessons/{lid}/submit", json={
        "score": 1, "total": 1,
        "answers": [{"concept": "closures", "correct": True, "question_index": 0}],
    })
    assert await s.list_all("concept_performance") == []
    assert await s.list_all("quiz_sessions") == []
```

- [ ] **Step 2: Run it to verify it fails**

```bash
cd /Users/swanandkadam/Desktop/01dev-React-hermes/backend
.venv/bin/python -m pytest tests/test_lab_learner_model_writes.py -v
```

Expected: FAIL — `student_id` is not a field on `SubmitReq`, and nothing is written.

- [ ] **Step 3: Accept `student_id` and write on submit**

In `backend/app/services/lab/routes.py`, add to `SubmitReq`:

```python
    student_id: str = ""
```

Add to the imports:

```python
from datetime import datetime, timezone

from app.services import adaptive_service
from app.services.store import store
```

Add this helper above the endpoints:

```python
async def _record_learner_model(
    student_id: str, lesson_id: str, doc_id: str, doc_title: str,
    answers: list, score: int, total: int,
) -> None:
    """Fold a completed objective into the ONE learner model.

    Writes the same two collections the course quiz writes, so a self-study
    session moves the same numbers: concept_performance (per concept) and
    quiz_sessions (per session, which is what journey_service reads for the
    streak and quiz counts). Concepts on the questions were already resolved
    to canonical names at generation time.

    `source: "self_study"` and `course_id: None` are the provenance that lets
    explain_concept tell the student WHERE a score came from.
    """
    if not student_id or not answers:
        return   # never create rows keyed on an empty student id

    for a in answers:
        if a.concept:
            await adaptive_service._update_perf(student_id, a.concept, a.correct)

    now = datetime.now(timezone.utc).isoformat()
    session_id = f"lab-{lesson_id}-{len(answers)}-{now}"
    await store.set("quiz_sessions", session_id, {
        "session_id": session_id,
        "user_id": student_id,
        "course_id": None,
        "course_title": doc_title or "Your own material",
        "source": "self_study",
        "doc_id": doc_id,
        "doc_title": doc_title,
        "score": score,
        "total": total,
        "answers": [
            {"question_id": f"{lesson_id}-{a.question_index}", "concept": a.concept,
             "difficulty": "", "correct": a.correct, "time_taken_ms": 0, "lecture": ""}
            for a in answers
        ],
        "concept_breakdown": _breakdown(answers),
        "completed_at": now,
    })


def _breakdown(answers: list) -> list[dict]:
    agg: dict[str, dict] = {}
    for a in answers:
        row = agg.setdefault(a.concept, {"attempts": 0, "correct": 0})
        row["attempts"] += 1
        row["correct"] += 1 if a.correct else 0
    out = [{"concept": c, "attempts": v["attempts"], "correct": v["correct"],
            "accuracy": round(v["correct"] / v["attempts"], 3) if v["attempts"] else 0.0}
           for c, v in agg.items()]
    out.sort(key=lambda r: r["accuracy"])
    return out
```

`DOCS` only holds `{text, title}`, so record the doc id on the lesson when it starts. In `start_lesson`, change the graph input to carry it:

```python
    values = await run_in_threadpool(
        GRAPH.invoke,
        {"doc": doc["text"], "title": doc["title"], "results": [],
         "doc_id": req.docId},
        _cfg(lesson_id),
    )
```

Add `doc_id: str` to `LessonState` in `app/services/lab/graph.py`.

Then call the helper from `submit_result`, after the graph resumes:

```python
@router.post("/lessons/{lesson_id}/submit")
async def submit_result(lesson_id: str, req: SubmitReq):
    v = _state_values(lesson_id)
    _audit("objective_submitted", lesson_id, score=req.score, total=req.total)
    values = await run_in_threadpool(
        GRAPH.invoke,
        Command(resume={"score": req.score, "total": req.total}),
        _cfg(lesson_id),
    )
    try:
        await _record_learner_model(
            req.student_id, lesson_id, v.get("doc_id", ""), v.get("title", ""),
            req.answers, req.score, req.total,
        )
    except Exception as e:  # noqa: BLE001 — never fail a quiz over analytics
        print(f"[lab] learner-model write failed for {lesson_id}: {e}")
    return lesson_view(lesson_id, values)
```

- [ ] **Step 4: Run the tests to verify they pass**

```bash
.venv/bin/python -m pytest tests/test_lab_learner_model_writes.py -v
```

Expected: 3 passed.

- [ ] **Step 5: Delete the Phase 1 constraint test**

It asserted the opposite of what this task implements, and is now obsolete rather than broken.

In `backend/tests/test_lab_routes.py`, delete `test_phase_1_writes_nothing_to_the_learner_model` entirely.

- [ ] **Step 6: Send the student id from the frontend**

In `frontend/src/lib/notesQuizApiLang.ts`, extend `submitResult` to pass it:

```typescript
export function submitResult(
  id: string,
  score: number,
  total: number,
  answers: AnswerResult[] = [],
  studentId = "",
): Promise<LessonView> {
  return post<LessonView>(`/lessons/${id}/submit`, {
    score, total, answers, student_id: studentId,
  });
}
```

In `NotesQuizModal.tsx`, the component needs the id. Add to its props:

```typescript
  studentId?: string;
```

and to the destructured parameters: `studentId = "",`. Pass it at the call site in `handleNext`:

```typescript
        const view = await api.submitResult(
          lesson.id, firstTry + 1, lesson.quiz.questions.length, answerLog, studentId,
        );
```

Then supply it from both render sites. In `frontend/src/pages/NotesQuizPage.tsx`:

```tsx
import { useUserSessionStore } from "../store/userSession";
// inside the component:
const { currentuser } = useUserSessionStore();
// ...
<NotesQuizModal variant="page" studentId={(currentuser?.uid as string) || ""}
                onClose={() => navigate(-1)} />
```

In `frontend/src/components/learn/CourseCompanion.tsx`, it already receives `userId`:

```tsx
{tool === "notes" && <NotesQuizModal studentId={userId} onClose={() => setTool(null)} />}
```

- [ ] **Step 7: Build and run everything**

```bash
cd /Users/swanandkadam/Desktop/01dev-React-hermes/frontend && npm run build
cd ../backend && bash scripts/run_tests.sh
```

Expected: clean build; `ALL PASSED`.

- [ ] **Step 8: Commit**

```bash
cd /Users/swanandkadam/Desktop/01dev-React-hermes
git add -A
git commit -m "feat: Lab quizzes write the one unified learner model

A self-study quiz now moves the same numbers a course quiz does —
concept_performance per resolved concept, plus a quiz_sessions row (what
journey_service reads for streak and quiz counts) carrying source=self_study
and the doc it came from, so explain_concept can say where a score came from.

Anonymous sessions write nothing rather than creating rows keyed on an empty
id. Removes the Phase 1 no-writes test, which asserted the opposite."
```

---

### Task 5: Route `record_observation` through the resolver

Hermes's chat observations accept any concept string and create rows today — the same fragmentation risk, in code we are already touching.

**Files:**
- Modify: `backend/app/services/skill_graph_service.py` (`record_observation`)
- Test: `backend/tests/test_skill_graph_service.py` (add a case)

**Interfaces:**
- Consumes: `concept_resolver.resolve`
- Produces: unchanged signature; the row is now keyed on the resolved concept

- [ ] **Step 1: Write the failing test**

Append to `backend/tests/test_skill_graph_service.py`:

```python
@pytest.mark.asyncio
async def test_record_observation_resolves_the_concept_name(monkeypatch):
    # Hermes may name a concept loosely ("React.memo"); it must land on the
    # canonical row rather than creating a near-duplicate.
    from app.services import concept_resolver, skill_graph_service

    real_store = InMemoryStore()
    monkeypatch.setattr(skill_graph_service, "store", real_store)

    async def fake_resolve(candidate, course_id=None):
        assert candidate == "React.memo"
        return "react-memo"

    monkeypatch.setattr(concept_resolver, "resolve", fake_resolve)

    await skill_graph_service.record_observation(
        "s1", "react-perf", "React.memo", "strong", "explained it unprompted")

    assert await real_store.get("concept_performance", "s1__react-memo") is not None
    assert await real_store.get("concept_performance", "s1__React.memo") is None
```

- [ ] **Step 2: Run it to verify it fails**

```bash
cd /Users/swanandkadam/Desktop/01dev-React-hermes/backend
.venv/bin/python -m pytest tests/test_skill_graph_service.py -k resolves_the_concept -v
```

Expected: FAIL — the row is created at `s1__React.memo`.

- [ ] **Step 3: Resolve before writing**

In `backend/app/services/skill_graph_service.py`, inside `record_observation`, immediately after the `confidence` validation and before `_perf_id` is used:

```python
    # Resolve loosely-named concepts onto the canonical one. Hermes supplies
    # whatever string it inferred from the conversation, and an unresolved
    # "React.memo" would create a near-duplicate of "react-memo".
    from app.services import concept_resolver
    concept = await concept_resolver.resolve(concept, course_id)
```

Note the import is local, matching the existing local-import pattern in this module (documented there as a circular-import guard).

- [ ] **Step 4: Run the tests to verify they pass**

```bash
.venv/bin/python -m pytest tests/test_skill_graph_service.py -v
```

Expected: all pass, including the pre-existing cases.

- [ ] **Step 5: Commit**

```bash
cd /Users/swanandkadam/Desktop/01dev-React-hermes
git add backend/app/services/skill_graph_service.py backend/tests/test_skill_graph_service.py
git commit -m "fix: resolve concept names in record_observation

Hermes supplies whatever string it inferred from the conversation, so an
unresolved 'React.memo' created a near-duplicate of the canonical
'react-memo' row. Same fragmentation the resolver exists to prevent."
```

---

### Task 6: `explain_concept`

**Files:**
- Create: `backend/app/services/concept_explain.py`
- Test: `backend/tests/test_concept_explain.py`

**Interfaces:**
- Consumes: `store.query("quiz_sessions", "user_id", ...)`, `store.list_all("concept_resolutions")`
- Produces: `async explain_concept(user_id: str, concept: str) -> dict` shaped
  `{"concept", "attempts", "correct", "accuracy", "sources": [...], "merged_tags": [...]}`

- [ ] **Step 1: Write the failing tests**

Create `backend/tests/test_concept_explain.py`:

```python
import pytest

from app.services import concept_explain
from app.services.store import InMemoryStore


@pytest.fixture
def store(monkeypatch):
    s = InMemoryStore()
    monkeypatch.setattr(concept_explain, "store", s)
    return s


@pytest.mark.asyncio
async def test_attributes_attempts_to_their_sources(store):
    await store.set("quiz_sessions", "course-1", {
        "user_id": "s1", "course_id": "react-perf",
        "course_title": "React Performance Patterns", "source": "course",
        "completed_at": "2026-09-01T00:00:00+00:00",
        "answers": [
            {"concept": "react-memo", "correct": True},
            {"concept": "react-memo", "correct": True},
            {"concept": "use-memo", "correct": False},
        ],
    })
    await store.set("quiz_sessions", "lab-1", {
        "user_id": "s1", "course_id": None, "doc_title": "React Perf Notes",
        "source": "self_study", "completed_at": "2026-09-18T00:00:00+00:00",
        "answers": [
            {"concept": "react-memo", "correct": True},
            {"concept": "react-memo", "correct": False},
        ],
    })

    out = await concept_explain.explain_concept("s1", "react-memo")

    assert out["attempts"] == 4
    assert out["correct"] == 3
    assert out["accuracy"] == 0.75
    by_label = {s["label"]: s for s in out["sources"]}
    assert by_label["React Performance Patterns"]["attempts"] == 2
    assert by_label["React Performance Patterns"]["correct"] == 2
    assert by_label["React Performance Patterns"]["source"] == "course"
    assert by_label["React Perf Notes"]["attempts"] == 2
    assert by_label["React Perf Notes"]["correct"] == 1
    assert by_label["React Perf Notes"]["source"] == "self_study"


@pytest.mark.asyncio
async def test_surfaces_merged_tags_so_a_merge_is_contestable(store):
    await store.set("concept_resolutions", "r1", {
        "candidate": "useCallback hook", "resolved_to": "use-callback",
        "method": "embedding", "score": 0.709, "at": "2026-09-18T00:00:00+00:00",
    })
    await store.set("concept_resolutions", "r2", {
        "candidate": "use-callback", "resolved_to": "use-callback",
        "method": "slug", "score": 1.0, "at": "2026-09-18T00:00:00+00:00",
    })

    out = await concept_explain.explain_concept("s1", "use-callback")

    # only the non-identical merge is worth showing the student
    assert out["merged_tags"] == [{"candidate": "useCallback hook", "score": 0.709}]


@pytest.mark.asyncio
async def test_unknown_concept_reports_no_attempts(store):
    out = await concept_explain.explain_concept("s1", "kubernetes")
    assert out["attempts"] == 0
    assert out["sources"] == []
    assert out["accuracy"] is None
```

- [ ] **Step 2: Run them to verify they fail**

```bash
cd /Users/swanandkadam/Desktop/01dev-React-hermes/backend
.venv/bin/python -m pytest tests/test_concept_explain.py -v
```

Expected: FAIL — `No module named 'app.services.concept_explain'`.

- [ ] **Step 3: Write it**

Create `backend/app/services/concept_explain.py`:

```python
"""
"Why is this my strong topic?" — answered from data already stored.

concept_performance is only a running counter, so it cannot explain itself.
But quiz_sessions already records every answer with its concept, so the
attribution exists; this module is the read path over it. No new collection.

Also surfaces which loosely-named tags the resolver merged into this concept,
which makes a merge auditable AND contestable: if the student says "those
aren't the same thing", that is the best possible signal to split — from the
person best placed to judge.
"""
from app.services.store import store


async def explain_concept(user_id: str, concept: str) -> dict:
    sessions = await store.query("quiz_sessions", "user_id", user_id)

    buckets: dict[str, dict] = {}
    attempts = correct = 0
    for s in sessions:
        matching = [a for a in s.get("answers", []) if a.get("concept") == concept]
        if not matching:
            continue
        label = s.get("course_title") or s.get("doc_title") or "Unknown source"
        b = buckets.setdefault(label, {
            "label": label,
            "source": s.get("source", "course"),
            "attempts": 0,
            "correct": 0,
            "last_at": s.get("completed_at", ""),
        })
        for a in matching:
            b["attempts"] += 1
            attempts += 1
            if a.get("correct"):
                b["correct"] += 1
                correct += 1
        if s.get("completed_at", "") > b["last_at"]:
            b["last_at"] = s.get("completed_at", "")

    merged = [
        {"candidate": r["candidate"], "score": r.get("score")}
        for r in await store.list_all("concept_resolutions")
        if r.get("resolved_to") == concept and r.get("method") == "embedding"
    ]

    return {
        "concept": concept,
        "attempts": attempts,
        "correct": correct,
        "accuracy": round(correct / attempts, 3) if attempts else None,
        "sources": sorted(buckets.values(), key=lambda b: -b["attempts"]),
        "merged_tags": merged,
    }
```

- [ ] **Step 4: Run the tests to verify they pass**

```bash
.venv/bin/python -m pytest tests/test_concept_explain.py -v
```

Expected: 3 passed.

- [ ] **Step 5: Commit**

```bash
cd /Users/swanandkadam/Desktop/01dev-React-hermes
git add backend/app/services/concept_explain.py backend/tests/test_concept_explain.py
git commit -m "feat: explain_concept — where a concept score actually came from

concept_performance is a bare counter and can't explain itself, but
quiz_sessions already stores every answer with its concept, so this is a
read path over existing data rather than a new collection. Also surfaces
resolver merges, making them auditable and contestable by the student."
```

---

### Task 7: Expose `explain_concept` to Hermes

**Files:**
- Modify: `backend/app/mcp/the01dev_tools.py`
- Modify: `backend/scripts/run_tests.sh` (`MCP_ONLY_TESTS`)
- Test: `backend/tests/test_mcp_explain_concept.py`

**Interfaces:**
- Consumes: `concept_explain.explain_concept`
- Produces: MCP tool `explain_concept(concept: str, student_id: str) -> dict`

- [ ] **Step 1: Write the failing test**

Create `backend/tests/test_mcp_explain_concept.py`:

```python
import pytest


@pytest.mark.asyncio
async def test_explain_concept_wraps_the_service(monkeypatch):
    from app.mcp import the01dev_tools
    from app.services import concept_explain

    async def fake_explain(user_id, concept):
        assert (user_id, concept) == ("student-1", "react-memo")
        return {
            "concept": "react-memo", "attempts": 4, "correct": 3, "accuracy": 0.75,
            "sources": [
                {"label": "React Performance Patterns", "source": "course",
                 "attempts": 2, "correct": 2, "last_at": "2026-09-01T00:00:00+00:00"},
                {"label": "React Perf Notes", "source": "self_study",
                 "attempts": 2, "correct": 1, "last_at": "2026-09-18T00:00:00+00:00"},
            ],
            "merged_tags": [{"candidate": "useCallback hook", "score": 0.709}],
        }

    monkeypatch.setattr(concept_explain, "explain_concept", fake_explain)

    out = await the01dev_tools.explain_concept(concept="react-memo", student_id="student-1")

    assert out["accuracy"] == 0.75
    assert {s["source"] for s in out["sources"]} == {"course", "self_study"}
    assert out["merged_tags"][0]["candidate"] == "useCallback hook"
```

- [ ] **Step 2: Run it to verify it fails**

```bash
cd /Users/swanandkadam/Desktop/01dev-React-hermes/backend
.mcp-venv/bin/python -m pytest tests/test_mcp_explain_concept.py -v
```

Expected: FAIL — `module 'app.mcp.the01dev_tools' has no attribute 'explain_concept'`.

- [ ] **Step 3: Add the tool**

In `backend/app/mcp/the01dev_tools.py`, add `concept_explain` to the guarded import block:

```python
    from app.services import journey_service, knowledge_graph_service, enrollment_service
    from app.services import concept_explain
```

Then add the tool immediately before the `# ── Enrollment` section:

```python
# ── Concept explainability (thin wrapper over concept_explain) ────────────────
@mcp.tool()
async def explain_concept(concept: str, student_id: str) -> dict:
    """WHERE a student's score on one concept came from — use this when they ask
    "why is this my strong/weak topic?", "I never took a course on this, why does
    it say I'm good at it?", or otherwise question a number you reported.

    Returns total `attempts`/`correct`/`accuracy` plus `sources`: one entry per
    course or per piece of the student's own uploaded material, each with its own
    attempts/correct. `source` is "course" or "self_study" — say which, plainly,
    because a student may genuinely not remember quizzing themselves on their own
    notes.

    `merged_tags` lists loosely-named tags that were treated as THIS concept
    (e.g. their notes said "useCallback hook"). Mention them when explaining a
    surprising score, and if the student says those are different things, tell
    them that's useful and worth flagging — they're right to question it.

    `attempts: 0` means no graded attempts exist; say so rather than guessing.

    Args:
        concept: The canonical concept name to explain.
        student_id: This student's id — use the exact value you were given for
            this conversation, never a different one.
    """
    return await concept_explain.explain_concept(student_id, concept)
```

- [ ] **Step 4: Register the test in the MCP venv list**

In `backend/scripts/run_tests.sh`, add to `MCP_ONLY_TESTS`:

```
  tests/test_mcp_explain_concept.py
```

- [ ] **Step 5: Run the tests to verify they pass**

```bash
.mcp-venv/bin/python -m pytest tests/test_mcp_explain_concept.py -v
bash scripts/run_tests.sh
```

Expected: 1 passed, then `ALL PASSED`.

- [ ] **Step 6: Commit**

```bash
cd /Users/swanandkadam/Desktop/01dev-React-hermes
git add backend/app/mcp/the01dev_tools.py backend/scripts/run_tests.sh \
        backend/tests/test_mcp_explain_concept.py
git commit -m "feat: expose explain_concept to Hermes

Lets a student ask 'I never took a course on React.memo, why is it my strong
topic?' and get a sourced answer — per-course and per-document attribution,
plus which loosely-named tags the resolver merged, so a merge is contestable
in conversation."
```

---

### Task 8: Deploy and verify live

**Files:** none — deployment.

- [ ] **Step 1: Deploy the backend**

```bash
cd /Users/swanandkadam/Desktop/01dev-React-hermes/backend
RAILWAY_CALLER="skill:use-railway@1.4.0" RAILWAY_AGENT_SESSION="lab-phase2" \
  railway up --service the01dev-backend --detach -m "feat: concept resolver + explainability"
```

- [ ] **Step 2: Deploy Hermes — required, not optional**

`app/mcp/the01dev_tools.py` changed, and that file is copied into the Hermes image at build time. Without this, Hermes will not have the `explain_concept` tool.

```bash
cd /Users/swanandkadam/Desktop/01dev-React-hermes
RAILWAY_CALLER="skill:use-railway@1.4.0" RAILWAY_AGENT_SESSION="lab-phase2" \
  railway up --service the01dev-hermes --detach -m "feat: explain_concept tool"
```

Wait for both to reach SUCCESS (Hermes builds slowly — several minutes is normal).

- [ ] **Step 3: Deploy the frontend**

```bash
cd /Users/swanandkadam/Desktop/01dev-React-hermes/frontend
npm run build && netlify deploy --prod --dir=dist
```

- [ ] **Step 4: Verify the resolver end-to-end against production**

Take a real quiz on self-study notes covering something the courses DO teach, then confirm the concept resolved onto the existing course concept rather than creating a duplicate:

```bash
BASE=https://the01dev-backend-production.up.railway.app/api/lab
SID=x94FcfXU7KRrobyOA4UHDukbRoC2
DOC=$(curl -s -X POST $BASE/upload-text -H "Content-Type: application/json" \
  -d '{"text":"React.memo skips a re-render when props are shallowly equal. useCallback keeps a function reference stable so a memoized child does not re-render.","title":"My React Notes"}' \
  | python3 -c "import sys,json;print(json.load(sys.stdin)['docId'])")
L=$(curl -s -X POST $BASE/lessons -H "Content-Type: application/json" -d "{\"docId\":\"$DOC\"}")
LID=$(echo "$L" | python3 -c "import sys,json;print(json.load(sys.stdin)['id'])")
OBJ=$(echo "$L" | python3 -c "import sys,json;print(json.dumps(json.load(sys.stdin)['plan']['objectives']))")
curl -s -X POST $BASE/lessons/$LID/approve -H "Content-Type: application/json" \
  -d "{\"objectives\":$OBJ,\"questionsPerQuiz\":2}" \
  | python3 -c "
import sys,json; v=json.load(sys.stdin)
print('concepts on questions:', [q.get('concept') for q in v['quiz']['questions']])
"
```

Expected: the printed concepts are canonical slugs. If the notes covered `React.memo` and the course already has `react-memo`, it must print `react-memo` — **not** `react-memo-1` or `reactmemo`. A brand-new concept would print its own slug, which is also correct.

- [ ] **Step 5: Verify explainability through Hermes**

```bash
curl -s -N -m 60 -X POST https://the01dev-backend-production.up.railway.app/api/hermes/chat \
  -H "Content-Type: application/json" \
  -d '{"question":"I never enrolled in a course on React.memo — why is it one of my strong topics?","user_id":"x94FcfXU7KRrobyOA4UHDukbRoC2","course_slug":"all-courses"}' \
  2>&1 | grep '"value"' | python3 -c "
import sys,json
for line in sys.stdin:
    line=line.strip()
    if line.startswith('data:'):
        try:
            d=json.loads(line[5:])
            if d.get('type')=='token': print(d['value'], end='')
        except: pass
"; echo
```

Expected: an answer naming the actual sources (the React Performance Patterns course quiz and/or the student's own notes) with attempt counts — not a generic "you did well" and not a refusal.

- [ ] **Step 6: Confirm no duplicate concepts were created**

```bash
cd /Users/swanandkadam/Desktop/01dev-React-hermes/backend
PYTHONPATH=. .venv/bin/python -c "
import asyncio
from dotenv import load_dotenv; load_dotenv()
async def main():
    from app.services.store import store
    names = sorted(c.get('name','') for c in await store.list_all('concepts'))
    print('concepts:', names)
    res = await store.list_all('concept_resolutions')
    for r in sorted(res, key=lambda r: r.get('at',''))[-10:]:
        print(f\"{r.get('method'):9} {r.get('score')}  {r.get('candidate')!r} -> {r.get('resolved_to')!r}\")
asyncio.run(main())
"
```

Review the output: near-duplicates in the concept list (e.g. both `react-memo` and `reactmemo`) mean the threshold needs raising; a `created` decision with a score just under 0.64 for something that clearly should have merged means it needs lowering. Record what you see — that is the tuning data this phase exists to start collecting.

---

## Not in this plan (deliberately)

- **Flashcards / summary / study-plan generators, the fan-out graph, the artifact library, the `/lab` page and nav rename** — Phase 3
- **Lecture-as-source and the `CourseCompanion` entry** — Phase 4
- **Backfilling or renaming existing `concept_performance` rows** — explicitly out of scope; `_perf_id` is the doc id, so renaming orphans rows including the seeded demo data
- **A dashboard breakdown of course vs self-study `concepts_mastered`** — the provenance now exists to build it; the UI work belongs with Phase 3's frontend pass
