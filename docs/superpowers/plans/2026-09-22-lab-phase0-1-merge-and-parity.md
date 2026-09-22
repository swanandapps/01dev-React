# Lab Phase 0 + 1 — LangGraph Spike, Merge & Quiz Parity — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Verify the one LangGraph assumption the Lab architecture rests on, then move the never-deployed `backend/lesson_service` package into the already-deployed `the01dev-backend` as `app/services/lab/`, serving the existing quiz flow from `/api/lab/*` with byte-identical response shapes, and retire the external Mastra service it replaces.

**Architecture:** `lesson_service` is currently a standalone FastAPI app (`lesson_service/main.py`) that was never packaged or deployed. Its FastAPI app is replaced by an `APIRouter(prefix="/api/lab")` mounted on the main backend, so one service serves everything. Its LangGraph modules (`graph.py`, `llm.py`, `schemas.py`, `artifacts_graph.py`) move unchanged except for making the OpenAI client lazy. No new outputs, no learner-model writes — this phase is a pure migration so that parity verification has nothing else confounding it.

**Tech Stack:** FastAPI 0.115.5, LangGraph 1.2.9, pypdf, langfuse, OpenAI 1.58.1, pytest. Frontend: React + Vite, deployed on Netlify. Backend deployed on Railway.

**Spec:** `docs/superpowers/specs/2026-09-22-lab-content-pipeline-design.md`

## Global Constraints

- **Phase 1 must NOT write `concept_performance` or `quiz_sessions`.** The Mastra service is external and writes nothing to our learner model today; a pure parity migration must preserve exactly that. Learner-model coupling lands in Phase 2 with the concept resolver. Task 4 includes a test that enforces this.
- **Exact dependency versions:** `langgraph==1.2.9`, `pypdf`, `langfuse`. Verified: these install on the backend's pinned stack with zero version drift — fastapi stays `0.115.5`, starlette `0.41.3`, pydantic `2.10.3`, openai `1.58.1`. **Do not upgrade fastapi/starlette/pydantic/openai.** No venv split is needed (unlike `fastmcp`).
- **`frontend/src/lib/notesQuizApi.ts` must NOT be deleted.** It is the shared TypeScript type source that `notesQuizApiLang.ts` imports from, and the Mastra reference implementation. Standing instruction from a prior session.
- **Response shapes must not change.** `lesson_view()` produces the exact `LessonView` the frontend expects. Preserve it verbatim so the frontend quiz UI works unchanged.
- **Artifacts endpoints stay unexposed.** `artifacts_graph.py` moves with the package but its `/artifacts/*` endpoints are deliberately NOT mounted in Phase 1. They are reshaped in Phase 3.
- **Tests:** full suite is `bash backend/scripts/run_tests.sh` (runs across `.venv` and `.mcp-venv`). Only tests importing `app.mcp.the01dev_tools` go in that script's `MCP_ONLY_TESTS` array — none in this plan do.
- Deploys: `railway up --service the01dev-backend` from `backend/`; `npm run build && netlify deploy --prod --dir=dist` from `frontend/`.

---

## File Structure

**Created:**
- `app/services/lab/__init__.py` — package marker
- `app/services/lab/graph.py` — moved from `lesson_service/graph.py`, unchanged
- `app/services/lab/artifacts_graph.py` — moved, unchanged, NOT wired up this phase
- `app/services/lab/schemas.py` — moved, unchanged
- `app/services/lab/llm.py` — moved, with the client made lazy
- `app/services/lab/routes.py` — **new**; `lesson_service/main.py`'s endpoints as an `APIRouter`, minus the artifacts endpoints and the standalone app/CORS setup
- `backend/tests/test_lab_llm_lazy_client.py` — asserts no client is built at import
- `backend/tests/test_lab_routes.py` — endpoint + `LessonView` shape parity, and the no-learner-model-writes constraint

**Modified:**
- `backend/requirements.txt` — add three dependencies
- `backend/app/main.py` — `include_router` the Lab router
- `backend/app/services/content.py:8-11` — docstring says lesson_service is a "separate process + venv"; no longer true
- `frontend/src/lib/notesQuizApiLang.ts:15` — `BASE` points at the merged backend
- `frontend/src/components/learn/NotesQuizModal.tsx:6,33` — default `api` switches to the LangGraph client
- `RAILWAY_DEPLOYMENT_PLAN.md:124-136` — the "where does lesson_service run?" open decision is now answered
- `DEMO_RUNBOOK.md:58-59` — the standalone `:8090` run command no longer exists

**Deleted:**
- `backend/lesson_service/` — entire directory, after its contents move

---

### Task 1: Phase 0 — LangGraph fan-out → join → interrupt spike

The whole Lab graph shape assumes that a `Send` fan-out which joins, followed by an `interrupt()` in the graph's tail, leaves the pre-interrupt writes durable and readable from the checkpoint while the run is suspended. Nothing else in this plan depends on the answer, but all of Phase 3 does. Find out now, cheaply.

**Files:**
- Create: `/tmp/lab_spike.py` (throwaway — deleted in the final step, not committed)

**Interfaces:**
- Consumes: nothing
- Produces: a recorded yes/no answer. If NO, Phase 3's design changes to two graphs invoked in sequence by the endpoint instead of one joined run. Phase 1 (this plan) is unaffected either way.

- [ ] **Step 1: Write the spike script**

