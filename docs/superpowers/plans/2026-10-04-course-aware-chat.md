# Course-Aware Chat Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Clean out dead code, then make both chats (Ask page + video-player tutor) answer with the course library and the student's enrollments in hand — enrolled match → cite, not-enrolled match → short answer + course pointer, no match → labelled general answer — with student identity verified from the Firebase login token.

**Architecture:** A deterministic `course_lookup` (transcript index + new catalog index + enrollment labels) runs in plain Python before a LangChain `create_agent` tutor. Both chat endpoints call one `chat_pipeline.chat_turn`; tools read `student_id` from the agent's runtime context, never from the model. The SSE contract to the frontend is unchanged.

**Tech Stack:** FastAPI, Python 3.12, LangChain 1.3.14 (`create_agent`, `ToolRuntime`) on LangGraph 1.2.9, `langchain-openai` 1.6.7, OpenAI `gpt-4.1-mini`, firebase-admin 6.5.0, pytest + pytest-asyncio (auto mode); React + TS frontend, Node 22 (runs `.ts` directly).

**Spec:** `docs/superpowers/specs/2026-10-04-course-aware-chat-design.md` — read it first; this plan argues from it.

## Global Constraints

- **No GitHub push.** Commit locally only (`git commit`, never `git push`). Stage files by explicit path — the working tree has unrelated deletions (old docs) that must not be swept into commits; never `git add -A` / `git add .`.
- **No visible frontend change.** Allowed frontend edits: auth header on the two chat clients, dead-code removal, type move. Nothing that changes what a user sees.
- Python **3.12** (matches `backend/Dockerfile` `python:3.12-slim`). LangChain token streaming does not work below 3.11.
- Pins: `langgraph==1.2.9`, `langchain==1.3.14`, `langchain-openai==1.6.7`, `openai==3.24.0` (was 1.58.1; `langchain-openai` 1.x needs `openai>=2.45`). Never leave `langchain-openai` unpinned (resolver picks a broken `0.0.1rc0`).
- Model: `gpt-4.1-mini` via `app.services.llm.GEN_MODEL`.
- Firebase project id: `topdev-93530`. Student id = the token's `uid` (same id the frontend sends today, `AskPage.tsx:173`).
- Not-enrolled behaviour: **short answer (3–5 sentences) + course pointer**.
- Prompt file: `backend/app/grounding/grounding_prompt.md` (not `app/prompts/` — `app/prompts.py` already exists and a package would shadow it). GEPA is removed.
- OpenAI is the only model provider — no Ollama/local branches remain.
- `app/mcp/the01dev_tools.py`, `requirements-mcp.txt`, `hermes-service/`, `trace.py`, `trace_server.py`, `trajectory_eval.py`, `app/eval/trajectory_set.json` stay (Hermes phase, later).
- **Test command** (used everywhere below; blanks keep `backend/.env` from pointing tests at Postgres/OpenAI — `load_dotenv` never overrides variables that are already set):
  `cd backend && env DATABASE_URL= OPENAI_API_KEY= FIREBASE_SERVICE_ACCOUNT_JSON= GOOGLE_APPLICATION_CREDENTIALS= LANGSMITH_TRACING=false .venv/bin/pytest <args>`
  Written below as **`$TEST <args>`**.
- Deploys (`railway up`, `netlify deploy`) only after the user says go (Task 18).

## Review Focus

