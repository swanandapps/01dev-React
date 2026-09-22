# Lab Phase 3 — The Other Three Outputs, Fan-Out, Library, and the Lab Page — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Turn the quiz-only pipeline into the actual product: a student brings material, ticks any combination of **quiz / flashcards / summary / study plan**, and gets them — artifacts generated in parallel and saved to a library, with the quiz running as the interactive tail.

**Architecture:** One graph. The selection drives a `Send` fan-out (no approval gate — the student already chose), artifacts persist as each generator lands, then the graph either ends or continues into the existing objectives→quiz tail. `/quizme` becomes `/lab`.

**Tech Stack:** FastAPI, LangGraph, Postgres via `store`, React + Vite + Tailwind, lucide-react icons.

**Spec:** `docs/superpowers/specs/2026-09-22-lab-content-pipeline-design.md`

**Depends on:** Phase 1 and Phase 2 plans complete.

## Global Constraints

- **Read Phase 0's spike verdict first** (recorded in the spec). If it FAILED, use Task 3's documented fallback — two graphs invoked in sequence from the endpoint — instead of one joined run. Everything else in this plan is unchanged either way.
- **Output set is exactly four: `quiz`, `flashcards`, `summary`, `study_plan`.** Notes is NOT an output; `content.py:generate_notes` stays where it is, untouched and unused by Lab.
- **No approval gate on artifacts.** The student's tick-boxes are the approval. HITL stays only on the quiz's objectives, which is where reviewing what you'll be tested on is real value.
- **Artifacts persist as each generator lands**, not at the end of the run, so the long-lived quiz tail never holds finished artifacts hostage.
- **Quiz-only selection must be byte-identical to Phase 1 behaviour** — the fan-out is an empty passthrough. There is a test for this; do not weaken it.
- **Ordering is artifacts-then-quiz.** Quiz-first-with-background-artifacts was considered and rejected as a bigger build.
- Tests: `bash backend/scripts/run_tests.sh`. Deploys: backend `railway up --service the01dev-backend`, frontend `npm run build && netlify deploy --prod --dir=dist` from `frontend/`. No Hermes redeploy needed — `app/mcp/the01dev_tools.py` is not touched.

---

## File Structure

**Created:**
- `app/services/lab/generators.py` — the three new artifact generators
- `app/services/lab/artifact_store.py` — persistence + library reads
- `backend/tests/test_lab_generators.py`
- `backend/tests/test_lab_artifact_store.py`
- `backend/tests/test_lab_generate_endpoint.py`
- `frontend/src/pages/LabPage.tsx` — replaces `NotesQuizPage.tsx`
- `frontend/src/components/lab/LabStudio.tsx` — source + output selection + results
- `frontend/src/components/lab/ArtifactView.tsx` — renders one artifact by type
- `frontend/src/components/lab/FlashcardDeck.tsx` — flip-through cards
- `frontend/src/lib/labApi.ts` — the `/api/lab/generate` + library client

**Modified:**
- `app/services/lab/artifacts_graph.py` — reshaped into the sequenced unified graph
- `app/services/lab/routes.py` — `/generate`, `/library`
- `app/routing/quiz_handoff.py` — copy says "Lab", not "QuizMe"
- `frontend/src/App.tsx:96` — route `/quizme` → `/lab`
- `frontend/src/components/Home/Header.tsx:11` — nav label/route
- `frontend/src/components/learn/CourseCompanion.tsx` — points at the Lab flow

**Deleted:**
- `frontend/src/pages/NotesQuizPage.tsx` (replaced by `LabPage.tsx`)

---

### Task 1: The three artifact generators

**Files:**
- Create: `backend/app/services/lab/generators.py`
- Test: `backend/tests/test_lab_generators.py`

> **Name collision warning.** `app/services/lab/llm.py` already has a
> `gen_summary` — that one writes the **end-of-lesson performance summary**
> ("you scored 4/5 on closures, here are study tips") from quiz results. The
> `gen_summary` in this task writes a **quick-revision summary of the
> material**, and takes a different argument (`document` only, not
> `document, objectives, results`). They are unrelated functions with the same
> name in sibling modules. Do not cross-wire them; always import explicitly
> (`from app.services.lab.generators import gen_summary`) rather than relying
> on whatever is already in scope.

**Interfaces:**
- Consumes: `app.services.lab.llm._get_client`
- Produces:
  - `OUTPUT_TYPES: list[str] = ["quiz", "flashcards", "summary", "study_plan"]`
  - `ARTIFACT_TYPES: list[str] = ["flashcards", "summary", "study_plan"]` (the fan-out set — quiz is the tail, not an artifact)
  - `gen_flashcards(document: str) -> list[dict]` — `[{"front": str, "back": str}]`
  - `gen_summary(document: str) -> str` — markdown prose
  - `gen_study_plan(document: str) -> list[dict]` — `[{"step": int, "title": str, "detail": str}]`
  - `generate(artifact_type: str, document: str) -> list | str`

- [ ] **Step 1: Write the failing tests**

Create `backend/tests/test_lab_generators.py`:

```python
import pytest

from app.services.lab import generators


class _FakeResp:
    def __init__(self, content):
        self.choices = [type("C", (), {"message": type("M", (), {"content": content})()})()]


def _fake_client(content):
    class _Completions:
        def create(self, **kwargs):
            return _FakeResp(content)

    class _Chat:
        completions = _Completions()

    return type("Client", (), {"chat": _Chat()})()


def test_output_types_are_exactly_the_four(monkeypatch):
    assert generators.OUTPUT_TYPES == ["quiz", "flashcards", "summary", "study_plan"]
    # quiz is the interactive tail, not a fan-out artifact
    assert generators.ARTIFACT_TYPES == ["flashcards", "summary", "study_plan"]
    assert "notes" not in generators.OUTPUT_TYPES


def test_gen_flashcards_parses_front_back_pairs(monkeypatch):
    payload = '{"cards":[{"front":"What is a closure?","back":"A function plus its captured scope."},{"front":"Why use useCallback?","back":"To keep a function reference stable."}]}'
    monkeypatch.setattr(generators, "_get_client", lambda: (_fake_client(payload), "m"))

    cards = generators.gen_flashcards("material")

    assert cards == [
        {"front": "What is a closure?", "back": "A function plus its captured scope."},
        {"front": "Why use useCallback?", "back": "To keep a function reference stable."},
    ]


def test_gen_flashcards_drops_malformed_cards(monkeypatch):
    payload = '{"cards":[{"front":"Good?","back":"Yes."},{"front":"","back":"no front"},{"back":"missing front"},{"front":"no back"}]}'
    monkeypatch.setattr(generators, "_get_client", lambda: (_fake_client(payload), "m"))

    cards = generators.gen_flashcards("material")

    assert cards == [{"front": "Good?", "back": "Yes."}]


def test_gen_flashcards_returns_empty_on_unparseable_json(monkeypatch):
    monkeypatch.setattr(generators, "_get_client", lambda: (_fake_client("not json at all"), "m"))
    assert generators.gen_flashcards("material") == []


def test_gen_summary_returns_prose(monkeypatch):
    monkeypatch.setattr(generators, "_get_client",
                        lambda: (_fake_client("  Closures capture scope.  "), "m"))
    assert generators.gen_summary("material") == "Closures capture scope."


def test_gen_study_plan_parses_numbered_steps(monkeypatch):
    payload = '{"steps":[{"title":"Understand scope","detail":"Read about lexical scope."},{"title":"Practise closures","detail":"Write three counters."}]}'
    monkeypatch.setattr(generators, "_get_client", lambda: (_fake_client(payload), "m"))

    plan = generators.gen_study_plan("material")

    assert plan == [
        {"step": 1, "title": "Understand scope", "detail": "Read about lexical scope."},
        {"step": 2, "title": "Practise closures", "detail": "Write three counters."},
    ]


def test_generate_dispatches_by_type(monkeypatch):
    monkeypatch.setattr(generators, "_get_client",
                        lambda: (_fake_client('{"cards":[{"front":"f","back":"b"}]}'), "m"))
    assert generators.generate("flashcards", "material") == [{"front": "f", "back": "b"}]


def test_generate_rejects_an_unknown_type(monkeypatch):
    with pytest.raises(ValueError, match="unknown artifact type"):
        generators.generate("horoscope", "material")
```

