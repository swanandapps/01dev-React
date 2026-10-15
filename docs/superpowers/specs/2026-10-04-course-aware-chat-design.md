# Course-Aware Chat — Design

**Date:** 2026-10-04 · **Status:** draft, awaiting review · **Scope:** cleanup + both chats (Ask page, video-player tutor) — build now; Hermes messaging channel — recorded here, built last

## 1. Why this exists

In a demo to a VP of Engineering, the student asked the web chat (`/ask`) "how do I publish an npm library". It returned a generic answer with no citation, no enrollment check, no course pointer. The VP: "this is similar to ChatGPT; anyone could build this."

The platform **has** this content: *Build a Custom Library* → lecture 8.1 "The npm link command" (transcript), and chapter "NPM Package Development" (catalog). The demo account is not enrolled in that course. Three code-level causes:

1. **Retrieval is optional.** `hermes_chat` (`backend/app/main.py:224`) hands the question to Hermes; course search is an MCP tool the model *may* call. Nothing forces it.
2. **The prompt instructs the ChatGPT behaviour.** `main.py:389-392` and `backend/hermes/SOUL.md` ("Avoid" section) say: when the course library doesn't cover it, answer from general knowledge — "never a reason to decline". The route's own docstring (`main.py:236`) claims the opposite rule.
3. **No catalog.** The 11-course catalog exists only in `frontend/src/data/tracks.ts`. The backend knows only the 4 courses with transcripts. Enrollments use numeric ids (`2`); transcripts use slugs (`custom-library`).

Separately, verified against Hermes source (commit `1cb26bf`): Hermes is documented as "a single-tenant personal agent" (`SECURITY.md:34`); its API server caps concurrent runs at 10 by default; built-in memory and `session_search` are profile-wide, not per student. Hermes is the wrong runtime for the high-traffic web chat and the right one for messaging channels (§7).

## 2. Goals and non-goals

**Goals**
- Remove dead, duplicate and out-of-scope code first (§3a), so the rebuild lands in a smaller codebase.
- **Both** chats — the global Ask page and the tutor inside the video player — answer with the course library and the student's enrollments in hand, guaranteed by code, not by the model choosing a tool. One shared pipeline (§4.8).
- Three answer cases (§4.3), including a course recommendation when the answer lives in a course the student doesn't own.
- Student identity reaches tools from the server, never from the model.
- No visible frontend change. Same URL, same SSE contract.

**Non-goals (separate specs)**
- Demo data enrichment, dashboard visuals, practice arena, demo script.
- Hermes messaging channel — designed in §7, built last.
- Renaming `/api/hermes/*` routes (later; would touch the frontend).
- Pushing to GitHub. Deploys go straight from the terminal (Railway CLI).

## 3. Decisions

| Decision | Choice | Why |
|---|---|---|
| Web chat runtime | **LangChain `create_agent`** (new deps `langchain`, `langchain-openai`) | Flow is linear: lookup → agent → save. No branching or human pause, so a custom LangGraph graph adds structure without value. `create_agent` runs on LangGraph underneath, so LangSmith tracing still applies. Lab keeps its LangGraph graph because it branches and pauses. |
| Where the "always look up first" guarantee lives | Plain Python before the agent call | The guarantee is a function call, not a framework feature. |
| Tool access for web chat | Direct in-process calls to `app/services/*` | Web chat lives in the same backend. MCP is a boundary for *external* runtimes; using it in-process adds a hop and buys nothing. |
| Single source of truth | `app/services/*` functions | Both doorways (LangChain tools now, MCP tools for Hermes later) are thin wrappers. Already the rule in `the01dev_tools.py` ("one capability = one implementation"). |
| Not-enrolled behaviour | **Short answer + course pointer** | Helpful, makes the course the obvious next step, doesn't read as a paywall. |
| System prompt file | Rename `backend/hermes/SOUL.md` → **`backend/app/grounding/grounding_prompt.md`** | It's the backend's file, not Hermes's. A file is easy to read and review, and the audit log fingerprints the exact version that answered. Same for every student — personalization comes from learner state, not this file. |
| GEPA (automated prompt evolution) | **Removed** | Not part of the demo story, no frontend caller; the prompt is now edited by hand and reviewed like code. |

## 3a. Cleanup — runs before the rebuild

Every "no caller" claim below was checked by grep on 2026-10-04; the implementation plan re-verifies each one immediately before deleting.