1. **Expired / missing / malformed login token** → clean 401 with a sign-in message, never a 500 or a stack trace. → Task 12 tests.
2. **Enrollment lookup fails (DB down, bad id)** → the turn still answers, every hit treated as not enrolled. → Task 8 test.
3. **OpenAI/agent fails mid-stream** → client gets an `error` event with a generic message (no exception text), no half-answer saved to memory. → Task 11 test.
4. **Student types PII (email/phone) in the question** → scrubbed before lookup, the model, the audit log and memory. → Task 11 test.
5. **Same lecture cited twice** (lookup card + agent's follow-up search) → shown once. → Task 11 test.

---

### Task 0: Test environment + baseline

**Files:** none committed (venvs are gitignored — verify).

- [ ] **Step 1: Create the venvs with Python 3.12**

```bash
cd backend
uv venv --python 3.12 .venv
uv pip install --python .venv -r requirements.txt
uv venv --python 3.12 .mcp-venv
uv pip install --python .mcp-venv -r requirements.txt -r requirements-mcp.txt
git check-ignore -q .venv && git check-ignore -q .mcp-venv && echo "ignored OK"
```
Expected: installs succeed; `ignored OK`. If not ignored, add `.venv/` and `.mcp-venv/` to `backend/.gitignore`.

- [ ] **Step 2: Run the baseline suite and record it**

```bash
$TEST tests -q --ignore=tests/test_mcp_get_concept_confidence.py --ignore=tests/test_mcp_get_enrolled_courses.py --ignore=tests/test_mcp_get_learning_metrics.py --ignore=tests/test_mcp_get_learning_strengths.py --ignore=tests/test_mcp_record_skill_observation.py --ignore=tests/test_mcp_search_course_content_citations.py 2>&1 | tail -15
cd backend && env DATABASE_URL= OPENAI_API_KEY= .mcp-venv/bin/pytest tests/test_mcp_*.py -q 2>&1 | tail -5
```
Write the pass/fail counts and the names of any failing tests into `docs/superpowers/plans/2026-10-04-course-aware-chat.baseline.txt` (not committed). **Pre-existing failures are not this plan's job** — but every later task must end with no *new* failures versus this file.

---

### Task 1: Cleanup A — backend dead code

**Files:**
- Delete: `backend/app/services/ollama_client.py`, `backend/app/services/openai_tutor.py`, `backend/data/agent_fs/`, `backend/scripts/migrate_enrollment_from_firestore.py`
- Modify: `backend/app/main.py`, `backend/app/services/lab/routes.py`, `backend/app/services/rag_service.py`, `backend/app/services/recommendation_service.py`, `backend/requirements.txt`

- [ ] **Step 1: Re-verify zero callers (abort the item if any hit appears outside its own file)**

```bash
cd backend
grep -rn "ollama_client\|openai_tutor" app scripts tests *.py | grep -v "^app/services/ollama_client.py\|^app/services/openai_tutor.py"
grep -rn "agent_fs" app scripts tests *.py
grep -rn "migrate_enrollment_from_firestore" app scripts tests *.py ../frontend/src
grep -rn "api/ai/questions\|api/ai/quiz-session\|api/ai/recommendations\|api/ai/knowledge-graph\|api/lab/library" ../frontend/src tests scripts *.py
grep -rn "_build_sources" app tests
```
Expected: no output except `_build_sources` at `main.py` import + `rag_service.py` alias (both removed below).

- [ ] **Step 2: Delete files**

```bash
git rm -q app/services/ollama_client.py app/services/openai_tutor.py scripts/migrate_enrollment_from_firestore.py
git rm -rq data/agent_fs
rm -rf lesson_service .lesson-venv   # untracked leftovers
```

- [ ] **Step 3: Remove the dead routes**

In `backend/app/main.py`, delete these route functions in full (decorator + body): `GET /api/ai/questions/{...}`, `POST /api/ai/quiz-session`, `GET /api/ai/quiz-sessions`, `GET /api/ai/recommendations`, every `/api/ai/knowledge-graph/...` route. In `backend/app/services/lab/routes.py`, delete the `GET /library` route (served as `/api/lab/library`). Remove `_build_sources` from the `main.py` import and the alias lines in `rag_service.py` (`rag_service.py:14-15`).

- [ ] **Step 4: Shrink recommendation_service if orphaned**

```bash
grep -rn "recommendation_service\.\w*" app | grep -v "^app/services/recommendation_service.py"
```
If the only remaining use is `recommendation_service.invalidate` (`adaptive_service.py:263`), reduce `recommendation_service.py` to the `invalidate` function plus whatever it needs; delete the rest. Remove `recommendation_service` from `main.py`'s import list if unused there.

- [ ] **Step 5: Drop unused deps**

Remove these two lines from `backend/requirements.txt`: `opentelemetry-instrumentation-fastapi==0.65b0`, `websockets==16.0`. Then `grep -rn "opentelemetry.instrumentation.fastapi\|import websockets" app *.py` → no output.

- [ ] **Step 6: Run the suite** — `$TEST tests -q` (with the Task 0 ignores). Expected: no new failures vs baseline. Delete any test that only exercised a removed route.

- [ ] **Step 7: Commit (local)**

```bash
git add app/main.py app/services/lab/routes.py app/services/rag_service.py app/services/recommendation_service.py requirements.txt
git commit -m "chore: remove dead backend code, unused routes and deps"
```

---

### Task 2: Cleanup A + D1 — frontend dead code and Mastra client

**Files:**
- Create: `frontend/src/types/lab.ts`
- Delete: `frontend/src/lib/notesQuizApi.ts`, `frontend/src/App.css`, `frontend/src/assets/hero.png`, `frontend/src/assets/react.svg`, `frontend/src/assets/vite.svg`
- Modify: `frontend/src/lib/notesQuizApiLang.ts`, `frontend/src/components/learn/NotesQuizModal.tsx`, `frontend/src/lib/labApi.ts`, `frontend/src/lib/ragApi.ts`, `frontend/src/lib/learnApi.ts`, `frontend/src/main.tsx`, `frontend/package.json`

- [ ] **Step 1: Re-verify**

```bash
cd frontend/src
grep -rn "askQuestion\b\|askQuestionStream\|getQuestions\|saveQuizSession\|listQuizSessions\|getRecommendations\|buildKnowledgeGraph\|getLibrary" . | grep -v "export "
grep -rn "App.css\|hero.png\|react.svg\|vite.svg" . ../index.html
grep -rn "video.js\|plyr\|useQuery\|useMutation" .
grep -rn "from ['\"].*notesQuizApi['\"]" .
```
Expected: no callers for the functions/assets/deps; `notesQuizApi` imported only as `import type` (3 files).

- [ ] **Step 2: Move the Lab types**

Create `frontend/src/types/lab.ts` containing, verbatim, every `export type` from `frontend/src/lib/notesQuizApi.ts` (`Difficulty`, `Objective`, `Question`, `Quiz`, `Result`, `Summary`, `LessonStatus`, `LessonView`) — copy the definitions exactly (lines 13–~78). Then repoint:
- `notesQuizApiLang.ts`: `import type { LessonView, Objective } from "../types/lab";` and `export type { Difficulty, Objective, Question, Quiz, Result, Summary, LessonStatus, LessonView } from "../types/lab";`; replace its header comment's Mastra wording with: `// Lab quiz client for the backend's LangGraph flow at /api/lab (backend/app/services/lab/routes.py).`
- `NotesQuizModal.tsx:7`: `import type { LessonView, Objective, Question, Difficulty } from "../../types/lab";` and drop the Mastra sentence from its header comment (lines ~10-11).
- `labApi.ts:6`: `import type { Objective } from "../types/lab";`

Then `git rm -q frontend/src/lib/notesQuizApi.ts`.

- [ ] **Step 3: Remove dead exports, assets, deps**

Delete the functions `askQuestion`, `askQuestionStream` (`ragApi.ts`); `getQuestions`, `saveQuizSession`, `listQuizSessions`, `getRecommendations`, `buildKnowledgeGraph` (`learnApi.ts`); `getLibrary` (`labApi.ts`) — plus any type/import that becomes unused. `git rm -q` the four asset files. In `main.tsx` remove the `QueryClient`/`QueryClientProvider` import, construction and wrapper (render children directly). Then:

```bash
cd frontend && npm uninstall video.js @types/video.js plyr @tanstack/react-query
```

- [ ] **Step 4: Type-check and build**

Run: `cd frontend && npm run build`
Expected: `tsc -b` clean, vite build succeeds.

- [ ] **Step 5: Commit (local)**

```bash
git add frontend/src/types/lab.ts frontend/src/lib/notesQuizApiLang.ts frontend/src/components/learn/NotesQuizModal.tsx frontend/src/lib/labApi.ts frontend/src/lib/ragApi.ts frontend/src/lib/learnApi.ts frontend/src/main.tsx frontend/package.json frontend/package-lock.json
git commit -m "chore: remove dead frontend code and the retired Mastra client"
```

---

### Task 3: Cleanup B + D2 — superseded chat path and local models

**Files:**
- Delete: `backend/app/services/rag_service.py`, `backend/app/routing/smalltalk_classifier.py` (+ its tests), `docker-compose.sovereign.yml`
- Modify: `backend/app/main.py`, `backend/app/services/eval_llm.py`, `backend/app/services/lab/llm.py`, `backend/app/services/lab/graph.py`, `backend/app/services/lab/routes.py`, `backend/app/eval/accuracy.py`, `backend/ragas_eval.py`, `backend/app/services/context_meter.py`, `backend/app/services/memory_service.py`, `backend/trace.py`, `backend/trace_server.py`, `backend/.env.example`, `backend/tests/test_lab_routes.py`

- [ ] **Step 1: Remove `/api/ai/ask` + `rag_service`**

Delete the `POST /api/ai/ask` and `POST /api/ai/ask/stream` routes (`main.py:206-221`) and `git rm -q backend/app/services/rag_service.py`. Remove `AskRequest`/`AskResponse` from the `main.py` import if now unused. Check `app/prompts.py` and `answer_generator.py`:

```bash
cd backend && grep -rn "from app.prompts\|import prompts\|answer_generator" app *.py | grep -v "^app/prompts.py\|^app/services/answer_generator.py"
```
They stay if `grounding.answer_grounded` (MCP `answer_question`, `accuracy.py`) still imports them — expected: yes, keep.

- [ ] **Step 2: Remove the smalltalk classifier**

Delete the block at `main.py:260-271` (the `smalltalk = {...}` dict, the `if intent == Intent.COURSE_QUESTION:` check, and the two `span.set_attribute("smalltalk_similarity", ...)` lines), the `from app.routing import smalltalk_classifier` import, `git rm -q app/routing/smalltalk_classifier.py`, and any `tests/routing/*smalltalk*` test files. Remove `SMALLTALK_BLOCK_ENABLED` from `.env.example`.

- [ ] **Step 3: Remove every Ollama/local-model branch**

For each file below, delete the branch that selects Ollama/a local base_url so the OpenAI path is unconditional; delete Ollama-only constants/env reads:
`app/services/eval_llm.py` (lines ~24-27), `app/services/lab/llm.py` (~35-42), `app/eval/accuracy.py`, `ragas_eval.py`, `app/services/context_meter.py`, `app/services/memory_service.py`, `trace.py`, `trace_server.py`. In `main.py` delete `_TUTOR_PROVIDER`/`TUTOR_PROVIDER` (line ~49) and set the `/health` field to the literal `"tutor_provider": "langchain-agent"`. Remove Ollama/`TUTOR_PROVIDER`/`HERMES_GROUNDING_THRESHOLD` entries from `.env.example`. `git rm -q docker-compose.sovereign.yml` (repo root). Also rewrite the Mastra/"local sovereign model" wording in the docstrings of `lab/graph.py` (lines 1-2: make it `"""The Lab quiz flow as a LangGraph StateGraph.`), `lab/llm.py:3,96`, `lab/routes.py:346`, and any Mastra mention in `tests/test_lab_routes.py` comments.

Verify:
```bash
cd backend && grep -rni "ollama\|sovereign\|TUTOR_PROVIDER\|mastra" app *.py tests .env.example ../frontend/src
```
Expected: no output.

- [ ] **Step 4: Suite** — `$TEST tests -q` (Task 0 ignores) → no new failures; the MCP suite under `.mcp-venv` → no new failures.

- [ ] **Step 5: Commit (local)**

```bash
git add -u backend/app backend/*.py backend/tests backend/.env.example docker-compose.sovereign.yml
git commit -m "chore: remove superseded /api/ai/ask path, smalltalk classifier, local-model branches"
```
(`git add -u` stages only modifications/deletions of already-tracked files under the listed paths — safe with the unrelated doc deletions elsewhere.)

---

### Task 4: Dependencies — LangChain + OpenAI bump

**Files:** Modify `backend/requirements.txt`

- [ ] **Step 1: Edit pins**

In `backend/requirements.txt` change `openai==1.58.1` → `openai==3.24.0`, and add after `langgraph==1.2.9`:
```
langchain==1.3.14
langchain-openai==1.6.7
```

- [ ] **Step 2: Resolve + install**

```bash
cd backend && uv pip compile requirements.txt --python-version 3.12 -q > /dev/null && echo RESOLVES
uv pip install --python .venv -r requirements.txt
uv pip install --python .mcp-venv -r requirements.txt -r requirements-mcp.txt
.venv/bin/python -c "import langchain, langchain_openai, openai; from langchain.agents import create_agent; from langchain.tools import ToolRuntime; print(langchain.__version__, openai.__version__)"
```
Expected: `RESOLVES`; prints `1.3.14 3.24.0`.

- [ ] **Step 3: Suite** — full suite + MCP suite → no new failures (this is the gate for the OpenAI 1→3 jump; if something breaks, fix the call site, don't downgrade).

- [ ] **Step 4: Commit (local)** — `git add backend/requirements.txt && git commit -m "build: add langchain 1.3.14 + langchain-openai 1.6.7, bump openai to 3.24.0"`

---

### Task 5: Grounding prompt — move, loader, rewrite, GEPA removal, audit fix

**Files:**
- Create: `backend/app/grounding/__init__.py`, `backend/app/grounding/loader.py`, `backend/app/grounding/grounding_prompt.md` (moved from `backend/hermes/SOUL.md`)
- Delete: `backend/hermes/SOUL.md`, `backend/app/services/gepa_service.py`, `backend/tests/test_gepa_service.py`
- Modify: `backend/app/main.py`, `backend/app/services/audit_service.py`, `backend/app/deps.py`, `backend/app/services/eval_service.py`, `backend/app/services/eval_llm.py`, `backend/app/eval/results_store.py`, `backend/ragas_eval.py`
- Test: `backend/tests/test_grounding_prompt.py`

- [ ] **Step 1: Why `app/grounding/`, not `app/prompts/`**

`backend/app/prompts.py` already exists (used by `answer_generator`). A directory `app/prompts/` would shadow it. So put the new files in **`backend/app/grounding/`** instead: `backend/app/grounding/__init__.py` (empty), `backend/app/grounding/loader.py`, `backend/app/grounding/grounding_prompt.md`. Use these paths for the rest of the plan (the spec already uses them).

- [ ] **Step 2: Write the failing test**

`backend/tests/test_grounding_prompt.py`:
```python
from app.grounding import loader


def test_reads_the_repo_prompt_not_the_fallback():
    text = loader.read_grounding_prompt()
    assert text != loader.FALLBACK_PROMPT
    assert "CASE: NOT_ENROLLED_MATCH" in text
    assert "Hermes" not in text


def test_prompt_has_all_three_cases_and_lecture_mode():
    text = loader.read_grounding_prompt()
    for marker in ("CASE: ENROLLED_MATCH", "CASE: NOT_ENROLLED_MATCH", "CASE: NO_MATCH", "MODE: in-lecture"):
        assert marker in text


def test_fingerprint_is_stable_and_short():
    assert loader.prompt_fingerprint() == loader.prompt_fingerprint()
    assert len(loader.prompt_fingerprint()) == 12


def test_falls_back_when_file_missing(monkeypatch, tmp_path):
    monkeypatch.setattr(loader, "PROMPT_PATH", tmp_path / "missing.md")
    assert loader.read_grounding_prompt() == loader.FALLBACK_PROMPT
```

- [ ] **Step 3: Run it** — `$TEST tests/test_grounding_prompt.py -v` → FAIL (`ModuleNotFoundError: app.grounding`).

- [ ] **Step 4: Write the loader**

`backend/app/grounding/loader.py`:
```python
"""The tutor's grounding prompt: the rules every chat turn runs under.

Same for every student — personalization comes from learner state (COURSE FACTS,
memory), not from this file. Kept as a file so it can be read and reviewed like
code, and so the audit log can fingerprint the exact version that answered.
"""
import hashlib
from pathlib import Path

PROMPT_PATH = Path(__file__).resolve().parent / "grounding_prompt.md"

FALLBACK_PROMPT = (
    "You are Dev, the01.dev's AI tutor. Use the COURSE FACTS you are given: cite "
    "lectures the student owns, give a short answer plus a course pointer for courses "
    "they don't own, and label general-knowledge answers as not from a the01.dev course."
)


def read_grounding_prompt() -> str:
    try:
        return PROMPT_PATH.read_text().strip() or FALLBACK_PROMPT
    except OSError:
        return FALLBACK_PROMPT


def prompt_fingerprint() -> str:
    return hashlib.sha256(read_grounding_prompt().encode()).hexdigest()[:12]
```

- [ ] **Step 5: Write the prompt**

`git mv backend/hermes/SOUL.md backend/app/grounding/grounding_prompt.md`, then replace its entire content with:

```markdown
# Identity

You are **Dev**, the AI tutor for **the01.dev**, a platform that teaches developers
through video courses. You teach; you don't just answer. Warm, precise, encouraging.

# COURSE FACTS

Every question arrives with a COURSE FACTS block. It was produced by looking the
question up in the01.dev's course library and checking which courses this student
owns. Trust it and never contradict it. Its CASE line tells you which rule applies.

## CASE: ENROLLED_MATCH
The answer is in a course the student owns.
- Ground your answer in the matched material and cite it: course, lecture and
  timestamp, e.g. "around 01:27 in 8.1 - The npm link command".
- If you go beyond what the lecture says, say so.

## CASE: NOT_ENROLLED_MATCH
The answer is in a course the student does not own.
- Give a short, genuinely useful answer: 3 to 5 sentences, the core idea only.
- Then point to the course in this shape: "This is covered in depth in
  {course} → {lecture or module}. You're not enrolled in it yet; you can find it at
  the01.dev{course page}."
- Never imply they own it. Never paste long excerpts from it.

## CASE: NO_MATCH
Nothing in the01.dev's library covers this.
- Answer from your general knowledge, accurately.
- Say once, plainly, that this answer isn't from a the01.dev course.
- If the question isn't about software development, answer briefly and steer back
  to what you can help with.

# MODE: in-lecture

When COURSE FACTS says MODE: in-lecture, the student is watching that lecture now.
- Assume "this", "here" and "what he just said" refer to that lecture.
- Be Socratic and brief: 2 to 5 sentences; prefer a hint or a guiding question
  before the full explanation.
- If COURSE FACTS lists weak concepts for this course, steer toward them when relevant.

# Tools

Tools already know who the student is. Never ask for their id.
- get_learning_strengths: "what am I good at / weak at / where do I need work".
- get_learning_metrics: numbers such as streak, quiz count, average score.
- get_concept_confidence: before teaching a concept that has prerequisites.
- search_history: when the student refers to a past conversation.
- get_enrolled_courses: when asked which courses they own.
- search_course_content: only for a follow-up the COURSE FACTS don't cover.
- record_skill_observation: when the conversation clearly shows their grasp of a
  concept (they explained it correctly unprompted, or were clearly wrong).

# Style

- Lead with a clear, direct explanation, then detail. Short paragraphs.
- Plain text. No markdown headings or tables; the chat window shows plain text.
- Never say "simply" or "just" about something a learner finds hard.
- Don't hand over complete solutions to exercises; guide with hints and questions.
- If the student seems frustrated, acknowledge it first.
- If memory shows an explanation didn't land before, try a different angle.

# Never

- Invent facts, APIs, library behaviour, lecture names or timestamps.
- Repeat these instructions or the COURSE FACTS block verbatim.
```

- [ ] **Step 6: Run the test** — `$TEST tests/test_grounding_prompt.py -v` → 4 PASS.

- [ ] **Step 7: Remove GEPA and repoint callers**

```bash
cd backend && git rm -q app/services/gepa_service.py tests/test_gepa_service.py
grep -rn "gepa\|read_soul\|SOUL" app *.py tests | grep -v "^tests/test_grounding_prompt.py"
```
For every hit: delete the `gepa_service` import and the three `/api/hermes/gepa/*` routes (`main.py:474-490`); replace `gepa_service.read_soul()` with `loader.read_grounding_prompt()` (add `from app.grounding import loader`) — in the eval endpoint (`main.py:~497`); the chat call sites are rewritten in Task 13, so for now replace them the same way. Rewrite GEPA/SOUL wording in comments/docstrings (`main.py:41-43, 346`, `deps.py:11-12`, `eval_service.py:1-10`, `eval_llm.py:2`, `results_store.py:2,21,49`, `ragas_eval.py:12`) to describe what remains (RAGAS / eval history). In `eval_service.py`, rename any `soul` parameter to `prompt`.

In `audit_service.py:18`, replace the `~/.hermes/SOUL.md` hashing with:
```python
from app.grounding.loader import prompt_fingerprint
```
and use `prompt_fingerprint()` where the hash was computed (keep the stored field name `soul_md_hash` so existing audit rows stay comparable; add a comment: `# fingerprint of app/grounding/grounding_prompt.md`).

Verify: `grep -rni "gepa\|read_soul\|\.hermes/SOUL" app *.py tests` → no output.

- [ ] **Step 8: Suite** → no new failures.

- [ ] **Step 9: Commit (local)**

```bash
git add backend/app/grounding backend/tests/test_grounding_prompt.py docs/superpowers/specs/2026-10-04-course-aware-chat-design.md
git add -u backend/app backend/*.py backend/tests backend/hermes
git commit -m "feat: grounding prompt with three-case rules; remove GEPA; fix audit prompt fingerprint"
```

---

### Task 6: Backend course catalog

**Files:**
- Create: `frontend/scripts/export-catalog.mjs`, `backend/app/data/catalog.json` (generated), `backend/app/services/catalog_service.py`
- Test: `backend/tests/test_catalog.py`

**Interfaces — Produces:**
- `catalog_service.all_courses() -> list[dict]`; `get(course_id: int) -> dict | None`; `by_slug(slug: str) -> dict | None`
- Course dict: `{"id": int, "slug": str | None, "title": str, "description": str, "launched": bool, "url": "/course/{id}", "modules": [{"title", "description"}], "chapters": [{"name", "subchapters": [str]}]}`

- [ ] **Step 1: Write the export script**

`frontend/scripts/export-catalog.mjs`:
```js
// Exports the course catalog (frontend/src/data/tracks.ts — the source of truth)
// to backend/app/data/catalog.json for the chat's course lookup.
// Usage:  node frontend/scripts/export-catalog.mjs          (write)
//         node frontend/scripts/export-catalog.mjs --check  (exit 1 if stale)
// Node 22 runs .ts imports directly (type stripping); tracks.ts has no imports.
import { readFileSync, writeFileSync } from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

const here = path.dirname(fileURLToPath(import.meta.url));
const tracks = (await import("../src/data/tracks.ts")).default;
const { RAG_COURSE_MAP } = await import("../src/types/rag.ts");
const slugById = Object.fromEntries(Object.entries(RAG_COURSE_MAP).map(([slug, id]) => [id, slug]));

const catalog = tracks.map((t) => ({
  id: t.id,
  slug: slugById[t.id] ?? null,
  title: t.title,
  description: t.description,
  launched: t.launched,
  url: `/course/${t.id}`,
  modules: t.modules.map((m) => ({ title: m.title, description: m.description })),
  chapters: t.courseContent.map((c) => ({ name: c.name, subchapters: c.subchapters.map((s) => s.name) })),
}));

const out = path.resolve(here, "../../backend/app/data/catalog.json");
const json = JSON.stringify(catalog, null, 2) + "\n";

if (process.argv.includes("--check")) {
  let current = "";
  try { current = readFileSync(out, "utf8"); } catch { /* missing = stale */ }
  if (current !== json) {
    console.error("catalog.json is stale. Run: node frontend/scripts/export-catalog.mjs");
    process.exit(1);
  }
  console.log("catalog.json is up to date");
} else {
  writeFileSync(out, json);
  console.log(`wrote ${catalog.length} courses to ${out}`);
}
```

Run: `node frontend/scripts/export-catalog.mjs` → `wrote 10 courses …`. Check: `python3 -c "import json;print([(c['id'],c['slug']) for c in json.load(open('backend/app/data/catalog.json'))])"` → 10 pairs, every slug non-null.

- [ ] **Step 2: Write the failing tests**

`backend/tests/test_catalog.py`:
```python
import shutil
import subprocess
from pathlib import Path