- [ ] **Step 2: Run them to verify they fail**

```bash
cd /Users/swanandkadam/Desktop/01dev-React-hermes/backend
.venv/bin/python -m pytest tests/test_lab_generators.py -v
```

Expected: FAIL — `No module named 'app.services.lab.generators'`.

- [ ] **Step 3: Write the generators**

Create `backend/app/services/lab/generators.py`:

```python
"""
The Lab's artifact generators — the outputs a student can ask for besides the
interactive quiz.

`quiz` is deliberately NOT here: it is the graph's interactive tail (objectives
→ approve → per-objective quiz with hints and a Socratic tutor), not a one-shot
document. It lives in llm.py/graph.py.

Each generator returns STRUCTURED data rather than a blob of markdown, so the
UI can render flashcards as actual cards and a study plan as actual steps.
"""
import json

from app.services.lab.llm import _get_client

OUTPUT_TYPES = ["quiz", "flashcards", "summary", "study_plan"]
# What the fan-out generates. `quiz` is the tail, not an artifact.
ARTIFACT_TYPES = ["flashcards", "summary", "study_plan"]


def _chat(system: str, document: str, max_tokens: int = 700) -> str:
    client, model = _get_client()
    resp = client.chat.completions.create(
        model=model,
        temperature=0.3,
        max_tokens=max_tokens,
        messages=[
            {"role": "system", "content": system},
            {"role": "user", "content": f"MATERIAL:\n{document[:4000]}"},
        ],
    )
    return (resp.choices[0].message.content or "").strip()


def _chat_json(system: str, document: str, max_tokens: int = 700) -> dict:
    raw = _chat(system, document, max_tokens)
    try:
        return json.loads(raw)
    except (json.JSONDecodeError, TypeError):
        # Try to salvage a JSON object embedded in prose.
        start, end = raw.find("{"), raw.rfind("}")
        if start != -1 and end > start:
            try:
                return json.loads(raw[start:end + 1])
            except json.JSONDecodeError:
                return {}
        return {}


def gen_flashcards(document: str) -> list[dict]:
    """5-10 front/back pairs. Malformed cards are dropped, not guessed at."""
    data = _chat_json(
        "You are a flashcard generator. Produce 5-10 flashcards from the material, "
        "each a question or term on the front and its answer on the back. Keep backs "
        'to one or two sentences. Return ONLY JSON: {"cards":[{"front":"...","back":"..."}]}',
        document,
    )
    out = []
    for c in data.get("cards", []) if isinstance(data, dict) else []:
        front = str(c.get("front", "")).strip()
        back = str(c.get("back", "")).strip()
        if front and back:
            out.append({"front": front, "back": back})
    return out[:10]


def gen_summary(document: str) -> str:
    """A 4-5 sentence "quick revision" summary as plain prose."""
    return _chat(
        "You are a study summarizer. Write a clear 4-5 sentence summary of the "
        "material that someone could read as quick revision. Plain prose, no "
        "headings, no preamble, no bullet points.",
        document,
        max_tokens=400,
    )


def gen_study_plan(document: str) -> list[dict]:
    """An ordered roadmap. Separate from the quiz's objectives by design — this
    is a standalone readable plan, not a rendering of what you'll be tested on."""
    data = _chat_json(
        "You are a study planner. Break the material into 4-6 ordered steps a "
        "student should work through, each with a short actionable detail. Order "
        'matters: earlier steps are prerequisites. Return ONLY JSON: '
        '{"steps":[{"title":"...","detail":"..."}]}',
        document,
    )
    out = []
    for i, s in enumerate(data.get("steps", []) if isinstance(data, dict) else [], start=1):
        title = str(s.get("title", "")).strip()
        if not title:
            continue
        out.append({"step": i, "title": title, "detail": str(s.get("detail", "")).strip()})
    return out[:6]


def generate(artifact_type: str, document: str):
    if artifact_type == "flashcards":
        return gen_flashcards(document)
    if artifact_type == "summary":
        return gen_summary(document)
    if artifact_type == "study_plan":
        return gen_study_plan(document)
    raise ValueError(f"unknown artifact type: {artifact_type!r}")
```

- [ ] **Step 4: Run the tests to verify they pass**

```bash
.venv/bin/python -m pytest tests/test_lab_generators.py -v
```

Expected: 8 passed.

- [ ] **Step 5: Commit**

```bash
cd /Users/swanandkadam/Desktop/01dev-React-hermes
git add backend/app/services/lab/generators.py backend/tests/test_lab_generators.py
git commit -m "feat: Lab artifact generators — flashcards, summary, study plan

Structured output rather than markdown blobs so the UI can render real cards
and real plan steps. Malformed items are dropped rather than guessed at.
Quiz is deliberately not here: it's the graph's interactive tail, not a
one-shot document."
```

---

### Task 2: Artifact persistence and the library

**Files:**
- Create: `backend/app/services/lab/artifact_store.py`
- Test: `backend/tests/test_lab_artifact_store.py`

**Interfaces:**
- Consumes: `app.services.store.store`
- Produces:
  - `async save(student_id, doc_id, doc_title, artifact_type, content) -> str` (returns artifact_id)
  - `async library(student_id: str, limit: int = 50) -> list[dict]` — newest first
  - `async get(artifact_id: str) -> dict | None`
  - `COLLECTION = "lab_artifacts"`

- [ ] **Step 1: Write the failing tests**

Create `backend/tests/test_lab_artifact_store.py`:

```python
import pytest

from app.services.lab import artifact_store
from app.services.store import InMemoryStore


@pytest.fixture
def store(monkeypatch):
    s = InMemoryStore()
    monkeypatch.setattr(artifact_store, "store", s)
    return s


@pytest.mark.asyncio
async def test_save_then_read_back(store):
    aid = await artifact_store.save(
        "s1", "doc1", "My Notes", "flashcards", [{"front": "f", "back": "b"}])
    got = await artifact_store.get(aid)
    assert got["student_id"] == "s1"
    assert got["artifact_type"] == "flashcards"
    assert got["content"] == [{"front": "f", "back": "b"}]
    assert got["doc_title"] == "My Notes"
    assert got["created_at"]


@pytest.mark.asyncio
async def test_library_is_scoped_to_the_student(store):
    await artifact_store.save("s1", "d", "t", "summary", "mine")
    await artifact_store.save("s2", "d", "t", "summary", "theirs")
    lib = await artifact_store.library("s1")
    assert [a["content"] for a in lib] == ["mine"]


@pytest.mark.asyncio
async def test_library_is_newest_first(store):
    a1 = await artifact_store.save("s1", "d", "t", "summary", "first")
    a2 = await artifact_store.save("s1", "d", "t", "summary", "second")
    lib = await artifact_store.library("s1")
    assert [a["artifact_id"] for a in lib] == [a2, a1]


@pytest.mark.asyncio
async def test_library_respects_the_limit(store):
    for i in range(5):
        await artifact_store.save("s1", "d", "t", "summary", f"s{i}")
    assert len(await artifact_store.library("s1", limit=2)) == 2


@pytest.mark.asyncio
async def test_anonymous_saves_nothing(store):
    aid = await artifact_store.save("", "d", "t", "summary", "orphan")
    assert aid == ""
    assert await store.list_all("lab_artifacts") == []
```

- [ ] **Step 2: Run them to verify they fail**

```bash
cd /Users/swanandkadam/Desktop/01dev-React-hermes/backend
.venv/bin/python -m pytest tests/test_lab_artifact_store.py -v
```

Expected: FAIL — `No module named 'app.services.lab.artifact_store'`.

- [ ] **Step 3: Write it**