**A. Dead code (no callers)**
- `backend/app/services/ollama_client.py`, `backend/app/services/openai_tutor.py`.
- Unused import `_build_sources` (`main.py:26`) and its alias (`rag_service.py:14-15`).
- Endpoints (routes only — their services stay, other features use them): `GET /api/ai/questions/{id}`, `POST /api/ai/quiz-session`, `GET /api/ai/quiz-sessions`, `GET /api/ai/recommendations`, both `/api/ai/knowledge-graph/*`, `GET /api/lab/library`. If `recommendation_service` is left with only `invalidate` (called from `adaptive_service.py:263`), reduce it to that.
- Frontend exports: `askQuestion`, `askQuestionStream` (`ragApi.ts`); `getQuestions`, `saveQuizSession`, `listQuizSessions`, `getRecommendations`, `buildKnowledgeGraph` (`learnApi.ts`); `getLibrary` (`labApi.ts`).
- Frontend files: `App.css`, `assets/hero.png`, `assets/react.svg`, `assets/vite.svg`.
- Dependencies: backend `websockets`, `opentelemetry-instrumentation-fastapi`; frontend `video.js`, `@types/video.js`, `plyr`, `@tanstack/react-query` (remove its provider in `main.tsx`).
- Leftovers: `backend/data/agent_fs/`, `backend/lesson_service/` + `.lesson-venv/` (local), `backend/scripts/migrate_enrollment_from_firestore.py`.

**B. Superseded chat path**
- `/api/ai/ask`, `/api/ai/ask/stream` (`main.py:206-221`) and `rag_service.py`. Keep `app/prompts.py` / `answer_generator.py` only if still reached via `grounding.answer_grounded` after §C; otherwise remove with them.
- `smalltalk_classifier` and its call site (`main.py:264-271`) — observe-only, never acts.

**C. Hermes web path (removed as part of §4.5)**
- `hermes_client.py`; `HERMES_URL`, `HERMES_API_KEY`, `HERMES_MODEL_LABEL` in the backend; the `chat_citations` delete/read in `main.py`.
- **Kept for §7:** `app/mcp/the01dev_tools.py`, `requirements-mcp.txt`, `hermes-service/`, `trace.py`, `trace_server.py`, `trajectory_eval.py`, `app/eval/trajectory_set.json`.
- Tests rewritten: `test_hermes_chat_{routing,citations,identity_context}.py`, `test_admin_auth_gate.py:57`.

**D1. Mastra**
- **Verified ported (2026-10-04):** the Lab UI (`LabStudio.tsx`, `NotesQuizModal.tsx`) calls the backend's own LangGraph flow at `/api/lab` through `notesQuizApiLang.ts`. `notesQuizApi.ts` (the Mastra client) is imported only for its types.
- Move those types to `frontend/src/types/lab.ts`; repoint imports in `notesQuizApiLang.ts`, `NotesQuizModal.tsx`, `labApi.ts`; delete `notesQuizApi.ts` (its functions and the Mastra URL constant). `notesQuizApiLang.ts` is live — keep it.
- Drop Mastra references from comments/docstrings (`lab/graph.py`, `lab/llm.py`, `lab/routes.py`, `NotesQuizModal.tsx`, `test_lab_routes.py`); history stays in git.
- The external Mastra service (`pdf-learning-tutor-v2-production.up.railway.app`) still answers HTTP 200 but is not in the user's Railway workspace (checked 2026-10-04) — deployed from another account. Nothing here calls it; shutting it down is the user's action, outside this work.

**D2. Local models / Ollama** — OpenAI is the only provider.
- Remove Ollama branches in `eval_llm.py`, `lab/llm.py`, `accuracy.py`, `ragas_eval.py`, `context_meter.py`, `memory_service.py`, `trace.py`, `trace_server.py`; `TUTOR_PROVIDER` (`main.py:49`); Ollama entries in `.env.example`; `docker-compose.sovereign.yml`.

**Unchanged for now:** the three observability stacks (LangSmith, Langfuse, OTel), offline keyword-search mode, the Firestore store fallback, the eval/RAGAS endpoints.

## 4. Web chat — components

```
POST /api/hermes/chat  (unchanged URL + SSE contract: sources / token / done / error)
  │  PII scrub → intent classify → audit → (unchanged)
  ├─ 1. course_lookup(question, student_id)        ← plain code, always runs
  │     ├─ transcript search (existing vector store)
  │     ├─ catalog search (new index)
  │     └─ label each hit enrolled / not enrolled → decide case
  ├─ emit `sources` event (citation cards) BEFORE the answer
  ├─ 2. tutor agent (LangChain create_agent, gpt-4.1-mini, streaming)
  │     system = grounding_prompt.md + case rule + lookup facts + student memory
  │     tools  = thin wrappers over app/services, student_id bound server-side
  └─ 3. record_turn (memory) → `done`
```