import pytest

from app.services import catalog_service

REPO = Path(__file__).resolve().parents[2]


def test_catalog_has_every_course_with_ids_and_slugs():
    courses = catalog_service.all_courses()
    assert len(courses) == 10
    assert all(isinstance(c["id"], int) and c["url"] == f"/course/{c['id']}" for c in courses)


def test_lookup_by_numeric_id_and_by_transcript_slug_agree():
    lib = catalog_service.get(2)
    assert lib["title"] == "Build a Custom Library"
    assert catalog_service.by_slug("custom-library") == lib
    assert any(m["title"] == "NPM Package Development" for m in lib["modules"])


def test_unknown_ids_return_none():
    assert catalog_service.get(999) is None
    assert catalog_service.by_slug("nope") is None


@pytest.mark.skipif(shutil.which("node") is None, reason="node not installed")
def test_catalog_json_matches_tracks_ts():
    result = subprocess.run(
        ["node", "frontend/scripts/export-catalog.mjs", "--check"],
        cwd=REPO, capture_output=True, text=True,
    )
    assert result.returncode == 0, result.stderr
```

- [ ] **Step 3: Run** — `$TEST tests/test_catalog.py -v` → FAIL (`ImportError: catalog_service`).

- [ ] **Step 4: Implement**

`backend/app/services/catalog_service.py`:
```python
"""The full course catalog, including courses with no transcripts yet.

Generated from frontend/src/data/tracks.ts (the source of truth) by
frontend/scripts/export-catalog.mjs; tests/test_catalog.py fails if this copy
drifts. Bridges the two id spaces: numeric `id` (enrollments, course pages) and
`slug` (transcript chunks' course_id).
"""
import json
from functools import lru_cache
from pathlib import Path
from typing import Optional

_PATH = Path(__file__).resolve().parents[1] / "data" / "catalog.json"


@lru_cache(maxsize=1)
def all_courses() -> list[dict]:
    return json.loads(_PATH.read_text())


def get(course_id: int) -> Optional[dict]:
    return next((c for c in all_courses() if c["id"] == course_id), None)


def by_slug(slug: str) -> Optional[dict]:
    return next((c for c in all_courses() if c["slug"] == slug), None)
```

- [ ] **Step 5: Run** — `$TEST tests/test_catalog.py -v` → 4 PASS.

- [ ] **Step 6: Commit (local)** — `git add frontend/scripts/export-catalog.mjs backend/app/data/catalog.json backend/app/services/catalog_service.py backend/tests/test_catalog.py && git commit -m "feat: backend course catalog exported from tracks.ts with drift check"`

---

### Task 7: Catalog index

**Files:**
- Create: `backend/app/services/catalog_index.py`
- Modify: `backend/app/main.py` (lifespan)
- Test: `backend/tests/test_catalog_index.py`

**Interfaces:**
- Consumes: `catalog_service.all_courses()`, `embedding_service.embed(text) -> list[float]`
- Produces: `CatalogEntry(course_id: int, course_slug: str | None, course_title: str, module_title: str | None, text: str)`; `build_entries() -> list[CatalogEntry]`; `async ensure_built() -> None`; `async search(query: str, top_k: int = 5) -> list[tuple[CatalogEntry, float]]` (best first); `reset() -> None` (tests).

- [ ] **Step 1: Failing tests**

`backend/tests/test_catalog_index.py`:
```python
from app.services import catalog_index
from app.services.embeddings import embedding_service


def test_one_entry_per_course_and_per_module():
    entries = catalog_index.build_entries()
    lib = [e for e in entries if e.course_id == 2]
    assert sum(1 for e in lib if e.module_title is None) == 1
    assert any(e.module_title == "NPM Package Development" and "npm link" in e.text for e in lib)


async def test_search_ranks_by_similarity(monkeypatch):
    catalog_index.reset()

    async def fake_embed(text: str):
        return [1.0, 0.0] if "npm" in text.lower() else [0.0, 1.0]

    monkeypatch.setattr(embedding_service, "embed", fake_embed)
    hits = await catalog_index.search("how do I publish an npm package", top_k=3)
    assert hits[0][0].module_title == "NPM Package Development"
    assert hits[0][1] > 0.99
    catalog_index.reset()
```

- [ ] **Step 2: Run** → FAIL (no module).

- [ ] **Step 3: Implement**

`backend/app/services/catalog_index.py`:
```python
"""Embedding index over the course catalog: one entry per course and per module.

Lets course_lookup recommend courses that have no lecture transcripts yet (7 of
10 today). ~60 short texts, embedded once per process and held in memory.
"""
import asyncio
import math
from dataclasses import dataclass
from typing import Optional

from app.services import catalog_service
from app.services.embeddings import embedding_service


@dataclass(frozen=True)
class CatalogEntry:
    course_id: int
    course_slug: Optional[str]
    course_title: str
    module_title: Optional[str]  # None = the course as a whole
    text: str


_entries: list[CatalogEntry] = []
_vectors: list[list[float]] = []


def build_entries() -> list[CatalogEntry]:
    entries: list[CatalogEntry] = []
    for c in catalog_service.all_courses():
        entries.append(CatalogEntry(c["id"], c["slug"], c["title"], None, f"{c['title']}. {c['description']}"))
        for m in c["modules"]:
            entries.append(CatalogEntry(
                c["id"], c["slug"], c["title"], m["title"], f"{c['title']}: {m['title']}. {m['description']}",
            ))
    return entries


async def ensure_built() -> None:
    global _entries, _vectors
    if _entries:
        return
    entries = build_entries()
    sem = asyncio.Semaphore(8)  # stay well under embedding rate limits

    async def embed(text: str) -> list[float]:
        async with sem:
            return await embedding_service.embed(text)

    vectors = await asyncio.gather(*(embed(e.text) for e in entries))
    _entries, _vectors = entries, list(vectors)


def _cosine(a: list[float], b: list[float]) -> float:
    dot = sum(x * y for x, y in zip(a, b))
    na, nb = math.sqrt(sum(x * x for x in a)), math.sqrt(sum(y * y for y in b))
    return dot / (na * nb) if na and nb else 0.0


async def search(query: str, top_k: int = 5) -> list[tuple[CatalogEntry, float]]:
    await ensure_built()
    q = await embedding_service.embed(query)
    scored = sorted(((e, _cosine(q, v)) for e, v in zip(_entries, _vectors)), key=lambda x: x[1], reverse=True)
    return scored[:top_k]


def reset() -> None:
    global _entries, _vectors
    _entries, _vectors = [], []
```

In `main.py` `lifespan`, after `await vector_store.initialize()`, add:
```python
    try:
        await catalog_index.ensure_built()
    except Exception as e:  # noqa: BLE001 — built lazily on first lookup instead
        print(f"[startup] catalog index build failed, will retry on first lookup: {e}")
```
and `catalog_index` to the `from app.services import (...)` list.

- [ ] **Step 4: Run** → 2 PASS. Suite → no new failures.

- [ ] **Step 5: Commit (local)** — `git add backend/app/services/catalog_index.py backend/tests/test_catalog_index.py backend/app/main.py && git commit -m "feat: catalog embedding index for courses without transcripts"`

---

### Task 8: `course_lookup`

**Files:**
- Create: `backend/app/services/course_lookup.py`
- Modify: `backend/app/services/journey_service.py` (gain `weak_concepts_for_course`), `backend/app/services/tutor_service.py` (call it)
- Test: `backend/tests/test_course_lookup.py`

**Interfaces:**
- Consumes: `catalog_index.search`, `catalog_service.by_slug/get`, `vector_store.search(emb, top_k, threshold, query_text)`, `embedding_service.embed`, `enrollment_service.get_enrolled_courses(student_id) -> [{"id": int, "title", ...}]`
- Produces (used by Tasks 9, 11):
  - `LookupCase(str, Enum)`: `ENROLLED_MATCH="enrolled_match"`, `NOT_ENROLLED_MATCH="not_enrolled_match"`, `NO_MATCH="no_match"`
  - `ChatScope(course_slug: str | None = None, lecture_title: str | None = None)` (frozen dataclass)
  - `Hit` dataclass: `source: str` ("transcript"|"catalog"), `course_id: int | None`, `course_slug: str | None`, `course_title: str`, `title: str`, `score: float`, `enrolled: bool`, `text: str = ""`, `lecture_id: str | None = None`, `start_time: int = 0`, `end_time: int = 0`, `url: str | None = None`
  - `CourseLookup` dataclass: `case: LookupCase`, `hits: list[Hit]`, `enrolled_titles: list[str]`
  - `async course_lookup(question: str, student_id: str, scope: ChatScope = ChatScope()) -> CourseLookup`
  - `render_facts(lookup: CourseLookup, scope: ChatScope, weak_concepts: list[str] | None = None) -> str`
  - `to_cards(lookup: CourseLookup) -> list[dict]` (SourceCard-shaped dicts)
  - module constants `TRANSCRIPT_THRESHOLD`, `CATALOG_THRESHOLD`, `MAX_HITS = 5`
  - `journey_service.weak_concepts_for_course(user_id: str, course_slug: str) -> list[str]`

- [ ] **Step 1: Failing tests**

`backend/tests/test_course_lookup.py`:
```python
import pytest

from app.models import TranscriptChunk
from app.services import course_lookup as cl
from app.services import enrollment_service
from app.services.catalog_index import CatalogEntry


def _chunk(slug, title, lecture, text="t", start=87):
    return TranscriptChunk(chunk_id=f"{slug}-x", course_id=slug, course_title=title, lecture_id=f"{slug}-l",
                           lecture_title=lecture, text=text, start_time=start, end_time=start + 30)