Create `backend/app/services/lab/artifact_store.py`:

```python
"""
The student's library of generated artifacts.

Persisted as each generator lands rather than at the end of a run, so a
long-lived interactive quiz tail never holds finished flashcards hostage — if
the process restarts mid-quiz, the artifacts the student already earned survive.
"""
import uuid
from datetime import datetime, timezone

from app.services.store import store

COLLECTION = "lab_artifacts"


async def save(student_id: str, doc_id: str, doc_title: str,
               artifact_type: str, content) -> str:
    """Persist one artifact. Anonymous sessions save nothing rather than
    creating rows keyed on an empty student id."""
    if not student_id:
        return ""
    artifact_id = uuid.uuid4().hex[:12]
    await store.set(COLLECTION, artifact_id, {
        "artifact_id": artifact_id,
        "student_id": student_id,
        "doc_id": doc_id,
        "doc_title": doc_title,
        "artifact_type": artifact_type,
        "content": content,
        "created_at": datetime.now(timezone.utc).isoformat(),
    })
    return artifact_id


async def get(artifact_id: str) -> dict | None:
    return await store.get(COLLECTION, artifact_id)


async def library(student_id: str, limit: int = 50) -> list[dict]:
    rows = await store.query(COLLECTION, "student_id", student_id)
    rows.sort(key=lambda r: r.get("created_at", ""), reverse=True)
    return rows[:limit]
```

- [ ] **Step 4: Run the tests to verify they pass**

```bash
.venv/bin/python -m pytest tests/test_lab_artifact_store.py -v
```

Expected: 5 passed.

> If `test_library_is_newest_first` is flaky, two saves landed on the same ISO
> timestamp. Fix it by sorting on `(created_at, artifact_id)` — do not add a
> `sleep` to the test.

- [ ] **Step 5: Commit**

```bash
cd /Users/swanandkadam/Desktop/01dev-React-hermes
git add backend/app/services/lab/artifact_store.py backend/tests/test_lab_artifact_store.py
git commit -m "feat: Lab artifact library

Artifacts persist per-generator as they land, so a long-lived quiz tail
never holds finished work hostage. Library reads are student-scoped and
newest-first; anonymous sessions save nothing."
```

---

### Task 3: The unified fan-out graph

**Read the Phase 0 spike verdict in the spec before starting.** This task assumes PASS. If it FAILED, use the fallback in Step 6.

**Files:**
- Modify: `backend/app/services/lab/artifacts_graph.py` (reshaped)
- Test: `backend/tests/test_lab_unified_graph.py`

**Interfaces:**
- Consumes: `generators.generate`, `generators.ARTIFACT_TYPES`
- Produces: `build_lab_graph() -> CompiledStateGraph` over state
  `{document, doc_id, doc_title, student_id, outputs_requested: list[str], artifacts: dict, status}`

- [ ] **Step 1: Write the failing tests**

Create `backend/tests/test_lab_unified_graph.py`:

```python
import pytest

from app.services.lab import artifacts_graph


@pytest.fixture
def graph(monkeypatch):
    monkeypatch.setattr(artifacts_graph, "generate",
                        lambda t, doc: f"GENERATED-{t}")
    saved = []

    async def fake_save(student_id, doc_id, doc_title, artifact_type, content):
        saved.append((artifact_type, content))
        return f"aid-{artifact_type}"

    monkeypatch.setattr(artifacts_graph, "save_artifact", fake_save)
    return artifacts_graph.build_lab_graph(), saved


def _cfg(tid):
    return {"configurable": {"thread_id": tid}}


def test_artifacts_only_runs_to_completion(graph):
    g, saved = graph
    v = g.invoke({"document": "d", "outputs_requested": ["flashcards", "summary"],
                  "artifacts": {}}, _cfg("t1"))
    assert v["status"] == "complete"
    assert v["artifacts"]["flashcards"] == "GENERATED-flashcards"
    assert v["artifacts"]["summary"] == "GENERATED-summary"
    assert not v.get("__interrupt__")


def test_each_artifact_is_persisted_as_it_lands(graph):
    g, saved = graph
    g.invoke({"document": "d", "outputs_requested": ["flashcards", "summary", "study_plan"],
              "artifacts": {}}, _cfg("t2"))
    assert sorted(t for t, _ in saved) == ["flashcards", "study_plan", "summary"]


def test_quiz_only_generates_no_artifacts_and_reaches_the_quiz_tail(graph):
    g, saved = graph
    v = g.invoke({"document": "d", "outputs_requested": ["quiz"], "artifacts": {}},
                 _cfg("t3"))
    assert saved == [], "quiz-only must be an empty fan-out passthrough"
    assert v["artifacts"] == {}
    assert v["status"] == "awaiting_objectives"


def test_all_four_generates_artifacts_then_reaches_the_quiz_tail(graph):
    g, saved = graph
    v = g.invoke({"document": "d",
                  "outputs_requested": ["quiz", "flashcards", "summary", "study_plan"],
                  "artifacts": {}}, _cfg("t4"))
    assert sorted(v["artifacts"]) == ["flashcards", "study_plan", "summary"]
    assert v["status"] == "awaiting_objectives"
    # THE PHASE 0 ASSUMPTION: artifacts finished before the tail are readable
    # from the checkpoint while it is suspended.
    snap = g.get_state(_cfg("t4"))
    assert sorted(snap.values["artifacts"]) == ["flashcards", "study_plan", "summary"]


def test_unknown_requested_output_is_ignored(graph):
    g, saved = graph
    v = g.invoke({"document": "d", "outputs_requested": ["flashcards", "horoscope"],
                  "artifacts": {}}, _cfg("t5"))
    assert sorted(v["artifacts"]) == ["flashcards"]
```

- [ ] **Step 2: Run them to verify they fail**

```bash
cd /Users/swanandkadam/Desktop/01dev-React-hermes/backend
.venv/bin/python -m pytest tests/test_lab_unified_graph.py -v
```

Expected: FAIL — `module 'app.services.lab.artifacts_graph' has no attribute 'build_lab_graph'`.

- [ ] **Step 3: Reshape the graph**

Replace the entire contents of `backend/app/services/lab/artifacts_graph.py`:

```python
"""
The Lab graph — the student's selection drives a fan-out, then the quiz tail.

    START
      → fan_out          Send() per requested artifact, driven straight by the
                         student's selection. NO approval gate: they already
                         chose in the UI; interrupting to confirm what they just
                         said is a wasted click.
      → join             each artifact persisted as it landed
      → quiz requested?  no  → END
                         yes → hand off to the objectives/quiz tail, which keeps
                               its HITL gate (reviewing what you'll be tested on
                               IS worth a gate)

Artifacts are sequenced BEFORE the quiz rather than run as a sibling branch: a
branch that interrupts inside the same superstep as the generators would make
the durability of their writes depend on LangGraph's pending-write semantics.
Sequencing removes the question entirely.
"""
from typing import Annotated, TypedDict

from langgraph.graph import StateGraph, START, END
from langgraph.checkpoint.memory import MemorySaver
from langgraph.types import Send

from app.services.lab.artifact_store import save as save_artifact
from app.services.lab.generators import ARTIFACT_TYPES, generate


def _merge(a: dict, b: dict) -> dict:
    return {**(a or {}), **(b or {})}


class LabState(TypedDict, total=False):
    document: str
    doc_id: str
    doc_title: str
    student_id: str
    outputs_requested: list[str]
    artifacts: Annotated[dict, _merge]   # artifact_type -> content
    status: str                          # complete | awaiting_objectives


def fan_out(state: LabState):
    """One Send per requested artifact. Quiz is not an artifact — it's the tail."""
    wanted = [t for t in (state.get("outputs_requested") or []) if t in ARTIFACT_TYPES]
    if not wanted:
        return "join"                     # empty passthrough (e.g. quiz-only)
    return [Send(f"gen_{t}", state) for t in wanted]


def _make_generator(artifact_type: str):
    async def _gen(state: LabState) -> dict:
        content = generate(artifact_type, state["document"])
        # Persist as it lands, not at end of run — a long quiz tail must not
        # hold finished artifacts hostage.
        await save_artifact(
            state.get("student_id", ""), state.get("doc_id", ""),
            state.get("doc_title", ""), artifact_type, content,
        )
        return {"artifacts": {artifact_type: content}}

    _gen.__name__ = f"gen_{artifact_type}"
    return _gen


def join(state: LabState) -> dict:
    return {}


def route_after_join(state: LabState) -> str:
    if "quiz" in (state.get("outputs_requested") or []):
        return "quiz_tail"
    return END


def quiz_tail(state: LabState) -> dict:
    """Marker node: the endpoint hands off to the lesson graph from here.

    The objectives→approve→quiz→summarize flow stays in graph.py, unchanged and
    already parity-verified. Duplicating it here would fork a working
    implementation for no gain.
    """
    return {"status": "awaiting_objectives"}


def build_lab_graph():
    b = StateGraph(LabState)
    b.add_node("join", join)
    b.add_node("quiz_tail", quiz_tail)
    for t in ARTIFACT_TYPES:
        b.add_node(f"gen_{t}", _make_generator(t))

    b.add_conditional_edges(
        START, fan_out, [f"gen_{t}" for t in ARTIFACT_TYPES] + ["join"],
    )
    for t in ARTIFACT_TYPES:
        b.add_edge(f"gen_{t}", "join")
    b.add_conditional_edges("join", route_after_join, ["quiz_tail", END])
    b.add_edge("quiz_tail", END)
    return b.compile(checkpointer=MemorySaver())
```