### 4.1 Course catalog — `backend/app/data/catalog.json`

- Generated from `frontend/src/data/tracks.ts` by `backend/scripts/build_catalog.py` (parses the TS data; no frontend change). `tracks.ts` stays the source of truth.
- Per course: `id` (numeric, matches enrollments), `slug` (transcript id, from the existing `RAG_COURSE_MAP` mapping in `frontend/src/types/rag.ts`; null if none), `title`, `description`, `launched`, `url` (`/course/{id}`), `chapters[]` and `modules[]` (name + description).
- `app/services/catalog_service.py`: load once; `get(course_id)`, `by_slug(slug)`, `all()`.
- **Drift test:** fails if `catalog.json` differs from a fresh build of `tracks.ts`.

### 4.2 Catalog index

- One entry per course *and* per module/chapter: text = course title + module title + description. About 100 entries.
- Embedded with the existing `embedding_service`; held in memory beside the transcript index, built at startup. Keyword fallback for local no-API mode, same as transcripts.
- Lets courses without transcripts (7 of 11) be recommended.

### 4.3 `course_lookup` — `backend/app/services/course_lookup.py`

```python
async def course_lookup(question: str, student_id: str) -> CourseLookup
# CourseLookup: case, transcript_hits[], catalog_hits[], enrolled_course_ids
# each hit carries: course_id, course_title, enrolled: bool, score, + lecture/timestamp/text (transcript) or module (catalog)
```

Case decision (code, not model):

| Case | Rule | Student gets |
|---|---|---|
| `ENROLLED_MATCH` | Best hit above threshold is in an enrolled course (transcript or catalog) | Answer grounded in the lecture; cite lecture + timestamp |
| `NOT_ENROLLED_MATCH` | Hits above threshold exist, none in an enrolled course | Short answer (3–5 sentences), then: "This is covered in *{course} → {lecture/module}*. You're not enrolled — here's the course." |
| `NO_MATCH` | Nothing above threshold | General answer, labelled plainly as not from a the01.dev course |