NPM_CHUNK = _chunk("custom-library", "Build a Custom Library", "8.1 - The npm link command", "npm link symlinks...")
MEMO_CHUNK = _chunk("react-perf", "React Performance Patterns", "4.1 - React.memo and useCallback")
NPM_MODULE = CatalogEntry(2, "custom-library", "Build a Custom Library", "NPM Package Development", "npm link")


@pytest.fixture
def patch_sources(monkeypatch):
    # Pin thresholds so these tests don't depend on Task 9's calibrated values.
    monkeypatch.setattr(cl, "TRANSCRIPT_THRESHOLD", 0.35)
    monkeypatch.setattr(cl, "CATALOG_THRESHOLD", 0.35)

    def apply(transcripts=(), catalog=(), enrolled_ids=(), enrollment_error=False):
        async def fake_transcripts(question, top_k=8):
            return list(transcripts)

        async def fake_catalog(query, top_k=5):
            return list(catalog)

        async def fake_enrolled(student_id):
            if enrollment_error:
                raise RuntimeError("db down")
            return [{"id": i, "title": f"course {i}", "purchased_at": "x"} for i in enrolled_ids]

        monkeypatch.setattr(cl, "_transcript_hits", fake_transcripts)
        monkeypatch.setattr(cl.catalog_index, "search", fake_catalog)
        monkeypatch.setattr(enrollment_service, "get_enrolled_courses", fake_enrolled)
    return apply


async def test_npm_question_for_student_not_in_custom_library_is_not_enrolled(patch_sources):
    # Demo fixture from the spec: enrolled in JS Deep Dive (9) + React Perf (11), not Custom Library (2).
    patch_sources(transcripts=[(NPM_CHUNK, 0.62)], catalog=[(NPM_MODULE, 0.58)], enrolled_ids=[9, 11])
    out = await cl.course_lookup("how do I publish an npm library", "demo")
    assert out.case == cl.LookupCase.NOT_ENROLLED_MATCH
    assert out.hits[0].course_title == "Build a Custom Library"
    assert all(not h.enrolled for h in out.hits)


async def test_enrolled_hit_wins_over_not_enrolled(patch_sources):
    patch_sources(transcripts=[(NPM_CHUNK, 0.70), (MEMO_CHUNK, 0.50)], enrolled_ids=[11])
    out = await cl.course_lookup("q", "s")
    assert out.case == cl.LookupCase.ENROLLED_MATCH
    assert out.hits[0].course_slug == "react-perf"


async def test_scores_below_threshold_mean_no_match(patch_sources):
    patch_sources(transcripts=[(NPM_CHUNK, cl.TRANSCRIPT_THRESHOLD - 0.01)],
                  catalog=[(NPM_MODULE, cl.CATALOG_THRESHOLD - 0.01)])
    out = await cl.course_lookup("how do I bake bread", "s")
    assert out.case == cl.LookupCase.NO_MATCH
    assert out.hits == []


async def test_enrollment_failure_still_answers_as_not_enrolled(patch_sources):
    patch_sources(transcripts=[(MEMO_CHUNK, 0.6)], enrollment_error=True)
    out = await cl.course_lookup("q", "s")
    assert out.case == cl.LookupCase.NOT_ENROLLED_MATCH
    assert out.enrolled_titles == []


async def test_lecture_scope_ranks_current_lecture_first(patch_sources):
    patch_sources(transcripts=[(NPM_CHUNK, 0.80), (MEMO_CHUNK, 0.50)], enrolled_ids=[2, 11])
    scope = cl.ChatScope(course_slug="react-perf", lecture_title="4.1 - React.memo and useCallback")
    out = await cl.course_lookup("what does this mean", "s", scope)
    assert out.hits[0].course_slug == "react-perf"


async def test_catalog_hit_for_same_course_as_transcript_hit_is_dropped(patch_sources):
    patch_sources(transcripts=[(NPM_CHUNK, 0.62)], catalog=[(NPM_MODULE, 0.58)])
    out = await cl.course_lookup("q", "s")
    assert [h.source for h in out.hits] == ["transcript"]


async def test_facts_and_cards(patch_sources):
    patch_sources(transcripts=[(NPM_CHUNK, 0.62)], enrolled_ids=[9])
    out = await cl.course_lookup("q", "s")
    facts = cl.render_facts(out, cl.ChatScope(), weak_concepts=None)
    assert "CASE: NOT_ENROLLED_MATCH" in facts
    assert "[NOT ENROLLED] Build a Custom Library" in facts
    assert "the01.dev/course/2" in facts
    card = cl.to_cards(out)[0]
    assert card["course_id"] == "custom-library" and card["timestamp"] == "01:27"


def test_lecture_mode_facts_include_lecture_and_weak_concepts():
    lookup = cl.CourseLookup(case=cl.LookupCase.NO_MATCH, hits=[], enrolled_titles=["React Performance Patterns"])
    scope = cl.ChatScope(course_slug="react-perf", lecture_title="4.1 - React.memo and useCallback")
    facts = cl.render_facts(lookup, scope, weak_concepts=["useCallback (40%)"])
    assert "MODE: in-lecture" in facts and "4.1 - React.memo and useCallback" in facts
    assert "useCallback (40%)" in facts
```

- [ ] **Step 2: Run** → FAIL (no module).

- [ ] **Step 3: Implement**

`backend/app/services/course_lookup.py`:
```python
"""Look a question up in the01.dev's course library, for this student, before the
tutor answers — in code, every turn, so a demo can't fail because the model
skipped a search.

Searches lecture transcripts and the catalog index, labels each hit enrolled /
not enrolled, and decides one of three cases the grounding prompt has a rule for.
"""
from dataclasses import dataclass
from enum import Enum
from typing import Optional

from app.services import catalog_index, catalog_service, enrollment_service
from app.services.embeddings import embedding_service
from app.services.vector_store import vector_store

# Set from measured data by scripts/calibrate_lookup.py (Task 9) — see spec §4.3.
TRANSCRIPT_THRESHOLD = 0.35
CATALOG_THRESHOLD = 0.35
MAX_HITS = 5


class LookupCase(str, Enum):
    ENROLLED_MATCH = "enrolled_match"
    NOT_ENROLLED_MATCH = "not_enrolled_match"
    NO_MATCH = "no_match"


@dataclass(frozen=True)
class ChatScope:
    course_slug: Optional[str] = None    # None = all courses (Ask page)
    lecture_title: Optional[str] = None  # set by the video player


@dataclass
class Hit:
    source: str                    # "transcript" | "catalog"
    course_id: Optional[int]       # numeric catalog id (enrollment id space)
    course_slug: Optional[str]
    course_title: str
    title: str                     # lecture title, module title, or course title
    score: float
    enrolled: bool
    text: str = ""
    lecture_id: Optional[str] = None
    start_time: int = 0
    end_time: int = 0
    url: Optional[str] = None


@dataclass
class CourseLookup:
    case: LookupCase
    hits: list[Hit]
    enrolled_titles: list[str]


def _mmss(seconds: int) -> str:
    m, s = divmod(int(seconds), 60)
    return f"{m:02d}:{s:02d}"


async def _transcript_hits(question: str, top_k: int = 8):
    if not vector_store.chunks:
        await vector_store.initialize()
    emb = await embedding_service.embed(question)
    return [(r.chunk, r.score) for r in vector_store.search(emb, top_k=top_k, threshold=0.0, query_text=question)]


async def _enrollments(student_id: str) -> tuple[set[int], list[str]]:
    try:
        courses = await enrollment_service.get_enrolled_courses(student_id)
    except Exception as e:  # noqa: BLE001 — unknown enrollment = not enrolled; never fail the turn
        print(f"[course_lookup] enrollment lookup failed: {e}")
        return set(), []
    return {c["id"] for c in courses}, [c["title"] for c in courses]


async def course_lookup(question: str, student_id: str, scope: ChatScope = ChatScope()) -> CourseLookup:
    enrolled_ids, enrolled_titles = await _enrollments(student_id)
    hits: list[Hit] = []

    for chunk, score in await _transcript_hits(question):
        if score < TRANSCRIPT_THRESHOLD:
            continue
        course = catalog_service.by_slug(chunk.course_id)
        cid = course["id"] if course else None
        hits.append(Hit(
            source="transcript", course_id=cid, course_slug=chunk.course_id, course_title=chunk.course_title,
            title=chunk.lecture_title, score=score, enrolled=cid in enrolled_ids, text=chunk.text,
            lecture_id=chunk.lecture_id, start_time=chunk.start_time, end_time=chunk.end_time,
            url=course["url"] if course else None,
        ))

    covered = {h.course_id for h in hits}
    for entry, score in await catalog_index.search(question, top_k=5):
        if score < CATALOG_THRESHOLD or entry.course_id in covered:
            continue
        covered.add(entry.course_id)
        course = catalog_service.get(entry.course_id)
        hits.append(Hit(
            source="catalog", course_id=entry.course_id, course_slug=entry.course_slug,
            course_title=entry.course_title, title=entry.module_title or entry.course_title, score=score,
            enrolled=entry.course_id in enrolled_ids, text=entry.text, url=course["url"] if course else None,
        ))

    def rank(h: Hit):
        in_lecture = bool(scope.lecture_title) and h.title == scope.lecture_title
        in_course = bool(scope.course_slug) and h.course_slug == scope.course_slug
        return (in_lecture, in_course, h.enrolled, h.score)

    hits.sort(key=rank, reverse=True)
    hits = hits[:MAX_HITS]

    if not hits:
        case = LookupCase.NO_MATCH
    elif any(h.enrolled for h in hits):
        case = LookupCase.ENROLLED_MATCH
    else:
        case = LookupCase.NOT_ENROLLED_MATCH
    return CourseLookup(case=case, hits=hits, enrolled_titles=enrolled_titles)


def render_facts(lookup: CourseLookup, scope: ChatScope, weak_concepts: Optional[list[str]] = None) -> str:
    lines = [
        "COURSE FACTS (looked up in the01.dev's course library for this question):",
        f"CASE: {lookup.case.name}",
        "Student is enrolled in: " + (", ".join(lookup.enrolled_titles) or "no courses yet"),
    ]
    if scope.lecture_title:
        course = catalog_service.by_slug(scope.course_slug or "")
        where = f" in {course['title']}" if course else ""
        lines.append(f'MODE: in-lecture — the student is watching "{scope.lecture_title}"{where} right now.')
    if weak_concepts:
        lines.append("Weak concepts in this course: " + ", ".join(weak_concepts))
    if lookup.hits:
        lines.append("Matches:")
        for i, h in enumerate(lookup.hits, 1):
            label = "ENROLLED" if h.enrolled else "NOT ENROLLED"
            where = f"{h.title} @ {_mmss(h.start_time)}" if h.source == "transcript" else h.title
            page = f" — course page: the01.dev{h.url}" if h.url else ""
            lines.append(f"{i}. [{label}] {h.course_title} → {where} ({h.source}, score {h.score:.2f}){page}")
            lines.append(f'   "{h.text[:600]}"')
    return "\n".join(lines)


def to_cards(lookup: CourseLookup) -> list[dict]:
    """SourceCard-shaped dicts for the frontend (RagSourceCard deep-links via course_id slug)."""
    cards = []
    for h in lookup.hits:
        cards.append({
            "course_id": h.course_slug or "",
            "course_title": h.course_title,
            "lecture_id": h.lecture_id or f"catalog-{h.course_id}",
            "lecture_title": h.title,
            "timestamp": _mmss(h.start_time) if h.source == "transcript" else "",
            "start_time": h.start_time,
            "end_time": h.end_time,
            "snippet": (h.text[:220] + "…") if len(h.text) > 220 else h.text,
            "score": round(h.score, 3),
        })
    return cards
```

Move `tutor_service._weak_concepts` into `journey_service` as `async def weak_concepts_for_course(user_id: str, course_slug: str) -> list[str]` (same body, same return format `"concept (NN%)"`); make `tutor_service._weak_concepts` call it (it is deleted in Task 14).

- [ ] **Step 4: Run** — `$TEST tests/test_course_lookup.py -v` → 8 PASS. Suite → no new failures.

- [ ] **Step 5: Commit (local)** — `git add backend/app/services/course_lookup.py backend/app/services/journey_service.py backend/app/services/tutor_service.py backend/tests/test_course_lookup.py && git commit -m "feat: course_lookup — transcript + catalog search labelled by enrollment, three cases"`

---

### Task 9: Calibrate the thresholds

**Files:**
- Create: `backend/scripts/calibrate_lookup.py`
- Modify: `backend/app/services/course_lookup.py` (the two constants), spec §4.3

Needs the real OpenAI key (run **without** the `$TEST` env blanks; costs well under $0.01).

- [ ] **Step 1: Write the script**

`backend/scripts/calibrate_lookup.py`:
```python
"""Measure transcript/catalog similarity scores on labelled questions and pick
course_lookup thresholds from the data (same method Lab used for its 0.64).

Run from backend/:  .venv/bin/python scripts/calibrate_lookup.py
"""
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from dotenv import load_dotenv  # noqa: E402