Also set `status` on the artifacts-only path. Add to `join`:

```python
def join(state: LabState) -> dict:
    if "quiz" in (state.get("outputs_requested") or []):
        return {}
    return {"status": "complete"}
```

- [ ] **Step 4: Run the tests to verify they pass**

```bash
.venv/bin/python -m pytest tests/test_lab_unified_graph.py -v
```

Expected: 5 passed.

- [ ] **Step 5: Run the full suite**

```bash
bash scripts/run_tests.sh
```

Expected: `ALL PASSED`.

- [ ] **Step 6: ONLY IF the Phase 0 spike FAILED — use this fallback instead**

Skip the graph entirely: delete `artifacts_graph.py` and have Task 4's `/generate` endpoint call the generators directly with `asyncio.gather`, then hand off to the lesson graph:

```python
    import asyncio
    wanted = [t for t in req.outputs if t in ARTIFACT_TYPES]
    results = await asyncio.gather(*[
        run_in_threadpool(generate, t, doc["text"]) for t in wanted
    ])
    artifacts = dict(zip(wanted, results))
    for t, content in artifacts.items():
        await save_artifact(req.student_id, req.docId, doc["title"], t, content)
```

Every other task in this plan is unchanged — only the orchestration mechanism differs, and `Task 3`'s tests should then be rewritten against the endpoint rather than the graph.

- [ ] **Step 7: Commit**

```bash
cd /Users/swanandkadam/Desktop/01dev-React-hermes
git add backend/app/services/lab/artifacts_graph.py backend/tests/test_lab_unified_graph.py
git commit -m "feat: unified Lab graph — selection-driven fan-out, then the quiz tail

The student's tick-boxes drive a Send fan-out with no approval gate (they
already chose). Artifacts persist as each lands. Quiz-only is an empty
passthrough, so it behaves exactly as the parity-verified flow does.
Artifacts are sequenced before the quiz rather than run as a sibling branch,
which avoids depending on LangGraph pending-write semantics."
```

---

### Task 4: `/generate` and `/library`

**Files:**
- Modify: `backend/app/services/lab/routes.py`
- Test: `backend/tests/test_lab_generate_endpoint.py`

**Interfaces:**
- Produces:
  - `POST /api/lab/generate {docId, outputs: list[str], student_id?}` → `{run_id, status, artifacts, lesson_id?, proposed_objectives?}`
  - `GET /api/lab/library?student_id=` → `list[artifact]`

- [ ] **Step 1: Write the failing tests**

Create `backend/tests/test_lab_generate_endpoint.py`:

```python
import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.services.store import InMemoryStore


@pytest.fixture
def client(monkeypatch):
    from app.services.lab import artifact_store, artifacts_graph, graph as lab_graph, routes

    s = InMemoryStore()
    monkeypatch.setattr(artifact_store, "store", s)
    monkeypatch.setattr(artifacts_graph, "generate", lambda t, doc: f"GEN-{t}")
    monkeypatch.setattr(lab_graph, "gen_objectives", lambda doc, title: [
        {"id": "o1", "title": "Closures", "difficulty": "beginner", "focus": "scope"},
    ])
    # rebuild the graph so the patched generate is picked up by fresh nodes
    monkeypatch.setattr(routes, "LAB_GRAPH", artifacts_graph.build_lab_graph())
    return TestClient(app), s


def test_artifacts_only_returns_them_and_completes(client):
    c, _ = client
    doc = c.post("/api/lab/upload-text",
                 json={"text": "Closures.", "title": "Notes"}).json()["docId"]
    r = c.post("/api/lab/generate", json={
        "docId": doc, "outputs": ["flashcards", "summary"], "student_id": "s1"})
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "complete"
    assert body["artifacts"]["flashcards"] == "GEN-flashcards"
    assert body["artifacts"]["summary"] == "GEN-summary"
    assert "lesson_id" not in body or body["lesson_id"] is None


def test_quiz_selected_returns_a_lesson_id_and_objectives(client):
    c, _ = client
    doc = c.post("/api/lab/upload-text", json={"text": "Closures."}).json()["docId"]
    r = c.post("/api/lab/generate", json={
        "docId": doc, "outputs": ["quiz"], "student_id": "s1"})
    body = r.json()
    assert body["status"] == "awaiting_approval"
    assert body["lesson_id"]
    assert [o["title"] for o in body["proposed_objectives"]] == ["Closures"]
    assert body["artifacts"] == {}


def test_all_four_returns_artifacts_and_a_lesson(client):
    c, _ = client
    doc = c.post("/api/lab/upload-text", json={"text": "Closures."}).json()["docId"]
    body = c.post("/api/lab/generate", json={
        "docId": doc,
        "outputs": ["quiz", "flashcards", "summary", "study_plan"],
        "student_id": "s1"}).json()
    assert sorted(body["artifacts"]) == ["flashcards", "study_plan", "summary"]
    assert body["lesson_id"]
    assert body["status"] == "awaiting_approval"


def test_generate_rejects_an_empty_selection(client):
    c, _ = client
    doc = c.post("/api/lab/upload-text", json={"text": "Closures."}).json()["docId"]
    r = c.post("/api/lab/generate", json={"docId": doc, "outputs": []})
    assert r.status_code == 400


def test_generate_unknown_doc_is_404(client):
    c, _ = client
    r = c.post("/api/lab/generate", json={"docId": "nope", "outputs": ["summary"]})
    assert r.status_code == 404


def test_library_returns_the_students_artifacts(client):
    c, _ = client
    doc = c.post("/api/lab/upload-text",
                 json={"text": "Closures.", "title": "Notes"}).json()["docId"]
    c.post("/api/lab/generate", json={
        "docId": doc, "outputs": ["summary"], "student_id": "s1"})
    lib = c.get("/api/lab/library?student_id=s1").json()
    assert len(lib) == 1
    assert lib[0]["artifact_type"] == "summary"
    assert lib[0]["doc_title"] == "Notes"


def test_library_is_empty_for_another_student(client):
    c, _ = client
    doc = c.post("/api/lab/upload-text", json={"text": "C."}).json()["docId"]
    c.post("/api/lab/generate", json={
        "docId": doc, "outputs": ["summary"], "student_id": "s1"})
    assert c.get("/api/lab/library?student_id=s2").json() == []
```

- [ ] **Step 2: Run them to verify they fail**

