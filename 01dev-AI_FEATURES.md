# 0.1% DEV — AI Learning Layer

This document explains the AI features added to the 0.1% DEV platform, the tech behind them,
and how the code is organized. It's the companion to `01dev-SYSTEM_DESIGN.md` (the base
platform) and covers everything built on top: a course AI assistant, an adaptive learning
engine, a conversational tutor, and a journey-analytics dashboard.

---

## 1. Overview

The platform now has an **AI learning layer** that sits across three surfaces:

| Surface | What it offers |
|---|---|
| **Global** (`/ask`) | Streaming RAG assistant over all course transcripts |
| **Per course** (course details page) | AI Tutor · Study Guide · Adaptive Quiz · My Progress |
| **In the player** (while watching) | Floating, lecture-aware AI tutor |
| **Dashboard** (`/dashboard`) | Personal learning-journey analytics with AI-found patterns |

All AI features are **gated behind sign-in** (Google via Firebase) — signed-out users see a
glimpse (teaser) and a "Sign in to unlock" CTA.

**Design principle:** every feature *captures real signals → models the learner → adapts the
experience → reflects it back*. AI is placed at the **point of need** (while watching, while
practicing), not as a separate destination.

---

## 2. Tech stack

**Backend** (`/backend`, FastAPI + Python 3.11)
- **LLM:** OpenAI `gpt-4.1-mini` (generation + chat), `text-embedding-3-small` (embeddings)
- **Streaming:** Server-Sent Events (SSE) for the RAG assistant and the tutor
- **Storage:** Firestore via `firebase-admin` in production, with an **in-memory fallback**
  locally / when no credentials are present
- **Structured output:** OpenAI JSON mode (`response_format={"type":"json_object"}`) validated
  against Pydantic models

**Frontend** (`/frontend`, React 18 + TypeScript + Vite + TailwindCSS)
- **State:** Zustand (`userSession`)
- **Auth:** Firebase (Google OAuth); chat history persisted client-side in Firestore
- **Graph viz dep:** none currently (an interactive `d3-force` concept map was prototyped and removed)

**Deployment**
- Frontend → **Netlify** (auto-deploy on push to `main`)
- Backend → **Render** (⚠️ **manual deploy** — auto-deploy is off; trigger "Deploy latest commit")

---

## 3. Feature catalog

### Feature 1 — Streaming RAG assistant (`/ask`) — *live in production*
Token-by-token streamed answers grounded in indexed lecture transcripts, with source cards
(course · lecture · timestamp). Chat history persists: `localStorage` for guests, Firestore
`chatHistories/{uid}` for signed-in users. Falls back to non-streaming if the stream endpoint
is unavailable.

### Feature 2 — Study Guide (per course)
One GPT call turns a course's aggregated lecture transcripts into a structured guide:
5 key concepts, a 3-paragraph summary, 5 practice Q&As, 3 misconceptions. Cached in the store.

### Feature 3 — Question generation (per course) — *bounded growing bank*
The question bank is a **cache that grows to a cap**, not a fixed set. The first access generates
a batch of 12 MCQs (mix: 5 easy / 5 medium / 2 hard); `top_up()` then generates more batches in
the background — **deduped** against existing questions — until the bank reaches `MAX_BANK` (50).
Because a course has finite transcript content, dedupe makes the bank **plateau** naturally well
before the cap. Each MCQ has 4 options, a correct index, an explanation, a concept tag, a
difficulty, and its lecture. Options are **shuffled server-side**. Adaptive practice prefers
questions a given user hasn't **seen** (tracked across sessions) and only repeats as deliberate
review (spaced repetition); when a user runs low on unseen questions, the bank tops up automatically.

### Feature 4 — Quiz sessions
A completed practice run is saved (score, per-question result with concept/difficulty/time) with
a weakest-first concept breakdown. (The fixed-order quiz UI was later replaced by adaptive-only;
adaptive now records these sessions.)

### Feature 5 — Adaptive practice
Replaces fixed ordering with performance-aware selection:
- After each answer, update **persistent per-concept performance** (attempts / correct / accuracy / last-seen).
- Pick the next question by accuracy band: `<50% → easy`, `50–80% → medium`, `≥80% → hard or move on`.
- **Never repeat** a question in a session.
- **Spaced repetition:** resurface a concept unseen for 3+ days.
- **Prerequisite gating** (via the knowledge graph): don't serve a hard question until prerequisites ≥ 70%.
- Ends at all-concepts-mastered (≥80%) or 20 questions, with a mastery summary.
- Captures **real time-per-question** (powers dashboard time metrics).

### Feature 6 — Knowledge graph (per course)
GPT extracts concept descriptions + typed relationships (`prerequisite_of` / `part_of` /
`related_to`) over the course's quiz concept tags — including **cross-lecture prerequisites**.
Not shown directly to students; used internally to (a) enrich RAG answers with concept context,
and (b) gate hard questions in adaptive practice.