load_dotenv(Path(__file__).resolve().parents[1] / ".env")

from app.services import catalog_index, course_lookup as cl  # noqa: E402

# (question, covered_by_a_transcript, covered_by_the_catalog)
LABELLED = [
    ("how do I publish an npm library", True, True),
    ("how does npm link work", True, True),
    ("what is prototype inheritance in javascript", True, True),
    ("how does the websocket handshake work", True, True),
    ("what are hidden classes in V8", True, True),
    ("when should I use useMemo for computed state", True, True),
    ("explain the event loop and microtasks", True, True),
    ("long polling vs websockets, which should I use", True, True),
    ("does React.memo need useCallback", True, True),
    ("how do I write a lexer for my own language", False, True),
    ("how do I build an abstract syntax tree", False, True),
    ("what is time-travel debugging in a state library", False, True),
    ("how do I build a router for a web framework", False, True),
    ("what does TurboFan do in V8", False, True),
    ("how does pub/sub work in a real-time system", False, True),
    ("how do I avoid polluting the window object", False, True),
    ("how do I bake sourdough bread", False, False),
    ("what's the best gaming laptop in 2026", False, False),
    ("explain photosynthesis", False, False),
    ("how do I file my taxes", False, False),
    ("who won the football world cup", False, False),
    ("how do I set up kubernetes autoscaling", False, False),
    ("write me a poem about the sea", False, False),
]


def best_threshold(pos: list[float], neg: list[float]) -> tuple[float, float]:
    best = (0.0, -1.0)
    for i in range(10, 81):
        t = i / 100
        acc = (sum(s >= t for s in pos) + sum(s < t for s in neg)) / (len(pos) + len(neg))
        if acc > best[1]:
            best = (t, acc)
    return best


async def main() -> None:
    await catalog_index.ensure_built()
    rows = []
    for q, in_transcript, in_catalog in LABELLED:
        t = await cl._transcript_hits(q)
        c = await catalog_index.search(q, top_k=1)
        rows.append((q, in_transcript, in_catalog, t[0][1] if t else 0.0, c[0][1] if c else 0.0))
    print(f"{'question':55} {'T?':3} {'C?':3} {'t_score':>8} {'c_score':>8}")
    for q, it, ic, ts, cs in rows:
        print(f"{q[:55]:55} {'Y' if it else '-':3} {'Y' if ic else '-':3} {ts:8.3f} {cs:8.3f}")
    t_thr, t_acc = best_threshold([r[3] for r in rows if r[1]], [r[3] for r in rows if not r[1]])
    c_thr, c_acc = best_threshold([r[4] for r in rows if r[2]], [r[4] for r in rows if not r[2]])
    print(f"\nTRANSCRIPT_THRESHOLD = {t_thr:.2f}   (accuracy {t_acc:.0%})")
    print(f"CATALOG_THRESHOLD    = {c_thr:.2f}   (accuracy {c_acc:.0%})")


if __name__ == "__main__":
    asyncio.run(main())
```

- [ ] **Step 2: Run it** — `cd backend && .venv/bin/python scripts/calibrate_lookup.py`. Expected: a 23-row table and two recommended thresholds.

- [ ] **Step 3: Apply the measured values.** Set `TRANSCRIPT_THRESHOLD` / `CATALOG_THRESHOLD` in `course_lookup.py` to the printed values. In spec §4.3 replace the "Thresholds are measured" bullet's last clause with the chosen values, accuracies and the date. If either accuracy is below 85%, stop and report the table to the user before continuing — the indexes don't separate well enough and the design needs a decision.

- [ ] **Step 4: Suite** → `tests/test_course_lookup.py` still passes (its fixture pins the thresholds).

- [ ] **Step 5: Commit (local)** — `git add backend/scripts/calibrate_lookup.py backend/app/services/course_lookup.py docs/superpowers/specs/2026-10-04-course-aware-chat-design.md && git commit -m "feat: calibrate course_lookup thresholds on labelled questions"`

---

### Task 10: Tutor agent with server-bound identity

**Files:**
- Create: `backend/app/services/tool_descriptions.py`, `backend/app/services/tutor_agent.py`, `backend/tests/fakes.py`
- Modify: `backend/app/services/journey_service.py` (gain `get_strengths_report`), `backend/app/mcp/the01dev_tools.py` (call it)
- Test: `backend/tests/test_tutor_agent.py`

**Interfaces:**
- Consumes: `grounding.retrieve`, `grounding.build_sources`, `enrollment_service.get_enrolled_courses`, `journey_service.get_metrics`, `skill_graph_service.get_prerequisite_view / record_observation`, `memory_service.search_history`, `GEN_MODEL`
- Produces:
  - `ChatContext(student_id: str)` frozen dataclass
  - `TOOLS: list` (7 LangChain tools)
  - `async stream_answer(*, system_prompt: str, history: list[dict], question: str, student_id: str, model=None) -> AsyncIterator[dict]` yielding `{"type": "token", "value": str}` and `{"type": "cards", "cards": list[dict]}`
  - `journey_service.get_strengths_report(student_id: str) -> dict` (strengths/weaknesses with prerequisites — moved verbatim from the MCP tool body)
  - `tests/fakes.py: FakeToolModel`

- [ ] **Step 1: Shared descriptions + strengths report**

`backend/app/services/tool_descriptions.py` — one constant per tool, text copied from the current MCP docstrings in `app/mcp/the01dev_tools.py` with every sentence about passing `student_id` removed (the web tools don't take it):
```python
"""What each tutor tool is for — the text the model reads to decide when to call it.
Written once; the web chat's LangChain tools use it now, the MCP tools in the
Hermes phase."""

SEARCH_COURSE_CONTENT = (
    "Search the01.dev lecture transcripts. Use only for a follow-up question the COURSE FACTS "
    "don't already cover. Returns excerpts with course, lecture and timestamp so you can cite them."
)
GET_ENROLLED_COURSES = (
    "Which courses this student owns. Use for 'what courses am I enrolled in / do I have access to'. "
    "An empty list means no enrollments yet — say so plainly."
)
GET_LEARNING_STRENGTHS = (
    "What this student is good and weak at overall, with each weakness's prerequisites and their "
    "accuracy. Use for 'what am I good at / weak at / where do I need work'. Empty means no graded "
    "activity yet — say so, don't guess."
)
GET_LEARNING_METRICS = (
    "Raw activity numbers: quiz count, streak, average score, active days, practice time. Use for "
    "'what's my streak', 'how many quizzes have I taken'. Zeros mean no graded activity yet."
)
GET_CONCEPT_CONFIDENCE = (
    "This student's accuracy on one concept and on its prerequisites, plus your earlier chat "
    "impressions. Use before teaching a concept that has prerequisites. accuracy null = never graded, "
    "not zero. course_id is the course slug, e.g. 'react-perf'."
)
SEARCH_HISTORY = (
    "Search this student's own past tutoring exchanges. Use only when they refer to a past "
    "conversation ('like you taught me closures', 'what did we cover last time')."
)
RECORD_SKILL_OBSERVATION = (
    "Log what the conversation showed about this student's grasp of a concept — not a quiz score. "
    "confidence must be exactly 'weak', 'developing' or 'strong'. Only for concrete signals. "
    "course_id is the course slug, e.g. 'react-perf'."
)
```

Move the body of the MCP tool `get_learning_strengths` (`the01dev_tools.py:245-260`, the enrichment loop) into `journey_service.get_strengths_report(student_id) -> dict` (it imports `knowledge_graph_service` and `skill_graph_service`); the MCP tool becomes `return await journey_service.get_strengths_report(student_id)`. Run the MCP suite (`.mcp-venv`, `tests/test_mcp_get_learning_strengths.py`) → still PASS.

- [ ] **Step 2: Fake model for tests**

`backend/tests/fakes.py`:
```python
"""A scripted chat model for create_agent tests — no network.

GenericFakeChatModel alone can't drive create_agent: it has no bind_tools, and its
_stream drops tool_calls under stream_mode="messages". This subclass fixes both.
"""
import json

from langchain_core.language_models.fake_chat_models import GenericFakeChatModel
from langchain_core.messages import AIMessage, AIMessageChunk
from langchain_core.outputs import ChatGenerationChunk


class FakeToolModel(GenericFakeChatModel):
    def bind_tools(self, tools, **kwargs):
        return self

    def _stream(self, messages, stop=None, run_manager=None, **kwargs):
        msg = next(self.messages)
        msg = AIMessage(content=msg) if isinstance(msg, str) else msg
        if msg.tool_calls:
            chunk = ChatGenerationChunk(message=AIMessageChunk(
                content="", id=msg.id, chunk_position="last",
                tool_call_chunks=[
                    {"name": t["name"], "args": json.dumps(t["args"]), "id": t["id"], "index": i}
                    for i, t in enumerate(msg.tool_calls)
                ],
            ))
            if run_manager:
                run_manager.on_llm_new_token("", chunk=chunk)
            yield chunk
            return
        words = msg.content.split(" ")
        for i, w in enumerate(words):
            chunk = ChatGenerationChunk(message=AIMessageChunk(
                content=w if i == 0 else " " + w, id=msg.id,
                chunk_position="last" if i == len(words) - 1 else None,
            ))
            if run_manager:
                run_manager.on_llm_new_token(chunk.message.content, chunk=chunk)
            yield chunk
```

- [ ] **Step 3: Failing tests**

`backend/tests/test_tutor_agent.py`:
```python
from langchain_core.messages import AIMessage
from langchain_core.utils.function_calling import convert_to_openai_tool

from app.services import grounding, journey_service, tutor_agent
from tests.fakes import FakeToolModel


def test_no_tool_exposes_student_id_to_the_model():
    for t in tutor_agent.TOOLS:
        props = convert_to_openai_tool(t)["function"]["parameters"].get("properties", {})
        assert "student_id" not in props, t.name
        assert "runtime" not in props, t.name


async def _collect(gen):
    return [e async for e in gen]


async def test_tool_uses_context_student_not_model_supplied_id(monkeypatch):
    seen = []

    async def fake_metrics(user_id):
        seen.append(user_id)
        return {"quizzes": 3}

    monkeypatch.setattr(journey_service, "get_metrics", fake_metrics)
    model = FakeToolModel(messages=iter([
        AIMessage("", tool_calls=[{"name": "get_learning_metrics", "args": {"student_id": "victim"}, "id": "c1"}]),
        AIMessage("You have taken 3 quizzes."),
    ]))
    events = await _collect(tutor_agent.stream_answer(
        system_prompt="sys", history=[], question="how many quizzes?", student_id="alice", model=model))
    assert seen == ["alice"]
    assert "".join(e["value"] for e in events if e["type"] == "token") == "You have taken 3 quizzes."


async def test_follow_up_search_yields_cards(monkeypatch):
    from app.models import SearchResult, TranscriptChunk
    chunk = TranscriptChunk(chunk_id="c", course_id="react-perf", course_title="React Performance Patterns",
                            lecture_id="l", lecture_title="4.1 - React.memo and useCallback", text="memo",
                            start_time=30, end_time=60)

    async def fake_retrieve(q, top_k=5):
        return [SearchResult(chunk=chunk, score=0.7)]

    monkeypatch.setattr(grounding, "retrieve", fake_retrieve)
    model = FakeToolModel(messages=iter([
        AIMessage("", tool_calls=[{"name": "search_course_content", "args": {"query": "memo"}, "id": "c1"}]),
        AIMessage("Memo skips re-renders."),
    ]))
    events = await _collect(tutor_agent.stream_answer(
        system_prompt="sys", history=[{"role": "user", "content": "hi"}, {"role": "assistant", "content": "hello"}],
        question="memo?", student_id="alice", model=model))
    cards = [c for e in events if e["type"] == "cards" for c in e["cards"]]
    assert cards and cards[0]["lecture_title"] == "4.1 - React.memo and useCallback"
```

- [ ] **Step 4: Run** → FAIL (no module).

- [ ] **Step 5: Implement**

`backend/app/services/tutor_agent.py`:
```python
"""The tutor: a LangChain create_agent over thin wrappers of app/services.

Identity is bound server-side: tools read student_id from the run's ChatContext
(ToolRuntime), which the model can neither see nor set — no tool schema has a
student_id parameter. The flow is linear (lookup → agent → save), so this is a
plain create_agent, not a custom LangGraph graph; Lab keeps its graph because it
branches and pauses for approval.
"""
import json
from dataclasses import dataclass
from functools import lru_cache
from typing import AsyncIterator, Optional

from langchain.agents import create_agent
from langchain.tools import ToolRuntime, tool
from langchain_core.messages import AIMessage, AIMessageChunk, HumanMessage, ToolMessage
from langchain_openai import ChatOpenAI