```bash
cd /Users/swanandkadam/Desktop/01dev-React-hermes/backend
.venv/bin/python -m pytest tests/test_lab_generate_endpoint.py -v
```

Expected: FAIL — `/api/lab/generate` 404s.

- [ ] **Step 3: Add the endpoints**

In `backend/app/services/lab/routes.py`, add imports:

```python
from app.services.lab.artifact_store import library as artifact_library
from app.services.lab.artifacts_graph import build_lab_graph
from app.services.lab.generators import OUTPUT_TYPES
```

Add the compiled graph next to `GRAPH`:

```python
LAB_GRAPH = build_lab_graph()
```

Add the request model:

```python
class GenerateReq(BaseModel):
    docId: str
    outputs: list[str]
    student_id: str = ""
```

Then the endpoints:

```python
@router.post("/generate")
async def generate_outputs(req: GenerateReq):
    """Fan out to the selected artifacts, then start the quiz if it was chosen.

    Returns artifacts plus, when the quiz was selected, a `lesson_id` and the
    proposed objectives — so the client goes straight into the existing
    objectives-approval screen.
    """
    doc = DOCS.get(req.docId)
    if not doc:
        raise HTTPException(status_code=404, detail="Unknown docId")
    wanted = [t for t in req.outputs if t in OUTPUT_TYPES]
    if not wanted:
        raise HTTPException(status_code=400, detail="choose at least one output")

    run_id = uuid.uuid4().hex[:12]
    values = await run_in_threadpool(
        LAB_GRAPH.invoke,
        {"document": doc["text"], "doc_id": req.docId, "doc_title": doc["title"],
         "student_id": req.student_id, "outputs_requested": wanted, "artifacts": {}},
        _cfg(f"lab-{run_id}"),
    )
    body: dict = {
        "run_id": run_id,
        "status": "complete",
        "artifacts": values.get("artifacts", {}),
        "lesson_id": None,
    }
    if "quiz" not in wanted:
        return body

    # Quiz selected: start the lesson graph, which owns the objectives HITL gate.
    lesson_id = uuid.uuid4().hex[:12]
    lesson_values = await run_in_threadpool(
        GRAPH.invoke,
        {"doc": doc["text"], "title": doc["title"], "results": [], "doc_id": req.docId},
        _cfg(lesson_id),
    )
    view = lesson_view(lesson_id, lesson_values)
    body["status"] = view["status"]
    body["lesson_id"] = lesson_id
    body["proposed_objectives"] = view.get("plan", {}).get("objectives", [])
    return body


@router.get("/library")
async def get_library(student_id: str, limit: int = 50):
    return await artifact_library(student_id, limit)
```

- [ ] **Step 4: Run the tests to verify they pass**

```bash
.venv/bin/python -m pytest tests/test_lab_generate_endpoint.py -v
```

Expected: 7 passed.

- [ ] **Step 5: Run the full suite and commit**

```bash
bash scripts/run_tests.sh
cd /Users/swanandkadam/Desktop/01dev-React-hermes
git add backend/app/services/lab/routes.py backend/tests/test_lab_generate_endpoint.py
git commit -m "feat: POST /api/lab/generate and GET /api/lab/library

One call takes the student's selection, fans out to the chosen artifacts,
and — when the quiz was selected — starts the lesson graph and returns its
proposed objectives, so the client lands straight on the approval screen.
The quiz continues on the existing /lessons/* endpoints."
```

---

### Task 5: The Lab API client and page shell

**Files:**
- Create: `frontend/src/lib/labApi.ts`
- Create: `frontend/src/pages/LabPage.tsx`
- Modify: `frontend/src/App.tsx:96`, `frontend/src/components/Home/Header.tsx:11`
- Delete: `frontend/src/pages/NotesQuizPage.tsx`

**Interfaces:**
- Produces:
  - `export type OutputType = "quiz" | "flashcards" | "summary" | "study_plan"`
  - `export type LabArtifacts = Partial<Record<Exclude<OutputType, "quiz">, unknown>>`
  - `generateOutputs(docId, outputs, studentId) -> Promise<GenerateResponse>`
  - `getLibrary(studentId) -> Promise<LabArtifact[]>`

- [ ] **Step 1: Write the client**

Create `frontend/src/lib/labApi.ts`:

```typescript
// Lab — the student content pipeline. Ingestion and the quiz flow live in
// notesQuizApiLang.ts (same LessonView contract as before); this module adds
// the output-selection and library calls.
import type { Objective } from "./notesQuizApi";

const BASE =
  import.meta.env.VITE_QUIZME_LANG_URL ||
  `${import.meta.env.VITE_RAG_API_URL || "http://localhost:8080"}/api/lab`;

export type OutputType = "quiz" | "flashcards" | "summary" | "study_plan";

export type Flashcard = { front: string; back: string };
export type StudyPlanStep = { step: number; title: string; detail: string };

export type LabArtifacts = {
  flashcards?: Flashcard[];
  summary?: string;
  study_plan?: StudyPlanStep[];
};

export type GenerateResponse = {
  run_id: string;
  status: string;
  artifacts: LabArtifacts;
  lesson_id: string | null;
  proposed_objectives?: Objective[];
};

export type LabArtifact = {
  artifact_id: string;
  artifact_type: Exclude<OutputType, "quiz">;
  doc_title: string;
  content: unknown;
  created_at: string;
};

async function post<T>(path: string, body: unknown): Promise<T> {
  const res = await fetch(`${BASE}${path}`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  if (!res.ok) {
    const text = await res.text().catch(() => "Unknown error");
    throw new Error(`Lab API error ${res.status}: ${text}`);
  }
  return res.json();
}

export function generateOutputs(
  docId: string,
  outputs: OutputType[],
  studentId = "",
): Promise<GenerateResponse> {
  return post<GenerateResponse>("/generate", {
    docId,
    outputs,
    student_id: studentId,
  });
}

export async function getLibrary(studentId: string): Promise<LabArtifact[]> {
  const res = await fetch(`${BASE}/library?student_id=${encodeURIComponent(studentId)}`);
  if (!res.ok) throw new Error(`Lab API error ${res.status}`);
  return res.json();
}

export const OUTPUT_LABELS: Record<OutputType, { label: string; blurb: string }> = {
  quiz: { label: "Quiz me", blurb: "Adaptive questions with hints and a tutor" },
  flashcards: { label: "Flashcards", blurb: "Front-and-back cards to drill" },
  summary: { label: "Quick revision", blurb: "A short summary to re-read" },
  study_plan: { label: "Study plan", blurb: "An ordered roadmap to work through" },
};
```

- [ ] **Step 2: Create the page**

Create `frontend/src/pages/LabPage.tsx`:

```tsx
import { useNavigate } from "react-router-dom";
import { Sparkles, FlaskConical, ShieldCheck } from "lucide-react";
import Header from "../components/Home/Header";
import { LabStudio } from "../components/lab/LabStudio";
import { useUserSessionStore } from "../store/userSession";

export default function LabPage() {
  const navigate = useNavigate();
  const { currentuser } = useUserSessionStore();
  const studentId = (currentuser?.uid as string) || "";

  return (
    <div className="bg-zinc-950 min-h-screen">
      <Header />
      <div className="max-w-2xl mx-auto px-4 pt-24 pb-16">
        <div className="mb-8">
          <div className="flex items-center gap-2 mb-4">
            <div className="w-10 h-10 rounded-xl bg-indigo-600/20 border border-indigo-500/30 flex items-center justify-center">
              <FlaskConical className="w-5 h-5 text-indigo-400" />
            </div>
            <div className="flex items-center gap-1.5 text-xs font-semibold text-indigo-400 uppercase tracking-wide">
              <Sparkles className="w-3.5 h-3.5" /> AI Feature
            </div>
            <span className="ml-auto flex items-center gap-1.5 text-xs text-emerald-400 bg-emerald-950/40 px-2.5 py-1 rounded-full border border-emerald-800/50">
              <ShieldCheck className="w-3.5 h-3.5" /> Grounded &amp; audited
            </span>
          </div>
          <h1 className="text-2xl font-bold text-zinc-100 mb-2">Lab</h1>
          <p className="text-sm text-zinc-500 leading-relaxed max-w-lg">
            Bring your own material — type a topic, paste notes, upload a PDF, or pick a
            lecture — then choose what to make from it: a quiz, flashcards, a quick
            revision summary, a study plan, or all of them.
          </p>
        </div>

        <LabStudio studentId={studentId} onClose={() => navigate(-1)} />
      </div>
    </div>
  );
}
```

