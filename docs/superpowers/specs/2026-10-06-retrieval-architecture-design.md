# Retrieval Architecture v2 — Context-Rich Chunks, Hybrid Indexed Search, Reranked Coverage, Measured — Design

**Date:** 2026-10-06 · **Status:** approved in conversation ("build") · **Branch:** `in-course-tutor`

## 1. Why

The AI tutor is a medium for talking to course transcripts: find where something is taught,
cite it with a link, and otherwise answer from the model, personalised to the student. The
product will scale to thousands of courses. Today every failure gets a per-question fix
(new threshold, title signal, agreement rule…). Root cause, measured on "what is an IIFE?":
the search ranked lecture 6.5 #1–#5 correctly (best 0.424), then the fixed cutoff
`TRANSCRIPT_THRESHOLD = 0.54` discarded all five → "not covered". Absolute cosine scores
between a short question and a minute of rambling speech are not comparable across
questions, so no fixed cutoff can work. Secondary causes: chunks are embedded as raw speech
with no course/lecture context; no lexical search (acronyms like IIFE, `np`); search scans
every chunk in Python then filters (owned matches crowded out at scale); no evaluation set.

Goal: fix the architecture once — (1) right chunks are retrievable, (2) "is it covered?" is
decided by relevance judgement not cutoffs, (3) quality is a tracked number — so later
questions don't need individual tuning.

## 2. Target pipeline (per question)

1. **Query understanding** — one cheap LLM call (OpenAI `gpt-4.1-mini`, JSON) turns the raw
   question + recent history + current lecture into `{search_query, keywords[], intent}`
   with intent ∈ explain | navigate | account | off_topic. Skipped (raw question used) when
   the question is already self-contained and there is no history/lecture context to fold
   in, to save latency. `account` (my courses / my progress) bypasses retrieval.
2. **Scope** — computed in code, never by the model: player → the watched course; Ask →
   courses that are launched AND owned (user policy F1, unchanged).
3. **Hybrid retrieval inside the scope** — vector search over context-rich embeddings
   (top 30) + lexical full-text search over title/keywords/text (top 30), fused with
   Reciprocal Rank Fusion (k=60) → top 12 candidates, at most 3 per lecture.
4. **Rerank + coverage decision** — one LLM call (`gpt-4.1-mini`, JSON) grades each candidate
   against the question: `answers | partial | related | no`, with a one-line reason. Outcome:
   any `answers` → COVERED (cite best answers chunk); else any `partial` → PARTIAL (general
   answer + "touches on it in …"); else NOT_COVERED (general answer, no course named).
   Replaces TRANSCRIPT/RELATED/MOMENT/TITLE/AGREE thresholds for the covered decision.
   On reranker failure/timeout: fall back to fused rank with a conservative rule (top
   candidate must be in both vector and lexical top-5) and log it.
5. **Answer** — unchanged contract: grounding prompt + COURSE FACTS built from the graded
   chunks (only `answers`/`partial` ones cited), deep links, suggest/navigate events.
   `find_moment` uses the same pipeline with intent=navigate and jumps to the best
   `answers` chunk (or best `partial` if the student explicitly asked).

## 3. Chunk model (ingestion, once per course)

Each chunk keeps `chunk_id`, times, ids (so jumps/links/suggest keep working) and gains:
`chapter`, `course_num_id`, `launched`, `text_raw`, `text_clean` (readable; glossary-fixed),
`summary` (1 sentence), `keywords` (3–8), `questions` (2–3 likely student questions),
`embed_text` = header (course › chapter › lecture) + summary + key terms + last sentence of
the previous chunk (overlap without changing times) + `text_clean`, `embed_model`,
`content_hash` (sha256 of embed_text + model). Enrichment is produced offline by a script
(`backend/scripts/enrich_chunks.py`, gpt-4.1-mini, batched, cached, idempotent) and stored
in the repo (seed) so prod boot never calls the LLM. A per-course glossary
(`backend/data/glossary/<slug>.json`) fixes transcription errors in `text_clean` only
(`text_raw` is preserved).

## 4. Storage and indexes

Postgres (prod, Neon) `rag_chunks` gains columns: course_id, course_num_id, launched,
lecture_id, lecture_title, chapter, start_time, end_time, text_clean, embed_text, keywords,
embedding vector(1536) with HNSW (cosine), `search_tsv` tsvector (weighted: lecture title +
keywords A, summary B, text C) with GIN, embed_model, content_hash. Boot sync upserts
changed rows (by content_hash) in batches; never blocks on the LLM. Search runs in SQL with
`WHERE course_id = ANY($scope)`.

A `Retriever` interface with two backends sharing one contract:
- `PgRetriever` (prod): SQL vector + SQL full-text, scope-filtered.
- `MemoryRetriever` (tests, local, DATABASE_URL blank): same API, in-Python cosine over
  precomputed norms + BM25 over the same tokenised fields.
Contract tests run against both; the Pg tests run against a throwaway local Postgres +
pgvector cluster (Homebrew postgresql + pgvector, temp data dir, random port) and are
skipped when unavailable. Production data is never used in tests.

## 5. Evaluation (built first)

`backend/eval/retrieval/`:
- **Generated set**: for every lecture, 3 questions written from its transcript by
  gpt-4.1-mini (varied styles: direct, casual, keyword/acronym, "how do I…"), labelled with
  the gold lecture (+ gold chunk when specific); plus off-topic negatives (generic
  programming and non-programming) and cross-course negatives (asked in a course that
  doesn't teach it). Stored as JSON, committed, regenerated only on demand.
- **Hand set**: the known cases (IIFE, np publish demo sentence, ES modules, virtualize the
  table, React reconciliation in react-perf, …) pinned as regression rows.
- **Metrics** (`scripts/eval_retrieval.py`): lecture recall@1/@5, MRR, coverage decision
  accuracy (covered vs not), false-cite rate on negatives, navigate accuracy; per course and
  overall; latency p50/p95. Output a markdown report + JSON; compare runs.
- Baseline = current system, measured before any change. Each phase reports deltas.

## 6. Phases (each shippable, measured)

1. Eval harness + baseline numbers.
2. Chunk enrichment + context-rich embed_text + glossary; re-embed (in-memory eval).
3. Retriever interface + MemoryRetriever hybrid (vector+BM25+RRF+scope); wire Ask, player,
   find_moment, search tool through it.
4. Reranker + coverage decision; retire threshold constants from the decision path.
5. Query understanding (rewrite + intent).
6. PgRetriever + schema migration + HNSW/GIN + boot sync; prod switches to SQL search.
Targets (provisional, set after baseline): recall@5 ≥ 0.9, coverage accuracy ≥ 0.9,
false-cite ≤ 0.03, p95 retrieval+rerank ≤ 1.5 s.

## 7. Constraints

- User policies stay: player is course-first and never names another course; Ask cites only
  launched AND owned courses with deep links; explicit "take me to" auto-jumps, otherwise
  suggest links only.
- No new accounts/vendors: OpenAI (existing key) for embeddings, rewrite, rerank,
  enrichment, eval generation.
- Tests never touch the real DB/OpenAI (conftest guard). Prod data is never modified by
  tests or scripts except the normal boot sync.
- Budget: enrichment ≈ 1,329 chunks × 1 call (batched) ≈ < $1; eval generation < $1;
  per-question cost rises by ~2 small LLM calls (~$0.0005).

## 8. Out of scope

Changing transcripts' wording; real videos for other courses; Hermes/MCP channels (note:
MCP `search_course_content` stays cross-course until those channels get a policy).