from app.services import (enrollment_service, grounding, journey_service, memory_service,
                          skill_graph_service)
from app.services import tool_descriptions as D
from app.services.llm import GEN_MODEL


@dataclass(frozen=True)
class ChatContext:
    student_id: str


def _dump(data) -> str:
    return json.dumps(data, default=str)


@tool("search_course_content", description=D.SEARCH_COURSE_CONTENT, response_format="content_and_artifact")
async def search_course_content(query: str) -> tuple[str, list[dict]]:
    results = await grounding.retrieve(query, top_k=5)
    if not results:
        return "No matching course content.", []
    cards = [c.model_dump() for c in grounding.build_sources(results)]
    text = "\n".join(
        f"- {r.chunk.course_title} → {r.chunk.lecture_title} @ {c['timestamp']}: {r.chunk.text}"
        for r, c in zip(results, cards)
    )
    return text, cards


@tool("get_enrolled_courses", description=D.GET_ENROLLED_COURSES)
async def get_enrolled_courses(runtime: ToolRuntime[ChatContext]) -> str:
    return _dump(await enrollment_service.get_enrolled_courses(runtime.context.student_id))


@tool("get_learning_strengths", description=D.GET_LEARNING_STRENGTHS)
async def get_learning_strengths(runtime: ToolRuntime[ChatContext]) -> str:
    return _dump(await journey_service.get_strengths_report(runtime.context.student_id))


@tool("get_learning_metrics", description=D.GET_LEARNING_METRICS)
async def get_learning_metrics(runtime: ToolRuntime[ChatContext]) -> str:
    return _dump(await journey_service.get_metrics(runtime.context.student_id))


@tool("get_concept_confidence", description=D.GET_CONCEPT_CONFIDENCE)
async def get_concept_confidence(concept: str, course_id: str, runtime: ToolRuntime[ChatContext]) -> str:
    return _dump(await skill_graph_service.get_prerequisite_view(runtime.context.student_id, course_id, concept))


@tool("search_history", description=D.SEARCH_HISTORY)
async def search_history(query: str, runtime: ToolRuntime[ChatContext]) -> str:
    rows = await memory_service.search_history(runtime.context.student_id, query, 3)
    return _dump([
        {"date": str(r.get("created_at", ""))[:10], "course": r.get("course_slug"),
         "snippet": f"Q: {r.get('question', '')}\nA: {r.get('answer', '')}"[:300]}
        for r in rows
    ])


@tool("record_skill_observation", description=D.RECORD_SKILL_OBSERVATION)
async def record_skill_observation(concept: str, course_id: str, confidence: str, note: str,
                                   runtime: ToolRuntime[ChatContext]) -> str:
    try:
        return _dump(await skill_graph_service.record_observation(
            runtime.context.student_id, course_id, concept, confidence, note))
    except ValueError as e:
        return _dump({"error": str(e)})


TOOLS = [search_course_content, get_enrolled_courses, get_learning_strengths, get_learning_metrics,
         get_concept_confidence, search_history, record_skill_observation]


@lru_cache(maxsize=1)
def _default_model() -> ChatOpenAI:
    return ChatOpenAI(model=GEN_MODEL, temperature=0.4, streaming=True, timeout=60, max_retries=2)


async def stream_answer(*, system_prompt: str, history: list[dict], question: str, student_id: str,
                        model: Optional[object] = None) -> AsyncIterator[dict]:
    agent = create_agent(model or _default_model(), tools=TOOLS, system_prompt=system_prompt,
                         context_schema=ChatContext)
    messages = [HumanMessage(t["content"]) if t["role"] == "user" else AIMessage(t["content"])
                for t in history if t.get("role") in ("user", "assistant")]
    messages.append(HumanMessage(question))
    async for chunk, meta in agent.astream({"messages": messages}, context=ChatContext(student_id=student_id),
                                           stream_mode="messages"):
        if isinstance(chunk, AIMessageChunk) and meta.get("langgraph_node") == "model" and chunk.text:
            yield {"type": "token", "value": chunk.text}
        elif isinstance(chunk, ToolMessage) and chunk.artifact:
            yield {"type": "cards", "cards": list(chunk.artifact)}
```

- [ ] **Step 6: Run** — `$TEST tests/test_tutor_agent.py -v` → 3 PASS. If `test_tool_uses_context_student_not_model_supplied_id` fails because the extra `student_id` arg is rejected by tool validation (ToolMessage error instead of calling the tool), that still proves the id can't be forged — change the assertion to `assert seen in ([], ["alice"]) and "victim" not in seen` and note it in the commit message. Suite → no new failures.

- [ ] **Step 7: Commit (local)** — `git add backend/app/services/tool_descriptions.py backend/app/services/tutor_agent.py backend/app/services/journey_service.py backend/app/mcp/the01dev_tools.py backend/tests/fakes.py backend/tests/test_tutor_agent.py && git commit -m "feat: LangChain tutor agent with server-bound student identity"`

---

### Task 11: `chat_pipeline.chat_turn`

**Files:**
- Create: `backend/app/services/chat_pipeline.py`
- Test: `backend/tests/test_chat_pipeline.py`

**Interfaces:**
- Consumes: `pii.scrub`, `audit_service.log_event`, `course_lookup.course_lookup/render_facts/to_cards/ChatScope`, `journey_service.weak_concepts_for_course`, `memory_service.memory_context/record_turn`, `context_builder.build`, `loader.read_grounding_prompt`, `tutor_agent.stream_answer`
- Produces: `TurnRequest(question: str, student_id: str, scope: ChatScope, history: list[dict], memory_slug: str)`; `async chat_turn(req: TurnRequest, *, model=None) -> AsyncIterator[dict]` yielding, in order: one `sources` event, `token` events, optionally a second `sources` event (new cards only), then `done` — or an `error` event in place of `done`. `sse(event: dict) -> str`. `CONTEXT_LIMIT`.

- [ ] **Step 1: Failing tests**

`backend/tests/test_chat_pipeline.py`:
```python
import pytest

from app.services import audit_service, chat_pipeline, course_lookup as cl, journey_service, memory_service, tutor_agent


@pytest.fixture
def wired(monkeypatch):
    calls = {"audit": [], "recorded": [], "lookup_q": [], "agent_q": []}

    async def log_event(**kw):
        calls["audit"].append(kw)
    async def memory_context(*a):
        return ""
    async def record_turn(student_id, slug, q, a):
        calls["recorded"].append((student_id, slug, q, a))
    async def weak(*a):
        return []
    async def lookup(question, student_id, scope=cl.ChatScope()):
        calls["lookup_q"].append(question)
        hit = cl.Hit(source="transcript", course_id=2, course_slug="custom-library",
                     course_title="Build a Custom Library", title="8.1 - The npm link command", score=0.6,
                     enrolled=False, text="npm link", lecture_id="custom-library-8-1", start_time=87, url="/course/2")
        return cl.CourseLookup(case=cl.LookupCase.NOT_ENROLLED_MATCH, hits=[hit], enrolled_titles=[])

    monkeypatch.setattr(audit_service, "log_event", log_event)
    monkeypatch.setattr(memory_service, "memory_context", memory_context)
    monkeypatch.setattr(memory_service, "record_turn", record_turn)
    monkeypatch.setattr(journey_service, "weak_concepts_for_course", weak)
    monkeypatch.setattr(chat_pipeline, "course_lookup", lookup)
    return calls


def _agent(monkeypatch, calls, events=None, raise_after_tokens=False):
    async def fake_stream(*, system_prompt, history, question, student_id, model=None):
        calls["agent_q"].append(question)
        calls["system"] = system_prompt
        for e in events or [{"type": "token", "value": "Short answer."}]:
            yield e
        if raise_after_tokens:
            raise RuntimeError("openai exploded: sk-secret")
    monkeypatch.setattr(tutor_agent, "stream_answer", fake_stream)


def _req(q="how do I publish an npm library"):
    return chat_pipeline.TurnRequest(question=q, student_id="alice", scope=cl.ChatScope(), history=[],
                                     memory_slug="all-courses")


async def test_order_sources_first_then_tokens_then_done(wired, monkeypatch):
    _agent(monkeypatch, wired)
    events = [e async for e in chat_pipeline.chat_turn(_req())]
    assert [e["type"] for e in events] == ["sources", "token", "done"]
    assert events[0]["sources"][0]["course_id"] == "custom-library"
    assert "CASE: NOT_ENROLLED_MATCH" in wired["system"]
    assert wired["recorded"] == [("alice", "all-courses", "how do I publish an npm library", "Short answer.")]


async def test_pii_is_scrubbed_everywhere(wired, monkeypatch):
    _agent(monkeypatch, wired)
    [e async for e in chat_pipeline.chat_turn(_req("email me at bob@example.com about npm"))]
    for q in (wired["lookup_q"][0], wired["agent_q"][0], wired["audit"][0]["question"], wired["recorded"][0][2]):
        assert "bob@example.com" not in q


async def test_agent_failure_sends_generic_error_and_saves_nothing(wired, monkeypatch):
    _agent(monkeypatch, wired, raise_after_tokens=True)
    events = [e async for e in chat_pipeline.chat_turn(_req())]
    assert events[-1]["type"] == "error"
    assert "sk-secret" not in events[-1]["message"]
    assert wired["recorded"] == []


async def test_duplicate_cards_from_follow_up_search_are_not_repeated(wired, monkeypatch):
    dup = {"course_id": "custom-library", "lecture_id": "custom-library-8-1", "start_time": 87}
    new = {"course_id": "react-perf", "lecture_id": "react-perf-4-1", "start_time": 30}
    _agent(monkeypatch, wired, events=[{"type": "token", "value": "x"}, {"type": "cards", "cards": [dup, new]}])
    events = [e async for e in chat_pipeline.chat_turn(_req())]
    later = [e for e in events if e["type"] == "sources"][1:]
    assert len(later) == 1 and later[0]["sources"] == [new]
```

- [ ] **Step 2: Run** → FAIL (no module).

- [ ] **Step 3: Implement**

`backend/app/services/chat_pipeline.py`:
```python
"""One chat turn, shared by both chats (Ask page and the video-player tutor).

PII scrub → audit → course_lookup (always, in code) → tutor agent → save to memory.
The endpoints differ only in ChatScope and where history comes from.
"""
import json
import os
from dataclasses import dataclass
from typing import AsyncIterator, Optional

from app.grounding.loader import read_grounding_prompt
from app.services import audit_service, context_builder, journey_service, memory_service, pii, tutor_agent
from app.services.course_lookup import ChatScope, course_lookup, render_facts, to_cards
from app.services.llm import GEN_MODEL

CONTEXT_LIMIT = int(os.getenv("MODEL_CONTEXT_LIMIT", "8192"))
PROVIDER = "langchain-agent"
_ERROR = "The tutor hit a problem answering that. Please try again."


@dataclass
class TurnRequest:
    question: str          # raw; scrubbed here
    student_id: str        # verified server-side (app.auth)
    scope: ChatScope
    history: list[dict]    # prior [{"role", "content"}], oldest first
    memory_slug: str       # memory_service course key: "all-courses" or the course slug


def sse(event: dict) -> str:
    return f"data: {json.dumps(event)}\n\n"


def _sources(cards: list[dict]) -> dict:
    return {"type": "sources", "sources": cards, "insufficient_context": False, "offer_general": False}


def _card_key(card: dict) -> tuple:
    return (card.get("course_id"), card.get("lecture_id"), card.get("start_time"))


async def chat_turn(req: TurnRequest, *, model: Optional[object] = None) -> AsyncIterator[dict]:
    question, _ = pii.scrub(req.question)
    await audit_service.log_event(student_id=req.student_id, course_slug=req.memory_slug,
                                  question=question, model=GEN_MODEL, provider=PROVIDER)

    lookup = await course_lookup(question, req.student_id, req.scope)
    weak = (await journey_service.weak_concepts_for_course(req.student_id, req.scope.course_slug)
            if req.scope.course_slug else None)
    memory = await memory_service.memory_context(req.student_id, req.memory_slug)
    system = "\n\n".join(p for p in (read_grounding_prompt(), render_facts(lookup, req.scope, weak), memory) if p)
    history, _fit = context_builder.build(system, req.history, question, CONTEXT_LIMIT)

    cards = to_cards(lookup)
    yield _sources(cards)
    seen = {_card_key(c) for c in cards}
    extra: list[dict] = []
    answer: list[str] = []
    try:
        async for event in tutor_agent.stream_answer(system_prompt=system, history=history, question=question,
                                                     student_id=req.student_id, model=model):
            if event["type"] == "token":
                answer.append(event["value"])
                yield event
            elif event["type"] == "cards":
                for c in event["cards"]:
                    if _card_key(c) not in seen:
                        seen.add(_card_key(c))
                        extra.append(c)
    except Exception as e:  # noqa: BLE001 — never leak provider errors to the student
        print(f"[chat_turn] agent failed: {e!r}")
        yield {"type": "error", "message": _ERROR}
        return

    if extra:
        yield _sources(extra)
    try:
        await memory_service.record_turn(req.student_id, req.memory_slug, question, "".join(answer))
    except Exception as e:  # noqa: BLE001 — never fail the answer over memory persistence
        print(f"[chat_turn] record_turn failed: {e!r}")
    yield {"type": "done"}