- [ ] **Step 3: Rename the route and nav entry**

In `frontend/src/App.tsx`, replace the import of `NotesQuizPage` with `LabPage`:

```tsx
import LabPage from "./pages/LabPage";
```

and replace line 96:

```tsx
      <Route path="/lab" element={<LabPage />} />
      {/* keep the old path working for anyone with a bookmark */}
      <Route path="/quizme" element={<LabPage />} />
```

In `frontend/src/components/Home/Header.tsx`, replace line 11:

```tsx
  { to: "/lab", label: "Lab", icon: FlaskConical, exact: false },
```

and swap the `NotebookPen` import for `FlaskConical` (check whether `NotebookPen` is still used elsewhere in that file before removing it from the import list).

- [ ] **Step 4: Delete the old page**

```bash
cd /Users/swanandkadam/Desktop/01dev-React-hermes
git rm frontend/src/pages/NotesQuizPage.tsx
```

- [ ] **Step 5: Update the chat hand-off copy**

`app/routing/quiz_handoff.py` tells students to "Head to the QuizMe tab", which no longer exists. Replace the function body:

```python
def build_handoff_message(course_slug: str) -> str:
    return (
        "I can't build a quiz straight from chat yet — Lab needs your material "
        "first. Head to the Lab tab, add the notes or topic you want quizzed on "
        f"from '{course_slug}', and it'll generate questions from that material. "
        "You can also get flashcards, a quick revision summary, or a study plan "
        "from the same material there."
    )
```

Update its module docstring's `lesson_service` reference to `app.services.lab`.

The existing assertion in `tests/test_hermes_chat_routing.py` checks for `"QuizMe" in tokens` — update that test to assert `"Lab" in tokens`.

- [ ] **Step 6: Build (will fail until Task 6 creates LabStudio)**

```bash
cd /Users/swanandkadam/Desktop/01dev-React-hermes/frontend && npm run build
```

Expected: FAIL — `Cannot find module '../components/lab/LabStudio'`. That is Task 6. Do not commit a broken build; commit after Task 6.

---

### Task 6: The Lab studio UI

**Files:**
- Create: `frontend/src/components/lab/LabStudio.tsx`
- Create: `frontend/src/components/lab/ArtifactView.tsx`
- Create: `frontend/src/components/lab/FlashcardDeck.tsx`
- Modify: `frontend/src/components/learn/CourseCompanion.tsx`

**Interfaces:**
- Consumes: `labApi.generateOutputs`, `labApi.OUTPUT_LABELS`, `notesQuizApiLang.uploadText/uploadPdf`, `NotesQuizModal`
- Produces: `<LabStudio studentId={string} onClose={() => void} lectureText?={string} />`

- [ ] **Step 1: Flashcard deck**

Create `frontend/src/components/lab/FlashcardDeck.tsx`:

```tsx
import { useState } from "react";
import { ChevronLeft, ChevronRight, RotateCcw } from "lucide-react";
import type { Flashcard } from "../../lib/labApi";

export function FlashcardDeck({ cards }: { cards: Flashcard[] }) {
  const [i, setI] = useState(0);
  const [flipped, setFlipped] = useState(false);
  if (!cards.length) return null;
  const card = cards[i];

  const go = (delta: number) => {
    setI((n) => (n + delta + cards.length) % cards.length);
    setFlipped(false);
  };

  return (
    <div className="flex flex-col gap-3">
      <button
        onClick={() => setFlipped((f) => !f)}
        className="w-full min-h-[160px] bg-zinc-800/60 border border-zinc-700/60 hover:border-indigo-500/40 rounded-xl p-6 text-left transition-colors flex flex-col justify-center"
      >
        <p className="text-[10px] font-bold uppercase tracking-wide text-indigo-400 mb-2">
          {flipped ? "Back" : "Front"}
        </p>
        <p className="text-base text-zinc-100 leading-relaxed">
          {flipped ? card.back : card.front}
        </p>
        <p className="text-xs text-zinc-600 mt-3">Click to flip</p>
      </button>

      <div className="flex items-center gap-2">
        <button onClick={() => go(-1)} aria-label="Previous card"
          className="p-2 rounded-lg bg-zinc-800 hover:bg-zinc-700 text-zinc-300">
          <ChevronLeft className="w-4 h-4" />
        </button>
        <span className="text-xs text-zinc-500 flex-1 text-center">
          {i + 1} / {cards.length}
        </span>
        <button onClick={() => setFlipped(false)} aria-label="Reset flip"
          className="p-2 rounded-lg bg-zinc-800 hover:bg-zinc-700 text-zinc-300">
          <RotateCcw className="w-4 h-4" />
        </button>
        <button onClick={() => go(1)} aria-label="Next card"
          className="p-2 rounded-lg bg-zinc-800 hover:bg-zinc-700 text-zinc-300">
          <ChevronRight className="w-4 h-4" />
        </button>
      </div>
    </div>
  );
}
```

- [ ] **Step 2: Artifact renderer**

Create `frontend/src/components/lab/ArtifactView.tsx`:

```tsx
import { Layers, FileText, ListOrdered } from "lucide-react";
import { FlashcardDeck } from "./FlashcardDeck";
import type { Flashcard, LabArtifacts, StudyPlanStep } from "../../lib/labApi";

const META = {
  flashcards: { icon: Layers, title: "Flashcards" },
  summary: { icon: FileText, title: "Quick revision" },
  study_plan: { icon: ListOrdered, title: "Study plan" },
} as const;

export function ArtifactView({ artifacts }: { artifacts: LabArtifacts }) {
  const present = (Object.keys(META) as (keyof typeof META)[]).filter(
    (k) => artifacts[k] !== undefined,
  );
  if (!present.length) return null;

  return (
    <div className="flex flex-col gap-5">
      {present.map((key) => {
        const { icon: Icon, title } = META[key];
        return (
          <div key={key}>
            <div className="flex items-center gap-2 mb-2.5">
              <Icon className="w-4 h-4 text-indigo-400" />
              <p className="text-xs font-semibold text-indigo-400 uppercase tracking-wide">
                {title}
              </p>
            </div>

            {key === "flashcards" && (
              <FlashcardDeck cards={(artifacts.flashcards ?? []) as Flashcard[]} />
            )}

            {key === "summary" && (
              <p className="text-sm text-zinc-300 leading-relaxed bg-zinc-800/40 border border-zinc-700/50 rounded-xl px-4 py-4">
                {artifacts.summary}
              </p>
            )}

            {key === "study_plan" && (
              <ol className="flex flex-col gap-2">
                {((artifacts.study_plan ?? []) as StudyPlanStep[]).map((s) => (
                  <li key={s.step}
                      className="bg-zinc-800/60 border border-zinc-700/60 rounded-xl px-4 py-3 flex gap-3">
                    <span className="w-6 h-6 rounded-lg bg-indigo-600/20 text-indigo-400 text-xs font-bold flex items-center justify-center flex-shrink-0">
                      {s.step}
                    </span>
                    <div>
                      <p className="text-sm font-semibold text-zinc-100">{s.title}</p>
                      {s.detail && <p className="text-xs text-zinc-500 mt-0.5">{s.detail}</p>}
                    </div>
                  </li>
                ))}
              </ol>
            )}
          </div>
        );
      })}
    </div>
  );
}
```

- [ ] **Step 3: The studio**