- Enrolled hits win over not-enrolled hits when both exist.
- **Thresholds are measured, not guessed.** `backend/scripts/calibrate_lookup.py` runs a labelled set of on-topic / off-topic questions through both indexes and prints score distributions; the chosen cut-offs are written back into this spec with the data that justified them (same method as Lab's 0.64). **Measured 2026-10-04** (23 labelled questions, OpenAI text-embedding-3-small): transcript **0.54** (100% accuracy, max-accuracy range 0.48–0.60), catalog **0.34** (100%, range 0.21–0.46); midpoint of each range. Demo question "how do I publish an npm library": transcript 0.601, catalog 0.567 — the catalog hit alone still yields the course pointer if the transcript score dips.
- Unknown enrollment (lookup error) → treat as not enrolled; never fail the turn.

### 4.4 Tutor agent — `backend/app/services/tutor_agent.py`

- `create_agent(model=ChatOpenAI("gpt-4.1-mini", streaming=True), tools=[...], system_prompt=...)`. Exact API verified against current LangChain docs during planning.
- **System prompt** = `grounding_prompt.md` + the one case rule for this turn + a "COURSE FACTS" block rendered from `CourseLookup` + the existing memory block (`memory_service.memory_context`) + last 3 turns as history (unchanged behaviour).
- **Tools** (thin wrappers, same services the MCP tools wrap): `search_course_content` (follow-up searches), `get_enrolled_courses`, `get_learning_strengths`, `get_learning_metrics`, `get_concept_confidence`, `search_history`, `record_skill_observation`. Not exposed: `generate_quiz`, `generate_notes`, `answer_question`.
- **Identity:** `student_id` is **never** a tool parameter: tools read it from the request's runtime context (`ToolRuntime`) set by the route, so the model cannot pass or forge it (proven by a test where a forged id is dropped). `course_id` is model-supplied on `get_concept_confidence` / `record_skill_observation` — the Ask page has no single course to bind — and can only touch this student's own rows. (Amended 2026-10-04 during Task 10 review.)
- **Shared tool descriptions:** each tool's description (the text that tells the model when to use it) lives once in `app/services/tool_descriptions.py`; LangChain tools use it now, MCP tools switch to it in §7.
- Streaming: agent token stream mapped to the existing `{"type":"token","value":...}` events.

### 4.5 Route changes — `main.py` `hermes_chat`

- Keep: access gate, PII scrub, intent router + quiz/out-of-scope hand-offs, smalltalk check, OTel span, audit, skill-graph back-fill, context builder, memory persistence.
- Replace: `hermes_client.stream_chat` → `chat_pipeline.chat_turn` (§4.8), which runs `course_lookup` + the tutor agent.
- Citations: emit lookup cards in the first `sources` event; if the agent's follow-up `search_course_content` adds new cards, send them in a second `sources` event after the stream (the frontend already handles this). The `chat_citations` store round-trip is no longer needed on the web path.
- Labels: audit `provider = "langchain-agent"`; `/health` `TUTOR_PROVIDER` reports the same.
- Fix the route docstring to describe what the code does.
- `hermes_client.py` is deleted (§3a C); the Hermes channel in §7 talks to Hermes directly, not through this backend client.

### 4.6 Grounding prompt rewrite + GEPA removal

- Move the file to `backend/app/grounding/grounding_prompt.md`. New loader `backend/app/grounding/loader.py` → `read_grounding_prompt()` (takes over `read_soul()` + its fallback from `gepa_service.py:24-40`).
- Switch every caller to the loader: chat (`main.py:356, 364`), eval endpoint (`main.py:497`), and `audit_service.py:18` — which today fingerprints `~/.hermes/SOUL.md`, a path that doesn't exist on the deployed container, so the audit hash is likely `"unknown"` in prod. This fixes it.
- Rewrite "Avoid"/"Defaults": drop "answer from general knowledge, never decline"; state the three cases; keep tone, citation, no-hallucination and teaching rules.
- Identity line becomes neutral: "Dev, the the01.dev tutor" — no Hermes references.
- **Remove GEPA:** `services/gepa_service.py`; endpoints `/api/hermes/gepa/run`, `/approve`, `/proposals` (`main.py:474-490`); the import (`main.py:33`); `tests/test_gepa_service.py` (its two assertions move to a loader test); GEPA wording in comments (`main.py:41-43, 346`, `deps.py:11-12`, `eval_service.py:1-10`, `eval_llm.py:2`, `results_store.py`, `ragas_eval.py:12`). Not coupled to the audit log. `eval_service`, `eval_set.json` and the RAGAS script stay (separate feature).

### 4.7 Identity at the edge — APPROVED 2026-10-04

The route trusts the client-supplied `user_id` (`main.py:244`); there is no Firebase ID-token check. Anyone who knows a student's email can read that student's strengths and history. Server-bound tool identity (§4.4) only stops the *model* forging an id, not the *client*.

Fix (approved; invisible frontend change):
- Frontend: both chat clients (`askHermesStream` in `ragApi.ts`, the tutor stream in `learnApi.ts`) send `Authorization: Bearer <Firebase ID token>` from `auth.currentUser.getIdToken()`. Body fields stay for compatibility but are ignored by the server.
- Backend: a FastAPI dependency `current_student` (`app/auth.py`) verifies the token with `firebase_admin.auth.verify_id_token` (Firebase project `topdev-93530`; initialised with the project id, no Firestore client needed) and returns the token's `uid` — the same id the frontend sends today (`AskPage.tsx:173` passes `uid`), so existing data keys are unchanged.
- Missing/invalid/expired token → 401. Both chat routes use the dependency; other student-data routes (journey, enrollment, adaptive, lab) are listed for the same treatment in a follow-up, not this phase.
- Local dev/tests: dependency overridden in tests; no bypass flag in production code.

### 4.8 Video-player tutor — same pipeline

`POST /api/ai/tutor/stream` (`main.py:196`, used by `TutorModal` and `PlayerTutor` via `learnApi.ts:123`) today runs its own pipeline in `tutor_service.py`: retrieval filtered to the current course, a separate Socratic prompt, weak concepts from `concept_performance`; no enrollment awareness, no citations, no PII scrub, no audit, no persisted memory. It also errors "Unknown course" for any course without transcripts.

Change: both endpoints call one shared function, `chat_turn(question, student_id, scope, history)` in `app/services/chat_pipeline.py`, which runs PII scrub → audit → `course_lookup` → tutor agent → `record_turn`. The two endpoints differ only in `scope`:

| | Ask page (`/api/hermes/chat`) | Video player (`/api/ai/tutor/stream`) |
|---|---|---|
| Scope | All courses | Current course + current lecture |
| Lookup bias | None | Hits in the current lecture, then current course, ranked first; other courses still searched, so "this goes deeper in *X*" and not-enrolled pointers still work |
| History | Last 3 turns from `memory_service` | The running message list the client sends (unchanged contract) |
| Style | Grounding prompt | Grounding prompt + an "in-lecture" section: Socratic, 2–5 sentences, assume "this" means the current lecture (carried over from `tutor_service._system_prompt`) |
| Course resolution | — | Via `catalog_service`, so courses without transcripts work (catalog hits only) instead of erroring |

- The current course's weak concepts (today's `_weak_concepts`) go into the COURSE FACTS block.
- Player turns are recorded with `memory_service.record_turn`, so the Ask page remembers what was asked mid-lecture and vice versa.
- The player client ignores `sources` events (`learnApi.ts` handles only `token`/`done`/`error`), so citations appear in the answer text ("around 1:27 in 8.1"); the endpoint still emits `sources` for future use. No frontend change.
- `tutor_service.py` shrinks to the endpoint adapter (or is removed if the adapter lives in the route).