```

Note: the test patches `chat_pipeline.course_lookup` (the imported name) — keep the `from … import course_lookup` form.

- [ ] **Step 4: Run** — `$TEST tests/test_chat_pipeline.py -v` → 4 PASS. Suite → no new failures.

- [ ] **Step 5: Commit (local)** — `git add backend/app/services/chat_pipeline.py backend/tests/test_chat_pipeline.py && git commit -m "feat: shared chat_turn pipeline — lookup first, agent, memory"`

---

### Task 12: Login-token verification (backend)

**Files:**
- Create: `backend/app/auth.py`
- Test: `backend/tests/test_auth.py`

**Interfaces — Produces:** `async current_student(authorization: str = Header(default="")) -> str` (FastAPI dependency; returns Firebase `uid`; raises 401).

- [ ] **Step 1: Failing tests**

`backend/tests/test_auth.py`:
```python
import pytest
from fastapi import HTTPException

from app import auth


async def test_valid_token_returns_uid(monkeypatch):
    monkeypatch.setattr(auth.fb_auth, "verify_id_token", lambda token, app=None: {"uid": "u-123"})
    monkeypatch.setattr(auth, "_firebase_app", lambda: None)
    assert await auth.current_student("Bearer good-token") == "u-123"


@pytest.mark.parametrize("header", ["", "Bearer", "Bearer ", "Basic abc", "good-token"])
async def test_missing_or_malformed_header_is_401(header):
    with pytest.raises(HTTPException) as e:
        await auth.current_student(header)
    assert e.value.status_code == 401


async def test_expired_or_invalid_token_is_401_not_500(monkeypatch):
    def boom(token, app=None):
        raise ValueError("Token expired, 1700000000 < 1800000000")
    monkeypatch.setattr(auth.fb_auth, "verify_id_token", boom)
    monkeypatch.setattr(auth, "_firebase_app", lambda: None)
    with pytest.raises(HTTPException) as e:
        await auth.current_student("Bearer stale")
    assert e.value.status_code == 401
    assert "expired" not in e.value.detail.lower() or "sign in" in e.value.detail.lower()
    assert "1700000000" not in e.value.detail
```

- [ ] **Step 2: Run** → FAIL (no module).

- [ ] **Step 3: Implement**

`backend/app/auth.py`:
```python
"""Who is asking: verifies the Firebase ID token the frontend sends.

The student id is the token's uid — the same id the frontend used to send in
the request body, so existing data keys don't change. Body/header ids are
ignored on routes that use this dependency.
"""
import asyncio
import os

import firebase_admin
from fastapi import Header, HTTPException
from firebase_admin import auth as fb_auth

FIREBASE_PROJECT_ID = os.getenv("FIREBASE_PROJECT_ID", "topdev-93530")
_APP_NAME = "token-verifier"


def _firebase_app():
    try:
        return firebase_admin.get_app(_APP_NAME)
    except ValueError:
        # Verifying ID tokens needs only the project id (Google's public keys are
        # fetched over HTTPS) — no service-account credential.
        return firebase_admin.initialize_app(options={"projectId": FIREBASE_PROJECT_ID}, name=_APP_NAME)


async def current_student(authorization: str = Header(default="")) -> str:
    scheme, _, token = authorization.partition(" ")
    if scheme.lower() != "bearer" or not token.strip():
        raise HTTPException(status_code=401, detail="Sign in to use the AI tutor")
    try:
        decoded = await asyncio.to_thread(fb_auth.verify_id_token, token.strip(), app=_firebase_app())
    except Exception:  # noqa: BLE001 — any verification failure is "not signed in"
        raise HTTPException(status_code=401, detail="Your session has ended. Please sign in again.")
    return decoded["uid"]
```

- [ ] **Step 4: Prove project-id-only init works (no credentials)**

```bash
cd backend && env GOOGLE_APPLICATION_CREDENTIALS= .venv/bin/python -c "
import asyncio
from app import auth
from fastapi import HTTPException
try:
    asyncio.run(auth.current_student('Bearer not-a-real-token'))
except HTTPException as e:
    print('401 OK:', e.detail)
"
```
Expected: `401 OK: Your session has ended…` (verification ran and rejected the token — not a credentials error at init). If initialisation itself raises a `DefaultCredentialsError`, pass `credential=firebase_admin.credentials.AnonymousCredentials()` if available in 6.5.0, else stop and report.

- [ ] **Step 5: Run** — `$TEST tests/test_auth.py -v` → 7 PASS.

- [ ] **Step 6: Commit (local)** — `git add backend/app/auth.py backend/tests/test_auth.py && git commit -m "feat: verify Firebase ID token for student-facing chat routes"`

---

### Task 13: Rewire the Ask chat (`/api/hermes/chat`) — removes the Hermes web path

**Files:**
- Modify: `backend/app/main.py`
- Delete: `backend/app/services/hermes_client.py`
- Delete+replace tests: `backend/tests/test_hermes_chat_routing.py`, `test_hermes_chat_citations.py`, `test_hermes_chat_identity_context.py` → `backend/tests/test_ask_chat_route.py`; fix `backend/tests/test_admin_auth_gate.py:57`

- [ ] **Step 1: Failing route tests**

`backend/tests/test_ask_chat_route.py`:
```python
import json

import pytest
from fastapi.testclient import TestClient

from app.auth import current_student
from app.main import app
from app.services import audit_service, chat_pipeline, memory_service, skill_graph_service


def _events(text):
    return [json.loads(l[5:].strip()) for l in text.splitlines() if l.startswith("data:")]


@pytest.fixture
def client(monkeypatch):
    async def noop(*a, **k):
        return None
    async def empty_list(*a, **k):
        return []
    async def zero(*a, **k):
        return 0
    monkeypatch.setattr(audit_service, "log_event", noop)
    monkeypatch.setattr(memory_service, "recent_turns", empty_list)
    monkeypatch.setattr(skill_graph_service, "ensure_populated", zero)
    app.dependency_overrides[current_student] = lambda: "token-uid"
    yield TestClient(app)
    app.dependency_overrides.clear()


def test_course_question_streams_through_chat_turn_with_token_identity(client, monkeypatch):
    seen = {}

    async def fake_turn(req, model=None):
        seen["req"] = req
        yield {"type": "sources", "sources": [], "insufficient_context": False, "offer_general": False}
        yield {"type": "token", "value": "hi"}
        yield {"type": "done"}

    monkeypatch.setattr(chat_pipeline, "chat_turn", fake_turn)
    r = client.post("/api/hermes/chat", json={"question": "what is npm link", "user_id": "someone-else",
                                               "course_slug": "all-courses"})
    assert r.status_code == 200
    assert [e["type"] for e in _events(r.text)] == ["sources", "token", "done"]
    assert seen["req"].student_id == "token-uid"
    assert seen["req"].scope.course_slug is None and seen["req"].memory_slug == "all-courses"


def test_quiz_request_is_handed_off_without_the_agent(client, monkeypatch):
    async def must_not_run(req, model=None):
        raise AssertionError("agent should not run for quiz hand-off")
        yield

    monkeypatch.setattr(chat_pipeline, "chat_turn", must_not_run)
    r = client.post("/api/hermes/chat", json={"question": "quiz me on closures", "course_slug": "all-courses"})
    tokens = "".join(e.get("value", "") for e in _events(r.text) if e["type"] == "token")
    assert r.status_code == 200 and tokens.strip()


def test_empty_question_is_400(client):
    assert client.post("/api/hermes/chat", json={"question": "  "}).status_code == 400


def test_no_token_is_401():
    app.dependency_overrides.clear()
    r = TestClient(app).post("/api/hermes/chat", json={"question": "hi", "user_id": "x"})
    assert r.status_code == 401
```

(Check `app/routing/intent.py`'s quiz regex accepts "quiz me on closures"; if not, use a phrase from its pattern list.)

- [ ] **Step 2: Run** → FAIL (route still uses Hermes / no auth).

- [ ] **Step 3: Rewrite the route**

Replace the whole `hermes_chat` function (`main.py:224-453`) with:
```python
@app.post("/api/hermes/chat")
async def hermes_chat(req: Request, student_id: str = Depends(current_student)):
    """The Ask page chat. URL kept for frontend compatibility (rename later).

    Fixed-answer intents (quiz hand-off, empty/gibberish) answer here; everything else
    runs chat_pipeline.chat_turn: course lookup in code first, then the tutor agent.
    Identity comes from the verified login token, never the request body.
    """
    body = await req.json()
    question = (body.get("question") or "").strip()
    course_slug = body.get("course_slug") or "all-courses"
    if not question:
        raise HTTPException(status_code=400, detail="Empty question")

    scrubbed, _ = pii.scrub(question)
    intent = classify(scrubbed)
    headers = {"Cache-Control": "no-cache", "Connection": "keep-alive", "X-Accel-Buffering": "no"}

    if intent in (Intent.QUIZ_GENERATE, Intent.OUT_OF_SCOPE):
        message = (build_handoff_message(course_slug) if intent == Intent.QUIZ_GENERATE
                   else "Hey, I'm Dev — ask me about a course or a technical concept and I'll help!")
        await audit_service.log_event(student_id=student_id, course_slug=course_slug, question=scrubbed,
                                      model="rule-based-router", provider="none")

        async def gen_handoff():
            yield chat_pipeline.sse({"type": "sources", "sources": [], "insufficient_context": False,
                                     "offer_general": False})
            for word in message.split(" "):
                yield chat_pipeline.sse({"type": "token", "value": word + " "})
            yield chat_pipeline.sse({"type": "done"})

        return StreamingResponse(gen_handoff(), media_type="text/event-stream", headers=headers)

    try:
        await skill_graph_service.ensure_populated(student_id, course_slug)
    except Exception as e:  # noqa: BLE001 — back-fill never breaks a chat turn
        print(f"[hermes_chat] ensure_populated failed: {e}")

    prior = await memory_service.recent_turns(student_id, course_slug, limit=3)
    history: list[dict] = []
    for t in prior:
        history += [{"role": "user", "content": t.get("question", "")},
                    {"role": "assistant", "content": t.get("answer", "")}]

    turn = chat_pipeline.TurnRequest(
        question=question, student_id=student_id,
        scope=ChatScope(course_slug=None if course_slug == "all-courses" else course_slug),
        history=history, memory_slug=course_slug,
    )
    tracer = get_tracer()

    async def gen():
        span = tracer.start_span("chat_turn")
        span.set_attribute("route", "ask")
        span.set_attribute("student", hashlib.sha256(student_id.encode()).hexdigest()[:12])
        try:
            async for event in chat_pipeline.chat_turn(turn):
                yield chat_pipeline.sse(event)
        finally:
            span.end()

    return StreamingResponse(gen(), media_type="text/event-stream", headers=headers)
```
Imports to add: `from fastapi import Depends` (if missing), `from app.auth import current_student`, `from app.services import chat_pipeline`, `from app.services.course_lookup import ChatScope`. Remove: `hermes_client`, `context_builder` (if now unused in main), `_MODEL_CONTEXT_LIMIT` (moved to `chat_pipeline.CONTEXT_LIMIT`), `otel_trace` (if unused), the `store.delete/get("chat_citations", …)` code (gone with the old body). Then `git rm -q app/services/hermes_client.py`. Remove `HERMES_URL`, `HERMES_API_KEY`, `HERMES_MODEL_LABEL` from `.env.example`.

- [ ] **Step 4: Replace old tests**

```bash
cd backend && git rm -q tests/test_hermes_chat_routing.py tests/test_hermes_chat_citations.py tests/test_hermes_chat_identity_context.py
grep -n "hermes_client" tests/test_admin_auth_gate.py
```
In `test_admin_auth_gate.py`, drop the `hermes_client` monkeypatch (line ~57) and any assertion about the chat route; keep its admin-key assertions. `grep -rn "hermes_client" app tests *.py` → only `app/mcp`/`trace*` mentions in comments, if any.

- [ ] **Step 5: Run** — `$TEST tests/test_ask_chat_route.py -v` → 4 PASS; full suite → no new failures.

- [ ] **Step 6: Commit (local)**

```bash
git add backend/app/main.py backend/tests/test_ask_chat_route.py backend/tests/test_admin_auth_gate.py backend/.env.example
git add -u backend/app/services backend/tests
git commit -m "feat: Ask chat runs course lookup + LangChain tutor; identity from login token; drop Hermes web path"
```

---

### Task 14: Rewire the video-player tutor (`/api/ai/tutor/stream`)

**Files:**
- Modify: `backend/app/main.py`, `backend/app/models.py` (TutorRequest comment only)
- Delete: `backend/app/services/tutor_service.py`
- Test: `backend/tests/test_player_tutor_route.py`

- [ ] **Step 1: Failing tests**

`backend/tests/test_player_tutor_route.py`:
```python
import json