```python
# /tmp/lab_spike.py
"""Throwaway: does a Send fan-out that joins, then interrupts in the tail,
leave the fan-out's writes readable from the checkpoint while suspended?"""
from typing import Annotated, TypedDict

from langgraph.graph import StateGraph, START, END
from langgraph.checkpoint.memory import MemorySaver
from langgraph.types import interrupt, Send


def _merge(a: dict, b: dict) -> dict:
    return {**(a or {}), **(b or {})}


class S(TypedDict, total=False):
    outputs: Annotated[dict, _merge]
    approved: bool


def start(state: S) -> dict:
    return {}


def fan(state: S):
    return [Send("gen_a", state), Send("gen_b", state)]


def gen_a(state: S) -> dict:
    return {"outputs": {"a": "ARTIFACT_A"}}


def gen_b(state: S) -> dict:
    return {"outputs": {"b": "ARTIFACT_B"}}


def join(state: S) -> dict:
    return {}


def tail_interrupt(state: S) -> dict:
    decision = interrupt({"phase": "tail"})
    return {"approved": bool(decision)}


b = StateGraph(S)
for name, fn in [("start", start), ("gen_a", gen_a), ("gen_b", gen_b),
                 ("join", join), ("tail_interrupt", tail_interrupt)]:
    b.add_node(name, fn)
b.add_edge(START, "start")
b.add_conditional_edges("start", fan, ["gen_a", "gen_b"])
b.add_edge("gen_a", "join")
b.add_edge("gen_b", "join")
b.add_edge("join", "tail_interrupt")
b.add_edge("tail_interrupt", END)
g = b.compile(checkpointer=MemorySaver())

cfg = {"configurable": {"thread_id": "spike-1"}}
values = g.invoke({"outputs": {}}, cfg)

print("=== returned from invoke ===")
print("outputs:", values.get("outputs"))
print("interrupted:", bool(values.get("__interrupt__")))

snap = g.get_state(cfg)
print("=== read back from the checkpoint while suspended ===")
print("outputs:", snap.values.get("outputs"))

ok = (snap.values.get("outputs") or {}).get("a") == "ARTIFACT_A" and \
     (snap.values.get("outputs") or {}).get("b") == "ARTIFACT_B"
print()
print("VERDICT:", "PASS — fan-out writes survive the tail interrupt" if ok
      else "FAIL — fan-out writes NOT readable while suspended")
```

- [ ] **Step 2: Run it in an environment that has langgraph**

```bash
cd /Users/swanandkadam/Desktop/01dev-React-hermes/backend
python3 -m venv /tmp/spikevenv
/tmp/spikevenv/bin/pip install -q "langgraph==1.2.9"
/tmp/spikevenv/bin/python /tmp/lab_spike.py
```

Expected: `VERDICT: PASS`. Both `ARTIFACT_A` and `ARTIFACT_B` must be present in the checkpoint read-back, not just in the `invoke` return value.

- [ ] **Step 3: Record the verdict in the spec**

If PASS, append to the spec's "Implementation task #1 — the spike" section:

```markdown
**Resolved 2026-09-XX: PASS.** A `Send` fan-out that joins, followed by an
`interrupt()` in the tail, leaves the fan-out's writes readable via
`get_state()` while the run is suspended. The single-graph design in
"Architecture" stands as written.
```

If FAIL, append instead:

```markdown
**Resolved 2026-09-XX: FAIL.** Fan-out writes are not readable from the
checkpoint while the tail interrupt is suspended. Phase 3 must therefore run
two graphs in sequence from the endpoint (artifacts graph to completion, then
the lesson graph), not one joined run. The sequencing and all other decisions
are unaffected.
```

- [ ] **Step 4: Clean up the throwaway**

```bash
rm -f /tmp/lab_spike.py && rm -rf /tmp/spikevenv
```

- [ ] **Step 5: Commit the spec update**

```bash
cd /Users/swanandkadam/Desktop/01dev-React-hermes
git add docs/superpowers/specs/2026-09-22-lab-content-pipeline-design.md
git commit -m "docs: record LangGraph fan-out/interrupt spike verdict in Lab spec"
```

---

### Task 2: Add the three dependencies

Gate task: prove adding LangGraph to the deployed backend's dependency set breaks nothing that already works.

**Files:**
- Modify: `backend/requirements.txt`

**Interfaces:**
- Consumes: nothing
- Produces: `langgraph`, `pypdf`, `langfuse` importable in `.venv`, with `fastapi==0.115.5` / `starlette==0.41.3` / `pydantic==2.10.3` / `openai==1.58.1` unchanged.

- [ ] **Step 1: Add the dependencies**

Append to `backend/requirements.txt`:

```
# Lab (student content pipeline) — the LangGraph orchestrator, PDF ingestion,
# and Langfuse tracing. Verified 2026-09-22: these resolve against the pins
# above with ZERO version drift (fastapi stays 0.115.5, starlette 0.41.3,
# pydantic 2.10.3, openai 1.58.1), so no venv split is needed here — unlike
# fastmcp, which required requirements-mcp.txt and .mcp-venv.
langgraph==1.2.9
pypdf==6.19.0
langfuse==4.15.4
```

- [ ] **Step 2: Rebuild the venv and verify no version drift**

```bash
cd /Users/swanandkadam/Desktop/01dev-React-hermes/backend
rm -rf .venv && python3 -m venv .venv
.venv/bin/pip install -q -r requirements.txt
.venv/bin/pip list | grep -iE "^(fastapi|starlette|pydantic|openai|langgraph|pypdf|langfuse) "
```

Expected exactly: `fastapi 0.115.5`, `starlette 0.41.3`, `pydantic 2.10.3`, `openai 1.58.1`, `langgraph 1.2.9`, `pypdf 6.19.0`, `langfuse 4.15.4`. Any other fastapi/starlette/pydantic/openai version is a STOP — do not proceed, report it.

- [ ] **Step 3: Verify the combined environment is functional**

```bash
.venv/bin/python -c "
from fastapi import FastAPI; FastAPI(); print('FastAPI() OK')
from langgraph.graph import StateGraph, START, END
from langgraph.checkpoint.memory import MemorySaver
from langgraph.types import interrupt, Send, Command; print('langgraph OK')
from pypdf import PdfReader; print('pypdf OK')
from langfuse.openai import OpenAI; print('langfuse.openai OK')
"
```