Create `frontend/src/components/lab/LabStudio.tsx`:

```tsx
import { useRef, useState } from "react";
import { Upload, NotebookPen, Loader2, Sparkles, ChevronRight, Check, RotateCcw } from "lucide-react";
import * as quizApi from "../../lib/notesQuizApiLang";
import { generateOutputs, OUTPUT_LABELS } from "../../lib/labApi";
import type { LabArtifacts, OutputType } from "../../lib/labApi";
import { ArtifactView } from "./ArtifactView";
import { NotesQuizModal } from "../learn/NotesQuizModal";

type InputMode = "text" | "pdf";
type Step = "input" | "generating" | "results";

const ALL_OUTPUTS: OutputType[] = ["quiz", "flashcards", "summary", "study_plan"];

export function LabStudio({
  studentId,
  onClose,
  lectureText,
}: {
  studentId: string;
  onClose: () => void;
  lectureText?: string;
}) {
  const [mode, setMode] = useState<InputMode>(lectureText ? "text" : "text");
  const [topic, setTopic] = useState("");
  const [notes, setNotes] = useState(lectureText ?? "");
  const fileRef = useRef<HTMLInputElement>(null);
  const [fileName, setFileName] = useState("");
  const [pdfFile, setPdfFile] = useState<File | null>(null);

  const [selected, setSelected] = useState<OutputType[]>(["quiz"]);
  const [step, setStep] = useState<Step>("input");
  const [error, setError] = useState("");
  const [artifacts, setArtifacts] = useState<LabArtifacts>({});
  const [lessonId, setLessonId] = useState<string | null>(null);

  const toggle = (t: OutputType) =>
    setSelected((s) => (s.includes(t) ? s.filter((x) => x !== t) : [...s, t]));

  const canSubmit =
    selected.length > 0 && (mode === "pdf" ? !!pdfFile : !!(notes.trim() || topic.trim()));

  async function handleGenerate() {
    setError("");
    setStep("generating");
    try {
      let docId: string;
      if (mode === "pdf") {
        if (!pdfFile) throw new Error("Please choose a PDF file.");
        docId = (await quizApi.uploadPdf(pdfFile)).docId;
      } else {
        const text = notes.trim() || topic.trim();
        if (!text) throw new Error("Please enter some notes or a topic.");
        docId = (await quizApi.uploadText(text, topic.trim() || undefined)).docId;
      }
      const res = await generateOutputs(docId, selected, studentId);
      setArtifacts(res.artifacts ?? {});
      setLessonId(res.lesson_id);
      setStep("results");
    } catch (e) {
      setError((e as Error).message);
      setStep("input");
    }
  }

  function restart() {
    setStep("input");
    setArtifacts({});
    setLessonId(null);
    setError("");
    setNotes(lectureText ?? "");
    setTopic("");
    setPdfFile(null);
    setFileName("");
  }

  if (step === "results" && lessonId) {
    // Quiz was selected — hand straight off to the existing, parity-verified
    // quiz UI, with any artifacts shown above it.
    return (
      <div className="flex flex-col gap-6">
        <ArtifactView artifacts={artifacts} />
        <NotesQuizModal
          variant="page"
          studentId={studentId}
          resumeLessonId={lessonId}
          onClose={onClose}
        />
      </div>
    );
  }

  return (
    <div className="flex flex-col gap-5">
      {error && (
        <p className="text-sm text-rose-300 bg-rose-950/40 border border-rose-800/50 rounded-xl px-4 py-3">
          {error}
        </p>
      )}

      {step === "input" && (
        <>
          {!lectureText && (
            <div className="flex bg-zinc-800/80 border border-zinc-700/50 rounded-xl p-1 gap-1">
              {(["text", "pdf"] as InputMode[]).map((m) => (
                <button
                  key={m}
                  onClick={() => setMode(m)}
                  className={`flex-1 flex items-center justify-center gap-2 py-2.5 rounded-lg text-sm font-medium transition-colors ${
                    mode === m
                      ? "bg-indigo-600 text-white shadow-lg shadow-indigo-900/40"
                      : "text-zinc-400 hover:text-zinc-200"
                  }`}
                >
                  {m === "pdf" ? <Upload className="w-3.5 h-3.5" /> : <NotebookPen className="w-3.5 h-3.5" />}
                  {m === "pdf" ? "Upload PDF" : "Type notes / topic"}
                </button>
              ))}
            </div>
          )}

          {lectureText && (
            <p className="text-xs text-indigo-300 bg-indigo-950/30 border border-indigo-800/40 rounded-xl px-4 py-3">
              Using this lecture's transcript as your material — no upload needed.
            </p>
          )}

          {mode === "text" ? (
            <div className="flex flex-col gap-3">
              <div>
                <label className="text-xs font-medium text-zinc-500 mb-1.5 block uppercase tracking-wide">
                  Topic
                </label>
                <input
                  value={topic}
                  onChange={(e) => setTopic(e.target.value)}
                  placeholder="e.g. React hooks, OS scheduling, Binary Search Trees…"
                  className="w-full bg-zinc-800/60 border border-zinc-700/60 rounded-xl px-4 py-3 text-sm text-zinc-100 placeholder-zinc-600 outline-none focus:border-indigo-500/60 transition-colors"
                />
              </div>
              <div>
                <label className="text-xs font-medium text-zinc-500 mb-1.5 block uppercase tracking-wide">
                  Notes <span className="normal-case text-zinc-600 font-normal">(optional)</span>
                </label>
                <textarea
                  value={notes}
                  onChange={(e) => setNotes(e.target.value)}
                  rows={6}
                  placeholder="Paste your notes here…"
                  className="w-full bg-zinc-800/60 border border-zinc-700/60 rounded-xl px-4 py-3 text-sm text-zinc-100 placeholder-zinc-600 outline-none focus:border-indigo-500/60 transition-colors resize-none"
                />
              </div>
            </div>
          ) : (
            <div
              onClick={() => fileRef.current?.click()}
              className="border-2 border-dashed border-zinc-700 hover:border-indigo-500/50 rounded-xl p-10 text-center cursor-pointer transition-colors"
            >
              <Upload className="w-5 h-5 text-indigo-400 mx-auto mb-3" />
              {fileName ? (
                <p className="text-sm text-indigo-300 font-medium">{fileName}</p>
              ) : (
                <p className="text-sm font-medium text-zinc-300">Click to choose a PDF</p>
              )}
              <input
                ref={fileRef}
                type="file"
                accept="application/pdf"
                className="hidden"
                onChange={(e) => {
                  const f = e.target.files?.[0];
                  if (f) { setPdfFile(f); setFileName(f.name); }
                }}
              />
            </div>
          )}

          <div>
            <p className="text-xs font-medium text-zinc-500 mb-2 uppercase tracking-wide">
              What should we make from it?
            </p>
            <div className="grid grid-cols-2 gap-2">
              {ALL_OUTPUTS.map((t) => {
                const on = selected.includes(t);
                const { label, blurb } = OUTPUT_LABELS[t];
                return (
                  <button
                    key={t}
                    onClick={() => toggle(t)}
                    aria-pressed={on}
                    className={`text-left rounded-xl border px-4 py-3 transition-colors ${
                      on
                        ? "border-indigo-500/60 bg-indigo-600/10"
                        : "border-zinc-700/60 bg-zinc-800/40 hover:border-zinc-600"
                    }`}
                  >
                    <div className="flex items-center gap-2">
                      <span
                        className={`w-4 h-4 rounded flex items-center justify-center flex-shrink-0 ${
                          on ? "bg-indigo-600" : "border border-zinc-600"
                        }`}
                      >
                        {on && <Check className="w-3 h-3 text-white" />}
                      </span>
                      <span className="text-sm font-semibold text-zinc-100">{label}</span>
                    </div>
                    <p className="text-xs text-zinc-500 mt-1 ml-6">{blurb}</p>
                  </button>
                );
              })}
            </div>
          </div>

          <button
            onClick={handleGenerate}
            disabled={!canSubmit}
            className="w-full flex items-center justify-center gap-2 bg-indigo-600 hover:bg-indigo-500 disabled:bg-zinc-800 disabled:text-zinc-600 text-white text-sm font-semibold rounded-xl py-3.5 transition-colors shadow-lg shadow-indigo-900/30"
          >
            <Sparkles className="w-4 h-4" />
            Generate {selected.length > 1 ? `${selected.length} things` : "it"}
            <ChevronRight className="w-4 h-4" />
          </button>
        </>
      )}

      {step === "generating" && (
        <div className="flex flex-col items-center justify-center py-20 text-center">
          <Loader2 className="w-7 h-7 text-indigo-400 animate-spin mb-4" />
          <p className="text-base font-semibold text-zinc-100 mb-1">Working through your material…</p>
          <p className="text-sm text-zinc-500">
            {selected.map((t) => OUTPUT_LABELS[t].label).join(" · ")}
          </p>
        </div>
      )}

      {step === "results" && !lessonId && (
        <>
          <ArtifactView artifacts={artifacts} />
          <button
            onClick={restart}
            className="w-full inline-flex items-center justify-center gap-2 bg-zinc-800 hover:bg-zinc-700 border border-zinc-700/50 text-zinc-300 text-sm font-medium rounded-xl py-3 transition-colors"
          >
            <RotateCcw className="w-4 h-4" /> Make something else
          </button>
        </>
      )}
    </div>
  );
}
```