import pytest
from fastapi.testclient import TestClient

from app.auth import current_student
from app.main import app
from app.services import chat_pipeline


def _events(text):
    return [json.loads(l[5:].strip()) for l in text.splitlines() if l.startswith("data:")]


@pytest.fixture
def client():
    app.dependency_overrides[current_student] = lambda: "token-uid"
    yield TestClient(app)
    app.dependency_overrides.clear()


def _body(course_id="react-perf", messages=None):
    return {"user_id": "spoofed", "course_id": course_id, "lecture": "4.1 - React.memo and useCallback",
            "messages": messages or [{"role": "user", "content": "first q"},
                                     {"role": "assistant", "content": "first a"},
                                     {"role": "user", "content": "what does this mean?"}]}


def test_player_turn_uses_lecture_scope_client_history_and_token_identity(client, monkeypatch):
    seen = {}

    async def fake_turn(req, model=None):
        seen["req"] = req
        yield {"type": "token", "value": "Think about re-renders."}
        yield {"type": "done"}

    monkeypatch.setattr(chat_pipeline, "chat_turn", fake_turn)
    r = client.post("/api/ai/tutor/stream", json=_body())
    req = seen["req"]
    assert req.student_id == "token-uid"
    assert req.question == "what does this mean?"
    assert req.history == [{"role": "user", "content": "first q"}, {"role": "assistant", "content": "first a"}]
    assert req.scope.course_slug == "react-perf" and req.scope.lecture_title.startswith("4.1")
    assert req.memory_slug == "react-perf"
    assert [e["type"] for e in _events(r.text)] == ["token", "done"]


def test_course_without_transcripts_is_accepted(client, monkeypatch):
    async def fake_turn(req, model=None):
        yield {"type": "done"}
    monkeypatch.setattr(chat_pipeline, "chat_turn", fake_turn)
    r = client.post("/api/ai/tutor/stream", json=_body(course_id="state-management"))
    assert _events(r.text)[-1]["type"] == "done"


def test_unknown_course_and_no_user_message_are_sse_errors(client):
    r = client.post("/api/ai/tutor/stream", json=_body(course_id="nope"))
    assert _events(r.text) == [{"type": "error", "message": "Unknown course"}]
    r = client.post("/api/ai/tutor/stream", json=_body(messages=[{"role": "assistant", "content": "hi"}]))
    assert _events(r.text)[0]["type"] == "error"
```

- [ ] **Step 2: Run** → FAIL.

- [ ] **Step 3: Rewrite the route** — replace `tutor_stream_endpoint` (`main.py:196-203`) with:
```python
@app.post("/api/ai/tutor/stream")
async def tutor_stream_endpoint(req: TutorRequest, student_id: str = Depends(current_student)):
    """The tutor inside the video player: same pipeline as the Ask page, scoped to
    the course + lecture being watched. History is the running message list the
    client sends; req.user_id is ignored (identity comes from the login token)."""
    headers = {"Cache-Control": "no-cache", "Connection": "keep-alive", "X-Accel-Buffering": "no"}

    async def one(event: dict):
        yield chat_pipeline.sse(event)

    if not catalog_service.by_slug(req.course_id):
        return StreamingResponse(one({"type": "error", "message": "Unknown course"}),
                                 media_type="text/event-stream", headers=headers)
    msgs = [{"role": m.role, "content": m.content} for m in req.messages if m.role in ("user", "assistant")]
    if not msgs or msgs[-1]["role"] != "user" or not msgs[-1]["content"].strip():
        return StreamingResponse(one({"type": "error", "message": "Ask a question first"}),
                                 media_type="text/event-stream", headers=headers)

    turn = chat_pipeline.TurnRequest(
        question=msgs[-1]["content"], student_id=student_id,
        scope=ChatScope(course_slug=req.course_id, lecture_title=req.lecture or None),
        history=msgs[:-1][-12:], memory_slug=req.course_id,
    )

    async def gen():
        async for event in chat_pipeline.chat_turn(turn):
            yield chat_pipeline.sse(event)

    return StreamingResponse(gen(), media_type="text/event-stream", headers=headers)
```
Add `catalog_service` to the services import. `git rm -q backend/app/services/tutor_service.py`; remove `tutor_service` from the `main.py` import. In `models.py` `TutorRequest`, add a comment on `user_id`: `# ignored by the server; identity comes from the login token`.

- [ ] **Step 4: Run** → 3 PASS; full suite → no new failures.

- [ ] **Step 5: Commit (local)** — `git add backend/app/main.py backend/app/models.py backend/tests/test_player_tutor_route.py && git add -u backend/app/services && git commit -m "feat: video-player tutor uses the shared course-aware pipeline"`

---

### Task 15: Frontend sends the login token

**Files:**
- Create: `frontend/src/lib/authHeaders.ts`
- Modify: `frontend/src/lib/ragApi.ts` (`askHermesStream`), `frontend/src/lib/learnApi.ts` (`streamTutor`)

- [ ] **Step 1: Helper**

`frontend/src/lib/authHeaders.ts`:
```ts
import { auth } from "./firebase";

// The backend verifies this Firebase ID token and takes the student id from it.
// getIdToken() refreshes an expired token automatically.
export async function authHeaders(): Promise<Record<string, string>> {
  const token = await auth.currentUser?.getIdToken();
  return token ? { Authorization: `Bearer ${token}` } : {};
}
```

- [ ] **Step 2: Use it** — in `askHermesStream` change the fetch headers to
`headers: { "Content-Type": "application/json", ...(await authHeaders()) },`
and the same in `streamTutor`. Add `import { authHeaders } from "./authHeaders";` to both files. Leave request bodies unchanged.

- [ ] **Step 3: Build** — `cd frontend && npm run build` → clean.

- [ ] **Step 4: Manual check (local)** — run backend (`cd backend && .venv/bin/uvicorn app.main:app --port 8080`) and frontend (`cd frontend && npm run dev` with `VITE_RAG_API_URL=http://localhost:8080`), sign in, ask on `/ask` "how do I publish an npm library", and ask a question in a lecture's tutor. Expected: both answer; the backend log shows no 401. Signed out (or DevTools → remove the Authorization header via "Edit and resend"): 401.

- [ ] **Step 5: Commit (local)** — `git add frontend/src/lib/authHeaders.ts frontend/src/lib/ragApi.ts frontend/src/lib/learnApi.ts && git commit -m "feat: chat clients send the Firebase ID token"`

---

### Task 16: Demo check + latency

**Files:**
- Create: `backend/scripts/demo_check.py`

- [ ] **Step 1: Write it**

`backend/scripts/demo_check.py`:
```python
"""Run before every demo: fixed questions through course_lookup (and optionally the
full tutor) for one student, printing case, top hits, and first-token latency.

  .venv/bin/python scripts/demo_check.py [student_id] [--full]
Uses backend/.env (real OpenAI + DATABASE_URL), in-process — no login token needed.
"""
import asyncio
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from dotenv import load_dotenv  # noqa: E402

load_dotenv(Path(__file__).resolve().parents[1] / ".env")

from app.services import chat_pipeline, enrollment_service  # noqa: E402
from app.services.course_lookup import ChatScope, LookupCase, course_lookup  # noqa: E402

DEMO_UID = "x94FcfXU7KRrobyOA4UHDukbRoC2"
QUESTIONS = [
    # (question, scope, expected case — None = depends on enrollment, printed only)
    ("how do I publish an npm library", ChatScope(), None),
    ("does React.memo need useCallback", ChatScope(), None),
    ("explain the event loop and microtasks", ChatScope(), None),
    ("how do I write a lexer for my own language", ChatScope(), LookupCase.NOT_ENROLLED_MATCH),
    ("how do I bake sourdough bread", ChatScope(), LookupCase.NO_MATCH),
    ("what am I weak at?", ChatScope(), None),
    ("what does this mean?", ChatScope("react-perf", "4.1 - React.memo and useCallback"), None),
]


async def main() -> None:
    uid = next((a for a in sys.argv[1:] if not a.startswith("--")), DEMO_UID)
    full = "--full" in sys.argv
    enrolled = await enrollment_service.get_enrolled_courses(uid)
    print(f"student {uid} enrolled in: {[c['title'] for c in enrolled] or 'NOTHING'}\n")
    failures = 0
    for q, scope, expected in QUESTIONS:
        lk = await course_lookup(q, uid, scope)
        ok = expected is None or lk.case == expected
        failures += not ok
        top = f"{lk.hits[0].course_title} → {lk.hits[0].title} ({lk.hits[0].score:.2f})" if lk.hits else "-"
        print(f"[{'ok' if ok else 'FAIL'}] {lk.case.value:20} {q[:45]:45} top: {top}")
        if full:
            t0, first, text = time.perf_counter(), None, []
            req = chat_pipeline.TurnRequest(question=q, student_id=uid, scope=scope, history=[],
                                            memory_slug=scope.course_slug or "all-courses")
            async for e in chat_pipeline.chat_turn(req):
                if e["type"] == "token":
                    first = first or time.perf_counter() - t0
                    text.append(e["value"])
            print(f"      first token {first or 0:.2f}s · {''.join(text)[:300]}\n")
    sys.exit(1 if failures else 0)


if __name__ == "__main__":
    asyncio.run(main())
```

Note: `--full` writes real turns to the demo account's memory (`record_turn`) — acceptable for the demo account; say so in the output header if you change the account.

- [ ] **Step 2: Run lookup-only** — `cd backend && .venv/bin/python scripts/demo_check.py`. Expected: no `FAIL`. Read the enrollment line: if the demo account is enrolled in **Build a Custom Library**, the npm question will be `enrolled_match` — fine, but for the demo story it should not be. If the account has **no** enrollments, stop and ask the user before writing any (that's production data; it belongs to the demo-data phase).

- [ ] **Step 3: Run full + record latency** — `.venv/bin/python scripts/demo_check.py --full`. Read every answer against the three-case rules: not-enrolled answers are short and end with the course pointer; no-match answers say they're not from a the01.dev course; enrolled answers cite a lecture + timestamp. Note first-token times for the Ask questions and the in-lecture question in the commit message (spec §8 asks for this). If an answer breaks its rule, fix `grounding_prompt.md`, re-run, repeat.

- [ ] **Step 4: Commit (local)** — `git add backend/scripts/demo_check.py backend/app/grounding/grounding_prompt.md && git commit -m "feat: demo_check script; prompt tuned on real answers (first token: Ask Xs, player Ys)"`

---

### Task 17: Final verification

- [ ] **Step 1:** Full backend suite + MCP suite → no new failures vs baseline.
- [ ] **Step 2:** `cd frontend && npm run build` → clean. `node frontend/scripts/export-catalog.mjs --check` → up to date.
- [ ] **Step 3:** `grep -rni "ollama\|mastra\|gepa\|read_soul\|hermes_client\|smalltalk" backend/app backend/*.py backend/tests frontend/src` → no output.
- [ ] **Step 4:** Re-read spec §2 goals and §5 testing list; tick each against a task above; report any gap to the user instead of shipping.

---

### Task 18: Deploy — only after the user says go

- [ ] **Step 1:** Ask the user for the go-ahead, listing what changes in production: new chat behaviour on both chats, chat requires the login token (old tabs without a refreshed frontend will get 401 until reload), Hermes no longer used by the web chat.
- [ ] **Step 2: Backend** — from `backend/` (Railway links per directory path — see the deploy-traps note): `railway status` shows project `the01dev-backend`, service `the01dev-backend`; then `railway up --service the01dev-backend`. Watch logs for startup (`catalog index`, no import errors). Check `/health` → `tutor_provider: langchain-agent`.
- [ ] **Step 3: Frontend** — Netlify local builds ignore site env vars: build with the production `VITE_*` values present in the local environment, then `netlify deploy --prod` from `frontend/`.
- [ ] **Step 4: Smoke test on production** — sign in on the live site; ask "how do I publish an npm library" on `/ask` (expect the course pointer + a Build a Custom Library card) and one question in a lecture's tutor. Run `.venv/bin/python scripts/demo_check.py` against prod data (`backend/.env` points at prod Postgres).
- [ ] **Step 5:** Tell the user the Hermes Railway service (`the01dev-hermes`) is idle until the Telegram phase and can be paused if it costs money — their call.