Expected: all four lines print OK. (`FastAPI()` is the exact call `fastmcp`'s starlette broke, which is why it is checked explicitly.)

- [ ] **Step 4: Run the existing suite as a regression gate**

```bash
cd /Users/swanandkadam/Desktop/01dev-React-hermes/backend
python3 -m venv .mcp-venv && .mcp-venv/bin/pip install -q -r requirements.txt \
  && .mcp-venv/bin/pip install -q -r requirements-mcp.txt
bash scripts/run_tests.sh
```

Expected: `ALL PASSED — full backend suite is green across both venvs.`

- [ ] **Step 5: Commit**

```bash
git add backend/requirements.txt
git commit -m "build: add langgraph, pypdf, langfuse for the Lab pipeline

Verified zero version drift against the existing pins — fastapi 0.115.5,
starlette 0.41.3, pydantic 2.10.3 and openai 1.58.1 all unchanged, so no
venv split is required (unlike fastmcp)."
```

---

### Task 3: Move the package and make the LLM client lazy

`lesson_service/llm.py` builds its OpenAI client at import time (`_client, _MODEL = _make_client()` at line 51). The main backend's services deliberately don't do that — an import-time client means importing the module requires credentials and performs work. Since `app/main.py` will now import this transitively, it must be lazy.

**Files:**
- Create: `backend/app/services/lab/__init__.py`, `backend/app/services/lab/{graph,artifacts_graph,schemas,llm}.py`
- Create: `backend/tests/test_lab_llm_lazy_client.py`
- Delete: `backend/lesson_service/` (whole directory, including `main.py` — its endpoints become Task 4's router)

**Interfaces:**
- Consumes: Task 2's dependencies
- Produces:
  - `app.services.lab.graph.build_graph() -> CompiledStateGraph`
  - `app.services.lab.artifacts_graph.build_artifacts_graph() -> CompiledStateGraph`
  - `app.services.lab.llm.tutor_answer(document: str, objective: dict | None, question: str) -> str`
  - `app.services.lab.llm.ARTIFACT_TYPES: list[str]`
  - `app.services.lab.llm._get_client() -> tuple[OpenAI, str]` (returns `(client, model)`, cached after first call)

- [ ] **Step 1: Move the four modules**

```bash
cd /Users/swanandkadam/Desktop/01dev-React-hermes/backend
mkdir -p app/services/lab
git mv lesson_service/graph.py           app/services/lab/graph.py
git mv lesson_service/artifacts_graph.py app/services/lab/artifacts_graph.py
git mv lesson_service/schemas.py         app/services/lab/schemas.py
git mv lesson_service/llm.py             app/services/lab/llm.py
git mv lesson_service/__init__.py        app/services/lab/__init__.py
```

The relative imports (`from .llm import ...`, `from .schemas import ...`) keep working unchanged because the package moved as a unit.

- [ ] **Step 2: Write the failing test for lazy client construction**

Create `backend/tests/test_lab_llm_lazy_client.py`:

```python
import app.services.lab.llm as llm_mod


def test_importing_llm_does_not_build_a_client():
    # Importing a service module must not construct an API client or require
    # credentials. This module used to do `_client, _MODEL = _make_client()`
    # at import time; the eagerly-built module attributes must be gone.
    #
    # Deliberately does NOT reload the module or touch sys.modules: that would
    # change module identity for every other test in the run.
    assert not hasattr(llm_mod, "_client"), "_client must not exist at module level"
    assert not hasattr(llm_mod, "_MODEL"), "_MODEL must not exist at module level"


def test_get_client_builds_once_and_caches(monkeypatch):
    calls = []

    def fake_make_client():
        calls.append(1)
        return ("CLIENT", "MODEL")

    # monkeypatch (not direct assignment) so the cache is restored afterwards
    # even if an assertion fails partway through.
    monkeypatch.setattr(llm_mod, "_CLIENT_CACHE", None)
    monkeypatch.setattr(llm_mod, "_make_client", fake_make_client)

    assert llm_mod._get_client() == ("CLIENT", "MODEL")
    assert llm_mod._get_client() == ("CLIENT", "MODEL")
    assert calls == [1], "client must be built once and cached"
```

- [ ] **Step 3: Run it to verify it fails**

```bash
cd /Users/swanandkadam/Desktop/01dev-React-hermes/backend
.venv/bin/python -m pytest tests/test_lab_llm_lazy_client.py -v
```

Expected: both tests FAIL — the first on `_client must not exist at module level` (it currently does, at line 51), the second with `AttributeError: ... has no attribute '_CLIENT_CACHE'` (monkeypatch.setattr raises when the target attribute doesn't exist yet).

- [ ] **Step 4: Make the client lazy**

In `app/services/lab/llm.py`, replace line 51:

```python
_client, _MODEL = _make_client()
```

with:

```python
# Built on first use, not at import: importing a service module must not
# require credentials or do work. app/main.py now imports this transitively.
_CLIENT_CACHE: tuple | None = None


def _get_client() -> tuple:
    """(client, model), constructed once on first call and cached."""
    global _CLIENT_CACHE
    if _CLIENT_CACHE is None:
        _CLIENT_CACHE = _make_client()
    return _CLIENT_CACHE
```

Then update all three call sites. In `_chat_json` (was line 59):

```python
        client, model = _get_client()
        resp = client.chat.completions.create(
            model=model,
```

In `tutor_answer` (was line 187):

```python
    client, model = _get_client()
    resp = client.chat.completions.create(
        model=model,
```

In `gen_artifact` (was line 230):

```python
    client, model = _get_client()
    resp = client.chat.completions.create(
        model=model,
```

- [ ] **Step 5: Run the test to verify it passes**

```bash
.venv/bin/python -m pytest tests/test_lab_llm_lazy_client.py -v
```

Expected: 2 passed.

- [ ] **Step 6: Verify the graphs still build after the move**

```bash
cd /Users/swanandkadam/Desktop/01dev-React-hermes/backend
PYTHONPATH=. .venv/bin/python -c "
from app.services.lab.graph import build_graph
from app.services.lab.artifacts_graph import build_artifacts_graph
print('lesson graph:', type(build_graph()).__name__)
print('artifacts graph:', type(build_artifacts_graph()).__name__)
from app.services.lab.llm import ARTIFACT_TYPES
print('ARTIFACT_TYPES:', ARTIFACT_TYPES)
"
```

Expected: both graphs build, `ARTIFACT_TYPES: ['notes', 'summary', 'quiz', 'flashcards']`.

- [ ] **Step 7: Delete the now-empty old package**

`lesson_service/main.py` is the only file left; its endpoints are reimplemented as a router in Task 4, so it is not needed.

```bash
cd /Users/swanandkadam/Desktop/01dev-React-hermes/backend
git rm lesson_service/main.py
rmdir lesson_service 2>/dev/null || true
rm -rf lesson_service/__pycache__ .lesson-venv
```

- [ ] **Step 8: Run the full suite**

```bash
bash scripts/run_tests.sh
```

Expected: `ALL PASSED`.

- [ ] **Step 9: Commit**

```bash
cd /Users/swanandkadam/Desktop/01dev-React-hermes
git add -A
git commit -m "refactor: move lesson_service into app/services/lab, lazy LLM client

The package moves as a unit so relative imports keep working. The OpenAI
client is no longer built at import time — app/main.py now imports this
transitively, and importing a service module must not require credentials
or do work. lesson_service/main.py is dropped; its endpoints become an
APIRouter in the next task."
```

---

### Task 4: Serve the quiz flow from `/api/lab/*`

Reimplement `lesson_service/main.py`'s endpoints as an `APIRouter` on the main backend. Response shapes are preserved verbatim — `lesson_view()` moves across unchanged.

**Files:**
- Create: `backend/app/services/lab/routes.py`
- Create: `backend/tests/test_lab_routes.py`
- Modify: `backend/app/main.py` (import + `include_router`)

**Interfaces:**
- Consumes: `app.services.lab.graph.build_graph`, `app.services.lab.llm.tutor_answer`, `app.services.lab.llm._get_client`
- Produces: `app.services.lab.routes.router` (an `APIRouter` with prefix `/api/lab`), and `app.services.lab.routes.lesson_view(lesson_id: str, v: dict) -> dict`

- [ ] **Step 1: Write the failing tests**

Create `backend/tests/test_lab_routes.py`:

```python
import pytest
from fastapi.testclient import TestClient

from app.main import app


@pytest.fixture
def client(monkeypatch):
    """Drive the real graph with a fake LLM so shapes are real but no network.

    IMPORTANT — patch `app.services.lab.graph`, NOT `app.services.lab.llm`.
    graph.py does `from .llm import gen_objectives, gen_quiz, gen_summary`, so
    those names are bound in graph.py's own module namespace. Its node functions
    look them up there at call time, which means patching the llm module has no
    effect at all. (Patching works despite the graph being compiled at import,
    because the lookup happens inside the node function body, not at compile.)
    """
    from app.services.lab import graph as lab_graph

    def fake_gen_objectives(doc, title):
        return [
            {"id": "o1", "title": "Closures", "difficulty": "beginner", "focus": "scope"},
            {"id": "o2", "title": "Hoisting", "difficulty": "beginner", "focus": "declarations"},
        ]

    def fake_gen_quiz(doc, objective, n):
        return [
            {"question": f"Q about {objective['title']}?", "options": ["a", "b", "c", "d"],
             "correctIndex": 1, "explanation": "because b", "hint": "think about b"}
            for _ in range(n)
        ]

    def fake_gen_summary(doc, objectives, results):
        return {"overall": "Good work.", "perObjective": [], "studyTips": ["Review closures."]}

    monkeypatch.setattr(lab_graph, "gen_objectives", fake_gen_objectives)
    monkeypatch.setattr(lab_graph, "gen_quiz", fake_gen_quiz)
    monkeypatch.setattr(lab_graph, "gen_summary", fake_gen_summary)
    return TestClient(app)


def test_upload_text_returns_a_doc_id(client):
    r = client.post("/api/lab/upload-text", json={"text": "Closures capture variables.",
                                                  "title": "My notes"})
    assert r.status_code == 200
    assert r.json()["docId"]


def test_upload_text_rejects_empty(client):
    r = client.post("/api/lab/upload-text", json={"text": "   "})
    assert r.status_code == 400


def test_start_lesson_returns_awaiting_approval_lessonview(client):
    doc_id = client.post("/api/lab/upload-text", json={"text": "Closures."}).json()["docId"]
    r = client.post("/api/lab/lessons", json={"docId": doc_id})
    assert r.status_code == 200
    v = r.json()
    # exact LessonView shape the frontend expects — do not change these keys
    assert v["status"] == "awaiting_approval"
    assert v["id"]
    assert [o["title"] for o in v["plan"]["objectives"]] == ["Closures", "Hoisting"]


def test_start_lesson_unknown_doc_is_404(client):
    r = client.post("/api/lab/lessons", json={"docId": "nope"})
    assert r.status_code == 404


def test_approve_then_submit_walks_the_quiz_to_completion(client):
    doc_id = client.post("/api/lab/upload-text", json={"text": "Closures."}).json()["docId"]
    lesson = client.post("/api/lab/lessons", json={"docId": doc_id}).json()
    lid = lesson["id"]
    objectives = lesson["plan"]["objectives"]

    r = client.post(f"/api/lab/lessons/{lid}/approve",
                    json={"objectives": objectives, "questionsPerQuiz": 2})
    assert r.status_code == 200
    v = r.json()
    assert v["status"] == "quizzing"
    assert v["objectivesCount"] == 2
    assert v["objectiveIndex"] == 0
    assert len(v["quiz"]["questions"]) == 2
    assert v["quiz"]["questions"][0]["hint"], "interactive UI needs hint"
    assert v["quiz"]["questions"][0]["explanation"], "interactive UI needs explanation"

    # finish objective 1 → still quizzing, now on objective 2
    v = client.post(f"/api/lab/lessons/{lid}/submit", json={"score": 2, "total": 2}).json()
    assert v["status"] == "quizzing"
    assert v["objectiveIndex"] == 1

    # finish objective 2 → complete, with a summary
    v = client.post(f"/api/lab/lessons/{lid}/submit", json={"score": 2, "total": 2}).json()
    assert v["status"] == "complete"
    assert v["summary"]["overall"] == "Good work."


def test_get_lesson_resumes_state(client):
    doc_id = client.post("/api/lab/upload-text", json={"text": "Closures."}).json()["docId"]
    lid = client.post("/api/lab/lessons", json={"docId": doc_id}).json()["id"]
    r = client.get(f"/api/lab/lessons/{lid}")
    assert r.status_code == 200
    assert r.json()["status"] == "awaiting_approval"


def test_get_unknown_lesson_is_404(client):
    assert client.get("/api/lab/lessons/nope").status_code == 404


def test_ask_returns_a_tutor_answer(client, monkeypatch):
    from app.services.lab import routes as lab_routes

    monkeypatch.setattr(lab_routes, "tutor_answer",
                        lambda doc, objective, question: "Think about scope.")
    doc_id = client.post("/api/lab/upload-text", json={"text": "Closures."}).json()["docId"]
    lid = client.post("/api/lab/lessons", json={"docId": doc_id}).json()["id"]
    r = client.post(f"/api/lab/lessons/{lid}/ask", json={"question": "I'm stuck"})
    assert r.status_code == 200
    assert r.json()["answer"] == "Think about scope."


def test_artifacts_endpoints_are_not_exposed_in_phase_1(client):
    # artifacts_graph.py ships with the package but is deliberately unwired
    # until Phase 3, when it is reshaped into the unified sequenced graph.
    assert client.post("/api/lab/artifacts/start", json={"docId": "x"}).status_code == 404


def test_phase_1_writes_nothing_to_the_learner_model(client, monkeypatch):
    # HARD CONSTRAINT: Mastra (the external service this replaces) writes
    # nothing to our learner model, so this parity migration must not either.
    # concept_performance / quiz_sessions coupling lands in Phase 2, together
    # with the concept resolver — writing them before the resolver exists
    # would start fragmenting concepts immediately.
    from app.services import store as store_mod

    writes: list[tuple] = []

    async def spy_set(collection, doc_id, data):
        writes.append((collection, doc_id))

    async def spy_update(collection, doc_id, changes):
        writes.append((collection, doc_id))

    monkeypatch.setattr(store_mod.store, "set", spy_set)
    monkeypatch.setattr(store_mod.store, "update", spy_update)

    doc_id = client.post("/api/lab/upload-text", json={"text": "Closures."}).json()["docId"]
    lesson = client.post("/api/lab/lessons", json={"docId": doc_id}).json()
    lid = lesson["id"]
    client.post(f"/api/lab/lessons/{lid}/approve",
                json={"objectives": lesson["plan"]["objectives"], "questionsPerQuiz": 1})
    client.post(f"/api/lab/lessons/{lid}/submit", json={"score": 1, "total": 1})
    client.post(f"/api/lab/lessons/{lid}/submit", json={"score": 1, "total": 1})

    touched = {c for c, _ in writes}
    assert "concept_performance" not in touched, f"Phase 1 must not write concepts: {writes}"
    assert "quiz_sessions" not in touched, f"Phase 1 must not write sessions: {writes}"
```

- [ ] **Step 2: Run the tests to verify they fail**

```bash
cd /Users/swanandkadam/Desktop/01dev-React-hermes/backend
.venv/bin/python -m pytest tests/test_lab_routes.py -v
```

Expected: FAIL — every endpoint returns 404 because the router does not exist yet.

- [ ] **Step 3: Create the router**

Create `backend/app/services/lab/routes.py`:

```python
"""
Lab — the student content pipeline's HTTP surface.

Phase 1 exposes ONLY the quiz flow, at the same contract the frontend already
speaks (`LessonView`), so the existing quiz UI drives it unchanged. This was
previously a standalone FastAPI app (lesson_service/main.py, never deployed);
it is now a router on the main backend so one service serves everything.

Deliberately NOT exposed yet: the /artifacts/* endpoints. artifacts_graph.py
ships with the package but is reshaped in Phase 3 into the unified sequenced
graph (fan-out, then the quiz tail).

Phase 1 writes NOTHING to concept_performance or quiz_sessions — see the spec:
the external service this replaces writes nothing to the learner model, so a
parity migration must not either. That coupling lands in Phase 2 alongside the
concept resolver.
"""
import io
import os
import uuid

from fastapi import APIRouter, File, HTTPException, UploadFile
from fastapi.concurrency import run_in_threadpool
from langgraph.types import Command
from pydantic import BaseModel

from app.services.lab.graph import build_graph
from app.services.lab.llm import tutor_answer

router = APIRouter(prefix="/api/lab", tags=["lab"])

GRAPH = build_graph()
DOCS: dict[str, dict] = {}   # docId -> {"text","title"} — in-memory by design in Phase 1
AUDIT: list[dict] = []       # HITL decision trail (EU AI Act)


class UploadTextReq(BaseModel):
    text: str
    title: str | None = None


class StartReq(BaseModel):
    docId: str


class ApproveReq(BaseModel):
    objectives: list[dict]
    questionsPerQuiz: int = 3


class SubmitReq(BaseModel):
    score: int
    total: int


class AskReq(BaseModel):
    question: str


# Langfuse tracing for the graph run: one trace per lesson, span per node,
# grouped by session = lesson_id. Only active when LANGFUSE keys are present.
try:
    if os.getenv("LANGFUSE_PUBLIC_KEY") and os.getenv("LANGFUSE_SECRET_KEY"):
        from langfuse.langchain import CallbackHandler
        _LF_HANDLER = CallbackHandler()
    else:
        _LF_HANDLER = None
except Exception:  # noqa: BLE001 — never let observability break the lesson graph
    _LF_HANDLER = None


def _cfg(lesson_id: str) -> dict:
    cfg = {"configurable": {"thread_id": lesson_id}}
    if _LF_HANDLER is not None:
        cfg["callbacks"] = [_LF_HANDLER]
        cfg["metadata"] = {
            "langfuse_session_id": lesson_id,
            "langfuse_user_id": "the01dev-lab",
            "langfuse_tags": ["lab", "langgraph"],
        }
    return cfg


def _audit(event: str, lesson_id: str, **fields) -> None:
    AUDIT.append({"event": event, "lesson_id": lesson_id, **fields})


def lesson_view(lesson_id: str, v: dict) -> dict:
    """Build the exact LessonView the frontend expects from graph state values.

    Moved verbatim from lesson_service/main.py — these keys are the contract
    the existing quiz UI reads. Do not rename them.
    """
    status = v.get("status")
    view: dict = {"id": lesson_id, "status": status}
    if status == "awaiting_approval":
        view["plan"] = {"objectives": v.get("proposed_objectives", [])}
    elif status == "quizzing":
        objectives = v.get("objectives", [])
        view["objectives"] = objectives
        view["objectiveIndex"] = v.get("objective_index", 0)
        view["objectivesCount"] = len(objectives)
        view["currentObjective"] = v.get("current_objective")
        view["quiz"] = v.get("quiz")
        view["results"] = v.get("results", [])
    elif status == "complete":
        view["objectives"] = v.get("objectives", [])
        view["results"] = v.get("results", [])
        view["summary"] = v.get("summary")
    return view


def _state_values(lesson_id: str) -> dict:
    snap = GRAPH.get_state(_cfg(lesson_id))
    if not snap or not snap.values:
        raise HTTPException(status_code=404, detail="Unknown lesson")
    return snap.values


@router.get("/health")
async def health():
    return {"status": "ok", "service": "lab", "orchestrator": "langgraph",
            "model": os.getenv("LESSON_MODEL", "gpt-4.1-mini"),
            "outputs_enabled": OUTPUT_TYPES}


@router.post("/upload-text")
async def upload_text(req: UploadTextReq):
    if not req.text.strip():
        raise HTTPException(status_code=400, detail="empty text")
    doc_id = uuid.uuid4().hex[:12]
    DOCS[doc_id] = {"text": req.text, "title": req.title or ""}
    return {"docId": doc_id}


@router.post("/upload")
async def upload_pdf(file: UploadFile = File(...)):
    data = await file.read()
    try:
        from pypdf import PdfReader
        reader = PdfReader(io.BytesIO(data))
        text = "\n".join((p.extract_text() or "") for p in reader.pages).strip()
    except Exception as e:  # noqa: BLE001
        raise HTTPException(status_code=400, detail=f"could not read PDF: {e}")
    if not text:
        raise HTTPException(status_code=400, detail="no extractable text in PDF")
    doc_id = uuid.uuid4().hex[:12]
    DOCS[doc_id] = {"text": text, "title": file.filename or ""}
    return {"docId": doc_id}


@router.post("/lessons")
async def start_lesson(req: StartReq):
    doc = DOCS.get(req.docId)
    if not doc:
        raise HTTPException(status_code=404, detail="Unknown docId")
    lesson_id = uuid.uuid4().hex[:12]
    values = await run_in_threadpool(
        GRAPH.invoke,
        {"doc": doc["text"], "title": doc["title"], "results": []},
        _cfg(lesson_id),
    )
    return lesson_view(lesson_id, values)


@router.get("/lessons/{lesson_id}")
async def get_lesson(lesson_id: str):
    return lesson_view(lesson_id, _state_values(lesson_id))


@router.post("/lessons/{lesson_id}/approve")
async def approve_lesson(lesson_id: str, req: ApproveReq):
    _state_values(lesson_id)  # 404 if unknown
    _audit("plan_approved", lesson_id, objectives=len(req.objectives),
           questionsPerQuiz=req.questionsPerQuiz)
    values = await run_in_threadpool(
        GRAPH.invoke,
        Command(resume={"objectives": req.objectives, "questionsPerQuiz": req.questionsPerQuiz}),
        _cfg(lesson_id),
    )
    return lesson_view(lesson_id, values)


@router.post("/lessons/{lesson_id}/submit")
async def submit_result(lesson_id: str, req: SubmitReq):
    _state_values(lesson_id)
    _audit("objective_submitted", lesson_id, score=req.score, total=req.total)
    values = await run_in_threadpool(
        GRAPH.invoke,
        Command(resume={"score": req.score, "total": req.total}),
        _cfg(lesson_id),
    )
    return lesson_view(lesson_id, values)


@router.post("/lessons/{lesson_id}/ask")
async def ask(lesson_id: str, req: AskReq):
    v = _state_values(lesson_id)
    answer = await run_in_threadpool(
        tutor_answer, v.get("doc", ""), v.get("current_objective"), req.question
    )
    return {"answer": answer}


@router.get("/audit")
async def audit(limit: int = 20):
    """HITL decision trail — additive, not part of the Mastra contract."""
    return list(reversed(AUDIT))[:limit]
```

- [ ] **Step 4: Mount the router on the main app**

In `backend/app/main.py`, add to the import block after `from app.routing import smalltalk_classifier`:

```python
from app.services.lab.routes import router as lab_router
```

Then immediately after the `app.add_middleware(CORSMiddleware, ...)` call, add:

```python
# Lab — the student content pipeline (Phase 1: quiz flow only, at /api/lab/*).
app.include_router(lab_router)
```

- [ ] **Step 5: Run the tests to verify they pass**

```bash
cd /Users/swanandkadam/Desktop/01dev-React-hermes/backend
.venv/bin/python -m pytest tests/test_lab_routes.py -v
```

Expected: 10 passed.

- [ ] **Step 6: Run the full suite**

```bash
bash scripts/run_tests.sh
```

Expected: `ALL PASSED`.

- [ ] **Step 7: Commit**

```bash
cd /Users/swanandkadam/Desktop/01dev-React-hermes
git add -A
git commit -m "feat: serve the Lab quiz flow from /api/lab/* on the main backend

Reimplements the never-deployed lesson_service FastAPI app as an APIRouter,
so one service serves everything. lesson_view() moves verbatim — those keys
are the contract the existing quiz UI reads.

Artifacts endpoints stay unexposed until Phase 3 reshapes them. A test
asserts Phase 1 writes nothing to concept_performance or quiz_sessions:
the external service this replaces writes nothing to the learner model, and
coupling before the concept resolver exists would fragment concepts."
```

---

### Task 5: Update the docs the merge invalidates

Three places now describe a world that no longer exists. Stale docs caused a real problem earlier in this project (a memory asserting the LangGraph cutover had happened, when production was still on Mastra), so these are fixed as part of the change that invalidates them.

**Files:**
- Modify: `backend/app/services/content.py:8-11`
- Modify: `RAILWAY_DEPLOYMENT_PLAN.md:124-136`
- Modify: `DEMO_RUNBOOK.md:58-59`

**Interfaces:**
- Consumes: nothing
- Produces: nothing

- [ ] **Step 1: Fix the `content.py` docstring**

It currently claims `lesson_service` is a "separate process + venv". Replace that clause:

```python
Note on scope (honest): `question_service` (course-wide MCQ *bank* with dedupe /
difficulty mix) and `app.services.lab` (per-objective quiz, now merged into this
service — no separate process or venv) are distinct capabilities and are NOT
collapsed into these primitives — see the build notes. These primitives are the
single source for *ad-hoc text → quiz/notes*.
```

- [ ] **Step 2: Close the open decision in `RAILWAY_DEPLOYMENT_PLAN.md`**

Replace the `## Open decision — where does lesson_service (QuizMe, :8090) run?` heading and its option list with:

```markdown
## Resolved — `lesson_service` runs inside `the01dev-backend`

Answered by `docs/superpowers/specs/2026-09-22-lab-content-pipeline-design.md`:
the package moved to `app/services/lab/` and is served from `/api/lab/*` by the
existing backend service. Not a separate Railway service — `langgraph`, `pypdf`
and `langfuse` were verified to install against the backend's pins with zero
version drift, so no venv or process split was needed.

`VITE_NOTES_QUIZ_URL` (the external Mastra service) is retired; the frontend
now calls `${VITE_RAG_API_URL}/api/lab`.
```

- [ ] **Step 3: Fix the `DEMO_RUNBOOK.md` run command**

The standalone `:8090` command no longer exists. Replace those lines with:

````markdown
Lab (the student content pipeline, including QuizMe's quiz flow) is served by
the main backend — no separate process. Starting the backend is enough:

```bash
.venv/bin/uvicorn app.main:app --port 8099
# quiz flow at http://127.0.0.1:8099/api/lab/*
```
````

- [ ] **Step 4: Verify nothing still references the old module path**

```bash
cd /Users/swanandkadam/Desktop/01dev-React-hermes
grep -rn "lesson_service" --include="*.py" --include="*.md" --include="*.sh" . 2>/dev/null \
  | grep -v __pycache__ | grep -v "\-venv" | grep -v "docs/superpowers"
```

Expected: no output. (Hits inside `docs/superpowers/` are historical spec/plan text and are correct to leave.)

- [ ] **Step 5: Commit**

```bash
git add -A
git commit -m "docs: update the three places the Lab merge invalidated

content.py no longer describes lesson_service as a separate process+venv;
RAILWAY_DEPLOYMENT_PLAN's open 'where does it run?' decision is answered;
DEMO_RUNBOOK's standalone :8090 command is replaced."
```

---

### Task 6: Deploy the backend and verify live

**Files:** none modified — deployment only.

**Interfaces:**
- Consumes: Tasks 2–5
- Produces: `https://the01dev-backend-production.up.railway.app/api/lab/*` live

- [ ] **Step 1: Deploy**

```bash
cd /Users/swanandkadam/Desktop/01dev-React-hermes/backend
RAILWAY_CALLER="skill:use-railway@1.4.0" RAILWAY_AGENT_SESSION="lab-phase1" \
  railway up --service the01dev-backend --detach -m "feat: Lab quiz flow at /api/lab/*"
```

- [ ] **Step 2: Wait for SUCCESS**

```bash
until s=$(RAILWAY_CALLER="skill:use-railway@1.4.0" RAILWAY_AGENT_SESSION="lab-phase1" \
  railway api 'query($id:String!){deployment(id:$id){status}}' \
  --variables "{\"id\":\"<DEPLOYMENT_ID_FROM_STEP_1>\"}" 2>/dev/null \
  | grep -o '"status": *"[A-Z]*"') && [[ "$s" == *SUCCESS* || "$s" == *FAILED* || "$s" == *CRASHED* ]]; do
  echo "deploying: $s"; sleep 15
done; echo "final: $s"
```

Expected: `final: "status": "SUCCESS"`.

- [ ] **Step 3: Verify the existing endpoints still work (regression)**

```bash
curl -s https://the01dev-backend-production.up.railway.app/health
```

Expected: `{"status":"ok","chunks_indexed":21,"db":"ok","tutor_provider":"openai"}`. If this regressed, the LangGraph dependency addition broke the deployed service — STOP and roll back.

- [ ] **Step 4: Verify the Lab health endpoint**

```bash
curl -s https://the01dev-backend-production.up.railway.app/api/lab/health
```

Expected (Phase 0/1): `{"status":"ok","service":"lab","orchestrator":"langgraph","model":"gpt-4.1-mini","outputs_enabled":["quiz"]}`.
As of Phase 3 (`/generate` and `/library`), `outputs_enabled` reflects all four:
`["quiz","flashcards","summary","study_plan"]`.

- [ ] **Step 5: Walk a real lesson end-to-end against production**

```bash
BASE=https://the01dev-backend-production.up.railway.app/api/lab
DOC=$(curl -s -X POST $BASE/upload-text -H "Content-Type: application/json" \
  -d '{"text":"A closure is a function that captures variables from its enclosing scope. The captured variables live on after the outer function returns.","title":"Closures"}' \
  | python3 -c "import sys,json;print(json.load(sys.stdin)['docId'])")
echo "docId=$DOC"

LESSON=$(curl -s -X POST $BASE/lessons -H "Content-Type: application/json" -d "{\"docId\":\"$DOC\"}")
echo "$LESSON" | python3 -m json.tool | head -30
```

Expected: `status: "awaiting_approval"` with real generated objectives (not the fakes from the tests — this hits the real model).

- [ ] **Step 6: Approve and confirm a real quiz comes back with hints**

```bash
LID=$(echo "$LESSON" | python3 -c "import sys,json;print(json.load(sys.stdin)['id'])")
OBJ=$(echo "$LESSON" | python3 -c "import sys,json;print(json.dumps(json.load(sys.stdin)['plan']['objectives']))")
curl -s -X POST $BASE/lessons/$LID/approve -H "Content-Type: application/json" \
  -d "{\"objectives\":$OBJ,\"questionsPerQuiz\":2}" | python3 -c "
import sys,json; v=json.load(sys.stdin)
q=v['quiz']['questions'][0]
print('status:', v['status'], '| objectives:', v['objectivesCount'])
print('has hint:', bool(q.get('hint')), '| has explanation:', bool(q.get('explanation')))
print('question:', q['question'])
"
```

Expected: `status: quizzing`, `has hint: True`, `has explanation: True`. Both fields are required by the interactive UI.

- [ ] **Step 7: Commit nothing; record the verification**

No code changed in this task. Note the verified deployment ID in the PR/handoff notes.

---

### Task 7: Point the frontend at the merged backend

**Files:**
- Modify: `frontend/src/lib/notesQuizApiLang.ts:15`
- Modify: `frontend/src/components/learn/NotesQuizModal.tsx:6,33`

**Interfaces:**
- Consumes: Task 6's live `/api/lab/*`
- Produces: the deployed frontend calling the merged backend

- [ ] **Step 1: Repoint the LangGraph client's base URL**

In `frontend/src/lib/notesQuizApiLang.ts`, replace line 15:

```typescript
const BASE = import.meta.env.VITE_QUIZME_LANG_URL || "http://localhost:8090";
```

with:

```typescript
// Lab is served by the main backend now, not a standalone :8090 service.
// VITE_QUIZME_LANG_URL is retained as an override for pointing at a local
// backend during development.
const BASE =
  import.meta.env.VITE_QUIZME_LANG_URL ||
  `${import.meta.env.VITE_RAG_API_URL || "http://localhost:8080"}/api/lab`;
```

- [ ] **Step 2: Switch the modal's default client**

In `frontend/src/components/learn/NotesQuizModal.tsx`, replace line 6:

```typescript
import * as quizApi from "../../lib/notesQuizApi";
```

with:

```typescript
import * as quizApi from "../../lib/notesQuizApiLang";
```

The `import type { LessonView, Objective, Question, Difficulty }` on line 7 stays pointed at `notesQuizApi` — that file remains the shared type source and must not be deleted.

Then update the stale comment above `export type QuizApi` (lines 9–13) to:

```typescript
/** The Lab backend client. Now the LangGraph implementation served by
 *  the01dev-backend at /api/lab/* (previously the external Mastra service at
 *  pdf-learning-tutor-v2-production.up.railway.app, retired). The Mastra
 *  client notesQuizApi.ts is kept as the shared TYPE source and the
 *  Mastra→LangGraph comparison reference — do NOT delete it. */
```

- [ ] **Step 3: Verify it compiles**

```bash
cd /Users/swanandkadam/Desktop/01dev-React-hermes/frontend
npm run build
```

Expected: `tsc -b` passes and vite builds with no errors.

- [ ] **Step 4: Confirm the built bundle points at the right host**

```bash
grep -o "api/lab" dist/assets/*.js | head -1
grep -c "pdf-learning-tutor-v2" dist/assets/*.js || echo "0 (Mastra URL gone from bundle)"
```

Expected: `api/lab` present. The Mastra URL may still appear because `notesQuizApi.ts` retains it as a default — that is expected and harmless since nothing calls those functions.

- [ ] **Step 5: Deploy**

```bash
netlify deploy --prod --dir=dist
```

- [ ] **Step 6: Verify in a browser**

Open `https://the01.dev/quizme`, paste a paragraph of notes, and click Generate. Confirm: objectives appear, approving them produces a quiz, a wrong answer shows a **hint**, a correct one shows an **explanation**, and finishing shows the summary.

Check the browser Network tab: requests must go to `the01dev-backend-production.up.railway.app/api/lab/*`, **not** to `pdf-learning-tutor-v2-production.up.railway.app`.

- [ ] **Step 7: Commit**

```bash
cd /Users/swanandkadam/Desktop/01dev-React-hermes
git add frontend/src/lib/notesQuizApiLang.ts frontend/src/components/learn/NotesQuizModal.tsx
git commit -m "feat: point the quiz UI at the merged Lab backend

NotesQuizModal defaults to the LangGraph client, which now resolves to
\${VITE_RAG_API_URL}/api/lab instead of a standalone :8090 service.
notesQuizApi.ts is retained as the shared type source and Mastra reference."
```

---

### Task 8: Verify parity, then retire Mastra

**This task decommissions an external service. The final step requires explicit human approval — do not decommission on your own initiative.**

**Files:** none — verification and infrastructure teardown.

**Interfaces:**
- Consumes: Task 7's deployed frontend
- Produces: the Mastra service decommissioned and `VITE_NOTES_QUIZ_URL` removed

- [ ] **Step 1: Run the same input through both services**

```bash
NOTES='A closure is a function that captures variables from its enclosing scope.'
for BASE in "https://pdf-learning-tutor-v2-production.up.railway.app" \
            "https://the01dev-backend-production.up.railway.app/api/lab"; do
  echo "=== $BASE ==="
  D=$(curl -s -X POST $BASE/upload-text -H "Content-Type: application/json" \
      -d "{\"text\":\"$NOTES\"}" | python3 -c "import sys,json;print(json.load(sys.stdin)['docId'])")
  curl -s -X POST $BASE/lessons -H "Content-Type: application/json" -d "{\"docId\":\"$D\"}" \
    | python3 -c "
import sys,json; v=json.load(sys.stdin)
print('keys:', sorted(v.keys()))
print('status:', v.get('status'))
print('plan.objectives keys:', sorted(v['plan']['objectives'][0].keys()) if v.get('plan',{}).get('objectives') else None)
"
done
```

Expected: both print the same `keys`, the same `status`, and the same objective field names. Content will differ (different models); **shape must not**.

- [ ] **Step 2: Confirm the frontend has been exercised against the new backend**

Re-run Task 7 Step 6's browser walkthrough if it has not been done since the last deploy. A green test suite is not sufficient evidence here — the point of this phase is that a real user flow works.

- [ ] **Step 3: STOP and get explicit approval**

Report to the human partner: parity verified, shapes match, browser flow works. Ask directly whether to decommission the Mastra service now. **Do not proceed without a clear yes** — this is an external service, and turning it off is not trivially reversible.

- [ ] **Step 4: Remove the now-unused Netlify variable (after approval)**

```bash
cd /Users/swanandkadam/Desktop/01dev-React-hermes/frontend
netlify env:unset VITE_NOTES_QUIZ_URL
```

- [ ] **Step 5: Decommission the Mastra service (after approval)**

The service lives in a **different Railway project** (`pdf-learning-tutor-v2`), not in `the01dev`. Removing it is a dashboard action against that project. Confirm with the human partner which they want: pause/sleep the service (reversible) or delete it (not). Default to pausing unless told otherwise.

- [ ] **Step 6: Record the retirement**

```bash
cd /Users/swanandkadam/Desktop/01dev-React-hermes
git commit --allow-empty -m "chore: retire the external Mastra QuizMe service

Quiz parity verified against /api/lab/* on the01dev-backend (identical
LessonView shapes, real browser flow exercised end to end). The frontend no
longer calls pdf-learning-tutor-v2; VITE_NOTES_QUIZ_URL is removed.
frontend/src/lib/notesQuizApi.ts stays as the shared type source."
```

---

## Not in this plan (deliberately)

These are Phase 2–4 in the spec; listing them so nobody "helpfully" adds them here and ruins parity verification:

- **Any `concept_performance` / `quiz_sessions` writes** — Phase 2, with the resolver
- **The concept resolver, `concept_resolutions` logging, `explain_concept`** — Phase 2
- **Flashcards / summary / study-plan generators and the fan-out graph** — Phase 3
- **Artifact persistence and the library** — Phase 3
- **The `/lab` route, the output-selection UI, and the QuizMe→Lab nav rename** — Phase 3. Note `app/routing/quiz_handoff.py`'s message says "Head to the QuizMe tab"; it must change when the nav does, not before.
- **Lecture-as-source and the `CourseCompanion` entry point** — Phase 4