- [ ] **Step 4: Let `NotesQuizModal` resume a lesson the studio already started**

The studio starts the lesson via `/generate`, so the modal must resume it rather than upload again. In `frontend/src/components/learn/NotesQuizModal.tsx`:

Add to the props type and destructuring: `resumeLessonId?: string;` / `resumeLessonId,`.

Add an effect after the state declarations:

```typescript
  // Started by LabStudio via /generate — fetch its state instead of showing
  // the upload form again.
  useEffect(() => {
    if (!resumeLessonId) return;
    setStep("loading");
    api.getLesson(resumeLessonId).then(applyLesson).catch((e) => {
      setError((e as Error).message);
      setStep("input");
    });
  }, [resumeLessonId]);
```

Add `useEffect` to the React import on line 1, and add `"getLesson"` to the `QuizApi` `Pick<...>` union on lines 14-17.

- [ ] **Step 5: Point the in-course companion at the Lab flow**

In `frontend/src/components/learn/CourseCompanion.tsx`, replace the `notes` tool render:

```tsx
      {tool === "notes" && (
        <div className="fixed inset-0 z-50 bg-black/70 flex items-center justify-center p-4"
             onClick={() => setTool(null)}>
          <div className="bg-zinc-900 border border-zinc-700/60 rounded-2xl w-full max-w-xl max-h-[90vh] overflow-y-auto p-6"
               onClick={(e) => e.stopPropagation()}>
            <LabStudio studentId={userId} onClose={() => setTool(null)} />
          </div>
        </div>
      )}
```

and import it: `import { LabStudio } from "../lab/LabStudio";`

- [ ] **Step 6: Build**

```bash
cd /Users/swanandkadam/Desktop/01dev-React-hermes/frontend && npm run build
```

Expected: clean build. Fix any type errors before committing.

- [ ] **Step 7: Run the backend suite too** (the hand-off copy test changed in Task 5)

```bash
cd ../backend && bash scripts/run_tests.sh
```

Expected: `ALL PASSED`.

- [ ] **Step 8: Commit**

```bash
cd /Users/swanandkadam/Desktop/01dev-React-hermes
git add -A
git commit -m "feat: the Lab page — source input, output selection, artifact rendering

/quizme becomes /lab (old path still routes there for bookmarks). Students
tick any combination of quiz/flashcards/quick-revision/study-plan; artifacts
render as real cards and ordered steps, and if the quiz was selected the
existing parity-verified quiz UI takes over below them, resuming the lesson
/generate already started. The in-course companion opens the same studio."
```

---

### Task 7: Deploy and verify the whole product

- [ ] **Step 1: Deploy backend, then frontend**

```bash
cd /Users/swanandkadam/Desktop/01dev-React-hermes/backend
RAILWAY_CALLER="skill:use-railway@1.4.0" RAILWAY_AGENT_SESSION="lab-phase3" \
  railway up --service the01dev-backend --detach -m "feat: Lab outputs + fan-out"
# wait for SUCCESS, then:
cd ../frontend && npm run build && netlify deploy --prod --dir=dist
```

No Hermes redeploy — `app/mcp/the01dev_tools.py` was not touched this phase.

- [ ] **Step 2: Verify each selection shape against production**

```bash
BASE=https://the01dev-backend-production.up.railway.app/api/lab
SID=x94FcfXU7KRrobyOA4UHDukbRoC2
NOTES='A closure is a function together with the variables captured from its enclosing scope. The captured variables outlive the outer call.'

for SEL in '["flashcards"]' '["summary","study_plan"]' '["quiz"]' '["quiz","flashcards","summary","study_plan"]'; do
  echo "=== outputs=$SEL ==="
  D=$(curl -s -X POST $BASE/upload-text -H "Content-Type: application/json" \
      -d "{\"text\":\"$NOTES\",\"title\":\"Closures\"}" \
      | python3 -c "import sys,json;print(json.load(sys.stdin)['docId'])")
  curl -s -X POST $BASE/generate -H "Content-Type: application/json" \
    -d "{\"docId\":\"$D\",\"outputs\":$SEL,\"student_id\":\"$SID\"}" \
    | python3 -c "
import sys,json; b=json.load(sys.stdin)
print(' status:', b['status'], '| artifacts:', sorted(b.get('artifacts') or {}), '| lesson:', bool(b.get('lesson_id')))
a=b.get('artifacts') or {}
if 'flashcards' in a: print(' first card:', a['flashcards'][0] if a['flashcards'] else 'EMPTY')
if 'summary' in a: print(' summary:', (a['summary'] or '')[:80])
if 'study_plan' in a: print(' plan steps:', len(a['study_plan'] or []))
"
done
```

Expected per selection: flashcards-only → `status: complete`, cards present, no lesson. summary+study_plan → both present, no lesson. quiz-only → `status: awaiting_approval`, `artifacts: []`, lesson present. All four → three artifacts **and** a lesson.

- [ ] **Step 3: Verify the library persisted them**

```bash
curl -s "$BASE/library?student_id=$SID" | python3 -c "
import sys,json
rows=json.load(sys.stdin)
print('artifacts saved:', len(rows))
for r in rows[:6]: print(' ', r['artifact_type'], '|', r['doc_title'], '|', r['created_at'][:19])
"
```

Expected: one row per artifact generated in Step 2 (6 total from those four runs), newest first.

- [ ] **Step 4: Browser walkthrough — required, not optional**

Open `https://the01.dev/lab` signed in, then check all of:
1. Nav reads **Lab**, not QuizMe; `the01.dev/quizme` still loads the page.
2. Tick **flashcards only** → cards render and flip; no quiz appears.
3. Tick **all four** → artifacts render, then the quiz's objectives screen appears below them; approving starts the quiz; a wrong answer shows a hint, a correct one an explanation.
4. Open a course page → the companion's notes tool opens the same studio.
5. Network tab: calls go to `the01dev-backend-production.up.railway.app/api/lab/*`.

- [ ] **Step 5: Report what needs design iteration**

The UI here is functional-first. Note anything that needs the human partner's eye — spacing, card sizing, whether artifacts-above-quiz reads well when all four are selected — rather than silently treating it as finished.

---

## Not in this plan (deliberately)

- **Lecture-as-source wiring** — `LabStudio` already accepts a `lectureText` prop, but nothing passes it yet. That is Phase 4.
- **A dashboard breakdown of course vs self-study `concepts_mastered`** — provenance exists from Phase 2; the dashboard change is its own small piece of work.
- **Library management (rename, delete, re-generate)** — read-only library this phase.