## 5. Testing

- `course_lookup` unit tests for each case. **Fixture that must pass:** demo account + "how do I publish an npm library" → `NOT_ENROLLED_MATCH`, top hit *Build a Custom Library*.
- Enrolled-wins test (hits in both enrolled and not-enrolled courses).
- Tool identity test: a tool call carrying a different `student_id` argument cannot reach another student's data (parameter absent from schema; context value used).
- Catalog drift test (§4.1).
- Player tutor: current-lecture hits rank first; a course without transcripts answers from catalog instead of erroring; SSE contract `token`… → `done` unchanged; turn is recorded to memory.
- Cleanup: full backend test suite and frontend `tsc` + build pass after §3a, before any rebuild work starts.
- Route test: SSE order is `sources` → `token`… → `done`; existing `test_hermes_chat_*` tests updated for the new internals.
- **Demo check:** `backend/scripts/demo_check.py` runs 6–8 fixed questions (enrolled / not-enrolled / off-topic / "what am I weak at") against local or prod and prints case + citations. Run before every demo.

## 6. Deploy

Backend via `railway up` from the backend directory (Railway links per directory path — see deploy notes). New pinned deps: `langchain`, `langchain-openai`. Hermes service untouched; it can be paused until §7.

## 7. Later: Hermes messaging channel (Telegram first, the user's own number)

Recorded now, built last. Facts below are from Hermes source at commit `1cb26bf` unless marked.

**Why Hermes here:** one agent on many channels from config (Telegram, WhatsApp, Slack, Discord, Signal, Email, SMS, …); voice notes transcribed; images handled; long chats auto-compressed; model swappable by config incl. local models.

**Many students on one profile:** sessions are keyed per chat (one per student in DMs). Gateway concurrency is unlimited by default (`max_concurrent_sessions: null`). The sender's platform id is attached server-side (`user_id=src.user_id`), not by the model.

**Leaks to close (config):** built-in memory off (`memory.memory_enabled: false`, `memory.user_profile_enabled: false`, `agent.disabled_toolsets: [memory, session_search]`); `session_search` crosses students; agent-written skills apply to everyone → `skills.write_approval: true`; default messaging toolsets include a terminal → restrict to `the01dev-tools`; `privacy.redact_pii: true`.

**Identity binding:** a Hermes plugin on `pre_tool_call` overwrites `student_id` with the student linked to the sender id (lookup in Postgres), and blocks on any failure. Reading the sender id inside that hook is code-derived, not yet run — **first task of that phase is a spike proving it**; if it fails, this section is redesigned. `pre_gateway_dispatch` hook admits only linked senders (no manual pairing per student).

**Linking:** table `channel_links(platform, platform_user_id, student_id)`; for the demo, a script links the user's Telegram id.

**Tools:** `course_lookup` exposed as an MCP tool (same function as §4.3), so Telegram answers follow the same three cases. MCP tools adopt `tool_descriptions.py`.

**Proactive nudge:** daily revision message on the student's weakest concept. Hermes cron delivers one job per target, so per-student nudges = a backend loop calling `hermes send --to telegram:<chat_id>`. WhatsApp Cloud cannot message outside Meta's 24-hour window (no template support in Hermes), so nudges are Telegram-only.

**Known limits to state honestly:** SECURITY.md treats all admitted users as equally trusted; MCP calls to one server serialize behind one lock (fine at small scale, to be load-tested); no documented capacity guidance for 100+ users.

## 8. Risks and open questions

- Other student-data routes (journey, enrollment, adaptive, lab) still trust client ids until the follow-up.
- Thresholds unknown until calibration runs; tiny corpus (21 transcript chunks) makes scores noisy — catalog index is the mitigation.
- `create_agent` API details to confirm against current LangChain docs.
- The RAGAS eval set (`app/eval/eval_set.json`) may encode the old "always answer" behaviour; review it when the prompt changes.
- Moving the player tutor onto the agent adds tool-call latency to a chat that was a single LLM call; measure first-token time before and after.
