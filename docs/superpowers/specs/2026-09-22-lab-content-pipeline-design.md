# Lab — student content generation pipeline

**Status:** design approved, not yet implemented
**Date:** 2026-09-22

## Goal

One pipeline where a student brings their own material and chooses what to make
from it. Ingest (typed topic/notes, uploaded PDF, or a course lecture) → pick any
subset of four outputs → generate.

Outputs: **quiz · flashcards · summary (quick revision) · study plan**

Selecting only the quiz must behave exactly like the quiz that works today.
Selecting several fans out. Everything a student does here feeds one learning
journey — including concepts the platform has never taught.

Product name: **Lab**. Route `/lab`, API `/api/lab/*`, module
`app/services/lab/`. This replaces "QuizMe", whose name described one of the
four outputs.

## Why this shape

The driving principle, in the user's words: *"I don't want our students to adapt
to our hard-coded schema, hard-coded concepts — students could choose to learn
whatever they want and it's our job to keep track of that."*

That rules out two tempting designs: a fixed concept vocabulary students must
map onto, and a separate "self-study" learner model kept away from real course
progress. Both make the student serve the schema.

## Starting state (verified 2026-09-22, not assumed)

- `backend/lesson_service/` is an **undeployed** sibling package: a LangGraph
  reimplementation of the quiz flow (`graph.py`) plus a planner-executor
  artifacts orchestrator (`artifacts_graph.py`). No Dockerfile, no
  requirements.txt — it has never run outside a dev machine.
- The live QuizMe the frontend actually calls is the **external Mastra service**
  at `pdf-learning-tutor-v2-production.up.railway.app`. Confirmed by `/health`
  shape: it returns `{"success":true}`, while `lesson_service` returns
  `{"status":"ok","service":"quizme","orchestrator":"langgraph",...}`.
  `NotesQuizModal.tsx` defaults to `api = quizApi` (the Mastra client) and
  neither call site overrides it. `VITE_QUIZME_LANG_URL` is unset in Netlify.