### Feature 7 — Recommendations
One GPT call reads quiz history + per-concept performance and returns 2–3 course recommendations
with reasons. Cached per user for 24h; invalidated when a new quiz completes.

### Course Insight — "My Progress" (per course)
Synthesizes **quiz performance + video rewatches + chat history** into a report: summary,
what you're doing well, where to improve, and concrete next steps.

### AI Tutor (conversational, with memory)
A Socratic per-course tutor that:
- knows the student's **weak concepts** (injected into the system prompt),
- is **grounded in the course transcripts** (RAG),
- **remembers** the conversation (client sends the running message list each turn),
- is **lecture-aware** in the player — vague questions ("what's happening here?") resolve to the
  lecture on screen.

Two entry points: a modal on the course page, and a **floating panel in the player** (video keeps
playing).

### Journey dashboard (`/dashboard`)
A personal analytics page (not a to-do list):
- **AI narrative** of the journey + a single **focus** suggestion,
- **metrics** (streak, avg score, concepts mastered, practice minutes, avg time/question),
- a **12-week activity heatmap** (GitHub-style),
- **strengths vs focus-areas**,
- **"patterns we noticed"** — non-obvious insights (e.g. *"~9s/question hints you're rushing"*,
  *"you only practice mornings"*).

---

## 4. Backend architecture

### Service layer (`backend/app/services/`)

| File | Responsibility |
|---|---|
| `store.py` | Document datastore. `FirestoreStore` (Admin SDK) in prod, `InMemoryStore` locally. Uniform `get/set/update/query/list_all/delete`. |
| `llm.py` | Shared `AsyncOpenAI` client + `generate_json()` structured-output helper. |
| `embeddings.py` | Text → vectors (OpenAI, or local hash fallback). |
| `vector_store.py` | In-memory vector store + cosine/BM25 search; course helpers (`get_course_transcript`, `get_course_meta`, `get_course_lectures`). |
| `rag_service.py` | `ask()` and `ask_stream()` (SSE); appends knowledge-graph context. |
| `answer_generator.py` | LLM answer generation, incl. streaming + local fallback. |
| `study_guide_service.py` | Feature 2 — generate/cache study guides. |
| `question_service.py` | Feature 3 — generate/cache 12-MCQ banks. |
| `quiz_service.py` | Feature 4 — save sessions + concept breakdown. |
| `adaptive_service.py` | Feature 5 — adaptive selection, per-concept perf, spaced repetition, records sessions. |
| `knowledge_graph_service.py` | Feature 6 — build/query the concept graph; `get_prerequisites()`. |
| `recommendation_service.py` | Feature 7 — course recommendations (24h cache). |
| `course_insight_service.py` | "My Progress" — per-course insight from multiple signals. |
| `tutor_service.py` | Conversational tutor stream (RAG + mastery-aware + lecture-aware). |
| `journey_service.py` | Dashboard analytics (metrics, heatmap, strengths/weak, AI insights). |

### API endpoints (`backend/app/main.py`)

```
# RAG assistant (Feature 1)
POST /api/ai/ask                       → grounded answer + sources
POST /api/ai/ask/stream                → SSE: sources, then token events, then done

# Catalog
GET  /api/courses                      → courses that have transcripts

# Study guide (Feature 2)
GET  /api/ai/study-guide/{course_id}            → status + guide
POST /api/ai/study-guide/{course_id}/generate   → kick off generation

# Questions (Feature 3)
GET  /api/ai/questions/{course_id}              → status + bank
POST /api/ai/questions/{course_id}/generate

# Quiz sessions (Feature 4)
POST /api/ai/quiz-session              → save a completed session
GET  /api/ai/quiz-sessions?user_id=    → list sessions

# Adaptive practice (Feature 5)
POST /api/ai/adaptive/start            → {session_id, first question}
POST /api/ai/adaptive/answer           → next question or {done, mastery summary}

# Knowledge graph (Feature 6, internal)
GET  /api/ai/knowledge-graph/{course_id}
POST /api/ai/knowledge-graph/{course_id}/build

# Recommendations (Feature 7)
GET  /api/ai/recommendations?user_id=

# Per-course insight
POST /api/ai/course-insight            → {summary, doing_well, improve, next_steps}

# Conversational tutor
POST /api/ai/tutor/stream              → SSE token stream (course + optional current lecture)

# Journey analytics
GET  /api/ai/journey?user_id=          → metrics, heatmap, strengths/weaknesses, AI insights
```

### Data model (store collections)

| Collection | Key | Holds |
|---|---|---|
| `study_guides` | `course_id` | generated study guide |
| `questions` | `course_id` | 12-MCQ bank |
| `quiz_sessions` | `session_id` (has `user_id`) | completed quiz/adaptive sessions |
| `concept_performance` | `{user_id}__{concept}` | attempts / correct / accuracy / last_seen |
| `adaptive_sessions` | `session_id` | in-progress adaptive state |
| `concepts` | `{course_id}::{name}` | concept nodes |
| `concept_relationships` | `{course_id}::rel{i}` | typed edges |
| `recommendations` | `user_id` | cached recommendations |
| `chatHistories` | `uid` | **client-side** Firestore chat history (`/ask`) |

### Key patterns
- **Graceful degradation** — no OpenAI key → keyword search + excerpt fallback; no Firebase key →
  in-memory store; tutor/insights degrade with a clear message rather than crashing.
- **SSE streaming** — `data: {json}\n\n` events with `type` of `sources` / `token` / `done` / `error`,
  consumed on the client via `fetch` + `ReadableStream`.
- **Background generation** — study guides, question banks, and graphs generate asynchronously and
  are polled by the client (`status: generating → ready`).
- **Per-course scoping** — generation aggregates a course's lecture transcripts (with `[Lecture: …]`
  headers) and keeps concept + lecture tags inside the artifacts.

---

## 5. Frontend architecture

### Pages (`frontend/src/pages/`)
- `AskPage.tsx` — streaming RAG chat; persisted history; sign-in gate.
- `LearnPage.tsx` — the journey-analytics **dashboard**; sign-in gate.
- `CourseDetailsPage.tsx` / `components/Tracks/Main.tsx` — hosts the **course AI companion**.
- `CoursePlayerPage.tsx` — hosts the **in-player tutor**; tracks lecture views (rewatch signal).

### Components (`frontend/src/components/`)
- `learn/CourseCompanion.tsx` — the per-course tool row (Tutor / Study Guide / Adaptive / My Progress) + modals; gated.
- `learn/StudyGuideModal.tsx`, `learn/AdaptiveModal.tsx`, `learn/InsightModal.tsx`, `learn/TutorModal.tsx` — tool UIs.
- `learn/PlayerTutor.tsx` — floating, lecture-aware tutor for the player.
- `common/FeatureGlimpse.tsx` — reusable signed-out teaser + sign-in CTA.

### Libraries (`frontend/src/lib/`)
- `ragApi.ts` — `askQuestion` + `askQuestionStream` (SSE).
- `learnApi.ts` — all AI endpoints (study guide, questions, quiz, adaptive, recommendations,
  insight, journey, tutor stream) + local signal readers (chat questions, rewatched lectures).
- `firebase.ts` — auth + Firestore chat-history helpers.

### Types (`frontend/src/types/`)
- `rag.ts` — chat + source-card types.
- `learn.ts` — course, study guide, questions, quiz, adaptive, insight, journey types.

---

## 6. Selected data flows

**Streaming answer (`/ask`)**
```
question → embed → vector search → SSE: sources event
         → gpt-4.1-mini (stream=True) → token events → done
client: fetch + ReadableStream → append tokens live → reveal sources on done
```

**Adaptive practice**
```
start → question bank (cached) → pick first by mastery band
answer → update concept_performance → pick next (band + prereq gate + no-repeat + spaced rep)
done  → record quiz_session → mastery summary
```

**Journey dashboard**
```
GET /api/ai/journey → read quiz_sessions + concept_performance
   → compute metrics, 12-week heatmap, strengths/weaknesses
   → one GPT call → narrative + non-obvious insights + focus
```

---

## 7. Deployment & operations

- **Push to `main`** → Netlify auto-deploys the frontend.
- **Render is manual** → after a backend change, trigger **Manual Deploy → Deploy latest commit**.
- Render free tier **cold-starts** (~25s) after 15 min idle.

### Environment variables
| Where | Var | Purpose |
|---|---|---|
| Render | `OPENAI_API_KEY` | LLM + embeddings |
| Render | `FIREBASE_SERVICE_ACCOUNT_JSON` | **(needed for persistence)** service-account JSON — without it the backend uses the in-memory store and AI data resets on restart |
| Render | `RAZORPAY_KEY_ID` / `RAZORPAY_KEY_SECRET` | payments |
| Netlify | `VITE_RAG_API_URL` | backend base URL (baked at build time) |

### Known limitations / next steps
- **Persistence:** add `FIREBASE_SERVICE_ACCOUNT_JSON` on Render so generated content and progress
  survive restarts (chat history already persists client-side).
- **Firestore rules** are currently open (`allow read, write: if true`) — tighten to per-uid.
- **Transcript coverage:** AI features work on the 4 transcript-backed courses
  (Build a Custom Library, JavaScript Deep Dive, Web APIs and Real-Time, React Performance Patterns).
  Adding real transcripts for more courses extends the AI to them automatically.
- **Signals** (video rewatches, chat questions) are device-local (`localStorage`) today; can move
  server-side once persistence is on.