- `the01dev-backend` already generates artifacts from arbitrary text:
  `content.py:generate_quiz(text)` returns **structured MCQ dicts** (better than
  the artifacts graph's flat text) and `generate_notes(text)` returns markdown.
- `vector_store.get_lecture_transcript(lecture_id)` already exists, so
  lecture-as-source needs no new retrieval code.
- `record_observation` already accepts **any** concept string with no
  validation and creates a `concept_performance` row
  (`created_by: "chat_observation"`). The open concept space already exists;
  what is missing is resolution.
- `quiz_sessions` already stores **per-answer** rows
  (`answers: [{question_id, concept, correct, ...}]`), so attempt-level
  provenance is already recorded — it has no read path.

### Dependency compatibility — measured, not assumed

`langgraph==1.2.9` + `pypdf` + `langfuse` install on top of the backend's exact
pinned requirements with **zero version drift**: fastapi stays 0.115.5, starlette
0.41.3, pydantic 2.10.3, openai 1.58.1. `FastAPI()` instantiates and
`StateGraph`/`interrupt`/`Send`/`Command` all import.

**No venv split needed** — unlike `fastmcp`, which forced the existing
`.venv`/`.mcp-venv` split. The modern fastapi/starlette/pydantic in
`backend/.lesson-venv` were incidental unpinned installs, not langgraph
requirements.

One thing to fix on merge: `lesson_service/llm.py` builds its OpenAI client **at
import time** (`_client, _MODEL = _make_client()`), which the main backend's
services deliberately don't do. Make it lazy.

## Architecture — one graph, fan-out sequenced before the quiz

```
START
  → fan_out (driven directly by the student's selection — NO approval gate)
        ──Send──►  gen_summary     ┐
                   gen_flashcards  ├── parallel, one-shot
                   gen_study_plan  ┘
  → join → persist each artifact to Postgres as it lands
  → quiz selected?  ── no ──► END
        │ yes
        ▼
    plan_objectives
  → await_approval        interrupt(): student reviews/edits objectives
  → generate_quiz
  → await_submit          interrupt(): one per objective
  → [loop to generate_quiz | summarize] → END
```

**Why artifacts are sequenced before the quiz rather than run as a sibling
branch.** If the quiz branch interrupts inside the same superstep as the artifact
generators, whether the completed artifacts' writes are durable and readable at
suspend time depends on LangGraph's pending-write semantics. Sequencing removes
the question: artifacts are finished and saved before the long-lived interactive
part begins.

**Why there is no approval gate on artifacts.** The student already chose their
outputs in the UI. `artifacts_graph.py` currently does
`planner → interrupt(approve plan) → fan out`, but that interrupt asks them to
confirm what they just said. HITL earns its place on the **quiz's objectives**
plan — reviewing what you'll be tested on is real value, and it is part of the
flow that exists today.

The quiz interrupts **twice per cycle, not per question**: once at plan
approval, once per objective submit. The frontend receives a whole objective's
quiz and runs the questions locally, calling back only with that objective's
score. That coarse granularity (2–5 interrupts per lesson) is what makes one
graph viable.

Selection behaviour:

| Selection | Behaviour |
|---|---|
| quiz only | fan-out is an empty passthrough; identical to today's flow |
| flashcards only | generates, persists, END after join |
| all four | three artifacts in parallel, saved, then the quiz |

Ordering when both are selected: artifacts first (roughly one generation's
latency since they're parallel), *then* the objectives screen. Quiz-first with
background artifact generation was considered and rejected as a bigger build
(needs background tasks plus UI polling/streaming).

## Ingestion

```
POST /api/lab/ingest
  {source:"text",    text, title?}      → stored as-is
  {source:"pdf",     file:<multipart>}  → pypdf extraction
  {source:"lecture", lecture_id}        → vector_store.get_lecture_transcript()
→ {doc_id, title, char_count}
```

All three normalize to one Postgres row in `lab_docs`:
`{doc_id, student_id, title, text, source, source_ref}` where `source_ref` holds
the `lecture_id` when applicable.

`source_ref` does double duty: **the ingest source determines whether resulting
concepts are course-grounded.** A quiz built from `react-perf-4-1` is course
content; one built from an uploaded PDF is not. Provenance falls out of
ingestion rather than needing separate bookkeeping.

## Output generators

Reuse before rebuilding, per the repo's own "one capability = one
implementation" rule:

| Output | Implementation |
|---|---|
| quiz | `lesson_service/llm.py:gen_quiz`, **extended to emit `concept`** |
| flashcards | new generator (port `lesson_service/llm.py:gen_artifact`'s prompt) |
| summary | new generator (same) |
| study plan | **new generator, separate from the quiz's objectives** |

Study plan is its own artifact — a standalone readable roadmap — not a rendering
of the quiz's objectives. Two plan-ish generators, deliberately.

### Why the quiz generator is NOT `content.py:generate_quiz`

The two existing quiz generators have disjoint output shapes — neither is a
superset, so they are not interchangeable:

| | `content.py:generate_quiz` | `lesson_service` `gen_quiz` |
|---|---|---|
| `question`, `options` | yes | yes |
| correct answer | `answer` (option **text**) | `correctIndex` |
| `explanation` | **no** | yes |
| `hint` | **no** | yes |
| `concept` | yes | **no** |

The interactive quiz UI displays `hint` on a wrong answer and `explanation` on a
correct one (see `NotesQuizModal`), so `content.py`'s output cannot drive it.
Concept resolution needs `concept`, which only `content.py` emits.

Resolution: keep `gen_quiz` (already wired into the interactive graph, already
produces hint/explanation/correctIndex) and **add `concept` to its prompt and its
`Question` schema** — an additive change. `content.py:generate_quiz` is left
untouched for its existing MCP-tool use rather than being forked or extended.

`content.py:generate_notes` likewise stays where it is, unused by Lab. Notes was
dropped from the output set.

## Concept resolution — the open, growing concept space

Every concept write goes through one resolver: the graded course quiz
(`adaptive_service`), Hermes's chat observations (`record_observation`), and Lab
quizzes.

```python
resolve(candidate_name, course_id | None) -> concept_id
  1. slug = slugify(candidate)               # "React.memo" → "react-memo"
  2. exact slug match against known concepts → use it          (free)
  3. embed(candidate); cosine vs cached embeddings of all
     known concept names; best >= 0.64      → use the match    (1 API call)
  4. otherwise → CREATE a new concept node, attached to
     `course_id` if one was supplied, else null;
     created_by: "student_content"
```

`course_id` is the **ingest source's** course, not a filter on the search. The
search pool is always every known concept — a self-study concept must be able to
resolve onto a course concept, which is the whole point. What `course_id` affects
is only step 4: a concept newly discovered from a *lecture* source attaches to
that lecture's course (it is genuinely course material the graph didn't have yet),
while one discovered from an uploaded PDF attaches to nothing (`null`).

This produces exactly the two required behaviours:

- Notes on **closures / scope / npm linking** resolve onto existing course
  concepts and **update those rows' weights** — their course mastery genuinely
  moves because they quizzed themselves.
- Notes on **Kubernetes** match nothing, so a new concept node is created and
  tracked. The graph grows to fit the student.

Unlike `record_observation` today (which creates only a performance row), this
creates a real **node** in `concepts`, so a self-study concept is a first-class
graph citizen that can later gain prerequisite edges.

**Efficiency:** the known pool is never re-embedded. Each concept node stores its
embedding once at creation in its `concepts` row — same caching precedent as
`vector_store`'s `rag_chunks`. Per unseen candidate: one embedding call plus
in-memory cosine. Exact-slug hits cost nothing.

**Where it runs:** at quiz *generation* time. Generated questions carry canonical
concept ids, so the grading path (`adaptive_service._update_perf`) needs **no
changes at all** — resolution happens once per quiz, not once per answer.

### Where 0.64 comes from

Measured over 31 pairs across two samples (real course concepts vs. plausible
LLM-generated candidate tags):

| similarity | pair | correct action |
|---|---|---|
| 0.755 | `react-memo` vs `React.memo` | merge |
| 0.716 | `use-callback` vs `useCallback` | merge |
| 0.709 | `use-callback` vs `useCallback hook` | merge |
| 0.578 | `event-loop` vs `Event Delegation` | split (shares a word, unrelated) |
| 0.567 | `shallow-equality` vs `referential equality` | split (debatable) |
| 0.514 | `use-memo` vs `memoization` | split (general ≠ specific) |
| 0.382 | `event-loop` vs `microtask-queue` | split (real prereq edge) |
| 0.367 | `prototype-inheritance` vs `class-syntax-sugar` | split (real prereq edge) |
| 0.334 | `event-loop` vs `kubernetes` | split (unrelated baseline) |

True matches cluster at **0.709–0.755**; false matches cap at **0.578**. The band
between is empty and 0.13 wide. **0.64** is its midpoint — ~0.066 margin down to
the nearest false match, ~0.069 up to the nearest true one.

Note for anyone revisiting this: an earlier draft used 0.9, which would have
merged **nothing** — even `React.memo` vs `react-memo` only scores 0.755. Short
concept names do not score like sentences, and unrelated short strings share a
noise floor around 0.33–0.38.

**Two caveats that belong in monitoring, not in a constant:**

1. Candidates above are LLM-imagined, not from real student uploads. Real notes
   will produce weirder tags — which is why every decision is logged.
2. **The threshold will likely need to rise as the concept pool grows.** With 9
   concepts there are 9 chances to draw a spurious high score; with 500
   accumulated self-study concepts there are 500. More draws, higher expected
   maximum, purely by chance.

Every decision writes to `concept_resolutions`:
`{candidate, resolved_to, score, method: slug|embedding|created, at}`.

## Learner model and explainability

One unified model. Lab quizzes write **both** `concept_performance` and
`quiz_sessions`, exactly as `adaptive_service` does.

`quiz_sessions` rows matter as much as performance rows: `journey_service._streak`
and the quiz counts read `quiz_sessions.completed_at`, so without them
self-study would not move the streak — defeating the intent. Lab sessions carry
`source`, `doc_id`, `doc_title` (course sessions carry `course_id`,
`course_title`).

### explain_concept

A student must be able to ask *"I never enrolled in a course on React.memo — why
is it my strong topic?"* and get a real answer. `concept_performance` is only a
running counter, but `quiz_sessions.answers[].concept` already records every
attempt, so this needs **no new collection**:

```
explain_concept(user_id, concept):
    read this student's quiz_sessions
    → every answer where answer.concept == concept
    → group by that session's source (course_id+title | doc_id+title)
    → return the breakdown
```

Exposed to Hermes as a tool, so the student just asks in chat. Target answer:

> "Your `react-memo` score is 89%. That's 5 questions from the **React
> Performance Patterns** course quiz (4 correct), plus 4 from the quiz you
> generated on your **own notes, 'React Perf Notes'**, on Sept 18 (all correct).
> You never took a course specifically on React.memo — the concept comes from
> lecture 4.1 of React Performance Patterns."

### Contestable merges

The explanation surfaces resolver decisions: *"…including 4 questions your notes
tagged 'useCallback hook', which we treated as the same concept."* If the student
disagrees, that is a signal to split — sourced from the person best placed to
judge. Merges are auditable and contestable, not silent. This is also the best
available source of resolver-tuning data.

### Consequence to handle in the UI

`concepts_mastered` will now mix course and self-study concepts. The dashboard
should break it down so the number stays honest.
`get_learning_strengths` already degrades correctly: self-study concepts have no
knowledge graph, so it returns `course_id: null` / `prerequisites: []` (verified
2026-09-22). Prerequisite reasoning stays course-only, which is correct — there
is no graph to reason over for an arbitrary PDF.

## Persistence

| Data | Where |
|---|---|
| ingested docs (`lab_docs`) | Postgres |
| generated artifacts (`lab_artifacts`) | Postgres — the student's library |
| concept nodes + embeddings (`concepts`) | Postgres |
| resolution decisions (`concept_resolutions`) | Postgres |
| in-flight graph state | in-memory `MemorySaver` |

Artifacts persist **as each generator lands**, not at end of run, so a long-lived
quiz tail never holds finished artifacts hostage.

Accepted tradeoff: a redeploy kills in-flight sessions (an upload plus an
unapproved objectives plan), but never past work.
`langgraph-checkpoint-postgres` is a drop-in upgrade if that becomes painful.

## API surface

```
POST /api/lab/ingest                        {source, ...}              → {doc_id, title}
POST /api/lab/generate                      {doc_id, outputs:[...]}    → {run_id, status, artifacts, proposed_objectives?}
POST /api/lab/{run_id}/approve-objectives    {objectives, per_quiz}     → {quiz, objective_index}
POST /api/lab/{run_id}/submit                {score, total}             → next quiz | summary
POST /api/lab/{run_id}/ask                   {question}                 → Socratic tutor nudge
GET  /api/lab/{run_id}                                                  → poll/resume state
GET  /api/lab/library                        ?student_id=               → saved artifacts
```

`/generate` behaves by selection: without a quiz it runs to completion and
returns artifacts; with a quiz it completes the artifacts, suspends at objectives
approval, and returns both.

**The quiz portion keeps the existing `LessonView` shape.** That is a deliberate
migration advantage: the frontend's quiz UI works nearly unchanged.

## Frontend

`/lab` becomes the Lab page: source tabs (type / PDF / **pick a lecture**) → four
output checkboxes → generate. Results render artifacts (flashcards as cards,
summary and study plan as markdown). If the quiz was selected, hand off into
`NotesQuizModal`'s existing `plan` / `quizzing` / `complete` steps — they already
speak `LessonView`, so they are reused rather than rewritten.

In-course, `CourseCompanion` gains "generate from this lecture" with the lecture
pre-selected and no upload step.

Nav label changes from **QuizMe** to **Lab**.

## Migration — this replaces a live feature

Order matters:

1. Build and deploy the pipeline into `the01dev-backend`; verify with real calls
2. Point the frontend at the new endpoints
3. **Verify quiz parity live** — the genuinely risky step
4. Only then decommission the Mastra service

`frontend/src/lib/notesQuizApi.ts` is kept as the shared type source and Mastra
reference — do not delete it (standing instruction from a prior session).

## Testing

- **Unit:** resolver (slug / embedding / create paths, threshold boundary), three
  ingest sources, each generator, graph routing for all three selection shapes
- **Integration:** full graph runs against `InMemoryStore` with a fake LLM
- **Live:** end-to-end on the deployed service, with an explicit quiz-parity
  check before retiring Mastra
- New MCP-tool tests go in `MCP_ONLY_TESTS` in `backend/scripts/run_tests.sh`
  (the `.mcp-venv` list), matching existing convention

## Risks

| Risk | Mitigation |
|---|---|
| Replacing a working live feature (the quiz) | Verify-then-retire ordering; Mastra stays up until parity is confirmed |
| In-memory checkpoints lose in-flight sessions on redeploy | Accepted; artifacts persist independently; Postgres checkpointer is a drop-in later |
| Resolver threshold derived from partly-synthetic data | Every decision logged; merges surfaced and contestable via `explain_concept` |
| Threshold drift as the concept pool grows | Monitor logged scores; treat 0.64 as a starting point, not a constant |
| Unbounded concept space mixes into dashboards | Provenance on every row; UI breakdown of course vs self-study |
| **LangGraph superstep semantics** | See below — implementation task #1 |

## Phasing

This is too large for one implementation plan. Four slices, each independently
shippable and separately planned.

**Phase 0 — spike.** The LangGraph semantics check below. Gates everything else.

**Phase 1 — merge and parity, no new behaviour.** Move `lesson_service` into
`app/services/lab/`, make the LLM client lazy, add `langgraph`/`pypdf`/`langfuse`
to `requirements.txt`, expose the quiz-only path via `/api/lab/*`, point the
frontend at it, verify quiz parity live, retire Mastra.

Ships real value on its own: the quiz stops depending on an external service we
don't control. And because nothing else changes, parity verification is clean —
no new features confounding the comparison.

> **Sequencing correction found during spec review.** Phase 1 must NOT write to
> `concept_performance` yet. The Mastra service is external and writes nothing to
> our learner model today, so a pure migration should preserve exactly that. If
> Phase 1 wrote concepts without the resolver existing yet, fragmentation would
> start immediately and need cleaning up later. Learner-model coupling lands with
> the resolver, together, in Phase 2.

**Phase 2 — concept resolution, learner-model coupling, explainability.** The
resolver plus `concept_resolutions` logging; route `record_observation` through
it; Lab quizzes begin writing `concept_performance` and `quiz_sessions` with
provenance; `explain_concept` and its Hermes tool.

Independently valuable — the resolver improves the *existing* learner model
(Hermes's chat observations stop fragmenting) even before Lab has new outputs.

**Phase 3 — the other three outputs.** Flashcards, summary and study-plan
generators; the fan-out graph shape; artifact persistence and the library; the
output-selection UI; the `/lab` page and nav rename. This is where the new
product capability actually lands.

**Phase 4 — lecture source and in-course entry.** The third ingest source and the
`CourseCompanion` integration. Purely additive.

## Implementation task #1 — the spike

The whole graph shape rests on one unverified assumption: that a `Send` fan-out
which joins, followed by an `interrupt()` in the graph's tail, behaves as
expected — specifically that artifacts written before the interrupt are durable
and readable from the checkpoint while the run is suspended.

Verify this with a throwaway graph before building anything else. If it does not
hold, the fallback is two graphs in one service (artifacts graph and lesson graph
invoked in sequence by the endpoint rather than joined in one run) — which loses
the single-run elegance but nothing functional.

**Resolved 2026-09-22: PASS.** A `Send` fan-out that joins, followed by an
`interrupt()` in the tail, leaves the fan-out's writes readable via
`get_state()` while the run is suspended. The single-graph design in
"Architecture" stands as written.
