# Retrieval Architecture v2 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace per-question threshold tuning with one measured retrieval architecture: context-rich enriched chunks, scope-filtered hybrid search (vector + BM25/full-text, RRF), an LLM reranker that decides coverage, query understanding, and a Postgres backend with HNSW/GIN indexes, every phase scored by a retrieval eval.

**Architecture:** A new package `backend/app/retrieval/` owns everything below "a question and a scope": enrichment/`embed_text`, tokenizer + BM25, the `Retriever` protocol with `MemoryRetriever` (local/tests) and `PgRetriever` (prod), RRF fusion, the reranker + coverage decision, query understanding and the `graded_search` pipeline. `course_lookup`, `find_moment`, `search_course_content` and the `suggest` event become thin consumers of that pipeline; their external contracts (SSE events, deep links, `LookupCase` values in COURSE FACTS) stay, plus one new Ask case `ENROLLED_RELATED`. `backend/scripts/eval_retrieval.py` measures recall/MRR/coverage/false-cite/navigate/latency per course and overall, and every phase ends by recording its delta against the Phase 1 baseline.

**Tech Stack:** Python 3.12, FastAPI, asyncpg 0.31 + pgvector 0.8 (Neon in prod; Homebrew postgresql@17 + pgvector 0.8.2 for integration tests), OpenAI SDK 3.24 (`text-embedding-3-small`, `gpt-4.1-mini` via `app.services.llm.generate_json`), LangChain tutor agent, pytest + pytest-asyncio (`asyncio_mode = auto`). No new dependencies.

**Spec:** `docs/superpowers/specs/2026-10-06-retrieval-architecture-design.md` (approved, binding — read it fully before any task).

## Global Constraints

- Work in the worktree `/Users/swanandkadam/Desktop/01dev-React-hermes/.worktrees/lab-phase0-1` (branch `in-course-tutor`). Backend commands run from `backend/` in that worktree, using its own `backend/.venv` (`.venv/bin/pytest`, `.venv/bin/python`).
- Full backend suite: `bash backend/scripts/run_tests.sh` (must end `ALL PASSED`). Single file: `cd backend && .venv/bin/pytest tests/<file> -q`.
- **Real-model / OpenAI steps** (enrichment, eval generation, eval runs) always run from `backend/` with the key passed inline and the database off — never create `backend/.env` in the worktree:
  `env OPENAI_API_KEY="$(grep '^OPENAI_API_KEY=' /Users/swanandkadam/Desktop/01dev-React-hermes/backend/.env | cut -d= -f2- | tr -d '"')" DATABASE_URL= .venv/bin/python scripts/<script>.py ...`
- Network in this sandbox: small requests work, large uploads can break. Every embeddings call carries **≤ 100 inputs** (`EMBED_BATCH = 100`); LLM calls are per lecture / per question, never one giant request.
- **User policies (unchanged by this work):** the player tutor is course-first — it searches only the watched course and never names, recommends or links another course; the Ask page cites only courses that are **launched AND owned** by the student (F1), always with the `/course/<id>?chapter=<c>&sub=<s>&t=<seconds>` deep link; an explicit "take me to …" request auto-jumps (`navigate` event), anything else only offers links (`suggest` event).
- Scope is computed in code, never by a model: player → `[watched course slug]`; Ask → slugs of catalog courses with `launched == true` whose numeric id is in the student's enrollments. An empty scope means no search and no rerank call.
- **No new vendors or accounts:** OpenAI (existing key) for embeddings (`text-embedding-3-small`), query understanding, rerank, enrichment and eval generation (`gpt-4.1-mini`). No new Python packages (BM25 is pure Python; Postgres uses the existing asyncpg + pgvector).
- **Tests never touch the real DB or OpenAI.** `backend/tests/conftest.py` fails any test that reaches `db.get_pool`, `EmbeddingService._openai_embed`, `AsyncEmbeddings.create`, and (added in Task 1) `AsyncCompletions.create`. LLM calls in new modules go through a module-level `_complete(...)` function that tests monkeypatch. Postgres integration tests use only a throwaway local cluster (Task 20, `scripts/local_pg.py`) and skip when it is unavailable. Production data is never used by tests or scripts; the only prod write is the normal boot sync.
- Prod boot never calls the LLM: enrichment is produced offline (`scripts/enrich_chunks.py`) and committed under `backend/data/enrichment/`.
- Enrichment never changes `text` (= `text_raw`), `start_time`, `end_time`, `chunk_id`, `lecture_id` — jumps, links and `suggest` keep working.
- Pipeline numbers (spec §2): vector top 30 + lexical top 30 → RRF (k = 60) → top 12 candidates, at most 3 per lecture; rerank grades `answers | partial | related | no`; reranker failure/timeout → fallback "top fused candidate is in both vector top-5 and lexical top-5" (logged).
- Targets (spec §6, provisional, revisited after the baseline): recall@5 ≥ 0.9, coverage accuracy ≥ 0.9, false-cite ≤ 0.03, p95 retrieval+rerank ≤ 1.5 s.
- Out of scope (spec §8): the MCP server's `search_course_content` (`app/mcp/the01dev_tools.py` → `grounding.retrieve`) stays cross-course and is not rewired; it simply searches the enriched embeddings.
- Deploy is not part of this plan. Phases 2–3 change embeddings while the old thresholds still decide coverage; do not deploy the branch until Phase 4's eval delta is recorded (the user deploys from the terminal; never push to GitHub).
- **Commits:** `git add` the exact paths listed in the task — never `git add -A` or `git add .`. Every commit message ends with the trailer line `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>`. Never push.

## Review Focus

Inputs the spec implies but no phase's headline tests exercise, most likely to bite first. Each line is pinned by a test in the named task.

1. **Student owns no launched course** (the demo account: enrolled in 9 and 11, both unlaunched) asks a course question on the Ask page → `NO_MATCH`, no hits, and **no** embedding/search/rerank call at all (empty scope short-circuits). Pinned: `test_ask_empty_scope_never_searches_or_reranks` (Task 14).
2. **Reranker answers with junk** — malformed JSON, grades for ids it was never shown, an unknown grade word, or nothing before the timeout → only shown candidates can be cited; unknown ids/grades count as `no`; a reply with zero usable grades triggers the logged fallback, never a crash or an invented citation. Pinned: `test_parse_ignores_unknown_ids_and_grades`, `test_empty_or_invalid_reply_falls_back`, `test_timeout_falls_back` (Task 12).
3. **Acronym / code-token questions** ("IIFE?", "np", "useMemo vs memo") — the tokenizer keeps 2-letter and camelCase tokens, BM25 finds the lecture even when the speech spells it "iffy", and the "self-contained question" skip rule never treats a one-word acronym as needing a rewrite or drops it. Pinned: `test_glossary_fixes_text_clean_only` (Task 4), `test_tokenize_keeps_acronyms_and_code_tokens` (Task 8), `test_acronym_question_is_self_contained` (Task 17).
4. **Transcript edited after enrichment** (staging edit + `build_course_transcripts.py --merge`) → that chunk's stored enrichment no longer matches its text hash and is ignored (header + text only), never applied to the wrong words; unchanged chunks keep theirs; `--merge` output is byte-identical with or without enrichment files present. Pinned: `test_stale_enrichment_is_ignored`, `test_merge_never_carries_enrichment_fields` (Task 4).
5. **Boot sync after a re-merge that removed or changed chunks** → only rows whose `content_hash` changed are re-embedded (≤ 100 per call), rows with metadata-only changes (e.g. a course launched) are updated without an embeddings call, and rows for chunk ids that no longer exist are deleted so search can never return a moment the player can't open. Pinned: `test_sync_reembeds_only_changed_rows`, `test_sync_updates_metadata_without_embedding`, `test_sync_deletes_vanished_chunks` (Task 21).

---

## File Structure

| File | Action | Responsibility |
|---|---|---|
| `backend/app/retrieval/__init__.py` | Create | Package marker; re-exports nothing (import modules explicitly). |
| `backend/app/retrieval/text.py` | Create | `norm_title`, `tokenize` (acronym/camelCase aware), `last_sentence`. Shared by BM25, Pg tsvector text, enrichment. |
| `backend/app/retrieval/enrichment.py` | Create | Glossary loading + `clean_text`, enrichment file load/save (keyed by chunk_id + text hash), chapter lookup, `build_embed_text`, `content_hash`, `apply_enrichment(chunks)`. |
| `backend/app/retrieval/embed_cache.py` | Create | Opt-in on-disk embedding cache (JSONL keyed by `content_hash`) for local/eval runs; never used in prod or tests. |
| `backend/app/retrieval/bm25.py` | Create | Pure-Python BM25 index with field weighting by repetition and a scope (positions) filter. |
| `backend/app/retrieval/base.py` | Create | `Retriever` protocol, `Candidate` dataclass, `rrf_fuse` (RRF k=60, per-lecture cap, limit). |
| `backend/app/retrieval/memory.py` | Create | `MemoryRetriever`: cosine over `vector_store` embeddings + BM25, scope/lecture filtered. |
| `backend/app/retrieval/factory.py` | Create | `get_retriever()` / `set_retriever()` — Pg when `DATABASE_URL` is set and the pool works, else Memory. |
| `backend/app/retrieval/pipeline.py` | Create | `search()` (embed + both searches concurrently + fuse), `graded_search()` (understand ∥ raw retrieval, rerank, decide), `Outcome`, `RetrievalResult`, `ask_scope()`, `lecture_id_for()`. |
| `backend/app/retrieval/rerank.py` | Create | Reranker prompt, `_complete`, `parse_grades`, `rerank()` with timeout + fallback, `decide()`. |
| `backend/app/retrieval/understand.py` | Create | Query-understanding prompt, `needs_rewrite()` skip rule, `understand()` with timeout + fallback. |
| `backend/app/retrieval/pg.py` | Create | `PgRetriever` (SQL vector + SQL full-text, scope filtered). |
| `backend/app/retrieval/pg_schema.py` | Create | Idempotent migration SQL (`migrate`), `row_values`, `sync_chunks` (content_hash / row_hash boot sync, batched embeds, deletes), `load_embeddings`. |
| `backend/app/eval/retrieval_metrics.py` | Create | Pure metric functions: recall@k, MRR, coverage accuracy, false-cite, navigate accuracy, percentiles, per-course aggregation, markdown/JSON report, run comparison. |
| `backend/app/eval/retrieval_systems.py` | Create | Eval adapters: `LegacySystem` (Phases 1–3, current code paths) and `V2System` (Phase 4+, `graded_search` + `locate_moment`). |
| `backend/scripts/generate_eval_set.py` | Create | Resumable, cached generator of the per-lecture question set + hand-written negatives and cross-course rows. |
| `backend/scripts/eval_retrieval.py` | Create | CLI: run a system over the eval sets, write `reports/<label>.json` + `.md`, compare to a previous run. |
| `backend/scripts/local_pg.py` | Create | Start/stop a throwaway local Postgres 17 + pgvector cluster (temp dir, random port) for integration tests and the Phase 6 eval. |
| `backend/scripts/enrich_chunks.py` | Create | Resumable, cached, idempotent offline enrichment (summary, keywords, questions, glossary suggestions) per lecture batch. |
| `backend/eval/retrieval/hand_set.json` | Create | Pinned regression rows (IIFE, np, ES modules, virtualize the table, React reconciliation, negatives, follow-ups). |
| `backend/eval/retrieval/generated_set.json` | Create (generated) | ~627 generated positives + negatives; committed, regenerated only on demand. |
| `backend/eval/retrieval/reports/*.json, *.md` | Create (generated) | One report per phase (`phase1-baseline`, `phase2-enriched`, …). |
| `backend/data/enrichment/<slug>.json` | Create (generated) | Committed enrichment per course, keyed by chunk_id + text hash. |
| `backend/data/glossary/custom-library.json` | Create | Hand-reviewed transcription fixes for `text_clean`. |
| `backend/.gitignore` | Modify | Ignore `data/cache/` (eval-generation cache, embedding cache). |
| `backend/app/models.py` | Modify | `TranscriptChunk` gains optional enrichment fields (defaults keep every existing consumer working). |
| `backend/app/services/vector_store.py` | Modify | Apply enrichment at load; embed `embed_text`; opt-in embed cache; Phase 6: boot sync through `pg_schema`. |
| `backend/app/services/course_lookup.py` | Modify | Ask + player lookups through the pipeline; `Hit.grade/reason` replace `via_title`; threshold/title machinery removed; `ENROLLED_RELATED`. |
| `backend/app/services/tutor_agent.py` | Modify | `search_course_content` (both branches) and `_locate_moment` through the pipeline. |
| `backend/app/services/chat_pipeline.py` | Modify | Pass history to `course_lookup`; `suggest` from `grade == "answers"`. |
| `backend/app/services/db.py` | Modify | `_init_schema` calls `pg_schema.migrate`. |
| `backend/app/main.py` | Modify | Lifespan: drop `prewarm_titles`; build the retriever. |
| `backend/app/grounding/grounding_prompt.md` | Modify | `ENROLLED_RELATED` rule; graded STRONG/WEAK wording. |
| `backend/scripts/demo_check.py` | Modify | Print outcome/grades; expected cases unchanged. |
| `backend/scripts/calibrate_lookup.py`, `backend/scripts/calibrate_in_course.py` | Delete (Task 15) | Superseded by `eval_retrieval.py`; they call removed functions. |
| `backend/tests/conftest.py` | Modify | Block chat completions; session `local_pg` fixture (throwaway Postgres + pgvector). |
| Tests (new) | Create | `test_retrieval_metrics.py`, `test_eval_sets.py`, `test_eval_runner.py`, `test_retrieval_text.py`, `test_enrichment.py`, `test_enrich_chunks.py`, `test_bm25.py`, `test_rrf.py`, `test_retriever_contract.py`, `test_retrieval_pipeline.py`, `test_rerank.py`, `test_understand.py`, `test_pg_schema.py`. |
| Tests (updated) | Modify | `test_conftest_guard.py`, `test_vector_store_batch.py`, `test_vector_store_course_scope.py`, `test_course_lookup.py`, `test_tutor_agent.py`, `test_chat_pipeline.py`, `test_grounding_prompt.py`, `test_build_course_transcripts.py` (one added test). |

**Design decisions locked here (justified in the task that implements each):**

- `text` stays the raw transcript field (`text_raw` in the spec) — renaming it would touch Lab, quiz, study-guide and MCP consumers for no retrieval gain.
- Enrichment lives in `backend/data/enrichment/<slug>.json`, keyed `chunk_id → {text_sha, summary, keywords, questions}` and merged at load time (Task 4). `build_course_transcripts.py --merge` writes only `FIELDS`, so neither seed regeneration nor staging edits can drop it, and custom-library's real chunks are enriched the same way. A text-hash mismatch makes the entry inert instead of wrong.
- `text_clean` is deterministic (glossary regexes + whitespace), computed at load, never LLM-rewritten — no risk of the model changing what the instructor said, and glossary edits apply without re-enrichment.
- `launched`, `course_num_id` and `chapter` are derived from `catalog.json` at load/sync time, not stored in enrichment (launch status changes without re-ingestion). In Postgres a `row_hash` column detects such metadata changes without re-embedding.
- BM25 field weighting is by token repetition (title+keywords ×3, summary+questions ×2, text ×1), mirroring the Postgres `setweight` A/B/C tsvector; both backends index the **same Python tokens** (Postgres uses the `simple` config over pre-tokenized strings), so lexical behaviour matches.
- Fusion lives once in `base.rrf_fuse`; backends only implement `vector_search` and `lexical_search`. Contract tests run the same cases against both backends.
- Ask catalog hits remain only for in-scope courses that have **no** transcript chunks (`CATALOG_THRESHOLD` kept for that); for courses with transcripts the reranker alone decides, so a vague catalog description can no longer produce a citation the transcripts don't support.

---

# Phase 1 — Eval harness + baseline

### Task 1: Retrieval metrics module + completions leak guard

**Files:**
- Create: `backend/app/eval/retrieval_metrics.py`
- Modify: `backend/tests/conftest.py` (block `AsyncCompletions.create`)
- Modify: `backend/.gitignore` (add `data/cache/`)
- Test: `backend/tests/test_retrieval_metrics.py`, `backend/tests/test_conftest_guard.py`

**Interfaces:**
- Consumes: nothing.
- Produces (module `app.eval.retrieval_metrics`):
  - constants `COVERED = "covered"`, `PARTIAL = "partial"`, `NOT_COVERED = "not_covered"`
  - `@dataclass Row(id, question, scope_course, expect, gold_lecture_ids=[], gold_chunk_ids=[], style="direct", intent="explain", source="generated", history=[], lecture_title=None, navigate_phrase=None)` with `Row.from_dict(d) -> Row`
  - `@dataclass Prediction(row_id, mode, ranked_lectures, outcome, cited_lecture, moment_lecture=None, latency_ms=0.0, fallback=False, error=None)`
  - `summarize(rows: dict[str, Row], preds: list[Prediction]) -> dict`
  - `per_course(rows, preds) -> dict[str, dict]`
  - `percentile(values: list[float], p: float) -> Optional[float]`
  - `render_markdown(run: dict) -> str`, `compare(base: dict, new: dict) -> str`
  - Run dict shape (written by Task 3): `{"label", "system", "created", "modes": {"player"|"ask": {"overall": summary, "per_course": {slug: summary}}}, "predictions": [asdict(Prediction)]}`

- [ ] **Step 1: Write the failing metrics tests**

`backend/tests/test_retrieval_metrics.py`:

```python
from app.eval import retrieval_metrics as m
from app.eval.retrieval_metrics import COVERED, NOT_COVERED, PARTIAL, Prediction, Row


def _rows():
    return {r.id: r for r in [
        Row(id="p1", question="what is an IIFE", scope_course="custom-library", expect=COVERED,
            gold_lecture_ids=["custom-library-5-2"]),
        Row(id="p2", question="np publish", scope_course="custom-library", expect=COVERED,
            gold_lecture_ids=["custom-library-10-0"]),
        Row(id="n1", question="sourdough", scope_course="custom-library", expect=NOT_COVERED, style="off_topic"),
        Row(id="n2", question="kubernetes pods", scope_course="react-perf", expect=NOT_COVERED, style="off_topic"),
        Row(id="v1", question="take me to the np part", scope_course="custom-library", expect=COVERED,
            gold_lecture_ids=["custom-library-10-0"], intent="navigate", navigate_phrase="np"),
    ]}


def _preds():
    return [
        Prediction("p1", "player", ["custom-library-5-2", "custom-library-9-0"], COVERED, "custom-library-5-2",
                   latency_ms=100),
        Prediction("p2", "player", ["custom-library-7-0", "custom-library-10-0"], PARTIAL, "custom-library-7-0",
                   latency_ms=300),
        Prediction("n1", "player", ["custom-library-0-0"], NOT_COVERED, None, latency_ms=200),
        Prediction("n2", "player", ["react-perf-4-0"], PARTIAL, "react-perf-4-0", latency_ms=400),
        Prediction("v1", "player", [], NOT_COVERED, None, moment_lecture="custom-library-10-0", latency_ms=500),
    ]


def test_summary_metrics():
    s = m.summarize(_rows(), _preds())
    assert s["recall@1"] == 0.5          # p1 hit at 1, p2 only at 2
    assert s["recall@5"] == 1.0
    assert s["mrr"] == 0.75              # (1 + 1/2) / 2
    # explain rows: p1 ok (covered), p2 wrong (partial != covered), n1 ok, n2 ok (partial is not "covered")
    assert s["coverage_accuracy"] == 0.75
    assert s["false_cite_rate"] == 0.5   # n2 cited something (partial counts as a cite)
    assert s["cite_accuracy"] == 1.0     # only p1 is covered, and it cites gold
    assert s["partial_rate_pos"] == 0.5
    assert s["navigate_accuracy"] == 1.0
    assert s["counts"] == {"positives": 2, "negatives": 2, "navigate": 1, "errors": 0}
    assert s["latency_p50_ms"] == 300 and s["latency_p95_ms"] == 500


def test_errors_are_counted_and_excluded():
    preds = _preds()
    preds[0] = Prediction("p1", "player", [], NOT_COVERED, None, error="TimeoutError()")
    s = m.summarize(_rows(), preds)
    assert s["counts"]["errors"] == 1 and s["counts"]["positives"] == 1


def test_empty_groups_give_none_not_zero_division():
    rows = {"n1": _rows()["n1"]}
    s = m.summarize(rows, [_preds()[2]])
    assert s["recall@5"] is None and s["navigate_accuracy"] is None and s["false_cite_rate"] == 0.0


def test_percentile_nearest_rank():
    assert m.percentile([], 95) is None
    assert m.percentile([5.0], 95) == 5.0
    assert m.percentile([float(i) for i in range(1, 101)], 95) == 95.0
    assert m.percentile([float(i) for i in range(1, 101)], 50) == 50.0


def test_per_course_groups_by_scope_course():
    pc = m.per_course(_rows(), _preds())
    assert set(pc) == {"custom-library", "react-perf"}
    assert pc["react-perf"]["false_cite_rate"] == 1.0


def test_markdown_and_compare():
    rows, preds = _rows(), _preds()
    run = {"label": "phase1-baseline", "system": "legacy", "created": "2026-10-06T00:00:00",
           "modes": {"player": {"overall": m.summarize(rows, preds), "per_course": m.per_course(rows, preds)}},
           "predictions": []}
    md = m.render_markdown(run)
    assert "phase1-baseline" in md and "| recall@5 |" in md and "custom-library" in md
    better = {**run, "label": "phase2", "modes": {"player": {"overall": {**run["modes"]["player"]["overall"],
                                                                        "recall@1": 1.0}, "per_course": {}}}}
    diff = m.compare(run, better)
    assert "| recall@1 | 0.500 | 1.000 | +0.500 |" in diff
```

Append to `backend/tests/test_conftest_guard.py`:

```python
@pytest.mark.asyncio
async def test_guard_blocks_direct_chat_completions_create(_no_real_db_or_embeddings):
    client = AsyncOpenAI(api_key="sk-test")
    with pytest.raises(AssertionError, match="real OpenAI chat completions"):
        await client.chat.completions.create(model="gpt-4.1-mini", messages=[{"role": "user", "content": "x"}])
    leaks = _no_real_db_or_embeddings
    assert len(leaks) == 1
    leaks.clear()
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `cd backend && .venv/bin/pytest tests/test_retrieval_metrics.py tests/test_conftest_guard.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'app.eval.retrieval_metrics'`, and the guard test fails with a network/auth error instead of the AssertionError.

- [ ] **Step 3: Implement the metrics module**

`backend/app/eval/retrieval_metrics.py`:

```python
"""Retrieval-eval metrics — pure functions, no I/O and no models (spec §5).

A Row is one labelled question; a Prediction is what a system did with it in one mode
("player" = scope is the row's course, "ask" = scope is every course). Navigate rows are scored
only by navigate accuracy; explain rows by recall/MRR (positives), coverage accuracy (all) and
false-cite rate (negatives). A PARTIAL outcome names a lecture, so on a negative it is a false cite.
"""
import math
from dataclasses import dataclass, field
from typing import Iterable, Optional

COVERED, PARTIAL, NOT_COVERED = "covered", "partial", "not_covered"
METRIC_KEYS = ["recall@1", "recall@5", "mrr", "coverage_accuracy", "cite_accuracy", "partial_rate_pos",
               "false_cite_rate", "navigate_accuracy", "fallback_rate", "latency_p50_ms", "latency_p95_ms"]


@dataclass
class Row:
    id: str
    question: str
    scope_course: str
    expect: str                                   # COVERED | NOT_COVERED
    gold_lecture_ids: list[str] = field(default_factory=list)
    gold_chunk_ids: list[str] = field(default_factory=list)
    style: str = "direct"                         # direct|casual|keyword|how_do_i|off_topic|cross_course|follow_up
    intent: str = "explain"                       # explain | navigate
    source: str = "generated"                     # generated | hand
    history: list[dict] = field(default_factory=list)
    lecture_title: Optional[str] = None
    navigate_phrase: Optional[str] = None

    @classmethod
    def from_dict(cls, d: dict) -> "Row":
        return cls(**{k: d[k] for k in cls.__dataclass_fields__ if k in d})


@dataclass
class Prediction:
    row_id: str
    mode: str                                     # "player" | "ask"
    ranked_lectures: list[str]                    # distinct lecture ids, best first
    outcome: str                                  # COVERED | PARTIAL | NOT_COVERED
    cited_lecture: Optional[str]                  # lecture of the cited chunk, None when nothing cited
    moment_lecture: Optional[str] = None          # navigate rows: where the player would jump
    latency_ms: float = 0.0
    fallback: bool = False                        # reranker fell back to the fused rule
    error: Optional[str] = None


def _mean(values: Iterable) -> Optional[float]:
    vals = [float(v) for v in values]
    return round(sum(vals) / len(vals), 4) if vals else None


def _rr(ranked: list[str], gold: list[str]) -> float:
    for i, lid in enumerate(ranked, 1):
        if lid in gold:
            return 1.0 / i
    return 0.0


def percentile(values: list[float], p: float) -> Optional[float]:
    """Nearest-rank percentile; None for no values."""
    if not values:
        return None
    s = sorted(values)
    return s[max(0, math.ceil(p / 100 * len(s)) - 1)]


def summarize(rows: dict[str, Row], preds: list[Prediction]) -> dict:
    ok = [(rows[p.row_id], p) for p in preds if p.error is None]
    explain = [(r, p) for r, p in ok if r.intent == "explain"]
    pos = [(r, p) for r, p in explain if r.expect == COVERED and r.gold_lecture_ids]
    neg = [(r, p) for r, p in explain if r.expect == NOT_COVERED]
    nav = [(r, p) for r, p in ok if r.intent == "navigate"]
    lat = [p.latency_ms for _, p in ok]
    return {
        "recall@1": _mean(bool(set(p.ranked_lectures[:1]) & set(r.gold_lecture_ids)) for r, p in pos),
        "recall@5": _mean(bool(set(p.ranked_lectures[:5]) & set(r.gold_lecture_ids)) for r, p in pos),
        "mrr": _mean(_rr(p.ranked_lectures, r.gold_lecture_ids) for r, p in pos),
        "coverage_accuracy": _mean((p.outcome == COVERED) == (r.expect == COVERED) for r, p in explain),
        "cite_accuracy": _mean(p.cited_lecture in r.gold_lecture_ids for r, p in pos if p.outcome == COVERED),
        "partial_rate_pos": _mean(p.outcome == PARTIAL for _, p in pos),
        "false_cite_rate": _mean(p.outcome in (COVERED, PARTIAL) for _, p in neg),
        "navigate_accuracy": _mean(p.moment_lecture in r.gold_lecture_ids for r, p in nav),
        "fallback_rate": _mean(p.fallback for _, p in ok),
        "latency_p50_ms": percentile(lat, 50),
        "latency_p95_ms": percentile(lat, 95),
        "counts": {"positives": len(pos), "negatives": len(neg), "navigate": len(nav),
                   "errors": sum(p.error is not None for p in preds)},
    }


def per_course(rows: dict[str, Row], preds: list[Prediction]) -> dict[str, dict]:
    groups: dict[str, list[Prediction]] = {}
    for p in preds:
        groups.setdefault(rows[p.row_id].scope_course, []).append(p)
    return {slug: summarize(rows, ps) for slug, ps in sorted(groups.items())}


def _fmt(v) -> str:
    return "—" if v is None else (f"{v:.0f}" if isinstance(v, float) and v > 1.0 else f"{v:.3f}")


def render_markdown(run: dict) -> str:
    out = [f"# Retrieval eval — {run['label']}", "",
           f"System: `{run['system']}` · created {run['created']}", ""]
    for mode, data in run["modes"].items():
        o = data["overall"]
        out += [f"## Mode: {mode}", "", f"Counts: {o['counts']}", "", "| metric | value |", "|---|---|"]
        out += [f"| {k} | {_fmt(o.get(k))} |" for k in METRIC_KEYS]
        if data.get("per_course"):
            keys = ["recall@1", "recall@5", "mrr", "coverage_accuracy", "false_cite_rate", "navigate_accuracy"]
            out += ["", "| course | " + " | ".join(keys) + " |", "|---" * (len(keys) + 1) + "|"]
            for slug, s in data["per_course"].items():
                out.append(f"| {slug} | " + " | ".join(_fmt(s.get(k)) for k in keys) + " |")
        out.append("")
    return "\n".join(out)


def compare(base: dict, new: dict) -> str:
    out = [f"# Delta: {base['label']} → {new['label']}", ""]
    for mode in new["modes"]:
        if mode not in base["modes"]:
            continue
        b, n = base["modes"][mode]["overall"], new["modes"][mode]["overall"]
        out += [f"## Mode: {mode}", "", f"| metric | {base['label']} | {new['label']} | delta |", "|---|---|---|---|"]
        for k in METRIC_KEYS:
            bv, nv = b.get(k), n.get(k)
            delta = "—" if bv is None or nv is None else f"{nv - bv:+.3f}"
            fmt = (lambda v: "—" if v is None else f"{v:.3f}")
            out.append(f"| {k} | {fmt(bv)} | {fmt(nv)} | {delta} |")
        out.append("")
    return "\n".join(out)
```

Add the completions guard to `backend/tests/conftest.py` (inside `_no_real_db_or_embeddings`, next to the other two guards):

```python
    async def _blocked_chat_completions(self, *a, **k):
        leaks.append("openai AsyncCompletions.create (real OpenAI chat completions, e.g. rerank/understand)")
        raise AssertionError("test reached the real OpenAI chat completions: stub the module's _complete")

    monkeypatch.setattr("openai.resources.chat.completions.completions.AsyncCompletions.create",
                        _blocked_chat_completions)
```

and update the module docstring's first line to "Leak guard: no test may reach the real database or the real OpenAI embeddings/chat completions."

Append to `backend/.gitignore`:

```
# local caches: eval-generation responses, on-disk embeddings (regenerable, large)
data/cache/
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `cd backend && .venv/bin/pytest tests/test_retrieval_metrics.py tests/test_conftest_guard.py -q`
Expected: PASS (all).

Then the whole suite, to prove the new guard breaks nothing: `bash backend/scripts/run_tests.sh` → `ALL PASSED`.

- [ ] **Step 5: Commit**

```bash
git add backend/app/eval/retrieval_metrics.py backend/tests/test_retrieval_metrics.py backend/tests/conftest.py backend/tests/test_conftest_guard.py backend/.gitignore
git commit -m "feat(eval): retrieval metrics (recall/MRR/coverage/false-cite/navigate/latency); guard chat completions in tests

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

### Task 2: Eval sets — hand set + resumable generator

**Files:**
- Create: `backend/eval/retrieval/hand_set.json`
- Create: `backend/scripts/generate_eval_set.py`
- Create (generated, Step 6): `backend/eval/retrieval/generated_set.json`
- Test: `backend/tests/test_eval_sets.py`

**Interfaces:**
- Consumes: `app.eval.retrieval_metrics.Row` (Task 1) — every row dict written here must load with `Row.from_dict`.
- Produces (module `scripts.generate_eval_set`, importable because `pytest.ini` sets `pythonpath = .`):
  - `STYLES = ["direct", "casual", "keyword", "how_do_i"]`, `styles_for(i: int) -> list[str]`
  - `lectures_from_seed(chunks: list[dict]) -> list[dict]` → `[{"lecture_id", "course_id", "course_title", "lecture_title", "chunks": [{"chunk_id", "text"}]}]` in seed order
  - `lecture_sha(lecture: dict) -> str`
  - `validate_generation(raw: Optional[dict], chunk_ids: set[str], styles: list[str]) -> Optional[dict]`
  - `rows_for_lecture(lecture: dict, i: int, gen: dict) -> list[dict]`
  - `negative_rows(course_slugs: list[str]) -> list[dict]`, `cross_course_rows(rows: list[dict]) -> list[dict]`, `golden_rows(chunks: list[dict]) -> list[dict]`
  - `async build_set(lectures, cache_dir: Path, *, limit=None, force=False, concurrency=4) -> list[dict]`
  - module-level `async def _complete(system: str, user: str) -> Optional[dict]` (tests monkeypatch it)
  - files: `backend/eval/retrieval/generated_set.json` (list of row dicts), `backend/eval/retrieval/hand_set.json` (list of row dicts)

- [ ] **Step 1: Write the hand set**

`backend/eval/retrieval/hand_set.json` — pinned regression rows (gold lecture ids checked against the seed on 2026-10-06):

```json
[
  {"id": "hand-iife", "question": "what is an IIFE?", "scope_course": "custom-library", "expect": "covered",
   "gold_lecture_ids": ["custom-library-5-2"], "style": "keyword", "source": "hand"},
  {"id": "hand-np-publish", "question": "how do I publish my package with np?", "scope_course": "custom-library",
   "expect": "covered", "gold_lecture_ids": ["custom-library-10-0"], "style": "how_do_i", "source": "hand"},
  {"id": "hand-np-what", "question": "what does the np package do?", "scope_course": "custom-library",
   "expect": "covered", "gold_lecture_ids": ["custom-library-10-0"], "style": "direct", "source": "hand"},
  {"id": "hand-es-modules", "question": "what are ES modules?", "scope_course": "custom-library", "expect": "covered",
   "gold_lecture_ids": ["custom-library-9-0"], "style": "direct", "source": "hand"},
  {"id": "hand-npm-link", "question": "how do I test my library locally without publishing it?",
   "scope_course": "custom-library", "expect": "covered",
   "gold_lecture_ids": ["custom-library-7-0", "custom-library-7-1"], "style": "how_do_i", "source": "hand"},
  {"id": "hand-react-reconciliation", "question": "how does React reconciliation work?", "scope_course": "react-perf",
   "expect": "covered", "gold_lecture_ids": ["react-perf-0-1", "react-perf-0-2"], "style": "direct", "source": "hand"},
  {"id": "hand-undo-redo", "question": "how do I implement undo and redo?", "scope_course": "state-management",
   "expect": "covered", "gold_lecture_ids": ["state-management-6-1"], "style": "how_do_i", "source": "hand"},
  {"id": "hand-tokenizer-loop", "question": "how does the tokenizer loop work?", "scope_course": "programming-language",
   "expect": "covered", "gold_lecture_ids": ["programming-language-5-1", "programming-language-7-2"],
   "style": "keyword", "source": "hand"},
  {"id": "hand-nav-virtualize", "question": "take me to where he virtualizes the table", "scope_course": "react-perf",
   "expect": "covered", "gold_lecture_ids": ["react-perf-4-0"], "intent": "navigate",
   "navigate_phrase": "virtualize the table", "style": "navigate", "source": "hand"},
  {"id": "hand-nav-np", "question": "take me to the npm publish command", "scope_course": "custom-library",
   "expect": "covered", "gold_lecture_ids": ["custom-library-10-0"], "intent": "navigate",
   "navigate_phrase": "npm publish command", "style": "navigate", "source": "hand"},
  {"id": "hand-nav-es-modules", "question": "jump to the part about ES modules", "scope_course": "custom-library",
   "expect": "covered", "gold_lecture_ids": ["custom-library-9-0"], "intent": "navigate",
   "navigate_phrase": "ES modules", "style": "navigate", "source": "hand"},
  {"id": "hand-neg-reconciliation-in-lib", "question": "how does React reconciliation work?",
   "scope_course": "custom-library", "expect": "not_covered", "style": "cross_course", "source": "hand"},
  {"id": "hand-neg-event-loop-in-lib", "question": "explain the event loop and microtasks",
   "scope_course": "custom-library", "expect": "not_covered", "style": "cross_course", "source": "hand"},
  {"id": "hand-neg-sql-join", "question": "how does a SQL join work?", "scope_course": "custom-library",
   "expect": "not_covered", "style": "off_topic", "source": "hand"},
  {"id": "hand-neg-k8s", "question": "what are Kubernetes pods?", "scope_course": "react-perf",
   "expect": "not_covered", "style": "off_topic", "source": "hand"},
  {"id": "hand-neg-sourdough", "question": "how do I bake sourdough bread?", "scope_course": "custom-library",
   "expect": "not_covered", "style": "off_topic", "source": "hand"},
  {"id": "hand-followup-np", "question": "ok how do I use it to publish?", "scope_course": "custom-library",
   "expect": "covered", "gold_lecture_ids": ["custom-library-10-0"], "style": "follow_up", "source": "hand",
   "history": [{"role": "user", "content": "what is the np package?"},
               {"role": "assistant", "content": "np is a small tool that runs the checks and steps for publishing an npm package."}]},
  {"id": "hand-followup-lecture", "question": "why does wrapping it like this create its own scope?",
   "scope_course": "custom-library", "expect": "covered", "gold_lecture_ids": ["custom-library-5-2"],
   "style": "follow_up", "source": "hand", "lecture_title": "6.5 - IIFE, To The Rescue"}
]
```

The 14 rows of the existing `backend/app/eval/golden_set.json` are reused (not copied) by `golden_rows()` below: each becomes a hand row whose gold lectures are its gold chunks' lectures.

- [ ] **Step 2: Write the failing generator tests**

`backend/tests/test_eval_sets.py`:

```python
import json
from pathlib import Path

import pytest

from app.eval.retrieval_metrics import Row
from scripts import generate_eval_set as g

BACKEND = Path(__file__).resolve().parents[1]


def _seed():
    return [
        {"chunk_id": "c-0-0-0", "course_id": "c", "course_title": "C", "lecture_id": "c-0-0",
         "lecture_title": "1.1 - IIFE", "text": "an iffy wraps code", "start_time": 0, "end_time": 50},
        {"chunk_id": "c-0-0-1", "course_id": "c", "course_title": "C", "lecture_id": "c-0-0",
         "lecture_title": "1.1 - IIFE", "text": "it runs at once", "start_time": 50, "end_time": 100},
        {"chunk_id": "d-0-0-0", "course_id": "d", "course_title": "D", "lecture_id": "d-0-0",
         "lecture_title": "1.1 - Tokens", "text": "a token is", "start_time": 0, "end_time": 50},
    ]


def _good(styles):
    return {"questions": [{"style": s, "question": f"q {s}?", "gold_chunk_id": "c-0-0-0"} for s in styles],
            "navigate_phrase": "the IIFE pattern"}


def test_styles_rotate_and_hand_set_loads():
    assert g.styles_for(0) == ["direct", "casual", "keyword"]
    assert g.styles_for(1) == ["casual", "keyword", "how_do_i"]
    rows = json.loads((BACKEND / "eval/retrieval/hand_set.json").read_text())
    assert len({r["id"] for r in rows}) == len(rows)
    for r in rows:
        Row.from_dict(r)  # every field is a Row field


def test_validate_relabels_styles_and_drops_unknown_gold_chunks():
    raw = _good(["x", "y", "z"])
    raw["questions"][1]["gold_chunk_id"] = "not-a-chunk"
    out = g.validate_generation(raw, {"c-0-0-0", "c-0-0-1"}, ["direct", "casual", "keyword"])
    assert [q["style"] for q in out["questions"]] == ["direct", "casual", "keyword"]
    assert out["questions"][1]["gold_chunk_id"] is None


@pytest.mark.parametrize("raw", [
    None, {}, {"questions": []}, {"questions": [{"question": "a"}] * 2, "navigate_phrase": "x"},
    {"questions": [{"question": "what does the lecture say?"}] * 3, "navigate_phrase": "x"},
    {"questions": [{"question": "a?"}] * 3, "navigate_phrase": ""},
])
def test_validate_rejects_bad_generations(raw):
    assert g.validate_generation(raw, {"c-0-0-0"}, ["direct", "casual", "keyword"]) is None


def test_rows_for_lecture_has_three_explain_rows_and_one_navigate_row():
    lec = g.lectures_from_seed(_seed())[0]
    rows = g.rows_for_lecture(lec, 0, g.validate_generation(_good(g.styles_for(0)), {"c-0-0-0", "c-0-0-1"},
                                                            g.styles_for(0)))
    assert [r["intent"] for r in rows] == ["explain", "explain", "explain", "navigate"]
    assert all(r["gold_lecture_ids"] == ["c-0-0"] and r["scope_course"] == "c" for r in rows)
    assert rows[0]["gold_chunk_ids"] == ["c-0-0-0"]
    assert rows[3]["navigate_phrase"] == "the IIFE pattern" and "the IIFE pattern" in rows[3]["question"]


async def test_build_set_is_resumable_and_uses_the_cache(tmp_path, monkeypatch):
    calls = []

    async def fake_complete(system, user):
        calls.append(user)
        styles = [s for s in g.STYLES if s in user.split("Styles, in order:")[1].split("\n")[0]]
        return _good(styles)

    monkeypatch.setattr(g, "_complete", fake_complete)
    lectures = g.lectures_from_seed(_seed())
    first = await g.build_set(lectures, tmp_path, limit=1)
    assert len(calls) == 1 and len(first) == 4           # --limit 1: one lecture generated
    second = await g.build_set(lectures, tmp_path)
    assert len(calls) == 2                               # only the missing lecture was requested
    assert second[:4] == first and len(second) == 8
    again = await g.build_set(lectures, tmp_path)
    assert len(calls) == 2 and again == second          # idempotent: everything cached


async def test_changed_lecture_text_invalidates_its_cache(tmp_path, monkeypatch):
    calls = []

    async def fake_complete(system, user):
        calls.append(user)
        return _good(["direct", "casual", "keyword"])

    monkeypatch.setattr(g, "_complete", fake_complete)
    seed = _seed()[:2]
    await g.build_set(g.lectures_from_seed(seed), tmp_path)
    seed[1]["text"] = "it runs immediately"
    await g.build_set(g.lectures_from_seed(seed), tmp_path)
    assert len(calls) == 2


def test_negatives_cross_course_and_golden_rows():
    negs = g.negative_rows(["custom-library", "react-perf"])
    assert negs and all(r["expect"] == "not_covered" and r["style"] == "off_topic" for r in negs)
    assert {r["scope_course"] for r in negs} == {"custom-library", "react-perf"}
    gen = [{"id": "gen-react-perf-0-0-q1", "question": "what triggers a re-render", "scope_course": "react-perf",
            "expect": "covered", "gold_lecture_ids": ["react-perf-0-0"], "style": "keyword", "intent": "explain"}]
    cross = g.cross_course_rows(gen)
    assert cross == [{"id": "cross-react-perf-0-0-q1-in-programming-language", "question": "what triggers a re-render",
                      "scope_course": "programming-language", "expect": "not_covered", "gold_lecture_ids": [],
                      "style": "cross_course", "intent": "explain", "source": "generated"}]
    seed = json.loads((BACKEND / "app/data/seed_transcripts.json").read_text())
    golden = g.golden_rows(seed)
    assert len(golden) == 14 and golden[0]["gold_lecture_ids"] == ["custom-library-7-0"]
```

- [ ] **Step 3: Run the tests to verify they fail**

Run: `cd backend && .venv/bin/pytest tests/test_eval_sets.py -q`
Expected: FAIL — `ImportError: cannot import name 'generate_eval_set' from 'scripts'` (and `hand_set.json` loads once Step 1 is done).

- [ ] **Step 4: Implement the generator**

`backend/scripts/generate_eval_set.py`:

```python
"""Generate the retrieval eval set (spec §5): 3 questions per lecture (rotating styles) + one
navigate request, written by gpt-4.1-mini from the lecture's transcript; plus hand-written off-topic
negatives and cross-course negatives. Resumable and cached per lecture under
backend/data/cache/eval_gen/<lecture_id>.json (keyed by a hash of the lecture's text), idempotent,
and --limit N generates at most N new lectures (trial runs).

Run from backend/ with the key inline and the database off:
  env OPENAI_API_KEY=... DATABASE_URL= .venv/bin/python scripts/generate_eval_set.py [--limit N] [--only slug] [--force]
"""
import argparse
import asyncio
import hashlib
import json
import os
import re
import sys
from pathlib import Path
from typing import Optional

BACKEND = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND))

SEED = BACKEND / "app" / "data" / "seed_transcripts.json"
GOLDEN = BACKEND / "app" / "eval" / "golden_set.json"
CACHE_DIR = BACKEND / "data" / "cache" / "eval_gen"
OUT = BACKEND / "eval" / "retrieval" / "generated_set.json"
STYLES = ["direct", "casual", "keyword", "how_do_i"]
NAV_TEMPLATES = ["take me to the part about {p}", "jump to where {p} is explained",
                 "show me where the video covers {p}"]
MAX_PROMPT_CHARS = 12000
BANNED = re.compile(r"\b(lecture|video|instructor|this course|chapter)\b", re.I)
CROSS_PAIRS = [("programming-language", "react-perf"), ("react-perf", "programming-language"),
               ("real-time", "custom-library"), ("state-management", "js-engine"),
               ("web-apis", "programming-language")]
CROSS_PER_PAIR = 8
OFF_TOPIC = [  # not taught anywhere in the library (JS/web/React/compilers/npm): other stacks + non-programming
    "how do I write a SQL join across three tables?", "what is the Rust borrow checker?",
    "how do Python decorators work?", "what are Kubernetes pods?", "how do I set up a Django model?",
    "what is a Go goroutine?", "how do I configure nginx as a reverse proxy?", "what is a Docker volume?",
    "how does garbage collection work in Java?", "how do I train a linear regression model?",
    "what is the CAP theorem?", "how do I write a bash for loop?", "what is a Terraform module?",
    "how do Swift optionals work?", "how do I index a MongoDB collection?", "what is a Kafka consumer group?",
    "how do I use pandas groupby?", "what is a C++ virtual destructor?", "how do I write a Spring Boot controller?",
    "what does git rebase do?",
    "how do I bake sourdough bread?", "what is the capital of Australia?", "how do I improve my running pace?",
    "what causes the seasons on Earth?", "how do I care for a succulent?", "who wrote Pride and Prejudice?",
    "how do I make cold brew coffee?", "what is compound interest?", "how many bones are in the human body?",
    "how do I tie a bowline knot?",
]

SYSTEM = """You write evaluation questions for a course-search system. You are given one lecture's transcript, split into passages with ids. Write questions a student might type into a tutor chat that THIS lecture answers.

Rules:
- Write exactly 3 questions, one per requested style, in the order given.
  - direct: a clear, complete question ("What does the np package do when publishing?")
  - casual: lowercase, informal, possibly imprecise ("wait how do i stop npm from publishing my test files")
  - keyword: a short query built around a technical term, acronym or command from the passages ("IIFE scope", "npm link")
  - how_do_i: starts with "How do I" and asks for a procedure the lecture shows
- Each question must be answerable from the transcript and make sense on its own: never mention "the lecture", "the video", "the instructor", "this course", lecture numbers or chapter names.
- Don't copy the lecture title word for word; use the words a student would use.
- gold_chunk_id: the id of the single passage that best answers the question, or null if the answer is spread over the lecture.
- navigate_phrase: 2 to 6 words naming the most specific thing the lecture shows (a command, function, pattern or term), as a student would say it after "take me to the part about".

Return only JSON: {"questions": [{"style": "...", "question": "...", "gold_chunk_id": "... or null"}], "navigate_phrase": "..."}"""


async def _complete(system: str, user: str) -> Optional[dict]:
    from app.services.llm import llm
    return await llm.generate_json(system, user, temperature=0.4, max_tokens=700)


def styles_for(i: int) -> list[str]:
    return [STYLES[(i + j) % len(STYLES)] for j in range(3)]


def lectures_from_seed(chunks: list[dict]) -> list[dict]:
    out: dict[str, dict] = {}
    for c in chunks:
        lec = out.setdefault(c["lecture_id"], {"lecture_id": c["lecture_id"], "course_id": c["course_id"],
                                               "course_title": c["course_title"],
                                               "lecture_title": c["lecture_title"], "chunks": []})
        lec["chunks"].append({"chunk_id": c["chunk_id"], "text": c["text"]})
    return list(out.values())


def lecture_sha(lecture: dict) -> str:
    body = "\n".join(f"{c['chunk_id']}\t{c['text']}" for c in lecture["chunks"])
    return hashlib.sha256(body.encode()).hexdigest()[:16]


def _passages(lecture: dict) -> str:
    chunks = lecture["chunks"]
    total = sum(len(c["text"]) for c in chunks)
    if total > MAX_PROMPT_CHARS:  # evenly spaced passages, ids kept, so gold ids stay real
        keep = max(1, int(len(chunks) * MAX_PROMPT_CHARS / total))
        step = len(chunks) / keep
        chunks = [chunks[int(i * step)] for i in range(keep)]
    return "\n".join(f"[{c['chunk_id']}] {c['text']}" for c in chunks)


def _user(lecture: dict, styles: list[str]) -> str:
    return (f"Course: {lecture['course_title']}\nLecture: {lecture['lecture_title']}\n"
            f"Styles, in order: {', '.join(styles)}\n\nPassages:\n{_passages(lecture)}")


def validate_generation(raw: Optional[dict], chunk_ids: set[str], styles: list[str]) -> Optional[dict]:
    if not isinstance(raw, dict):
        return None
    qs = raw.get("questions")
    phrase = str(raw.get("navigate_phrase") or "").strip()
    if not isinstance(qs, list) or len(qs) != 3 or not phrase:
        return None
    out = []
    for q, style in zip(qs, styles):
        text = str((q or {}).get("question") or "").strip()
        if not text or BANNED.search(text):
            return None
        gold = (q or {}).get("gold_chunk_id")
        out.append({"style": style, "question": text, "gold_chunk_id": gold if gold in chunk_ids else None})
    return {"questions": out, "navigate_phrase": phrase}


def rows_for_lecture(lecture: dict, i: int, gen: dict) -> list[dict]:
    lid, slug = lecture["lecture_id"], lecture["course_id"]
    rows = [{"id": f"gen-{lid}-q{n}", "question": q["question"], "scope_course": slug, "expect": "covered",
             "gold_lecture_ids": [lid], "gold_chunk_ids": [q["gold_chunk_id"]] if q["gold_chunk_id"] else [],
             "style": q["style"], "intent": "explain", "source": "generated"}
            for n, q in enumerate(gen["questions"], 1)]
    phrase = gen["navigate_phrase"]
    rows.append({"id": f"gen-{lid}-nav", "question": NAV_TEMPLATES[i % len(NAV_TEMPLATES)].format(p=phrase),
                 "scope_course": slug, "expect": "covered", "gold_lecture_ids": [lid], "gold_chunk_ids": [],
                 "style": "navigate", "intent": "navigate", "navigate_phrase": phrase, "source": "generated"})
    return rows


def negative_rows(course_slugs: list[str]) -> list[dict]:
    return [{"id": f"neg-{n:02d}", "question": q, "scope_course": course_slugs[n % len(course_slugs)],
             "expect": "not_covered", "gold_lecture_ids": [], "style": "off_topic", "intent": "explain",
             "source": "generated"} for n, q in enumerate(OFF_TOPIC)]


def cross_course_rows(rows: list[dict]) -> list[dict]:
    out = []
    for src, dst in CROSS_PAIRS:
        picked = [r for r in rows if r["scope_course"] == src and r["intent"] == "explain"
                  and r["style"] in ("keyword", "direct")][:CROSS_PER_PAIR]
        out += [{"id": f"cross-{r['id'].removeprefix('gen-')}-in-{dst}", "question": r["question"],
                 "scope_course": dst, "expect": "not_covered", "gold_lecture_ids": [], "style": "cross_course",
                 "intent": "explain", "source": "generated"} for r in picked]
    return out


def golden_rows(chunks: list[dict]) -> list[dict]:
    by_id = {c["chunk_id"]: c for c in chunks}
    out = []
    for n, item in enumerate(json.loads(GOLDEN.read_text())):
        gold = [by_id[c] for c in item["gold_chunk_ids"] if c in by_id]
        if not gold:
            continue
        lectures = list(dict.fromkeys(c["lecture_id"] for c in gold))
        out.append({"id": f"golden-{n:02d}", "question": item["question"], "scope_course": gold[0]["course_id"],
                    "expect": "covered", "gold_lecture_ids": lectures, "gold_chunk_ids": item["gold_chunk_ids"],
                    "style": "direct", "intent": "explain", "source": "hand"})
    return out


def _cache_path(cache_dir: Path, lecture_id: str) -> Path:
    return Path(cache_dir) / f"{lecture_id}.json"


def _read_cache(cache_dir: Path, lecture: dict) -> Optional[dict]:
    p = _cache_path(cache_dir, lecture["lecture_id"])
    if not p.exists():
        return None
    data = json.loads(p.read_text())
    return data["gen"] if data.get("sha") == lecture_sha(lecture) else None


def _write_cache(cache_dir: Path, lecture: dict, gen: dict) -> None:
    p = _cache_path(cache_dir, lecture["lecture_id"])
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.with_suffix(".tmp")
    tmp.write_text(json.dumps({"sha": lecture_sha(lecture), "gen": gen}, indent=1))
    os.replace(tmp, p)


async def _generate(lecture: dict, styles: list[str]) -> Optional[dict]:
    ids = {c["chunk_id"] for c in lecture["chunks"]}
    for _attempt in range(2):
        try:
            gen = validate_generation(await _complete(SYSTEM, _user(lecture, styles)), ids, styles)
        except Exception as e:  # noqa: BLE001 — one lecture failing must not stop the run
            print(f"  {lecture['lecture_id']}: {e!r}")
            gen = None
        if gen:
            return gen
    print(f"  {lecture['lecture_id']}: no valid generation, skipped")
    return None


async def build_set(lectures: list[dict], cache_dir: Path, *, limit: Optional[int] = None, force: bool = False,
                    concurrency: int = 4) -> list[dict]:
    todo = [(i, lec) for i, lec in enumerate(lectures) if force or _read_cache(cache_dir, lec) is None]
    if limit is not None:
        todo = todo[:limit]
    sem = asyncio.Semaphore(concurrency)

    async def one(i: int, lec: dict):
        async with sem:
            gen = await _generate(lec, styles_for(i))
            if gen:
                _write_cache(cache_dir, lec, gen)

    await asyncio.gather(*(one(i, lec) for i, lec in todo))
    rows = []
    for i, lec in enumerate(lectures):
        gen = _read_cache(cache_dir, lec)
        if gen:
            rows += rows_for_lecture(lec, i, gen)
    return rows


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--limit", type=int, help="generate at most N new lectures (trial run)")
    ap.add_argument("--only", help="only this course slug")
    ap.add_argument("--force", action="store_true", help="ignore the cache and regenerate")
    ap.add_argument("--concurrency", type=int, default=4)
    a = ap.parse_args(argv)
    chunks = json.loads(SEED.read_text())
    lectures = lectures_from_seed(chunks)
    if a.only:
        lectures = [lec for lec in lectures if lec["course_id"] == a.only]
    rows = asyncio.run(build_set(lectures, CACHE_DIR, limit=a.limit, force=a.force, concurrency=a.concurrency))
    slugs = list(dict.fromkeys(c["course_id"] for c in chunks))
    rows += cross_course_rows(rows) + negative_rows(slugs) + golden_rows(chunks)
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(rows, indent=1, ensure_ascii=False) + "\n")
    cached = sum(_read_cache(CACHE_DIR, lec) is not None for lec in lectures)
    print(f"{len(rows)} rows ({cached}/{len(lectures)} lectures generated) -> {OUT}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
```

Note: the golden rows are merged into `generated_set.json` (source `"hand"`), so the eval runner reads two files: `generated_set.json` and `hand_set.json`.

- [ ] **Step 5: Run the tests to verify they pass**

Run: `cd backend && .venv/bin/pytest tests/test_eval_sets.py -q`
Expected: PASS.

- [ ] **Step 6: Generate the set (real model) — trial, then full**

Trial (2 lectures, look at the output before spending more):

```bash
cd backend && env OPENAI_API_KEY="$(grep '^OPENAI_API_KEY=' /Users/swanandkadam/Desktop/01dev-React-hermes/backend/.env | cut -d= -f2- | tr -d '"')" DATABASE_URL= .venv/bin/python scripts/generate_eval_set.py --limit 2
```

Expected: `... rows (2/209 lectures generated)`. Open `eval/retrieval/generated_set.json` and read the 8 `gen-*` rows: questions self-contained, styles as labelled, gold chunk ids real. Then the full run (resumes; ~207 small calls, < $1):

```bash
cd backend && env OPENAI_API_KEY="$(grep '^OPENAI_API_KEY=' /Users/swanandkadam/Desktop/01dev-React-hermes/backend/.env | cut -d= -f2- | tr -d '"')" DATABASE_URL= .venv/bin/python scripts/generate_eval_set.py
```

Expected: `... rows (209/209 lectures generated)` (≈ 836 lecture rows + 40 cross + 30 negatives + 14 golden). If some lectures were skipped, run the same command again — only the missing ones are requested.

- [ ] **Step 7: Commit**

```bash
git add backend/scripts/generate_eval_set.py backend/tests/test_eval_sets.py backend/eval/retrieval/hand_set.json backend/eval/retrieval/generated_set.json
git commit -m "feat(eval): retrieval eval sets — generated per-lecture questions + hand regression rows

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

### Task 3: Eval runner + legacy adapter + baseline numbers

**Files:**
- Create: `backend/app/eval/retrieval_systems.py`
- Create: `backend/scripts/eval_retrieval.py`
- Create (generated, Step 6): `backend/eval/retrieval/reports/phase1-baseline.json`, `.md`, `backend/eval/retrieval/reports/HISTORY.md`
- Test: `backend/tests/test_eval_runner.py`

**Interfaces:**
- Consumes: `Row`, `Prediction`, `summarize`, `per_course`, `render_markdown`, `compare`, `COVERED/PARTIAL/NOT_COVERED` (Task 1); the two set files (Task 2); current `course_lookup.course_lookup`, `course_lookup.search_in_course`, `course_lookup._transcript_hits`, `course_lookup.TRANSCRIPT_THRESHOLD`, `tutor_agent._locate_moment(what, slug) -> Optional[tuple[TranscriptChunk, float]]`.
- Produces:
  - `app.eval.retrieval_systems.LegacySystem` with `name = "legacy"` and `async predict(row: Row, mode: str) -> Prediction` (later tasks add `V2System` with the same method).
  - `scripts.eval_retrieval`: `TARGETS`, `load_rows(paths) -> dict[str, Row]`, `rows_for_mode(rows, mode) -> list[Row]`, `async run_system(system, rows: list[Row], mode: str, concurrency: int) -> list[Prediction]`, `build_run(label, system_name, rows, preds_by_mode) -> dict`, `check_targets(summary) -> list[str]`, `write_report(run, out_dir, compare_to=None) -> tuple[Path, Path]`, `make_system(name: str)`.
  - CLI: `scripts/eval_retrieval.py --system legacy|v2 --label <name> [--modes player,ask] [--limit N] [--only slug] [--concurrency 6] [--compare <label>]`. Reports land in `backend/eval/retrieval/reports/<label>.json|.md`, and one line per mode is appended to `reports/HISTORY.md`.

- [ ] **Step 1: Write the failing runner tests**

`backend/tests/test_eval_runner.py`:

```python
import json

from app.eval import retrieval_systems as rs
from app.eval.retrieval_metrics import COVERED, NOT_COVERED, PARTIAL, Prediction, Row
from app.models import TranscriptChunk
from scripts import eval_retrieval as ev


def _row(id, **kw):
    base = dict(id=id, question="q", scope_course="custom-library", expect=COVERED,
                gold_lecture_ids=["custom-library-5-2"])
    return Row(**{**base, **kw})


def _chunk(lid, n=0):
    return TranscriptChunk(chunk_id=f"{lid}-{n}", course_id="custom-library", course_title="C", lecture_id=lid,
                           lecture_title=f"T {lid}", text="t", start_time=n * 60, end_time=n * 60 + 60)


def test_rows_for_mode_ask_skips_navigate_and_cross_course():
    rows = [_row("a"), _row("b", intent="navigate"), _row("c", style="cross_course", expect=NOT_COVERED)]
    assert [r.id for r in ev.rows_for_mode(rows, "player")] == ["a", "b", "c"]
    assert [r.id for r in ev.rows_for_mode(rows, "ask")] == ["a"]


async def test_run_system_records_errors_and_keeps_order():
    class Fake:
        name = "fake"

        async def predict(self, row, mode):
            if row.id == "b":
                raise TimeoutError("slow")
            return Prediction(row.id, mode, ["custom-library-5-2"], COVERED, "custom-library-5-2", latency_ms=5)

    preds = await ev.run_system(Fake(), [_row("a"), _row("b"), _row("c")], "player", concurrency=2)
    assert [p.row_id for p in preds] == ["a", "b", "c"]
    assert preds[1].error == "TimeoutError('slow')" and preds[0].error is None


def test_write_report_writes_json_md_history_and_compare(tmp_path):
    rows = {r.id: r for r in [_row("a")]}
    preds = {"player": [Prediction("a", "player", ["custom-library-5-2"], COVERED, "custom-library-5-2", latency_ms=9)]}
    base = ev.build_run("phase1-baseline", "legacy", rows, preds)
    ev.write_report(base, tmp_path)
    new = ev.build_run("phase2-enriched", "legacy", rows, preds)
    j, md = ev.write_report(new, tmp_path, compare_to="phase1-baseline")
    assert json.loads(j.read_text())["label"] == "phase2-enriched"
    assert "Delta: phase1-baseline → phase2-enriched" in md.read_text()
    history = (tmp_path / "HISTORY.md").read_text().splitlines()
    assert sum("| phase1-baseline | legacy | player |" in line for line in history) == 1
    assert sum("| phase2-enriched | legacy | player |" in line for line in history) == 1


def test_check_targets_names_misses():
    misses = ev.check_targets({"recall@5": 0.95, "coverage_accuracy": 0.8, "false_cite_rate": 0.05,
                               "latency_p95_ms": 1200.0})
    assert misses == ["coverage_accuracy 0.800 (target >= 0.9)", "false_cite_rate 0.050 (target <= 0.03)"]


async def test_legacy_player_mapping(monkeypatch):
    from app.services import course_lookup as cl

    async def lookup(q, student, scope):
        assert scope.in_player and scope.course_slug == "custom-library"
        hit = cl.Hit(source="transcript", course_id=2, course_slug="custom-library", course_title="C",
                     title="T", score=0.5, enrolled=True, lecture_id="custom-library-5-2")
        return cl.CourseLookup(case=cl.LookupCase.IN_COURSE_RELATED, hits=[hit], enrolled_titles=[])

    async def in_course(q, slug, top_k=8):
        return [(_chunk("custom-library-9-0"), 0.5), (_chunk("custom-library-5-2"), 0.45),
                (_chunk("custom-library-9-0", 1), 0.44)]

    monkeypatch.setattr(cl, "course_lookup", lookup)
    monkeypatch.setattr(cl, "search_in_course", in_course)
    p = await rs.LegacySystem().predict(_row("a"), "player")
    assert (p.outcome, p.cited_lecture) == (PARTIAL, "custom-library-5-2")
    assert p.ranked_lectures == ["custom-library-9-0", "custom-library-5-2"]


async def test_legacy_ask_and_navigate_mapping(monkeypatch):
    from app.services import course_lookup as cl, tutor_agent

    async def hits(q, top_k=8):
        return [(_chunk("custom-library-5-2"), cl.TRANSCRIPT_THRESHOLD + 0.01), (_chunk("custom-library-9-0"), 0.1)]

    async def locate(what, slug):
        assert what == "np"
        return _chunk("custom-library-10-0"), 0.7

    monkeypatch.setattr(cl, "_transcript_hits", hits)
    monkeypatch.setattr(tutor_agent, "_locate_moment", locate)
    p = await rs.LegacySystem().predict(_row("a"), "ask")
    assert (p.outcome, p.cited_lecture) == (COVERED, "custom-library-5-2")
    nav = await rs.LegacySystem().predict(_row("n", intent="navigate", navigate_phrase="np"), "player")
    assert nav.moment_lecture == "custom-library-10-0"
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `cd backend && .venv/bin/pytest tests/test_eval_runner.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'app.eval.retrieval_systems'`.

- [ ] **Step 3: Implement the legacy adapter**

`backend/app/eval/retrieval_systems.py`:

```python
"""Eval adapters (spec §5): run one labelled Row through a retrieval system, in one mode, and say
what it did. "player" = scope is the row's course; "ask" = scope is every course (the eval pretends
the student owns every course and all are launched — the F1 filter is policy, not retrieval quality).
Latency covers the decision call only (not the extra ranking call made for recall/MRR)."""
import time

from app.eval.retrieval_metrics import COVERED, NOT_COVERED, PARTIAL, Prediction, Row

EVAL_STUDENT = "eval-student"


def _lecture_order(pairs) -> list[str]:
    """(chunk, score) best-first -> distinct lecture ids, best first."""
    return list(dict.fromkeys(c.lecture_id for c, _ in pairs))


def _ms(t0: float) -> float:
    return round((time.perf_counter() - t0) * 1000, 1)


class LegacySystem:
    """Phases 1-3: the threshold-based code paths exactly as they are (course_lookup, find_moment)."""
    name = "legacy"

    async def predict(self, row: Row, mode: str) -> Prediction:
        from app.services import course_lookup as cl, tutor_agent
        t0 = time.perf_counter()
        if row.intent == "navigate":
            hit = await tutor_agent._locate_moment(row.navigate_phrase or row.question, row.scope_course)
            return Prediction(row.id, mode, [], NOT_COVERED, None,
                              moment_lecture=hit[0].lecture_id if hit else None, latency_ms=_ms(t0))
        if mode == "player":
            scope = cl.ChatScope(course_slug=row.scope_course, lecture_title=row.lecture_title, in_player=True)
            lk = await cl.course_lookup(row.question, EVAL_STUDENT, scope)
            ms = _ms(t0)
            ranked = _lecture_order(await cl.search_in_course(row.question, row.scope_course, top_k=None))
            outcome = {cl.LookupCase.IN_COURSE_MATCH: COVERED,
                       cl.LookupCase.IN_COURSE_RELATED: PARTIAL}.get(lk.case, NOT_COVERED)
            cited = lk.hits[0].lecture_id if lk.hits else None
            return Prediction(row.id, mode, ranked, outcome, cited, latency_ms=ms)
        pairs = await cl._transcript_hits(row.question)
        ms = _ms(t0)
        strong = [(c, s) for c, s in pairs if s >= cl.TRANSCRIPT_THRESHOLD]
        return Prediction(row.id, mode, _lecture_order(pairs), COVERED if strong else NOT_COVERED,
                          strong[0][0].lecture_id if strong else None, latency_ms=ms)
```

- [ ] **Step 4: Implement the runner**

`backend/scripts/eval_retrieval.py`:

```python
"""Retrieval eval runner (spec §5). Runs a system over the eval sets in player and/or ask mode and
writes backend/eval/retrieval/reports/<label>.json + .md, appending one line per mode to HISTORY.md.

LOCAL ONLY — the in-memory store; run from backend/ with the key inline and the database off:
  env OPENAI_API_KEY=... DATABASE_URL= .venv/bin/python scripts/eval_retrieval.py --system legacy --label phase1-baseline
Options: --modes player,ask  --limit N (first N rows per set, trial)  --only <slug>  --concurrency 6
         --compare <earlier label>
"""
import argparse
import asyncio
import json
import os
import sys
from dataclasses import asdict
from datetime import datetime
from pathlib import Path
from typing import Optional

BACKEND = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND))

from app.eval.retrieval_metrics import (Prediction, Row, compare, per_course, render_markdown,  # noqa: E402
                                        summarize)

SETS = [BACKEND / "eval" / "retrieval" / "generated_set.json", BACKEND / "eval" / "retrieval" / "hand_set.json"]
REPORTS = BACKEND / "eval" / "retrieval" / "reports"
TARGETS = {"recall@5": (">=", 0.9), "coverage_accuracy": (">=", 0.9), "false_cite_rate": ("<=", 0.03),
           "latency_p95_ms": ("<=", 1500.0)}
HISTORY_HEADER = ("| label | system | mode | recall@1 | recall@5 | mrr | coverage | false_cite | navigate "
                  "| p50 ms | p95 ms | rows |\n|---|---|---|---|---|---|---|---|---|---|---|---|\n")


def load_rows(paths=SETS, limit: Optional[int] = None, only: Optional[str] = None) -> dict[str, Row]:
    rows: dict[str, Row] = {}
    for p in paths:
        items = [Row.from_dict(d) for d in json.loads(Path(p).read_text())]
        items = [r for r in items if not only or r.scope_course == only]
        for r in items[:limit] if limit else items:
            rows[r.id] = r
    return rows


def rows_for_mode(rows: list[Row], mode: str) -> list[Row]:
    if mode == "ask":  # no navigation on the Ask page; a cross-course row is taught somewhere in the library
        return [r for r in rows if r.intent != "navigate" and r.style != "cross_course"]
    return list(rows)


async def run_system(system, rows: list[Row], mode: str, concurrency: int = 6) -> list[Prediction]:
    sem = asyncio.Semaphore(concurrency)

    async def one(r: Row) -> Prediction:
        async with sem:
            try:
                return await system.predict(r, mode)
            except Exception as e:  # noqa: BLE001 — a failed row is reported, never fatal
                return Prediction(r.id, mode, [], "not_covered", None, error=repr(e))

    return list(await asyncio.gather(*(one(r) for r in rows)))


def build_run(label: str, system_name: str, rows: dict[str, Row], preds_by_mode: dict[str, list[Prediction]]) -> dict:
    return {"label": label, "system": system_name, "created": datetime.now().isoformat(timespec="seconds"),
            "modes": {m: {"overall": summarize(rows, ps), "per_course": per_course(rows, ps)}
                      for m, ps in preds_by_mode.items()},
            "predictions": [asdict(p) for ps in preds_by_mode.values() for p in ps]}


def check_targets(summary: dict) -> list[str]:
    misses = []
    for key, (op, target) in TARGETS.items():
        v = summary.get(key)
        if v is None:
            continue
        if (op == ">=" and v < target) or (op == "<=" and v > target):
            misses.append(f"{key} {v:.3f} (target {op} {target:g})")
    return misses


def _f(v) -> str:
    return "—" if v is None else (f"{v:.0f}" if v > 1.0 else f"{v:.3f}")


def write_report(run: dict, out_dir: Path = REPORTS, compare_to: Optional[str] = None) -> tuple[Path, Path]:
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    j, md = out_dir / f"{run['label']}.json", out_dir / f"{run['label']}.md"
    j.write_text(json.dumps(run, indent=1) + "\n")
    text = render_markdown(run)
    for mode, data in run["modes"].items():
        misses = check_targets(data["overall"])
        text += f"\nTargets ({mode}): " + ("all met" if not misses else "MISSED — " + "; ".join(misses)) + "\n"
    if compare_to:
        base = json.loads((out_dir / f"{compare_to}.json").read_text())
        text += "\n" + compare(base, run)
    md.write_text(text)
    hist = out_dir / "HISTORY.md"
    lines = hist.read_text() if hist.exists() else "# Retrieval eval history\n\n" + HISTORY_HEADER
    for mode, data in run["modes"].items():
        o = data["overall"]
        n = sum(v for k, v in o["counts"].items() if k != "errors")
        lines += (f"| {run['label']} | {run['system']} | {mode} | {_f(o['recall@1'])} | {_f(o['recall@5'])} | "
                  f"{_f(o['mrr'])} | {_f(o['coverage_accuracy'])} | {_f(o['false_cite_rate'])} | "
                  f"{_f(o['navigate_accuracy'])} | {_f(o['latency_p50_ms'])} | {_f(o['latency_p95_ms'])} | {n} |\n")
    hist.write_text(lines)
    return j, md


def make_system(name: str):
    from app.eval import retrieval_systems as rs
    return {"legacy": rs.LegacySystem}[name]()


def _memoize_question_embeddings():
    """Within one mode the same question is embedded by several code paths: embed it once."""
    from app.services.embeddings import embedding_service
    orig, memo = embedding_service.embed, {}

    async def embed(text: str):
        if text not in memo:
            memo[text] = await orig(text)
        return memo[text]

    embedding_service.embed = embed
    return memo


async def _main(a) -> int:
    from app.services.vector_store import vector_store
    if os.getenv("DATABASE_URL"):
        print("Refusing to run: DATABASE_URL is set (the eval is local-only; pass DATABASE_URL=)")
        return 2
    await vector_store.initialize()
    rows = load_rows(limit=a.limit, only=a.only)
    system = make_system(a.system)
    memo = _memoize_question_embeddings()
    preds = {}
    for mode in a.modes.split(","):
        memo.clear()
        todo = rows_for_mode(list(rows.values()), mode)
        print(f"[{mode}] {len(todo)} rows …")
        preds[mode] = await run_system(system, todo, mode, a.concurrency)
    run = build_run(a.label, system.name, rows, preds)
    j, md = write_report(run, compare_to=a.compare)
    print(md.read_text())
    errors = sum(p.error is not None for ps in preds.values() for p in ps)
    if errors:
        print(f"WARNING: {errors} rows errored (see {j}); numbers exclude them")
    return 0


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--system", default="legacy", choices=["legacy", "v2"])
    ap.add_argument("--label", required=True)
    ap.add_argument("--modes", default="player,ask")
    ap.add_argument("--limit", type=int)
    ap.add_argument("--only")
    ap.add_argument("--concurrency", type=int, default=6)
    ap.add_argument("--compare")
    return asyncio.run(_main(ap.parse_args(argv)))


if __name__ == "__main__":
    sys.exit(main())
```

(`"v2"` is accepted by the argument parser now and wired in `make_system` by Task 13.)

- [ ] **Step 5: Run the tests to verify they pass**

Run: `cd backend && .venv/bin/pytest tests/test_eval_runner.py tests/test_retrieval_metrics.py tests/test_eval_sets.py -q`
Expected: PASS.

- [ ] **Step 6: Eval delta — record the baseline (real model)**

Trial (20 rows per set, both modes) to check the plumbing:

```bash
cd backend && env OPENAI_API_KEY="$(grep '^OPENAI_API_KEY=' /Users/swanandkadam/Desktop/01dev-React-hermes/backend/.env | cut -d= -f2- | tr -d '"')" DATABASE_URL= .venv/bin/python scripts/eval_retrieval.py --system legacy --label trial --limit 20
```

Expected: a markdown report with numbers for both modes and no `WARNING: … rows errored`. Delete the trial files: `rm backend/eval/retrieval/reports/trial.json backend/eval/retrieval/reports/trial.md backend/eval/retrieval/reports/HISTORY.md`.

Full baseline:

```bash
cd backend && env OPENAI_API_KEY="$(grep '^OPENAI_API_KEY=' /Users/swanandkadam/Desktop/01dev-React-hermes/backend/.env | cut -d= -f2- | tr -d '"')" DATABASE_URL= .venv/bin/python scripts/eval_retrieval.py --system legacy --label phase1-baseline
```

Expected: `reports/phase1-baseline.md` with overall + per-course tables for `player` and `ask`, a `Targets (…)` line per mode, and two rows in `reports/HISTORY.md`. The IIFE hand row (`hand-iife`) should show as `not_covered` in the player predictions (the spec's root-cause case) — confirm with `grep -A3 '"row_id": "hand-iife"' backend/eval/retrieval/reports/phase1-baseline.json`. If more than 2% of rows errored, rerun before recording.

- [ ] **Step 7: Commit**

```bash
git add backend/app/eval/retrieval_systems.py backend/scripts/eval_retrieval.py backend/tests/test_eval_runner.py backend/eval/retrieval/reports/phase1-baseline.json backend/eval/retrieval/reports/phase1-baseline.md backend/eval/retrieval/reports/HISTORY.md
git commit -m "feat(eval): retrieval eval runner + legacy adapter; phase 1 baseline numbers

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

# Phase 2 — Chunk enrichment + context-rich `embed_text` + glossary

### Task 4: Chunk model fields + enrichment loader, glossary and `embed_text`

**Why a separate keyed file (design decision):** enrichment is stored in `backend/data/enrichment/<slug>.json` as `{"version": 1, "model": "gpt-4.1-mini", "chunks": {chunk_id: {"text_sha", "summary", "keywords", "questions"}}}` and merged into the chunks **at load time**. `build_course_transcripts.py --merge` rebuilds the seed from staging files and writes only its `FIELDS`, so anything stored in the seed would be lost on the next merge, and anything stored in staging files would not exist for custom-library (whose real chunks never pass through staging). A keyed side file survives both, applies to custom-library exactly like the other nine courses, never edits `text`/times/ids, and the `text_sha` key makes an entry inert (not wrong) the moment its chunk's text changes. `text_clean`, `chapter`, `embed_text` and `content_hash` are derived at load (cheap, deterministic), so glossary edits apply without re-running the LLM.

**Files:**
- Modify: `backend/app/models.py` (`TranscriptChunk` optional fields)
- Create: `backend/app/retrieval/__init__.py`, `backend/app/retrieval/text.py`, `backend/app/retrieval/enrichment.py`
- Test: `backend/tests/test_enrichment.py`; add one test to `backend/tests/test_build_course_transcripts.py`

**Interfaces:**
- Consumes: `app.services.catalog_service.by_slug(slug) -> Optional[dict]` (chapters: `[{"name", "subchapters": [...]}]`).
- Produces:
  - `TranscriptChunk` gains (all defaulted): `chapter: str = ""`, `text_clean: str = ""`, `summary: str = ""`, `keywords: List[str] = []`, `questions: List[str] = []`, `embed_text: str = ""`, `embed_model: str = ""`, `content_hash: str = ""`. `text` stays the raw transcript (`text_raw` in the spec).
  - `app.retrieval.text`: `norm_title(s: str) -> str`, `last_sentence(text: str, max_chars: int = 200) -> str`
  - `app.retrieval.enrichment`: `ENRICH_DIR`, `GLOSSARY_DIR`, `EMBED_MODEL = "text-embedding-3-small"`, `text_sha(text) -> str` (16 hex), `load_glossary(slug, glossary_dir=GLOSSARY_DIR) -> list[tuple[re.Pattern, str]]`, `clean_text(text, glossary) -> str`, `load_enrichment(slug, enrich_dir=ENRICH_DIR) -> dict[str, dict]`, `save_enrichment(slug, entries, model, enrich_dir=ENRICH_DIR) -> Path`, `chapter_for(lecture_id, slug) -> str`, `build_embed_text(chunk, prev_text: Optional[str]) -> str`, `content_hash(embed_text, model=EMBED_MODEL) -> str`, `apply_enrichment(chunks, enrich_dir=ENRICH_DIR, glossary_dir=GLOSSARY_DIR) -> list[TranscriptChunk]`, `embed_input(chunk) -> str` (`chunk.embed_text or chunk.text`).

- [ ] **Step 1: Write the failing tests**

`backend/tests/test_enrichment.py`:

```python
import json

from app.models import TranscriptChunk
from app.retrieval import enrichment as en
from app.retrieval.text import last_sentence, norm_title


def _c(n, text, lecture="custom-library-5-2", title="6.5 - IIFE, To The Rescue"):
    return TranscriptChunk(chunk_id=f"{lecture}-{n}", course_id="custom-library", course_title="Build a Custom Library",
                           lecture_id=lecture, lecture_title=title, text=text, start_time=n * 60,
                           end_time=n * 60 + 60)


def _dirs(tmp_path, entries=None, glossary=None):
    e, g = tmp_path / "enrichment", tmp_path / "glossary"
    e.mkdir()
    g.mkdir()
    if entries is not None:
        (e / "custom-library.json").write_text(json.dumps({"version": 1, "model": "m", "chunks": entries}))
    if glossary is not None:
        (g / "custom-library.json").write_text(json.dumps({"replacements": glossary}))
    return e, g


def test_text_helpers():
    assert norm_title("8.1 - The `npm link`   Command") == "8.1 - the npm link command"
    assert last_sentence("First one. Second one is here.") == "Second one is here."
    assert last_sentence("no punctuation at all") == "no punctuation at all"
    assert len(last_sentence("x" * 500)) == 200


def test_glossary_fixes_text_clean_only(tmp_path):
    e, g = _dirs(tmp_path, glossary=[{"pattern": r"\biffy\b", "replace": "IIFE"},
                                     {"pattern": r"\bmodel pattern(s?)\b", "replace": r"module pattern\1"}])
    raw = "the new pattern  was iffy, the model patterns before modules"
    out = en.apply_enrichment([_c(0, raw)], e, g)[0]
    assert out.text == raw                                   # text_raw untouched
    assert out.text_clean == "the new pattern was IIFE, the module patterns before modules"
    assert (out.start_time, out.end_time, out.chunk_id) == (0, 60, "custom-library-5-2-0")


def test_embed_text_has_header_summary_terms_overlap_and_text(tmp_path):
    first, second = _c(0, "Intro. We wrap the function in parens."), _c(1, "Then we call it at once.")
    e, g = _dirs(tmp_path, entries={second.chunk_id: {"text_sha": en.text_sha(second.text),
                                                      "summary": "Calling the wrapped function immediately.",
                                                      "keywords": ["IIFE", "scope"],
                                                      "questions": ["what is an IIFE?"]}})
    a, b = en.apply_enrichment([first, second], e, g)
    assert a.summary == "" and a.keywords == []
    from app.services import catalog_service
    assert b.chapter == catalog_service.by_slug("custom-library")["chapters"][5]["name"]   # lecture id ...-5-2
    lines = b.embed_text.split("\n")
    assert lines[0].startswith("Build a Custom Library › ") and lines[0].endswith("› 6.5 - IIFE, To The Rescue")
    assert "Summary: Calling the wrapped function immediately." in lines
    assert "Key terms: IIFE, scope" in lines
    assert "Previously: We wrap the function in parens." in lines
    assert lines[-1] == "Then we call it at once."
    assert "Previously:" not in a.embed_text                 # first chunk of a lecture has no overlap
    assert b.embed_model == en.EMBED_MODEL and b.content_hash == en.content_hash(b.embed_text)
    assert b.questions == ["what is an IIFE?"]


def test_stale_enrichment_is_ignored(tmp_path):
    c = _c(0, "edited transcript text")
    e, g = _dirs(tmp_path, entries={c.chunk_id: {"text_sha": en.text_sha("the OLD text"), "summary": "old",
                                                 "keywords": ["old"], "questions": []}})
    out = en.apply_enrichment([c], e, g)[0]
    assert out.summary == "" and out.keywords == [] and "old" not in out.embed_text


def test_content_hash_changes_with_text_model_or_glossary(tmp_path):
    e, g = _dirs(tmp_path)
    h1 = en.apply_enrichment([_c(0, "an iffy")], e, g)[0].content_hash
    assert en.apply_enrichment([_c(0, "an iffy")], e, g)[0].content_hash == h1          # deterministic
    assert en.content_hash("x", "text-embedding-3-large") != en.content_hash("x")
    (g / "custom-library.json").write_text(json.dumps({"replacements": [{"pattern": r"\biffy\b", "replace": "IIFE"}]}))
    assert en.apply_enrichment([_c(0, "an iffy")], e, g)[0].content_hash != h1


def test_missing_files_mean_header_plus_text(tmp_path):
    e, g = _dirs(tmp_path)
    out = en.apply_enrichment([_c(0, "plain")], e, g)[0]
    assert out.embed_text.split("\n")[-1] == "plain" and en.embed_input(out) == out.embed_text
    assert en.embed_input(_c(0, "raw only")) == "raw only"


def test_save_then_load_round_trip_is_sorted_and_atomic(tmp_path):
    entries = {"b-1": {"text_sha": "1", "summary": "s", "keywords": [], "questions": []},
               "a-1": {"text_sha": "2", "summary": "t", "keywords": [], "questions": []}}
    p = en.save_enrichment("x", entries, "gpt-4.1-mini", tmp_path)
    assert list(json.loads(p.read_text())["chunks"]) == ["a-1", "b-1"]
    assert en.load_enrichment("x", tmp_path) == entries
    assert en.load_enrichment("missing", tmp_path) == {}
    assert not list(tmp_path.glob("*.tmp"))
```

Append to `backend/tests/test_build_course_transcripts.py` (pins that `--merge` can never carry enrichment into the seed, so the side files stay the only source):

```python
def test_merge_never_carries_enrichment_fields(tmp_path):
    cat, seed, src, _ = setup_merge(tmp_path)
    staged = json.loads((src / "demo.json").read_text())
    for c in staged:
        c.update(summary="s", keywords=["k"], embed_text="e", content_hash="h")
    (src / "demo.json").write_text(json.dumps(staged))
    assert b.merge(cat, seed, src, {}) == []
    demo = [c for c in json.loads(seed.read_text()) if c["course_id"] == "demo"]
    assert demo and all(list(c) == b.FIELDS for c in demo)
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `cd backend && .venv/bin/pytest tests/test_enrichment.py tests/test_build_course_transcripts.py -q`
Expected: `test_enrichment.py` FAILS with `ModuleNotFoundError: No module named 'app.retrieval'`; `test_merge_never_carries_enrichment_fields` PASSES already (it pins existing behaviour).

- [ ] **Step 3: Implement**

`backend/app/models.py` — extend `TranscriptChunk` (keep field order; new fields after `embedding`):

```python
class TranscriptChunk(BaseModel):
    chunk_id: str
    course_id: str
    course_title: str
    lecture_id: str
    lecture_title: str
    text: str                      # the raw transcript ("text_raw" in the retrieval spec) — never rewritten
    start_time: int
    end_time: int
    embedding: List[float] = []
    # Retrieval v2 (derived at load by app.retrieval.enrichment; empty for un-enriched chunks)
    chapter: str = ""
    text_clean: str = ""           # glossary-fixed, whitespace-normalised text (shown to the model and on cards)
    summary: str = ""
    keywords: List[str] = []
    questions: List[str] = []
    embed_text: str = ""           # what is embedded: header + summary + key terms + overlap + text_clean
    embed_model: str = ""
    content_hash: str = ""         # sha256(embed_model + embed_text)
```

`backend/app/retrieval/__init__.py`:

```python
"""Retrieval v2 (docs/superpowers/specs/2026-10-06-retrieval-architecture-design.md)."""
```

`backend/app/retrieval/text.py`:

```python
"""Text helpers shared by enrichment, BM25 and the Postgres full-text columns."""
import re


def norm_title(s: str) -> str:
    """Compare lecture titles loosely: backticks, spacing and case drift between player and transcripts."""
    return " ".join(s.replace("`", "").split()).casefold()


_SENTENCE_END = re.compile(r"(?<=[.!?])\s+")


def last_sentence(text: str, max_chars: int = 200) -> str:
    parts = [p for p in _SENTENCE_END.split(text.strip()) if p.strip()]
    tail = parts[-1].strip() if parts else ""
    return tail[-max_chars:]
```

`backend/app/retrieval/enrichment.py`:

```python
"""Context-rich chunks (spec §3): merge the committed offline enrichment into the chunks at load time
and derive text_clean (glossary), chapter, embed_text and content_hash. Never touches text/times/ids.

Enrichment file: backend/data/enrichment/<slug>.json
  {"version": 1, "model": "gpt-4.1-mini", "chunks": {chunk_id: {"text_sha", "summary", "keywords", "questions"}}}
An entry applies only while sha256(chunk.text)[:16] == text_sha, so a transcript edit makes it inert.
Glossary file: backend/data/glossary/<slug>.json  {"replacements": [{"pattern": regex, "replace": str}]}
(case-insensitive; applied to text_clean only).
"""
import hashlib
import json
import os
import re
from pathlib import Path
from typing import Optional

from app.models import TranscriptChunk
from app.retrieval.text import last_sentence

BACKEND = Path(__file__).resolve().parents[2]
ENRICH_DIR = BACKEND / "data" / "enrichment"
GLOSSARY_DIR = BACKEND / "data" / "glossary"
EMBED_MODEL = "text-embedding-3-small"
EMBED_TEXT_CHARS = 8000  # embeddings.py truncates input at 8000 chars too


def text_sha(text: str) -> str:
    return hashlib.sha256(text.encode()).hexdigest()[:16]


def load_glossary(slug: str, glossary_dir: Path = GLOSSARY_DIR) -> list[tuple[re.Pattern, str]]:
    p = Path(glossary_dir) / f"{slug}.json"
    if not p.exists():
        return []
    return [(re.compile(r["pattern"], re.IGNORECASE), r["replace"])
            for r in json.loads(p.read_text()).get("replacements", [])]


def clean_text(text: str, glossary: list[tuple[re.Pattern, str]]) -> str:
    for pattern, replacement in glossary:
        text = pattern.sub(replacement, text)
    return " ".join(text.split())


def load_enrichment(slug: str, enrich_dir: Path = ENRICH_DIR) -> dict[str, dict]:
    p = Path(enrich_dir) / f"{slug}.json"
    return json.loads(p.read_text()).get("chunks", {}) if p.exists() else {}


def save_enrichment(slug: str, entries: dict[str, dict], model: str, enrich_dir: Path = ENRICH_DIR) -> Path:
    p = Path(enrich_dir) / f"{slug}.json"
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.with_name(p.name + ".tmp")
    body = {"version": 1, "model": model, "chunks": {k: entries[k] for k in sorted(entries)}}
    tmp.write_text(json.dumps(body, indent=1, ensure_ascii=False) + "\n")
    os.replace(tmp, p)
    return p


def chapter_for(lecture_id: str, slug: str) -> str:
    from app.services import catalog_service
    m = re.search(r"-(\d+)-(\d+)$", lecture_id)
    chapters = (catalog_service.by_slug(slug) or {}).get("chapters", [])
    if not m or int(m.group(1)) >= len(chapters):
        return ""
    return chapters[int(m.group(1))].get("name", "")


def build_embed_text(chunk: TranscriptChunk, prev_text: Optional[str]) -> str:
    header = " › ".join(p for p in (chunk.course_title, chunk.chapter, chunk.lecture_title) if p)
    parts = [header]
    if chunk.summary:
        parts.append(f"Summary: {chunk.summary}")
    if chunk.keywords:
        parts.append("Key terms: " + ", ".join(chunk.keywords))
    if prev_text:
        parts.append(f"Previously: {last_sentence(prev_text)}")
    parts.append(chunk.text_clean or chunk.text)
    return "\n".join(parts)[:EMBED_TEXT_CHARS]


def content_hash(embed_text: str, model: str = EMBED_MODEL) -> str:
    return hashlib.sha256(f"{model}\n{embed_text}".encode()).hexdigest()


def embed_input(chunk: TranscriptChunk) -> str:
    """What to embed for this chunk: embed_text once enrichment has run, else the raw text."""
    return chunk.embed_text or chunk.text


def apply_enrichment(chunks: list[TranscriptChunk], enrich_dir: Path = ENRICH_DIR,
                     glossary_dir: Path = GLOSSARY_DIR) -> list[TranscriptChunk]:
    glossaries: dict[str, list] = {}
    entries: dict[str, dict] = {}
    prev_clean: dict[str, str] = {}   # lecture_id -> previous chunk's text_clean (seed order = time order)
    out = []
    for c in chunks:
        slug = c.course_id
        if slug not in glossaries:
            glossaries[slug] = load_glossary(slug, glossary_dir)
            entries[slug] = load_enrichment(slug, enrich_dir)
        e = entries[slug].get(c.chunk_id)
        fresh = bool(e) and e.get("text_sha") == text_sha(c.text)
        new = c.model_copy(update={
            "chapter": chapter_for(c.lecture_id, slug),
            "text_clean": clean_text(c.text, glossaries[slug]),
            "summary": (e or {}).get("summary", "") if fresh else "",
            "keywords": list((e or {}).get("keywords", [])) if fresh else [],
            "questions": list((e or {}).get("questions", [])) if fresh else [],
        })
        new.embed_text = build_embed_text(new, prev_clean.get(c.lecture_id))
        new.embed_model = EMBED_MODEL
        new.content_hash = content_hash(new.embed_text, EMBED_MODEL)
        prev_clean[c.lecture_id] = new.text_clean
        out.append(new)
    return out
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `cd backend && .venv/bin/pytest tests/test_enrichment.py tests/test_build_course_transcripts.py -q`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add backend/app/models.py backend/app/retrieval/__init__.py backend/app/retrieval/text.py backend/app/retrieval/enrichment.py backend/tests/test_enrichment.py backend/tests/test_build_course_transcripts.py
git commit -m "feat(retrieval): enriched chunk model — side-file enrichment, glossary text_clean, embed_text, content_hash

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

### Task 5: Vector store embeds `embed_text` (+ opt-in local embedding cache)

**Files:**
- Create: `backend/app/retrieval/embed_cache.py`
- Modify: `backend/app/services/vector_store.py` (`initialize`, `_init_with_pgvector`, new `_embed_chunks`)
- Modify: `backend/scripts/eval_retrieval.py` (`_main` turns the cache on)
- Test: `backend/tests/test_vector_store_batch.py` (update `FakePool`, add 3 tests)

**Interfaces:**
- Consumes: `apply_enrichment`, `embed_input`, `text_sha` (Task 4); `embedding_service.embed_many(texts, batch_size=100)`.
- Produces:
  - `app.retrieval.embed_cache.EmbedCache(path: Path)` with `get_many(keys) -> dict[str, list[float]]`, `put_many(items: dict[str, list[float]]) -> None`, and `EmbedCache.from_env() -> Optional[EmbedCache]` (reads env `RAG_EMBED_CACHE` = a directory; file `<dir>/text-embedding-3-small.jsonl`). Used only when `RAG_EMBED_CACHE` is set and OpenAI embeddings are on — never in prod (Railway has no such variable) and never in tests.
  - `InMemoryVectorStore.initialize()` now: loads the seed → `apply_enrichment` → embeds `embed_input(c)` for every chunk. `vector_store.chunks[i].embed_text/content_hash/text_clean/keywords/summary/questions/chapter` are populated for every chunk.
  - pgvector path re-embeds a chunk when its stored `meta->>'content_hash'` (or, for rows written before this change, its stored `text`) differs from the chunk's `content_hash` (or text).

- [ ] **Step 1: Write the failing tests**

In `backend/tests/test_vector_store_batch.py`, make `FakePool` carry stored hashes (existing tests keep passing because un-enriched test chunks have `content_hash == ""` and fall back to text):

```python
class FakePool:
    def __init__(self, cached=(), hashes=None):
        # list of ids (stored text == seed text "t"*(i+1)) or dict id -> stored text
        if not isinstance(cached, dict):
            cached = {c: "t" * (int(c.split("-")[1]) + 1) for c in cached}
        self.cached = dict(cached)
        self.hashes = dict(hashes or {})
        self.inserted = []

    async def fetch(self, sql, *a):
        return [{"chunk_id": c, "text": t, "h": self.hashes.get(c), "emb": "[0.5,0.5]"}
                for c, t in self.cached.items()]
```

In `test_inmemory_path_batches`, add `monkeypatch.delenv("RAG_EMBED_CACHE", raising=False)` as its first line. Then append:

```python
def _seed_two():
    return [dict(chunk_id=f"custom-library-5-2-{i}", course_id="custom-library", course_title="Build a Custom Library",
                 lecture_id="custom-library-5-2", lecture_title="6.5 - IIFE, To The Rescue", text=t,
                 start_time=60 * i, end_time=60 * i + 60, embedding=[])
            for i, t in enumerate(["We wrap it.", "Then call it."])]


def test_initialize_enriches_and_embeds_embed_text(monkeypatch):
    client = FakeClient()
    monkeypatch.setattr(embedding_service, "use_openai", True)
    monkeypatch.setattr(embedding_service, "client", client)
    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.delenv("RAG_EMBED_CACHE", raising=False)
    monkeypatch.setattr(vs, "json", SimpleNamespace(load=lambda f: _seed_two()))
    store = vs.InMemoryVectorStore()
    asyncio.run(store.initialize())
    assert store.chunks[1].embed_text.startswith("Build a Custom Library › ")
    assert "Previously: We wrap it." in store.chunks[1].embed_text
    assert [t for c in client.calls for t in c] == [c.embed_text for c in store.chunks]
    assert store.chunks[1].text == "Then call it."          # raw text unchanged


def test_embed_cache_skips_openai_on_the_second_boot(monkeypatch, tmp_path):
    client = FakeClient()
    monkeypatch.setattr(embedding_service, "use_openai", True)
    monkeypatch.setattr(embedding_service, "client", client)
    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.setenv("RAG_EMBED_CACHE", str(tmp_path))
    monkeypatch.setattr(vs, "json", SimpleNamespace(load=lambda f: _seed_two()))
    first = vs.InMemoryVectorStore()
    asyncio.run(first.initialize())
    n_calls = len(client.calls)
    second = vs.InMemoryVectorStore()
    asyncio.run(second.initialize())
    assert n_calls == 1 and len(client.calls) == 1          # second boot: all from the cache
    assert second._embeddings == first._embeddings


def test_pg_path_reembeds_when_the_content_hash_changes(monkeypatch):
    client = FakeClient()
    store = _setup(monkeypatch, 2, client, FakePool(cached=["c-0", "c-1"], hashes={"c-0": "same", "c-1": "old"}))
    store.chunks[0].content_hash, store.chunks[0].embed_text = "same", "E0"
    store.chunks[1].content_hash, store.chunks[1].embed_text = "new", "E1"
    asyncio.run(store._init_with_pgvector())
    assert client.calls == [["E1"]]
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `cd backend && .venv/bin/pytest tests/test_vector_store_batch.py -q`
Expected: the three new tests FAIL (no enrichment applied / cache ignored / hash not compared); the existing ones PASS.

- [ ] **Step 3: Implement**

`backend/app/retrieval/embed_cache.py`:

```python
"""Opt-in on-disk embedding cache for LOCAL runs (eval, demo checks): set RAG_EMBED_CACHE=<dir>.
Keyed by content_hash (which already includes the embedding model), one JSON line per vector.
Never used in prod or tests (the variable is unset there)."""
import json
import os
from pathlib import Path
from typing import Optional

FILE = "text-embedding-3-small.jsonl"


class EmbedCache:
    def __init__(self, path: Path):
        self.path = Path(path)
        self._data: dict[str, list[float]] = {}
        if self.path.exists():
            for line in self.path.read_text().splitlines():
                if line.strip():
                    row = json.loads(line)
                    self._data[row["k"]] = row["v"]

    @classmethod
    def from_env(cls) -> Optional["EmbedCache"]:
        d = os.getenv("RAG_EMBED_CACHE")
        return cls(Path(d) / FILE) if d else None

    def get_many(self, keys) -> dict[str, list[float]]:
        return {k: self._data[k] for k in keys if k in self._data}

    def put_many(self, items: dict[str, list[float]]) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.path.open("a") as f:
            for k, v in items.items():
                f.write(json.dumps({"k": k, "v": v}) + "\n")
        self._data.update(items)
```

`backend/app/services/vector_store.py` — imports and three edits:

```python
from app.retrieval.embed_cache import EmbedCache
from app.retrieval.enrichment import apply_enrichment, embed_input, text_sha
```

In `initialize()`, replace `self.chunks = [TranscriptChunk(**item) for item in data]` with:

```python
        self.chunks = apply_enrichment([TranscriptChunk(**item) for item in data])
```

and replace the in-memory embedding line `self._embeddings = await embedding_service.embed_many([c.text for c in self.chunks])` with:

```python
        self._embeddings = await self._embed_chunks(self.chunks)
```

Add the method:

```python
    async def _embed_chunks(self, chunks: List[TranscriptChunk]) -> List[List[float]]:
        """Embed embed_text (raw text for un-enriched chunks), ≤ EMBED_BATCH inputs per call. With
        RAG_EMBED_CACHE set (local eval only) vectors are read from / appended to the disk cache."""
        cache = EmbedCache.from_env() if embedding_service.use_openai else None
        texts = [embed_input(c) for c in chunks]
        if cache is None:
            return await embedding_service.embed_many(texts, batch_size=EMBED_BATCH)
        keys = [c.content_hash or text_sha(t) for c, t in zip(chunks, texts)]
        have = cache.get_many(keys)
        todo = [i for i, k in enumerate(keys) if k not in have]
        for start in range(0, len(todo), EMBED_BATCH):
            batch = todo[start:start + EMBED_BATCH]
            embs = await embedding_service.embed_many([texts[i] for i in batch], batch_size=EMBED_BATCH)
            fresh = {keys[i]: e for i, e in zip(batch, embs)}
            cache.put_many(fresh)
            have.update(fresh)
        if todo:
            print(f"Embedding cache: {len(todo)} embedded, {len(chunks) - len(todo)} from {cache.path}")
        return [have[k] for k in keys]
```

In `_init_with_pgvector()`, select the stored hash and compare keys, and embed `embed_input`:

```python
        rows = await pool.fetch(
            "select chunk_id, text, meta->>'content_hash' as h, embedding::text as emb "
            "from rag_chunks where embedding is not null"
        )
        cached = {r["chunk_id"]: _parse_vec(r["emb"]) for r in rows}
        stored_key = {r["chunk_id"]: (r.get("h") or r["text"]) for r in rows}

        # Re-embed chunks whose id is new OR whose embed_text (content_hash) / text changed since stored.
        new_count = sum(1 for c in self.chunks if c.chunk_id not in cached)
        missing = [
            c for c in self.chunks
            if c.chunk_id not in cached or stored_key.get(c.chunk_id) != (c.content_hash or c.text)
        ]
```

and in the batch loop change `embs = await embedding_service.embed_many([c.text for c in batch])` to `embs = await embedding_service.embed_many([embed_input(c) for c in batch])`. The upsert still writes `text = c.text` and `meta = c.model_dump(exclude={"embedding"})`, which now includes `content_hash`, so the next boot finds it.

`backend/scripts/eval_retrieval.py` — in `_main`, before `await vector_store.initialize()`:

```python
    os.environ.setdefault("RAG_EMBED_CACHE", str(BACKEND / "data" / "cache" / "embeddings"))
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `cd backend && .venv/bin/pytest tests/test_vector_store_batch.py tests/test_vector_store_course_scope.py tests/test_enrichment.py -q`
Expected: PASS. Then `bash backend/scripts/run_tests.sh` → `ALL PASSED`.

- [ ] **Step 5: Commit**

```bash
git add backend/app/retrieval/embed_cache.py backend/app/services/vector_store.py backend/scripts/eval_retrieval.py backend/tests/test_vector_store_batch.py
git commit -m "feat(retrieval): embed enriched embed_text; re-embed on content_hash change; local embedding cache for evals

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

### Task 6: Offline enrichment script + glossary + enrichment run

**Files:**
- Create: `backend/scripts/enrich_chunks.py`
- Create: `backend/data/glossary/custom-library.json`
- Create (generated, Step 6): `backend/data/enrichment/<slug>.json` for all 10 courses, `backend/data/glossary/<slug>.suggested.json` (review aid)
- Test: `backend/tests/test_enrich_chunks.py`

**Interfaces:**
- Consumes: `TranscriptChunk` (Task 4 fields), `apply_enrichment`, `load_enrichment`, `save_enrichment`, `text_sha`, `ENRICH_DIR`, `GLOSSARY_DIR` (Task 4).
- Produces (module `scripts.enrich_chunks`): `BATCH_CHUNKS = 12`, `SYSTEM` prompt, `async _complete(system, user) -> Optional[dict]`, `make_batches(chunks, todo_ids, size=BATCH_CHUNKS) -> list[list[TranscriptChunk]]`, `validate_batch(raw, ids) -> tuple[dict[str, dict], list[dict]]`, `async enrich(chunks, enrich_dir=ENRICH_DIR, glossary_dir=GLOSSARY_DIR, *, limit=None, force=False, concurrency=4) -> dict` (stats `{"calls", "enriched", "skipped_fresh", "failed_batches"}`). Each saved entry is `{"text_sha", "summary", "keywords", "questions"}`.

- [ ] **Step 1: Write the glossary**

`backend/data/glossary/custom-library.json` (both fixes verified in the seed on 2026-10-06: "iffy" in `custom-library-8-0-1/2`, "model pattern" for "module pattern" in `custom-library-5-2-0`):

```json
{
  "replacements": [
    {"pattern": "\\biffy\\b", "replace": "IIFE"},
    {"pattern": "\\bmodel pattern(s?)\\b", "replace": "module pattern\\1"}
  ]
}
```

- [ ] **Step 2: Write the failing tests**

`backend/tests/test_enrich_chunks.py`:

```python
import json

from app.models import TranscriptChunk
from app.retrieval import enrichment as en
from scripts import enrich_chunks as ec


def _chunks(texts, lecture="custom-library-5-2"):
    return [TranscriptChunk(chunk_id=f"{lecture}-{i}", course_id="custom-library", course_title="Build a Custom Library",
                            lecture_id=lecture, lecture_title="6.5 - IIFE, To The Rescue", text=t,
                            start_time=60 * i, end_time=60 * i + 60) for i, t in enumerate(texts)]


def _reply(ids, fixes=()):
    return {"chunks": [{"id": i, "summary": f"about {i}", "keywords": ["IIFE", "scope"],
                        "questions": [f"what is {i}?"]} for i in ids], "fixes": list(fixes)}


def test_validate_batch_keeps_only_sent_ids_and_cleans_fields():
    raw = {"chunks": [
        {"id": "a", "summary": " s ", "keywords": ["k"] * 3 + [f"k{n}" for n in range(10)],
         "questions": [f"q{n}?" for n in range(5)]},
        {"id": "zzz", "summary": "s", "keywords": ["k"], "questions": ["q?"]},
        {"id": "b", "summary": "", "keywords": ["k"], "questions": ["q?"]},
    ], "fixes": [{"heard": "iffy", "means": "IIFE"}, {"heard": "", "means": "x"}]}
    entries, fixes = ec.validate_batch(raw, {"a", "b"})
    assert list(entries) == ["a"]                                   # zzz never sent, b has no summary
    assert entries["a"]["summary"] == "s"
    assert entries["a"]["keywords"] == ["k"] + [f"k{n}" for n in range(7)]   # deduped, max 8
    assert len(entries["a"]["questions"]) == 3
    assert fixes == [{"heard": "iffy", "means": "IIFE"}]
    assert ec.validate_batch(None, {"a"}) == ({}, [])


def test_batches_stay_inside_one_lecture_and_respect_the_size():
    chunks = _chunks(["t"] * 13) + _chunks(["u"] * 2, lecture="custom-library-9-0")
    out = ec.make_batches(chunks, {c.chunk_id for c in chunks}, size=12)
    assert [len(b) for b in out] == [12, 1, 2]
    assert all(len({c.lecture_id for c in b}) == 1 for b in out)


async def test_enrich_is_resumable_idempotent_and_keyed_by_text(tmp_path, monkeypatch):
    calls = []

    async def fake(system, user):
        ids = [line.split("]")[0][1:] for line in user.splitlines() if line.startswith("[")]
        calls.append(ids)
        return _reply(ids, fixes=[{"heard": "iffy", "means": "IIFE"}])

    monkeypatch.setattr(ec, "_complete", fake)
    e, g = tmp_path / "enrichment", tmp_path / "glossary"
    chunks = _chunks(["one"] * 13)
    s1 = await ec.enrich(chunks, e, g, limit=1)
    assert s1["calls"] == 1 and s1["enriched"] == 12
    assert len(en.load_enrichment("custom-library", e)) == 12      # saved after the batch: resumable
    s2 = await ec.enrich(chunks, e, g)
    assert s2["calls"] == 1 and s2["enriched"] == 1 and s2["skipped_fresh"] == 12
    s3 = await ec.enrich(chunks, e, g)
    assert s3["calls"] == 0                                         # idempotent
    chunks[0].text = "edited"
    s4 = await ec.enrich(chunks, e, g)
    assert s4["calls"] == 1 and s4["enriched"] == 1                 # stale text_sha -> re-enriched
    entry = en.load_enrichment("custom-library", e)["custom-library-5-2-0"]
    assert entry["text_sha"] == en.text_sha("edited")
    sugg = json.loads((g / "custom-library.suggested.json").read_text())
    assert sugg["iffy"]["means"] == "IIFE" and sugg["iffy"]["count"] >= 1
    assert sorted(p.name for p in tmp_path.rglob("*") if p.is_file()) == ["custom-library.json",
                                                                          "custom-library.suggested.json"]


async def test_a_failed_batch_is_reported_and_saves_nothing(tmp_path, monkeypatch):
    async def boom(system, user):
        raise TimeoutError("slow")

    monkeypatch.setattr(ec, "_complete", boom)
    s = await ec.enrich(_chunks(["one", "two"]), tmp_path / "e", tmp_path / "g")
    assert s["failed_batches"] == 1 and s["enriched"] == 0
    assert en.load_enrichment("custom-library", tmp_path / "e") == {}
```

- [ ] **Step 3: Run the tests to verify they fail**

Run: `cd backend && .venv/bin/pytest tests/test_enrich_chunks.py -q`
Expected: FAIL — `ImportError: cannot import name 'enrich_chunks' from 'scripts'`.

- [ ] **Step 4: Implement the script**

`backend/scripts/enrich_chunks.py`:

```python
"""Offline chunk enrichment (spec §3): summary, keywords and likely questions per transcript chunk,
written by gpt-4.1-mini, one call per batch of ≤ 12 consecutive chunks of one lecture. Results go to
backend/data/enrichment/<slug>.json keyed by chunk_id + text hash (see app/retrieval/enrichment.py),
saved after every batch, so the run is resumable; fresh entries are skipped, so it is idempotent.
Suspected speech-to-text errors are collected in backend/data/glossary/<slug>.suggested.json for a
human to copy into <slug>.json — never applied automatically. Never changes the seed.

Run from backend/ with the key inline and the database off:
  env OPENAI_API_KEY=... DATABASE_URL= .venv/bin/python scripts/enrich_chunks.py [--only slug] [--limit N] [--force]
"""
import argparse
import asyncio
import json
import os
import sys
from pathlib import Path
from typing import Optional

BACKEND = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND))

from app.models import TranscriptChunk  # noqa: E402
from app.retrieval.enrichment import (ENRICH_DIR, GLOSSARY_DIR, apply_enrichment, load_enrichment,  # noqa: E402
                                      save_enrichment, text_sha)

SEED = BACKEND / "app" / "data" / "seed_transcripts.json"
MODEL = "gpt-4.1-mini"
BATCH_CHUNKS = 12

SYSTEM = """You index lecture transcripts for a course search engine. For each passage you are given, write:
- summary: one sentence (at most 30 words) saying what the passage teaches or shows, in plain words. Name the concrete technique, command or term. Never start with "In this passage" or mention "the instructor".
- keywords: 3 to 8 search terms a student might type for this passage: technical terms, acronyms, commands, function or package names, written the standard way (e.g. "IIFE", "npm link", "useMemo", "ES modules"). Correct obvious speech-to-text spellings in keywords (e.g. "iffy" -> "IIFE").
- questions: 2 or 3 short questions a student could ask that this passage answers. Each must make sense on its own (never "in this video" or "in this lecture").
Also list "fixes": words in the passages that look like speech-to-text mistakes for technical terms, as {"heard": "<word as written>", "means": "<correct term>"}; [] if none. Only list fixes you are confident about.
The passages are consecutive parts of one lecture: use the neighbouring passages for context, but describe each passage on its own.
Return only JSON: {"chunks": [{"id": "<passage id>", "summary": "...", "keywords": ["..."], "questions": ["..."]}], "fixes": [{"heard": "...", "means": "..."}]}"""


async def _complete(system: str, user: str) -> Optional[dict]:
    from app.services.llm import llm
    return await llm.generate_json(system, user, temperature=0.2, max_tokens=2000)


def _user(batch: list[TranscriptChunk]) -> str:
    c0 = batch[0]
    body = "\n".join(f"[{c.chunk_id}] {c.text_clean or c.text}" for c in batch)
    return f"Course: {c0.course_title}\nChapter: {c0.chapter}\nLecture: {c0.lecture_title}\n\nPassages:\n{body}"


def make_batches(chunks: list[TranscriptChunk], todo_ids: set[str], size: int = BATCH_CHUNKS):
    by_lecture: dict[str, list[TranscriptChunk]] = {}
    for c in chunks:
        if c.chunk_id in todo_ids:
            by_lecture.setdefault(c.lecture_id, []).append(c)
    return [group[i:i + size] for group in by_lecture.values() for i in range(0, len(group), size)]


def _strings(v, limit: int, max_len: int) -> list[str]:
    out: list[str] = []
    for s in v if isinstance(v, list) else []:
        s = str(s).strip()
        if s and len(s) <= max_len and s not in out:
            out.append(s)
    return out[:limit]


def validate_batch(raw: Optional[dict], ids: set[str]) -> tuple[dict[str, dict], list[dict]]:
    if not isinstance(raw, dict):
        return {}, []
    entries: dict[str, dict] = {}
    for item in raw.get("chunks") or []:
        if not isinstance(item, dict) or item.get("id") not in ids or item["id"] in entries:
            continue
        summary = str(item.get("summary") or "").strip()
        keywords = _strings(item.get("keywords"), 8, 40)
        questions = _strings(item.get("questions"), 3, 200)
        if summary and len(summary) <= 300 and keywords and questions:
            entries[item["id"]] = {"summary": summary, "keywords": keywords, "questions": questions}
    fixes = [{"heard": str(f["heard"]).strip(), "means": str(f["means"]).strip()}
             for f in raw.get("fixes") or []
             if isinstance(f, dict) and str(f.get("heard") or "").strip() and str(f.get("means") or "").strip()]
    return entries, fixes


def _save_suggestions(slug: str, fixes: list[tuple[dict, str]], glossary_dir: Path) -> None:
    p = Path(glossary_dir) / f"{slug}.suggested.json"
    data = json.loads(p.read_text()) if p.exists() else {}
    for fix, chunk_id in fixes:
        row = data.setdefault(fix["heard"], {"means": fix["means"], "count": 0, "chunk_ids": []})
        row["count"] += 1
        if chunk_id not in row["chunk_ids"]:
            row["chunk_ids"].append(chunk_id)
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.with_name(p.name + ".tmp")
    tmp.write_text(json.dumps(dict(sorted(data.items())), indent=1, ensure_ascii=False) + "\n")
    os.replace(tmp, p)


async def enrich(chunks: list[TranscriptChunk], enrich_dir: Path = ENRICH_DIR, glossary_dir: Path = GLOSSARY_DIR,
                 *, limit: Optional[int] = None, force: bool = False, concurrency: int = 4) -> dict:
    chunks = apply_enrichment(chunks, enrich_dir, glossary_dir)   # chapter + text_clean for the prompt
    stats = {"calls": 0, "enriched": 0, "skipped_fresh": 0, "failed_batches": 0}
    entries = {slug: load_enrichment(slug, enrich_dir) for slug in dict.fromkeys(c.course_id for c in chunks)}
    todo = set()
    for c in chunks:
        e = entries[c.course_id].get(c.chunk_id)
        if not force and e and e.get("text_sha") == text_sha(c.text):
            stats["skipped_fresh"] += 1
        else:
            todo.add(c.chunk_id)
    batches = make_batches(chunks, todo)
    if limit is not None:
        batches = batches[:limit]
    sem, lock = asyncio.Semaphore(concurrency), asyncio.Lock()

    async def one(batch: list[TranscriptChunk]):
        slug = batch[0].course_id
        async with sem:
            stats["calls"] += 1
            try:
                got, fixes = validate_batch(await _complete(SYSTEM, _user(batch)), {c.chunk_id for c in batch})
            except Exception as e:  # noqa: BLE001 — one batch failing must not stop the run
                print(f"  {batch[0].lecture_id}: {e!r}")
                got, fixes = {}, []
            if not got:
                stats["failed_batches"] += 1
                return
            async with lock:  # one writer per file; saved after every batch (resumable)
                for c in batch:
                    if c.chunk_id in got:
                        entries[slug][c.chunk_id] = {"text_sha": text_sha(c.text), **got[c.chunk_id]}
                        stats["enriched"] += 1
                save_enrichment(slug, entries[slug], MODEL, enrich_dir)
                if fixes:
                    _save_suggestions(slug, [(f, batch[0].chunk_id) for f in fixes], glossary_dir)

    await asyncio.gather(*(one(b) for b in batches))
    return stats


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--only", help="only this course slug")
    ap.add_argument("--limit", type=int, help="at most N LLM calls (trial run)")
    ap.add_argument("--force", action="store_true", help="re-enrich even fresh entries")
    ap.add_argument("--concurrency", type=int, default=4)
    a = ap.parse_args(argv)
    chunks = [TranscriptChunk(**c) for c in json.loads(SEED.read_text())]
    if a.only:
        chunks = [c for c in chunks if c.course_id == a.only]
    stats = asyncio.run(enrich(chunks, limit=a.limit, force=a.force, concurrency=a.concurrency))
    print(stats)
    return 1 if stats["failed_batches"] else 0


if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 5: Run the tests to verify they pass**

Run: `cd backend && .venv/bin/pytest tests/test_enrich_chunks.py tests/test_enrichment.py -q`
Expected: PASS.

- [ ] **Step 6: Run the enrichment (real model) — trial, review, full**

Trial — two batches of custom-library, then read the result:

```bash
cd backend && env OPENAI_API_KEY="$(grep '^OPENAI_API_KEY=' /Users/swanandkadam/Desktop/01dev-React-hermes/backend/.env | cut -d= -f2- | tr -d '"')" DATABASE_URL= .venv/bin/python scripts/enrich_chunks.py --only custom-library --limit 2
```

Expected: `{'calls': 2, 'enriched': ~24, 'skipped_fresh': 0, 'failed_batches': 0}`. Open `backend/data/enrichment/custom-library.json`: summaries are one plain sentence, keywords are real terms (standard spelling), questions are self-contained. Then the full run (resumes; ~1,300 remaining chunks in ~130–200 calls):

```bash
cd backend && env OPENAI_API_KEY="$(grep '^OPENAI_API_KEY=' /Users/swanandkadam/Desktop/01dev-React-hermes/backend/.env | cut -d= -f2- | tr -d '"')" DATABASE_URL= .venv/bin/python scripts/enrich_chunks.py
```

Expected: `failed_batches: 0` (if not, rerun the same command — only missing chunks are requested) and `skipped_fresh + enriched == 1329` across runs. Check coverage:

```bash
cd backend && .venv/bin/python -c "
import json
from app.models import TranscriptChunk
from app.retrieval.enrichment import apply_enrichment
cs = apply_enrichment([TranscriptChunk(**c) for c in json.load(open('app/data/seed_transcripts.json'))])
print(sum(bool(c.summary) for c in cs), '/', len(cs), 'enriched')"
```

Expected: `1329 / 1329 enriched`.

Review `backend/data/glossary/*.suggested.json`: copy into that course's `<slug>.json` only entries where `means` is a technical term and the `heard` spelling is never a correct word in that course's transcripts (check with `grep -c -i '\b<heard>\b' backend/app/data/seed_transcripts.json` and read two hits). Glossary changes do not need re-enrichment (entries are keyed by raw text).

- [ ] **Step 7: Commit**

```bash
git add backend/scripts/enrich_chunks.py backend/tests/test_enrich_chunks.py backend/data/glossary/ backend/data/enrichment/
git commit -m "feat(retrieval): offline chunk enrichment (summary, keywords, questions) + glossary; enrich all 1,329 chunks

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

(`backend/data/glossary/` and `backend/data/enrichment/` contain only files this task created.)

### Task 7: Phase 2 eval delta

**Files:**
- Create (generated): `backend/eval/retrieval/reports/phase2-enriched.json`, `.md`; Modify: `backend/eval/retrieval/reports/HISTORY.md`

- [ ] **Step 1: Run the eval on enriched embeddings (legacy decision logic)**

```bash
cd backend && env OPENAI_API_KEY="$(grep '^OPENAI_API_KEY=' /Users/swanandkadam/Desktop/01dev-React-hermes/backend/.env | cut -d= -f2- | tr -d '"')" DATABASE_URL= .venv/bin/python scripts/eval_retrieval.py --system legacy --label phase2-enriched --compare phase1-baseline
```

Expected: the first run embeds 1,329 chunks into `backend/data/cache/embeddings/` (14 calls of ≤ 100), later runs reuse it. The report ends with a `Delta: phase1-baseline → phase2-enriched` table. Recall@5 and MRR should rise; coverage accuracy may move either way because the 0.54/0.40 thresholds were calibrated on raw-text embeddings — that is expected and is why Phases 2–3 are not deployed alone.

- [ ] **Step 2: Commit the numbers**

```bash
git add backend/eval/retrieval/reports/phase2-enriched.json backend/eval/retrieval/reports/phase2-enriched.md backend/eval/retrieval/reports/HISTORY.md
git commit -m "eval(retrieval): phase 2 delta — enriched embed_text

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

# Phase 3 — Retriever interface + MemoryRetriever hybrid (vector + BM25 + RRF + scope)

### Task 8: Tokenizer + BM25 index

**Why pure Python (design decision):** the corpus is 1,329 chunks today and lexical search runs in Postgres in prod (Task 19), so the in-memory BM25 only serves local runs and tests. A ~60-line index (postings + Okapi BM25, k1 = 1.2, b = 0.75) needs no dependency (`rank_bm25` would pull numpy) and lets the tokenizer be ours — the same tokens are written to the Postgres `search_tsv` with the `simple` config, so both backends see identical terms (no English stemmer turning "np" or "IIFE" into something else).

**Files:**
- Modify: `backend/app/retrieval/text.py` (add `tokenize`, `lexical_fields`, `lexical_doc`)
- Create: `backend/app/retrieval/bm25.py`
- Test: `backend/tests/test_retrieval_text.py`, `backend/tests/test_bm25.py`

**Interfaces:**
- Consumes: `TranscriptChunk` with Task 4 fields.
- Produces:
  - `app.retrieval.text.tokenize(text: str) -> list[str]` — lowercase `[a-z0-9]+` tokens, ≥ 2 chars, English stopwords removed, light plural stemming, camelCase identifiers (`useMemo`) emitted whole **and** split (`usememo`, `use`, `memo`), acronyms kept (`IIFE` → `iife`, `np` → `np`).
  - `app.retrieval.text.lexical_fields(chunk) -> tuple[list[str], list[str], list[str]]` — (A: lecture title + keywords, B: summary + questions, C: `text_clean or text`), each tokenized.
  - `app.retrieval.text.lexical_doc(chunk) -> list[str]` — `A*3 + B*2 + C` (field weighting by repetition).
  - `app.retrieval.bm25.BM25Index(docs: list[list[str]], k1=1.2, b=0.75)` with `search(query_tokens: list[str], allowed: Optional[set[int]], k: int) -> list[tuple[int, float]]` (doc position, score), best first, ties by position.

- [ ] **Step 1: Write the failing tests**

`backend/tests/test_retrieval_text.py`:

```python
from app.models import TranscriptChunk
from app.retrieval.text import lexical_doc, lexical_fields, tokenize


def test_tokenize_keeps_acronyms_and_code_tokens():
    assert tokenize("What is an IIFE?") == ["iife"]
    assert tokenize("publish with np") == ["publish", "np"]
    assert tokenize("useMemo vs React.memo") == ["usememo", "use", "memo", "vs", "react", "memo"]
    assert tokenize("innerHTML") == ["innerhtml", "inner", "html"]
    assert tokenize("ES modules and npm packages") == ["es", "module", "npm", "package"]
    assert tokenize("dependencies") == ["dependency"]


def test_tokenize_does_not_split_brand_names_or_mangle_short_words():
    assert tokenize("JavaScript and TypeScript") == ["javascript", "typescript"]
    assert tokenize("class status analysis uses") == ["class", "status", "analysis", "uses"]
    assert tokenize("a 6 x") == []
    assert tokenize("8.1 - The `npm link` command") == ["npm", "link", "command"]


def test_lexical_fields_and_weighted_doc():
    c = TranscriptChunk(chunk_id="x", course_id="c", course_title="C", lecture_id="l", lecture_title="6.5 - IIFE",
                        text="raw iffy", start_time=0, end_time=1, text_clean="clean IIFE body", summary="wraps code",
                        keywords=["module pattern"], questions=["what is scope?"])
    a, b, cc = lexical_fields(c)
    assert a == ["iife", "module", "pattern"] and b == ["wrap", "code", "scope"] and cc == ["clean", "iife", "body"]
    doc = lexical_doc(c)
    assert doc.count("iife") == 3 + 1 and doc.count("wrap") == 2 and doc.count("body") == 1
```

`backend/tests/test_bm25.py`:

```python
from app.retrieval.bm25 import BM25Index


DOCS = [["iife", "scope", "function"], ["npm", "publish", "np", "np"], ["module", "scope"], ["np"] + ["filler"] * 40]


def test_rare_term_and_term_frequency_rank_first():
    idx = BM25Index(DOCS)
    out = idx.search(["np"], None, 10)
    assert [i for i, _ in out] == [1, 3]                    # tf 2 in a short doc beats tf 1 in a long doc
    assert out[0][1] > out[1][1] > 0


def test_allowed_positions_filter_and_k():
    idx = BM25Index(DOCS)
    assert [i for i, _ in idx.search(["scope"], {2}, 10)] == [2]
    assert len(idx.search(["scope"], None, 1)) == 1
    assert idx.search(["missing"], None, 10) == []
    assert idx.search([], None, 10) == []


def test_repeated_query_terms_count_once_and_ties_break_by_position():
    idx = BM25Index([["a1", "b1"], ["a1", "b1"]])
    assert idx.search(["a1", "a1"], None, 5) == idx.search(["a1"], None, 5)
    assert [i for i, _ in idx.search(["a1"], None, 5)] == [0, 1]


def test_empty_corpus():
    assert BM25Index([]).search(["np"], None, 5) == []
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `cd backend && .venv/bin/pytest tests/test_retrieval_text.py tests/test_bm25.py -q`
Expected: FAIL — `ImportError: cannot import name 'tokenize'` / `No module named 'app.retrieval.bm25'`.

- [ ] **Step 3: Implement**

Append to `backend/app/retrieval/text.py`:

```python
_WORD = re.compile(r"[A-Za-z0-9]+")
_CAMEL_PART = re.compile(r"[A-Z]+(?=[A-Z][a-z])|[A-Z]?[a-z]+|[A-Z]+|[0-9]+")
_STOP = frozenset("""
a an the and or but if then else of to in on at by for with from as is are was were be been being it its this
that these those there here we you he she they me my our your their them his her what which who whom when where
why how do does did doing done can could would should will shall may might must not no so just also about into
over under up down out than too very more most some any all each other such only own same both few again once
let lets get got go going gonna wanna like okay ok yeah um uh""".split())


def _stem(t: str) -> str:
    if len(t) > 4 and t.endswith("ies"):
        return t[:-3] + "y"
    if len(t) > 4 and t.endswith("s") and not t.endswith(("ss", "us", "is")):
        return t[:-1]
    return t


def tokenize(text: str) -> list[str]:
    """Search tokens shared by BM25 and the Postgres search_tsv ('simple' config over these tokens).
    Acronyms and short code words survive (IIFE, np, js); camelCase identifiers that start lowercase
    (useMemo, innerHTML) are kept whole and split; PascalCase brand names (JavaScript) are not split."""
    out: list[str] = []
    for raw in _WORD.findall(text or ""):
        low = raw.lower()
        variants = [low]
        if raw[0].islower() and any(ch.isupper() for ch in raw[1:]):
            parts = [p.lower() for p in _CAMEL_PART.findall(raw)]
            if len(parts) > 1:
                variants += parts
        for tok in variants:
            if len(tok) >= 2 and tok not in _STOP:
                out.append(_stem(tok))
    return out


def lexical_fields(chunk) -> tuple[list[str], list[str], list[str]]:
    """(A, B, C) = (lecture title + keywords, summary + questions, text) — the Postgres setweight A/B/C."""
    a = tokenize(chunk.lecture_title + " " + " ".join(chunk.keywords))
    b = tokenize(chunk.summary + " " + " ".join(chunk.questions))
    c = tokenize(chunk.text_clean or chunk.text)
    return a, b, c


def lexical_doc(chunk) -> list[str]:
    a, b, c = lexical_fields(chunk)
    return a * 3 + b * 2 + c
```

`backend/app/retrieval/bm25.py`:

```python
"""Okapi BM25 over pre-tokenized docs (app.retrieval.text.lexical_doc), pure Python.
idf = ln(1 + (N - df + 0.5) / (df + 0.5)); a query term counts once however often it is typed."""
import math
from collections import Counter, defaultdict
from typing import Optional


class BM25Index:
    def __init__(self, docs: list[list[str]], k1: float = 1.2, b: float = 0.75):
        self.k1, self.b = k1, b
        self.lens = [len(d) for d in docs]
        self.avg = (sum(self.lens) / len(docs)) if docs else 1.0
        self.postings: dict[str, list[tuple[int, int]]] = defaultdict(list)
        for i, d in enumerate(docs):
            for term, tf in Counter(d).items():
                self.postings[term].append((i, tf))
        n = len(docs)
        self.idf = {t: math.log(1 + (n - len(p) + 0.5) / (len(p) + 0.5)) for t, p in self.postings.items()}

    def search(self, query_tokens: list[str], allowed: Optional[set[int]], k: int) -> list[tuple[int, float]]:
        scores: dict[int, float] = defaultdict(float)
        for term in dict.fromkeys(query_tokens):
            for i, tf in self.postings.get(term, ()):
                if allowed is not None and i not in allowed:
                    continue
                norm = tf + self.k1 * (1 - self.b + self.b * self.lens[i] / (self.avg or 1.0))
                scores[i] += self.idf[term] * tf * (self.k1 + 1) / norm
        return sorted(scores.items(), key=lambda t: (-t[1], t[0]))[:k]
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `cd backend && .venv/bin/pytest tests/test_retrieval_text.py tests/test_bm25.py -q`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add backend/app/retrieval/text.py backend/app/retrieval/bm25.py backend/tests/test_retrieval_text.py backend/tests/test_bm25.py
git commit -m "feat(retrieval): acronym/camelCase-aware tokenizer and pure-Python BM25 with field weighting

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

### Task 9: `Retriever` protocol, RRF fusion, `MemoryRetriever`, `pipeline.search`

**Files:**
- Create: `backend/app/retrieval/base.py`, `backend/app/retrieval/memory.py`, `backend/app/retrieval/factory.py`, `backend/app/retrieval/pipeline.py`
- Test: `backend/tests/test_rrf.py`, `backend/tests/test_retriever_contract.py`, `backend/tests/test_retrieval_pipeline.py`

**Interfaces:**
- Consumes: `tokenize`, `lexical_doc`, `norm_title` (Tasks 4, 8); `BM25Index` (Task 8); `vector_store` (`chunks`, `_embeddings`, `_norms`, `_course_idx`, `_ensure_index()`, `initialize()`); `embedding_service.embed(text) -> list[float]`; `catalog_service.all_courses()`.
- Produces:
  - `app.retrieval.base`:
    ```python
    RRF_K = 60

    @dataclass
    class Candidate:
        chunk: TranscriptChunk
        vec_rank: Optional[int] = None     # best 1-based rank in any vector list (None = not in a vector top-k)
        lex_rank: Optional[int] = None     # best 1-based rank in any lexical list
        vec_score: Optional[float] = None  # cosine similarity
        lex_score: Optional[float] = None  # BM25 (memory) / ts_rank (pg)
        fused: float = 0.0                 # Σ 1/(RRF_K + rank) over every list it appears in

    class Retriever(Protocol):
        name: str
        async def vector_search(self, embedding: list[float], scope: Sequence[str], k: int,
                                lecture_id: Optional[str] = None) -> list[tuple[TranscriptChunk, float]]: ...
        async def lexical_search(self, tokens: list[str], scope: Sequence[str], k: int,
                                 lecture_id: Optional[str] = None) -> list[tuple[TranscriptChunk, float]]: ...

    def rrf_fuse(vec_lists, lex_lists, *, limit: int = 12, per_lecture: Optional[int] = 3,
                 k: int = RRF_K) -> list[Candidate]
    ```
    Both search methods return best-first `(chunk, score)` pairs **only from courses in `scope`** (and only from `lecture_id` when given); an empty scope returns `[]`.
  - `app.retrieval.memory.MemoryRetriever(store=vector_store)` implementing `Retriever` (`name = "memory"`).
  - `app.retrieval.factory.get_retriever() -> Retriever`, `set_retriever(r) -> None` (Task 23 adds `init_retriever()`).
  - `app.retrieval.pipeline`: constants `VEC_K = 30`, `LEX_K = 30`, `LIMIT = 12`, `PER_LECTURE = 3`; `async search(question, scope, *, lecture_id=None, limit=LIMIT, per_lecture=PER_LECTURE, extra_queries=(), extra_terms=()) -> list[Candidate]`; `ask_scope(enrolled_ids: set[int]) -> tuple[str, ...]`; `lecture_id_for(slug: str, lecture_title: str) -> Optional[str]`.

- [ ] **Step 1: Write the failing tests**

`backend/tests/test_rrf.py`:

```python
from app.models import TranscriptChunk
from app.retrieval.base import RRF_K, rrf_fuse


def _c(cid, lecture):
    return TranscriptChunk(chunk_id=cid, course_id="c", course_title="C", lecture_id=lecture, lecture_title=lecture,
                           text=cid, start_time=0, end_time=1)


A, B, C, D, E = _c("a", "L1"), _c("b", "L1"), _c("c", "L2"), _c("d", "L1"), _c("e", "L1")


def test_rrf_formula_ranks_and_scores():
    out = rrf_fuse([[(A, 0.9), (C, 0.5)]], [[(C, 7.0), (B, 3.0)]], limit=10, per_lecture=None)
    assert [x.chunk.chunk_id for x in out] == ["c", "a", "b"]
    c = out[0]
    assert c.fused == 1 / (RRF_K + 2) + 1 / (RRF_K + 1)
    assert (c.vec_rank, c.lex_rank, c.vec_score, c.lex_score) == (2, 1, 0.5, 7.0)
    assert (out[1].vec_rank, out[1].lex_rank) == (1, None)


def test_per_lecture_cap_and_limit():
    vec = [[(A, 0.9), (B, 0.8), (D, 0.7), (E, 0.6), (C, 0.5)]]
    out = rrf_fuse(vec, [], limit=12, per_lecture=3)
    assert [x.chunk.chunk_id for x in out] == ["a", "b", "d", "c"]      # 4th chunk of L1 dropped
    assert len(rrf_fuse(vec, [], limit=2, per_lecture=3)) == 2


def test_multiple_lists_keep_the_best_rank_and_ties_prefer_vector_rank():
    out = rrf_fuse([[(A, 0.9)], [(B, 0.95), (A, 0.4)]], [[(B, 1.0)], [(A, 2.0)]], limit=5, per_lecture=None)
    a = next(x for x in out if x.chunk.chunk_id == "a")
    assert a.vec_rank == 1 and a.vec_score == 0.9 and a.lex_rank == 1
    assert rrf_fuse([], [], limit=5) == []
```

`backend/tests/test_retriever_contract.py` (Task 22 adds the `"pg"` backend to `BACKENDS`):

```python
"""One contract, every Retriever backend: scope filtering, lecture filtering, ranking, empty scope."""
import pytest

from app.models import TranscriptChunk
from app.retrieval.memory import MemoryRetriever
from app.retrieval.text import tokenize
from app.services.vector_store import InMemoryVectorStore

DIM = 1536
BACKENDS = ["memory"]


def vec(*weights):
    """Sparse test vector: weights for dims 0..3, the rest 0."""
    v = [0.0] * DIM
    for i, w in enumerate(weights):
        v[i] = w
    return v


def chunk(cid, slug, lecture_id, title, text):
    return TranscriptChunk(chunk_id=cid, course_id=slug, course_title=slug, lecture_id=lecture_id,
                           lecture_title=title, text=text, start_time=0, end_time=60)


CORPUS = [
    (chunk("cl-5-2-0", "custom-library", "cl-5-2", "6.5 - IIFE, To The Rescue",
           "the IIFE pattern gives a function its own scope"), vec(1, 0, 0, 0)),
    (chunk("cl-10-0-0", "custom-library", "cl-10-0", "11.1 - Publishing using np",
           "np runs the checks and publishes the package to npm"), vec(0, 1, 0, 0)),
    (chunk("cl-10-0-1", "custom-library", "cl-10-0", "11.1 - Publishing using np",
           "after np finishes the version is tagged"), vec(0, 0.9, 0.1, 0)),
    (chunk("rp-4-0-0", "react-perf", "rp-4-0", "5.1 - Virtualizing the Table",
           "virtualizing the table renders only visible rows"), vec(0, 0, 1, 0)),
    (chunk("rp-0-1-0", "react-perf", "rp-0-1", "1.2 - Render vs Commit",
           "React reconciliation compares the trees"), vec(0, 0, 0, 1)),
    (chunk("je-1-0-0", "js-engine", "je-1-0", "2.1 - Tokenization in V8",
           "the IIFE is parsed lazily by V8"), vec(0.8, 0, 0, 0.2)),
]


async def make_retriever(kind: str, corpus=CORPUS, request=None):
    if kind == "memory":
        store = InMemoryVectorStore()
        store.chunks = [c for c, _ in corpus]
        store._embeddings = [e for _, e in corpus]
        return MemoryRetriever(store)
    raise ValueError(kind)


@pytest.fixture(params=BACKENDS)
async def retriever(request):
    return await make_retriever(request.param, request=request)


def ids(pairs):
    return [c.chunk_id for c, _ in pairs]


async def test_vector_search_is_scoped_and_best_first(retriever):
    out = await retriever.vector_search(vec(1, 0, 0, 0), ["custom-library", "js-engine"], 10)
    assert ids(out)[:2] == ["cl-5-2-0", "je-1-0-0"]
    assert all(c.course_id in ("custom-library", "js-engine") for c, _ in out)
    assert out[0][1] == pytest.approx(1.0, abs=1e-6)
    assert ids(await retriever.vector_search(vec(1, 0, 0, 0), ["js-engine"], 10)) == ["je-1-0-0"]
    assert len(await retriever.vector_search(vec(0, 1, 0, 0), ["custom-library"], 1)) == 1


async def test_lexical_search_finds_acronyms_scoped(retriever):
    out = await retriever.lexical_search(tokenize("what is an IIFE?"), ["custom-library", "js-engine"], 10)
    assert ids(out) == ["cl-5-2-0", "je-1-0-0"]        # title (weight A) outranks body-only
    assert ids(await retriever.lexical_search(tokenize("IIFE"), ["react-perf"], 10)) == []
    assert set(ids(await retriever.lexical_search(tokenize("np"), ["custom-library"], 10))) == {"cl-10-0-0",
                                                                                                  "cl-10-0-1"}


async def test_lecture_filter(retriever):
    out = await retriever.lexical_search(tokenize("np"), ["custom-library"], 10, lecture_id="cl-10-0")
    assert set(ids(out)) == {"cl-10-0-0", "cl-10-0-1"}
    vout = await retriever.vector_search(vec(0, 1, 0, 0), ["custom-library"], 10, lecture_id="cl-10-0")
    assert set(ids(vout)) == {"cl-10-0-0", "cl-10-0-1"}


async def test_empty_scope_returns_nothing(retriever):
    assert await retriever.vector_search(vec(1, 0, 0, 0), [], 10) == []
    assert await retriever.lexical_search(["iife"], [], 10) == []
    assert await retriever.lexical_search([], ["custom-library"], 10) == []
```

`backend/tests/test_retrieval_pipeline.py` (Tasks 13, 18 and 23 append to this file):

```python
import pytest

from app.retrieval import factory, pipeline
from app.retrieval.memory import MemoryRetriever
from app.services import catalog_service
from app.services.embeddings import embedding_service
from app.services.vector_store import InMemoryVectorStore
from tests.test_retriever_contract import CORPUS, vec


@pytest.fixture
def mem(monkeypatch):
    store = InMemoryVectorStore()
    store.chunks = [c for c, _ in CORPUS]
    store._embeddings = [e for _, e in CORPUS]
    monkeypatch.setattr(pipeline, "vector_store", store)
    monkeypatch.setattr(factory, "_retriever", MemoryRetriever(store))
    embedded = []
    table = {"what is an IIFE?": vec(1, 0, 0, 0), "publish with np": vec(0, 1, 0, 0)}

    async def fake_embed(text):
        embedded.append(text)
        return table.get(text, vec(0, 0, 0, 1))

    monkeypatch.setattr(embedding_service, "embed", fake_embed)
    return embedded


async def test_search_fuses_vector_and_lexical_inside_the_scope(mem):
    out = await pipeline.search("what is an IIFE?", ["custom-library"])
    assert out[0].chunk.chunk_id == "cl-5-2-0"
    assert (out[0].vec_rank, out[0].lex_rank) == (1, 1)
    assert {c.chunk.course_id for c in out} == {"custom-library"}


async def test_search_empty_scope_embeds_nothing(mem):
    assert await pipeline.search("what is an IIFE?", []) == []
    assert mem == []


async def test_search_lecture_filter_and_extra_queries(mem):
    out = await pipeline.search("publish with np", ["custom-library"], lecture_id="cl-10-0", per_lecture=None)
    assert {c.chunk.lecture_id for c in out} == {"cl-10-0"}
    await pipeline.search("publish with np", ["custom-library"], extra_queries=["what is an IIFE?"])
    assert mem[-2:] == ["publish with np", "what is an IIFE?"]


def test_ask_scope_is_launched_and_owned_only(monkeypatch):
    courses = [{"id": 2, "slug": "custom-library", "launched": True},
               {"id": 9, "slug": "javascript-deep-dive", "launched": False},
               {"id": 4, "slug": "product-engineering", "launched": True}]
    monkeypatch.setattr(catalog_service, "all_courses", lambda: courses)
    assert pipeline.ask_scope({2, 9}) == ("custom-library",)
    assert pipeline.ask_scope({9, 11}) == ()
    assert pipeline.ask_scope(set()) == ()


def test_lecture_id_for_matches_loosely(mem):
    assert pipeline.lecture_id_for("custom-library", "11.1 - Publishing using `np`") == "cl-10-0"
    assert pipeline.lecture_id_for("custom-library", "9.9 - Nope") is None
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `cd backend && .venv/bin/pytest tests/test_rrf.py tests/test_retriever_contract.py tests/test_retrieval_pipeline.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'app.retrieval.base'` (and `.memory`, `.pipeline`).

- [ ] **Step 3: Implement**

`backend/app/retrieval/base.py`:

```python
"""Retriever contract + Reciprocal Rank Fusion (spec §2.3, §4). Backends implement only the two
searches; fusion, caps and limits live here once, so Memory and Pg can't drift apart."""
from dataclasses import dataclass
from typing import Optional, Protocol, Sequence, runtime_checkable

from app.models import TranscriptChunk

RRF_K = 60


@dataclass
class Candidate:
    chunk: TranscriptChunk
    vec_rank: Optional[int] = None
    lex_rank: Optional[int] = None
    vec_score: Optional[float] = None
    lex_score: Optional[float] = None
    fused: float = 0.0


@runtime_checkable
class Retriever(Protocol):
    name: str

    async def vector_search(self, embedding: list[float], scope: Sequence[str], k: int,
                            lecture_id: Optional[str] = None) -> list[tuple[TranscriptChunk, float]]: ...

    async def lexical_search(self, tokens: list[str], scope: Sequence[str], k: int,
                             lecture_id: Optional[str] = None) -> list[tuple[TranscriptChunk, float]]: ...


def rrf_fuse(vec_lists, lex_lists, *, limit: int = 12, per_lecture: Optional[int] = 3,
             k: int = RRF_K) -> list[Candidate]:
    """fused = Σ 1 / (k + rank) over every list a chunk appears in (rank is 1-based). Sorted by fused,
    then best vector rank, then chunk id; then at most `per_lecture` chunks per lecture, `limit` in all."""
    by_id: dict[str, Candidate] = {}
    for lists, kind in ((vec_lists, "vec"), (lex_lists, "lex")):
        for lst in lists:
            for rank, (chunk, score) in enumerate(lst, 1):
                cand = by_id.setdefault(chunk.chunk_id, Candidate(chunk=chunk))
                cand.fused += 1.0 / (k + rank)
                if kind == "vec":
                    if cand.vec_rank is None or rank < cand.vec_rank:
                        cand.vec_rank = rank
                    cand.vec_score = score if cand.vec_score is None else max(cand.vec_score, score)
                else:
                    if cand.lex_rank is None or rank < cand.lex_rank:
                        cand.lex_rank = rank
                    cand.lex_score = score if cand.lex_score is None else max(cand.lex_score, score)
    ordered = sorted(by_id.values(),
                     key=lambda c: (-c.fused, c.vec_rank if c.vec_rank is not None else 10 ** 9, c.chunk.chunk_id))
    out, per = [], {}
    for cand in ordered:
        lid = cand.chunk.lecture_id
        if per_lecture is not None and per.get(lid, 0) >= per_lecture:
            continue
        per[lid] = per.get(lid, 0) + 1
        out.append(cand)
        if len(out) == limit:
            break
    return out
```

Check `test_rrf_formula_ranks_and_scores`: `c` = 1/62 + 1/61 ≈ 0.03253; `a` = 1/61 ≈ 0.01639; `b` = 1/62 ≈ 0.01613 → order c, a, b. In `test_multiple_lists_…`, `a` keeps `vec_rank` 1 and `vec_score` 0.9 (max of 0.9 and 0.4).

`backend/app/retrieval/memory.py`:

```python
"""MemoryRetriever: the Retriever contract over the in-process vector_store (local runs, tests,
DATABASE_URL blank). Cosine over precomputed norms + BM25 over lexical_doc, both scope-filtered
BEFORE scoring, so another course's chunk is never scored, let alone returned."""
import math
from typing import Optional, Sequence

from app.models import TranscriptChunk
from app.retrieval.bm25 import BM25Index
from app.retrieval.text import lexical_doc


class MemoryRetriever:
    name = "memory"

    def __init__(self, store=None):
        if store is None:
            from app.services.vector_store import vector_store as store
        self.store = store
        self._bm25: Optional[BM25Index] = None
        self._bm25_key: tuple = ()

    def _scoped(self, scope: Sequence[str], lecture_id: Optional[str]) -> list[int]:
        self.store._ensure_index()
        idx = [i for slug in dict.fromkeys(scope) for i in self.store._course_idx.get(slug, [])]
        if lecture_id:
            idx = [i for i in idx if self.store.chunks[i].lecture_id == lecture_id]
        return idx

    def _index(self) -> BM25Index:
        key = (id(self.store.chunks), len(self.store.chunks))
        if self._bm25 is None or self._bm25_key != key:
            self._bm25 = BM25Index([lexical_doc(c) for c in self.store.chunks])
            self._bm25_key = key
        return self._bm25

    async def vector_search(self, embedding: list[float], scope: Sequence[str], k: int,
                            lecture_id: Optional[str] = None) -> list[tuple[TranscriptChunk, float]]:
        if not scope or not embedding:
            return []
        pos = self._scoped(scope, lecture_id)
        qn = math.sqrt(sum(x * x for x in embedding))
        embs, norms, n = self.store._embeddings, self.store._norms, len(self.store._embeddings)
        if not qn:
            return []
        scored = [(i, sum(x * y for x, y in zip(embedding, embs[i])) / (qn * norms[i]))
                  for i in pos if i < n and norms[i]]
        scored.sort(key=lambda t: (-t[1], t[0]))
        return [(self.store.chunks[i], s) for i, s in scored[:k]]

    async def lexical_search(self, tokens: list[str], scope: Sequence[str], k: int,
                             lecture_id: Optional[str] = None) -> list[tuple[TranscriptChunk, float]]:
        if not scope or not tokens:
            return []
        allowed = set(self._scoped(scope, lecture_id))
        if not allowed:
            return []
        return [(self.store.chunks[i], s) for i, s in self._index().search(tokens, allowed, k)]
```

`backend/app/retrieval/factory.py`:

```python
"""Which Retriever serves this process. Memory by default; Task 23's init_retriever() switches prod
(DATABASE_URL set) to PgRetriever at startup."""
from typing import Optional

from app.retrieval.base import Retriever

_retriever: Optional[Retriever] = None


def set_retriever(r: Optional[Retriever]) -> None:
    global _retriever
    _retriever = r


def get_retriever() -> Retriever:
    global _retriever
    if _retriever is None:
        from app.retrieval.memory import MemoryRetriever
        _retriever = MemoryRetriever()
    return _retriever
```

`backend/app/retrieval/pipeline.py` (Tasks 12 and 15 extend this file):

```python
"""The retrieval pipeline (spec §2): scope (code) → hybrid retrieval → [rerank + coverage, Task 13]
→ [query understanding, Task 18]. Every consumer (Ask lookup, player lookup, find_moment,
search_course_content) goes through here."""
import asyncio
from typing import Optional, Sequence

from app.retrieval import factory
from app.retrieval.base import Candidate, rrf_fuse
from app.retrieval.text import norm_title, tokenize
from app.services import catalog_service
from app.services.embeddings import embedding_service
from app.services.vector_store import vector_store

VEC_K = 30
LEX_K = 30
LIMIT = 12
PER_LECTURE = 3


def ask_scope(enrolled_ids: set[int]) -> tuple[str, ...]:
    """Ask citation policy F1, as a search scope: catalog courses that are launched AND owned."""
    return tuple(c["slug"] for c in catalog_service.all_courses()
                 if c.get("launched") and c.get("id") in enrolled_ids and c.get("slug"))


def lecture_id_for(slug: str, lecture_title: str) -> Optional[str]:
    want = norm_title(lecture_title or "")
    for c in vector_store.chunks:
        if c.course_id == slug and norm_title(c.lecture_title) == want:
            return c.lecture_id
    return None


async def _ensure_loaded() -> None:
    if not vector_store.chunks:
        await vector_store.initialize()


async def search(question: str, scope: Sequence[str], *, lecture_id: Optional[str] = None, limit: int = LIMIT,
                 per_lecture: Optional[int] = PER_LECTURE, extra_queries: Sequence[str] = (),
                 extra_terms: Sequence[str] = ()) -> list[Candidate]:
    """Vector top VEC_K + lexical top LEX_K for every query (the question plus any rewrites), all
    inside `scope`, fused with RRF. extra_terms (keywords) join the lexical queries only."""
    scope = tuple(dict.fromkeys(s for s in scope if s))
    if not scope:
        return []
    await _ensure_loaded()
    r = factory.get_retriever()
    queries = list(dict.fromkeys(q for q in (question, *extra_queries) if q and q.strip()))
    embeddings = await asyncio.gather(*(embedding_service.embed(q) for q in queries))
    terms = " ".join(extra_terms)
    lists = await asyncio.gather(
        *(r.vector_search(e, scope, VEC_K, lecture_id) for e in embeddings),
        *(r.lexical_search(tokenize(f"{q} {terms}"), scope, LEX_K, lecture_id) for q in queries))
    return rrf_fuse(lists[:len(queries)], lists[len(queries):], limit=limit, per_lecture=per_lecture)
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `cd backend && .venv/bin/pytest tests/test_rrf.py tests/test_retriever_contract.py tests/test_retrieval_pipeline.py -q`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add backend/app/retrieval/base.py backend/app/retrieval/memory.py backend/app/retrieval/factory.py backend/app/retrieval/pipeline.py backend/tests/test_rrf.py backend/tests/test_retriever_contract.py backend/tests/test_retrieval_pipeline.py
git commit -m "feat(retrieval): Retriever protocol, RRF fusion with per-lecture cap, MemoryRetriever (cosine + BM25), scoped search

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

### Task 10: Wire every search through the scoped hybrid pipeline (decision logic unchanged)

Phase 3 swaps the **candidate source** only: `search_in_course`, `search_in_lecture`, `_transcript_hits` and the Ask branch of `search_course_content` now call `pipeline.search` inside a code-computed scope, and return `(chunk, cosine)` pairs in fused order, so the existing threshold/title decision code keeps working unchanged until Phase 4 replaces it. The Ask path computes the F1 scope (launched AND owned) **before** searching — an owned-launched match can no longer be crowded out of a global top-k by unowned courses, and a student with no launched course triggers no search at all.

**Files:**
- Modify: `backend/app/services/course_lookup.py` (`_transcript_hits`, `search_in_course`, `search_in_lecture`, Ask branch of `course_lookup`)
- Modify: `backend/app/services/tutor_agent.py` (Ask branch of `search_course_content`)
- Modify: `backend/app/eval/retrieval_systems.py` (`LegacySystem` ask branch passes every slug)
- Test: `backend/tests/test_course_lookup.py`, `backend/tests/test_tutor_agent.py`, `backend/tests/test_vector_store_course_scope.py`, `backend/tests/test_eval_runner.py`

**Interfaces:**
- Consumes: `pipeline.search`, `pipeline.ask_scope`, `pipeline.lecture_id_for`, `pipeline.VEC_K`, `pipeline.LEX_K`, `Candidate` (Task 9).
- Produces (signatures after this task):
  - `course_lookup._transcript_hits(question: str, scope: Sequence[str], top_k: int = 8) -> list[tuple[TranscriptChunk, float]]`
  - `course_lookup.search_in_course(query, course_slug, top_k: Optional[int] = 8)` — `top_k=None` now means "the whole fused candidate list" (≤ `VEC_K + LEX_K`), no per-lecture cap.
  - `course_lookup.search_in_lecture(query, course_slug, lecture_title)` — fused order within that lecture; `[]` when the lecture has no transcript.
  - Scores in all three are the candidate's cosine (`vec_score`, `0.0` for lexical-only candidates).

- [ ] **Step 1: Update the tests first**

`backend/tests/test_course_lookup.py`:

1. Replace the `patch_sources` fixture so the fake takes the scope, honours it and records it:

```python
@pytest.fixture
def patch_sources(monkeypatch):
    # Pin thresholds so these tests don't depend on Task 9's calibrated values.
    monkeypatch.setattr(cl, "TRANSCRIPT_THRESHOLD", 0.35)
    monkeypatch.setattr(cl, "CATALOG_THRESHOLD", 0.35)
    seen_scopes: list = []

    def apply(transcripts=(), catalog=(), enrolled_ids=(), enrollment_error=False):
        async def fake_transcripts(question, scope, top_k=8):
            seen_scopes.append(tuple(scope))
            return [(c, s) for c, s in transcripts if c.course_id in scope]

        async def fake_catalog(query, top_k=5):
            return list(catalog)

        async def fake_enrolled(student_id):
            if enrollment_error:
                raise RuntimeError("db down")
            return [{"id": i, "title": f"course {i}", "purchased_at": "x"} for i in enrolled_ids]

        monkeypatch.setattr(cl, "_transcript_hits", fake_transcripts)
        monkeypatch.setattr(cl.catalog_index, "search", fake_catalog)
        monkeypatch.setattr(enrollment_service, "get_enrolled_courses", fake_enrolled)

    apply.scopes = seen_scopes
    return apply
```

Existing Ask tests whose transcripts are in a course outside the student's launched+owned scope now get no transcript hit from the fake — that is the new behaviour and their expected cases (`NO_MATCH` for the 9/11 demo student) do not change. In `patch_in_course`, change `no_global_transcripts(question, top_k=8)` to `no_global_transcripts(question, scope, top_k=8)`. In `test_lecture_title_steers_the_transcript_search_but_not_the_catalog`, change `fake_transcripts(question, top_k=8)` to `fake_transcripts(question, scope, top_k=8)` and call `patch_sources(enrolled_ids=[2])` (an empty scope no longer searches at all).

2. Add:

```python
async def test_ask_scope_is_launched_and_owned_before_searching(patch_sources):
    patch_sources(transcripts=[(NPM_CHUNK, 0.62), (MEMO_CHUNK, 0.9)], enrolled_ids=[2, 11])
    out = await cl.course_lookup("npm link", "demo")
    assert patch_sources.scopes == [("custom-library",)]      # 11 is owned but unlaunched: not searched
    assert {h.course_slug for h in out.hits} == {"custom-library"}


async def test_ask_with_no_launched_owned_course_never_searches(patch_sources, monkeypatch):
    patch_sources(transcripts=[(NPM_CHUNK, 0.62)], enrolled_ids=[9, 11])

    async def no_catalog(query, top_k=5):
        raise AssertionError("an empty Ask scope must not search the catalog either")

    monkeypatch.setattr(cl.catalog_index, "search", no_catalog)
    out = await cl.course_lookup("how do I publish an npm library", "demo")
    assert out.case == cl.LookupCase.NO_MATCH and out.hits == [] and patch_sources.scopes == []
```

3. Replace `test_search_in_course_keeps_only_that_course_best_first` and `test_search_in_lecture_scores_only_that_lectures_chunks` with:

```python
async def test_search_in_course_goes_through_the_scoped_pipeline(monkeypatch):
    from app.retrieval import pipeline
    from app.retrieval.base import Candidate
    calls = []

    async def fake_search(q, scope, **kw):
        calls.append((q, tuple(scope), kw))
        return [Candidate(chunk=PUBLISH_CHUNK, vec_rank=1, vec_score=0.6), Candidate(chunk=NPM_CHUNK, lex_rank=1)]

    monkeypatch.setattr(pipeline, "search", fake_search)
    assert await cl.search_in_course("publish", "custom-library", top_k=1) == [(PUBLISH_CHUNK, 0.6), (NPM_CHUNK, 0.0)]
    assert calls[0] == ("publish", ("custom-library",), {"limit": 1, "per_lecture": None})
    await cl.search_in_course("publish", "custom-library", top_k=None)
    assert calls[1][2]["limit"] == pipeline.VEC_K + pipeline.LEX_K


async def test_search_in_lecture_filters_by_the_resolved_lecture(monkeypatch):
    from app.retrieval import pipeline
    from app.retrieval.base import Candidate
    calls = []

    async def fake_search(q, scope, **kw):
        calls.append(kw)
        return [Candidate(chunk=NPM_CHUNK, vec_rank=1, vec_score=0.7)]

    monkeypatch.setattr(pipeline, "search", fake_search)
    monkeypatch.setattr(pipeline, "lecture_id_for",
                        lambda slug, title: "custom-library-7-0" if "npm link" in title else None)
    out = await cl.search_in_lecture("q", "custom-library", "8.1 - The `npm link` command")
    assert out == [(NPM_CHUNK, 0.7)] and calls[0]["lecture_id"] == "custom-library-7-0"
    assert await cl.search_in_lecture("q", "custom-library", "9.9 - No transcript") == []
    assert len(calls) == 1
```

`backend/tests/test_vector_store_course_scope.py` — replace `test_search_in_course_never_touches_other_courses_chunks` with:

```python
def test_search_in_course_never_touches_other_courses_chunks(monkeypatch):
    from app.retrieval import factory, pipeline
    from app.retrieval.memory import MemoryRetriever
    monkeypatch.setattr(embedding_service, "use_openai", True)
    st = _store()
    q = [0.5] * DIM
    seen = []

    class Spy(list):
        def __getitem__(self, i):
            seen.append(i)
            return list.__getitem__(self, i)

    st._embeddings = Spy(st._embeddings)
    st._ensure_index()
    seen.clear()

    async def fake_embed(_):
        return q

    monkeypatch.setattr(pipeline, "vector_store", st)
    monkeypatch.setattr(factory, "_retriever", MemoryRetriever(st))
    monkeypatch.setattr(embedding_service, "embed", fake_embed)
    out = asyncio.run(cl.search_in_course("x", "js-engine", top_k=None))
    assert out and all(c.course_id == "js-engine" for c, _ in out)
    assert seen and all(st.chunks[i].course_id == "js-engine" for i in seen)
    assert len(out) == 30          # every js-engine chunk (90 / 3) was scored; nothing else was
```

`backend/tests/test_tutor_agent.py`:

1. Rewrite `_ask_tool_setup` so the fake replaces `cl._transcript_hits` and honours the scope:

```python
def _ask_tool_setup(monkeypatch, enrolled_ids, rows):
    """rows: [(slug, course_title, lecture_id, lecture_title, score)] the scoped search can return."""
    from types import SimpleNamespace

    from app.models import TranscriptChunk
    from app.services import course_lookup as cl, enrollment_service

    async def fake_hits(q, scope, top_k=8):
        return [(TranscriptChunk(chunk_id=f"{s}-{i}", course_id=s, course_title=t, lecture_id=lid,
                                 lecture_title=lt, text="body", start_time=87, end_time=117), sc)
                for i, (s, t, lid, lt, sc) in enumerate(rows) if s in scope]

    async def fake_enrolled(student_id):
        assert student_id == "alice"
        return [{"id": i, "title": f"course {i}"} for i in enrolled_ids]

    monkeypatch.setattr(cl, "_transcript_hits", fake_hits)
    monkeypatch.setattr(enrollment_service, "get_enrolled_courses", fake_enrolled)
    return SimpleNamespace(context=tutor_agent.ChatContext(student_id="alice"))
```

2. In `test_follow_up_search_drops_results_below_the_transcript_threshold`, replace both `fake_retrieve`/`only_weak` stubs on `grounding.retrieve` with stubs on `course_lookup._transcript_hits` of signature `(q, scope, top_k=8)` returning `(chunk, score)` pairs (same chunks and scores as now).

3. In `test_follow_up_search_in_the_player_stays_in_this_course`, change `all_courses(q, top_k=5)` to `all_courses(q, scope, top_k=8)` and patch it onto `course_lookup._transcript_hits` instead of `grounding.retrieve`.

`backend/tests/test_eval_runner.py` — in `test_legacy_ask_and_navigate_mapping` change `async def hits(q, top_k=8)` to:

```python
    async def hits(q, scope, top_k=8):
        assert "custom-library" in scope and "react-perf" in scope     # ask mode: every course
        return [(_chunk("custom-library-5-2"), cl.TRANSCRIPT_THRESHOLD + 0.01), (_chunk("custom-library-9-0"), 0.1)]
```

- [ ] **Step 2: Run the updated tests to verify they fail**

Run: `cd backend && .venv/bin/pytest tests/test_course_lookup.py tests/test_tutor_agent.py tests/test_vector_store_course_scope.py tests/test_eval_runner.py -q`
Expected: FAIL — `TypeError: fake_transcripts() missing 1 required positional argument: 'scope'`-style errors, the new scope tests fail, and the pipeline-based search tests fail.

- [ ] **Step 3: Implement**

`backend/app/services/course_lookup.py` — add `from typing import Optional, Sequence` and `from app.retrieval import pipeline`; replace the three search helpers:

```python
async def _transcript_hits(question: str, scope: Sequence[str], top_k: int = 8):
    """Ask: best-first (chunk, cosine) from the hybrid search INSIDE the scope (launched AND owned)."""
    return [(c.chunk, c.vec_score or 0.0) for c in await pipeline.search(question, scope, limit=top_k)]


async def search_in_course(query: str, course_slug: str, top_k: Optional[int] = 8) -> list[tuple[TranscriptChunk, float]]:
    """Fused-order transcript chunks of ONE course (another course's chunk is never scored).
    top_k=None = the whole fused candidate list, no per-lecture cap."""
    limit = top_k if top_k is not None else pipeline.VEC_K + pipeline.LEX_K
    return [(c.chunk, c.vec_score or 0.0)
            for c in await pipeline.search(query, [course_slug], limit=limit, per_lecture=None)]


async def search_in_lecture(query: str, course_slug: str, lecture_title: str) -> list[tuple[TranscriptChunk, float]]:
    """Chunks of ONE lecture for the query, fused order; [] when that lecture has no transcript."""
    lid = pipeline.lecture_id_for(course_slug, lecture_title)
    if not lid:
        return []
    return [(c.chunk, c.vec_score or 0.0)
            for c in await pipeline.search(query, [course_slug], lecture_id=lid,
                                           limit=pipeline.VEC_K + pipeline.LEX_K, per_lecture=None)]
```

In `course_lookup()`'s Ask branch, compute the scope first and short-circuit:

```python
    scope_slugs = pipeline.ask_scope(enrolled_ids)
    if not scope_slugs:  # F1: nothing launched AND owned -> nothing to search, nothing to cite
        return CourseLookup(case=LookupCase.NO_MATCH, hits=[], enrolled_titles=[])
    hits: list[Hit] = []
    transcript_q = f"{scope.lecture_title} {question}" if scope.lecture_title else question
    for chunk, score in await _transcript_hits(transcript_q, scope_slugs):
```

(the rest of the Ask branch — threshold, catalog, `ask_citable`, ranking — is unchanged in this task).

`backend/app/services/tutor_agent.py` — add `from app.retrieval import pipeline`; replace the Ask `else:` branch of `search_course_content`:

```python
    else:
        # Ask: search ONLY launched AND owned courses (F1), with the exact-lecture deep link.
        enrolled_ids = await _enrolled_ids(runtime.context.student_id)
        scope = pipeline.ask_scope(enrolled_ids)
        pairs = await cl._transcript_hits(query, scope, top_k=15) if scope else []
        keep = [(SearchResult(chunk=c, score=s), h) for c, s in pairs if s >= TRANSCRIPT_THRESHOLD
                and cl.ask_citable(h := cl.transcript_hit(c, s, enrolled_ids))][:5]
        results = [r for r, _ in keep]
        cards = cl.to_cards(cl.CourseLookup(case=cl.LookupCase.ENROLLED_MATCH, hits=[h for _, h in keep],
                                            enrolled_titles=[]))
```

Remove the now-unused `grounding` import only if nothing else in the file uses it (`grounding.build_sources` is still used by the player branch — keep it).

`backend/app/eval/retrieval_systems.py` — ask branch of `LegacySystem.predict`:

```python
        from app.services import catalog_service
        every = [c["slug"] for c in catalog_service.all_courses() if c.get("slug")]
        pairs = await cl._transcript_hits(row.question, every)
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `cd backend && .venv/bin/pytest tests/test_course_lookup.py tests/test_tutor_agent.py tests/test_vector_store_course_scope.py tests/test_eval_runner.py tests/test_chat_pipeline.py -q`
Expected: PASS. Then `bash backend/scripts/run_tests.sh` → `ALL PASSED`.

- [ ] **Step 5: Commit**

```bash
git add backend/app/services/course_lookup.py backend/app/services/tutor_agent.py backend/app/eval/retrieval_systems.py backend/tests/test_course_lookup.py backend/tests/test_tutor_agent.py backend/tests/test_vector_store_course_scope.py backend/tests/test_eval_runner.py
git commit -m "feat(retrieval): Ask, player, find_moment and search tool use the scoped hybrid search; Ask scope = launched AND owned before searching

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

### Task 11: Phase 3 eval delta

**Files:** generated `backend/eval/retrieval/reports/phase3-hybrid.json`, `.md`; modify `HISTORY.md`.

- [ ] **Step 1: Run**

```bash
cd backend && env OPENAI_API_KEY="$(grep '^OPENAI_API_KEY=' /Users/swanandkadam/Desktop/01dev-React-hermes/backend/.env | cut -d= -f2- | tr -d '"')" DATABASE_URL= .venv/bin/python scripts/eval_retrieval.py --system legacy --label phase3-hybrid --compare phase2-enriched
```

Expected: recall@1/@5 and MRR at or above Phase 2 (BM25 lifts acronym rows such as `hand-iife`, `gen-*` keyword-style rows); coverage/false-cite still governed by the old thresholds. If recall@5 dropped versus Phase 2, stop and investigate (`grep '"style": "keyword"'` rows in the predictions) before Phase 4.

- [ ] **Step 2: Commit the numbers**

```bash
git add backend/eval/retrieval/reports/phase3-hybrid.json backend/eval/retrieval/reports/phase3-hybrid.md backend/eval/retrieval/reports/HISTORY.md
git commit -m "eval(retrieval): phase 3 delta — hybrid vector + BM25 + RRF inside the scope

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

# Phase 4 — Reranker + coverage decision; retire the thresholds

### Task 12: Reranker module (prompt, parsing, timeout, fallback, decision)

**Files:**
- Create: `backend/app/retrieval/rerank.py`
- Test: `backend/tests/test_rerank.py`

**Interfaces:**
- Consumes: `Candidate` (Task 9); `app.services.llm.llm.generate_json(system, user, temperature, max_tokens) -> Optional[dict]` (returns `None` when no client is configured).
- Produces (`app.retrieval.rerank`):
  - `GRADES = ("answers", "partial", "related", "no")`, `CITED = ("answers", "partial")`, `MAX_CANDIDATES = 12`, `RERANK_TIMEOUT_S = 5.0`, `PASSAGE_CHARS = 700`, `FALLBACK_TOP = 5`
  - `class Outcome(str, Enum): COVERED = "covered"; PARTIAL = "partial"; NOT_COVERED = "not_covered"` (values equal the eval's `COVERED/PARTIAL/NOT_COVERED` strings)
  - `@dataclass Graded(candidate: Candidate, grade: str, reason: str)`
  - `@dataclass RerankResult(graded: list[Graded], fallback: bool, error: Optional[str] = None)` — `graded` is in the input (fused) order
  - `build_user_prompt(question: str, cands: list[Candidate], intent: str = "explain") -> str`
  - `parse_grades(raw, n: int) -> Optional[dict[int, tuple[str, str]]]` (1-based candidate index → (grade, reason); `None` = unusable reply)
  - `fallback_grades(cands) -> list[Graded]`
  - `async rerank(question: str, cands: list[Candidate], *, intent: str = "explain") -> RerankResult`
  - `decide(graded: list[Graded]) -> tuple[Outcome, list[Graded]]` (ordered answers → partial → related → no, fused order within a grade)
  - module-level `async _complete(system, user) -> Optional[dict]` (tests monkeypatch it)

**Reranker JSON contract** (enforced by `parse_grades`, requested with `response_format={"type": "json_object"}` through `llm.generate_json`):

```json
{"grades": [{"id": "c1", "grade": "answers | partial | related | no", "reason": "at most 12 words"}]}
```

Ids are `c1 … cN` in the order the passages were shown. Unknown ids, ids beyond N and grades outside `GRADES` are ignored; the first grade for an id wins; an id the model skipped is graded `no` ("not graded"). A reply with zero usable grades, an exception, or no reply within `RERANK_TIMEOUT_S` → **fallback**: the top fused candidate is graded `answers` only if it is in **both** the vector top-5 and the lexical top-5 (`vec_rank <= 5 and lex_rank <= 5`), everything else `no`; the fallback is logged as `[rerank] fallback (<why>): <question>`.

**Why 5 s and 12 candidates:** a gpt-4.1-mini JSON grading of 12 passages × ~700 chars (~2.5k input tokens, ~250 output tokens) typically returns in 0.6–1.2 s; 5 s is ~4× that, past which the fused fallback is a better answer than a stalled chat. 12 is the spec's candidate count and keeps the prompt small enough for the network limits of this sandbox.

- [ ] **Step 1: Write the failing tests**

`backend/tests/test_rerank.py`:

```python
import asyncio

import pytest

from app.models import TranscriptChunk
from app.retrieval import rerank as rr
from app.retrieval.base import Candidate


def cand(i, vec_rank=None, lex_rank=None, lecture="custom-library-5-2"):
    chunk = TranscriptChunk(chunk_id=f"{lecture}-{i}", course_id="custom-library", course_title="Build a Custom Library",
                            lecture_id=lecture, lecture_title="6.5 - IIFE, To The Rescue", text=f"raw {i}",
                            text_clean=f"clean passage {i} " + "x" * 900, summary=f"summary {i}",
                            start_time=60 * i, end_time=60 * i + 60)
    return Candidate(chunk=chunk, vec_rank=vec_rank, lex_rank=lex_rank, vec_score=0.5, fused=1.0 / (60 + i))


def test_prompt_lists_ids_course_lecture_time_summary_and_truncated_text():
    text = rr.build_user_prompt("what is an IIFE?", [cand(1), cand(2)])
    assert text.startswith("Question: what is an IIFE?")
    assert "[c1] Build a Custom Library › 6.5 - IIFE, To The Rescue @ 01:00" in text
    assert "Summary: summary 2" in text and "[c3]" not in text
    assert "x" * rr.PASSAGE_CHARS not in text                       # passage cut to PASSAGE_CHARS
    assert "navigate" not in text.lower()
    assert "Intent: navigate" in rr.build_user_prompt("take me to the IIFE part", [cand(1)], intent="navigate")


def test_parse_valid_reply_and_missing_ids_are_no():
    raw = {"grades": [{"id": "c1", "grade": "answers", "reason": "defines IIFE"},
                      {"id": "c3", "grade": "Partial ", "reason": "mentions scope"}]}
    assert rr.parse_grades(raw, 3) == {1: ("answers", "defines IIFE"), 3: ("partial", "mentions scope")}


def test_parse_ignores_unknown_ids_and_grades():
    raw = {"grades": [{"id": "c9", "grade": "answers", "reason": "x"}, {"id": "c1", "grade": "maybe", "reason": "x"},
                      {"id": "zz", "grade": "answers"}, {"id": "c2", "grade": "related", "reason": "r" * 500},
                      {"id": "c2", "grade": "answers", "reason": "dup"}]}
    out = rr.parse_grades(raw, 2)
    assert out == {2: ("related", "r" * 200)}


@pytest.mark.parametrize("raw", [None, "text", {}, {"grades": "x"}, {"grades": [{"id": "c1", "grade": "nah"}]}])
def test_parse_unusable_reply_is_none(raw):
    assert rr.parse_grades(raw, 2) is None


async def test_rerank_sends_at_most_12_and_keeps_fused_order(monkeypatch):
    seen = {}

    async def fake(system, user):
        seen["user"] = user
        return {"grades": [{"id": "c2", "grade": "answers", "reason": "shows it"}]}

    monkeypatch.setattr(rr, "_complete", fake)
    cands = [cand(i) for i in range(1, 16)]
    out = await rr.rerank("q", cands)
    assert "[c12]" in seen["user"] and "[c13]" not in seen["user"]
    assert len(out.graded) == 12 and not out.fallback
    assert [g.grade for g in out.graded[:3]] == ["no", "answers", "no"]
    assert out.graded[0].reason == "not graded"


async def test_empty_or_invalid_reply_falls_back(monkeypatch, capsys):
    async def junk(system, user):
        return {"grades": []}

    monkeypatch.setattr(rr, "_complete", junk)
    both = await rr.rerank("what is an IIFE?", [cand(1, vec_rank=2, lex_rank=1), cand(2, vec_rank=1)])
    assert both.fallback and [g.grade for g in both.graded] == ["answers", "no"]
    assert "[rerank] fallback" in capsys.readouterr().out
    one_signal = await rr.rerank("q", [cand(1, vec_rank=1, lex_rank=None), cand(2, vec_rank=2, lex_rank=1)])
    assert one_signal.fallback and {g.grade for g in one_signal.graded} == {"no"}
    deep = await rr.rerank("q", [cand(1, vec_rank=6, lex_rank=1)])
    assert [g.grade for g in deep.graded] == ["no"]                    # vector rank 6 > FALLBACK_TOP


async def test_timeout_falls_back(monkeypatch):
    async def slow(system, user):
        await asyncio.sleep(1)

    monkeypatch.setattr(rr, "RERANK_TIMEOUT_S", 0.01)
    monkeypatch.setattr(rr, "_complete", slow)
    out = await rr.rerank("q", [cand(1, vec_rank=1, lex_rank=1)])
    assert out.fallback and out.error == "TimeoutError" and out.graded[0].grade == "answers"


async def test_exception_falls_back_and_no_candidates_never_calls_the_model(monkeypatch):
    async def boom(system, user):
        raise RuntimeError("openai down")

    monkeypatch.setattr(rr, "_complete", boom)
    out = await rr.rerank("q", [cand(1)])
    assert out.fallback and out.error.startswith("RuntimeError")

    async def never(system, user):
        raise AssertionError("no candidates: no rerank call")

    monkeypatch.setattr(rr, "_complete", never)
    assert (await rr.rerank("q", [])).graded == []


def test_decide_orders_by_grade_then_fused_and_picks_the_outcome():
    a, b, c, d = cand(1), cand(2), cand(3), cand(4)
    G = rr.Graded
    outcome, ordered = rr.decide([G(a, "related", ""), G(b, "partial", ""), G(c, "answers", ""), G(d, "partial", "")])
    assert outcome == rr.Outcome.COVERED and [g.candidate for g in ordered] == [c, b, d, a]
    assert rr.decide([G(a, "related", ""), G(b, "partial", "")])[0] == rr.Outcome.PARTIAL
    assert rr.decide([G(a, "related", ""), G(b, "no", "")])[0] == rr.Outcome.NOT_COVERED
    assert rr.decide([]) == (rr.Outcome.NOT_COVERED, [])
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `cd backend && .venv/bin/pytest tests/test_rerank.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'app.retrieval.rerank'`.

- [ ] **Step 3: Implement**

`backend/app/retrieval/rerank.py`:

```python
"""Rerank + coverage decision (spec §2.4): one gpt-4.1-mini JSON call grades each fused candidate
answers | partial | related | no. Coverage is decided by those grades, not by score cutoffs:
any answers -> COVERED, else any partial -> PARTIAL, else NOT_COVERED. On failure/timeout, a
conservative fallback (top fused candidate in BOTH vector and lexical top-5) is used and logged."""
import asyncio
from dataclasses import dataclass
from enum import Enum
from typing import Optional

from app.retrieval.base import Candidate

GRADES = ("answers", "partial", "related", "no")
CITED = ("answers", "partial")
MAX_CANDIDATES = 12
RERANK_TIMEOUT_S = 5.0
PASSAGE_CHARS = 700
FALLBACK_TOP = 5
_ORDER = {g: i for i, g in enumerate(GRADES)}

SYSTEM = """You judge search results for a programming course tutor. A student asked a question; below are transcript passages from the student's courses, each with an id, its course and lecture, a time, a one-line summary and the passage text. Grade EVERY passage against the question:

- "answers": the passage itself explains, defines or demonstrates what the student asked, so pointing the student to it would directly help. A passage that only names the topic, promises to cover it later, or uses it in passing does not answer.
- "partial": the passage covers part of what was asked, or a closely related step, so it is worth mentioning as "the course touches on this here" — but it does not fully answer.
- "related": same general area, but it does not address the question.
- "no": unrelated.

Judge by what is actually said in the passage, not by the lecture title alone. Passages are speech-to-text, so spellings may be off (e.g. "iffy" for IIFE). For a navigation request ("take me to ...", "where does he ..."), grade "answers" for the passage where that thing is actually shown or explained.
Grade each id exactly once and give a reason of at most 12 words.
Return only JSON: {"grades": [{"id": "c1", "grade": "answers|partial|related|no", "reason": "..."}]}"""


class Outcome(str, Enum):
    COVERED = "covered"
    PARTIAL = "partial"
    NOT_COVERED = "not_covered"


@dataclass
class Graded:
    candidate: Candidate
    grade: str
    reason: str


@dataclass
class RerankResult:
    graded: list[Graded]
    fallback: bool
    error: Optional[str] = None


async def _complete(system: str, user: str) -> Optional[dict]:
    from app.services.llm import llm
    return await llm.generate_json(system, user, temperature=0.0, max_tokens=900)


def _mmss(seconds: int) -> str:
    m, s = divmod(int(seconds), 60)
    return f"{m:02d}:{s:02d}"


def build_user_prompt(question: str, cands: list[Candidate], intent: str = "explain") -> str:
    lines = [f"Question: {question}"]
    if intent == "navigate":
        lines.append("Intent: navigate (the student wants to jump to where this is shown)")
    lines += ["", "Passages:"]
    for i, c in enumerate(cands, 1):
        ch = c.chunk
        lines.append(f"[c{i}] {ch.course_title} › {ch.lecture_title} @ {_mmss(ch.start_time)}")
        if ch.summary:
            lines.append(f"Summary: {ch.summary}")
        lines.append((ch.text_clean or ch.text)[:PASSAGE_CHARS])
        lines.append("")
    return "\n".join(lines).rstrip()


def parse_grades(raw, n: int) -> Optional[dict[int, tuple[str, str]]]:
    if not isinstance(raw, dict) or not isinstance(raw.get("grades"), list):
        return None
    out: dict[int, tuple[str, str]] = {}
    for item in raw["grades"]:
        if not isinstance(item, dict):
            continue
        cid, grade = str(item.get("id") or "").strip().lower(), str(item.get("grade") or "").strip().lower()
        if not cid.startswith("c") or not cid[1:].isdigit() or grade not in GRADES:
            continue
        idx = int(cid[1:])
        if 1 <= idx <= n and idx not in out:
            out[idx] = (grade, str(item.get("reason") or "").strip()[:200])
    return out or None


def fallback_grades(cands: list[Candidate]) -> list[Graded]:
    out = [Graded(c, "no", "fallback: not judged") for c in cands]
    top = cands[0] if cands else None
    if top and top.vec_rank is not None and top.lex_rank is not None \
            and top.vec_rank <= FALLBACK_TOP and top.lex_rank <= FALLBACK_TOP:
        out[0] = Graded(top, "answers", "fallback: top of both vector and lexical search")
    return out


def _fall_back(question: str, cands: list[Candidate], why: str) -> RerankResult:
    print(f"[rerank] fallback ({why}): {question[:80]!r}")
    return RerankResult(fallback_grades(cands), fallback=True, error=why)


async def rerank(question: str, cands: list[Candidate], *, intent: str = "explain") -> RerankResult:
    cands = cands[:MAX_CANDIDATES]
    if not cands:
        return RerankResult([], fallback=False)
    try:
        raw = await asyncio.wait_for(_complete(SYSTEM, build_user_prompt(question, cands, intent)),
                                     timeout=RERANK_TIMEOUT_S)
    except asyncio.TimeoutError:
        return _fall_back(question, cands, "TimeoutError")
    except Exception as e:  # noqa: BLE001 — a reranker outage must never fail the turn
        return _fall_back(question, cands, repr(e))
    parsed = parse_grades(raw, len(cands))
    if parsed is None:
        return _fall_back(question, cands, "no usable grades")
    return RerankResult([Graded(c, *parsed.get(i, ("no", "not graded"))) for i, c in enumerate(cands, 1)],
                        fallback=False)


def decide(graded: list[Graded]) -> tuple[Outcome, list[Graded]]:
    ordered = sorted(graded, key=lambda g: _ORDER.get(g.grade, len(GRADES)))  # stable: fused order kept
    grades = {g.grade for g in graded}
    if "answers" in grades:
        return Outcome.COVERED, ordered
    if "partial" in grades:
        return Outcome.PARTIAL, ordered
    return Outcome.NOT_COVERED, ordered
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `cd backend && .venv/bin/pytest tests/test_rerank.py -q`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add backend/app/retrieval/rerank.py backend/tests/test_rerank.py
git commit -m "feat(retrieval): LLM reranker grading answers/partial/related/no, coverage decision, logged fused fallback

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

### Task 13: `pipeline.graded_search` + the v2 eval adapter

**Files:**
- Modify: `backend/app/retrieval/pipeline.py` (add `RetrievalResult`, `graded_search`)
- Modify: `backend/app/eval/retrieval_systems.py` (add `V2System`), `backend/scripts/eval_retrieval.py` (`make_system` knows `"v2"`)
- Test: `backend/tests/test_retrieval_pipeline.py`, `backend/tests/test_eval_runner.py`

**Interfaces:**
- Consumes: `search` (Task 9); `rerank`, `decide`, `Outcome`, `Graded`, `CITED` (Task 12).
- Produces (`app.retrieval.pipeline`):
  ```python
  @dataclass
  class RetrievalResult:
      outcome: Outcome
      graded: list[Graded]                 # answers, partial, related, no — fused order within a grade
      intent: str = "explain"              # explain | navigate | account | off_topic (Task 17 sets the last two)
      search_query: str = ""
      fallback: bool = False
      timings_ms: dict = field(default_factory=dict)   # "understand", "retrieve", "rerank", "total"
      def cited(self) -> list[Graded]                   # grade in CITED, in order
      def best(self, allow_partial: bool = True) -> Optional[Graded]

  async def graded_search(question: str, scope: Sequence[str], *, intent: str = "explain",
                          lecture_id: Optional[str] = None, history: Sequence[dict] = (),
                          lecture_title: Optional[str] = None) -> RetrievalResult
  ```
  (`history` and `lecture_title` are accepted now and used by query understanding in Task 18.)
  Also re-exported from `pipeline`: `Outcome`, `Graded`, `CITED`.
- `app.eval.retrieval_systems.V2System` (`name = "v2"`, same `predict(row, mode)` contract as `LegacySystem`).

- [ ] **Step 1: Write the failing tests**

Append to `backend/tests/test_retrieval_pipeline.py`:

```python
from app.retrieval import rerank as rr


@pytest.fixture
def grader(monkeypatch):
    calls = []

    def set_reply(grades):
        async def fake(system, user):
            calls.append(user)
            return {"grades": [{"id": f"c{i}", "grade": g, "reason": f"r{i}"} for i, g in grades.items()]}
        monkeypatch.setattr(rr, "_complete", fake)

    set_reply.calls = calls
    return set_reply


async def test_graded_search_decides_from_grades(mem, grader):
    grader({1: "answers"})
    res = await pipeline.graded_search("what is an IIFE?", ["custom-library"])
    assert res.outcome == pipeline.Outcome.COVERED and not res.fallback
    assert res.best().candidate.chunk.chunk_id == "cl-5-2-0" and res.best().reason == "r1"
    assert [g.grade for g in res.cited()] == ["answers"]
    assert set(res.timings_ms) >= {"retrieve", "rerank", "total"}


async def test_graded_search_partial_and_best(mem, grader):
    grader({2: "partial"})
    res = await pipeline.graded_search("what is an IIFE?", ["custom-library"])
    assert res.outcome == pipeline.Outcome.PARTIAL
    assert res.best().grade == "partial" and res.best(allow_partial=False) is None


async def test_graded_search_empty_scope_never_embeds_or_reranks(mem, grader):
    res = await pipeline.graded_search("what is an IIFE?", [])
    assert res.outcome == pipeline.Outcome.NOT_COVERED and res.graded == []
    assert mem == [] and grader.calls == []


async def test_graded_search_tells_the_reranker_about_navigation(mem, grader):
    grader({1: "answers"})
    await pipeline.graded_search("IIFE", ["custom-library"], intent="navigate")
    assert "Intent: navigate" in grader.calls[0]
```

Append to `backend/tests/test_eval_runner.py`:

```python
async def test_v2_mapping(monkeypatch):
    from app.retrieval import pipeline
    from app.retrieval.base import Candidate
    from app.retrieval.rerank import Graded, Outcome

    async def fake_graded(question, scope, **kw):
        assert list(scope) == ["custom-library"] and kw["history"] == [] and kw["lecture_title"] is None
        a, b = Candidate(chunk=_chunk("custom-library-9-0")), Candidate(chunk=_chunk("custom-library-5-2"))
        return pipeline.RetrievalResult(Outcome.PARTIAL, [Graded(b, "partial", "x"), Graded(a, "related", "y")],
                                        fallback=True)

    monkeypatch.setattr(pipeline, "graded_search", fake_graded)
    p = await rs.V2System().predict(_row("a"), "player")
    assert (p.outcome, p.cited_lecture, p.fallback) == (PARTIAL, "custom-library-5-2", True)
    assert p.ranked_lectures == ["custom-library-5-2", "custom-library-9-0"]
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `cd backend && .venv/bin/pytest tests/test_retrieval_pipeline.py tests/test_eval_runner.py -q`
Expected: FAIL — `AttributeError: module 'app.retrieval.pipeline' has no attribute 'graded_search'`, `module 'app.eval.retrieval_systems' has no attribute 'V2System'`.

- [ ] **Step 3: Implement**

Append to `backend/app/retrieval/pipeline.py` (add `import time` and `from dataclasses import dataclass, field` to the imports):

```python
from app.retrieval.rerank import CITED, Graded, Outcome, decide, rerank  # noqa: E402


@dataclass
class RetrievalResult:
    outcome: Outcome
    graded: list[Graded]
    intent: str = "explain"
    search_query: str = ""
    fallback: bool = False
    timings_ms: dict = field(default_factory=dict)

    def cited(self) -> list[Graded]:
        return [g for g in self.graded if g.grade in CITED]

    def best(self, allow_partial: bool = True) -> Optional[Graded]:
        for wanted in ("answers", "partial") if allow_partial else ("answers",):
            for g in self.graded:
                if g.grade == wanted:
                    return g
        return None


def _ms(t0: float) -> float:
    return round((time.perf_counter() - t0) * 1000, 1)


async def graded_search(question: str, scope: Sequence[str], *, intent: str = "explain",
                        lecture_id: Optional[str] = None, history: Sequence[dict] = (),
                        lecture_title: Optional[str] = None) -> RetrievalResult:
    """Scope (given, computed by the caller in code) → hybrid retrieval → rerank → coverage decision."""
    t0 = time.perf_counter()
    scope = tuple(dict.fromkeys(s for s in scope if s))
    if not scope:
        return RetrievalResult(Outcome.NOT_COVERED, [], intent=intent, search_query=question)
    cands = await search(question, scope, lecture_id=lecture_id)
    t_retrieve = _ms(t0)
    t1 = time.perf_counter()
    rr = await rerank(question, cands, intent=intent)
    outcome, ordered = decide(rr.graded)
    return RetrievalResult(outcome, ordered, intent=intent, search_query=question, fallback=rr.fallback,
                           timings_ms={"retrieve": t_retrieve, "rerank": _ms(t1), "total": _ms(t0)})
```

Append to `backend/app/eval/retrieval_systems.py`:

```python
class V2System:
    """Phase 4+: graded_search (hybrid → rerank → decision); navigation through find_moment's locator."""
    name = "v2"

    async def predict(self, row: Row, mode: str) -> Prediction:
        from app.retrieval import pipeline
        from app.services import catalog_service, tutor_agent
        t0 = time.perf_counter()
        if row.intent == "navigate":
            hit = await tutor_agent._locate_moment(row.navigate_phrase or row.question, row.scope_course)
            return Prediction(row.id, mode, [], NOT_COVERED, None,
                              moment_lecture=hit[0].lecture_id if hit else None, latency_ms=_ms(t0))
        scope = ([row.scope_course] if mode == "player"
                 else [c["slug"] for c in catalog_service.all_courses() if c.get("slug")])
        res = await pipeline.graded_search(row.question, scope, history=list(row.history),
                                           lecture_title=row.lecture_title)
        ms = _ms(t0)
        best = res.best()
        return Prediction(row.id, mode, list(dict.fromkeys(g.candidate.chunk.lecture_id for g in res.graded)),
                          res.outcome.value, best.candidate.chunk.lecture_id if best else None,
                          latency_ms=ms, fallback=res.fallback)
```

In `backend/scripts/eval_retrieval.py`, `make_system`:

```python
def make_system(name: str):
    from app.eval import retrieval_systems as rs
    return {"legacy": rs.LegacySystem, "v2": rs.V2System}[name]()
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `cd backend && .venv/bin/pytest tests/test_retrieval_pipeline.py tests/test_eval_runner.py tests/test_rerank.py -q`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add backend/app/retrieval/pipeline.py backend/app/eval/retrieval_systems.py backend/scripts/eval_retrieval.py backend/tests/test_retrieval_pipeline.py backend/tests/test_eval_runner.py
git commit -m "feat(retrieval): graded_search (hybrid -> rerank -> coverage) and the v2 eval adapter

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

### Task 14: Ask + player lookups decide coverage from grades (`ENROLLED_RELATED`, graded facts, `suggest`)

**Contract mapping (kept stable for the prompt, SSE and frontend):**

| Pipeline outcome | Ask (`ChatScope.in_player=False`) | Player (`in_player=True`) |
|---|---|---|
| `COVERED` (any `answers`) | `ENROLLED_MATCH`, hits = cited chunks (answers first, then partial) | `IN_COURSE_MATCH`, hits = `answers` chunks, one per lecture, ≤ 3 |
| `PARTIAL` (no answers, any `partial`) | **`ENROLLED_RELATED`** (new), hits = partial chunks | `IN_COURSE_RELATED`, hits = `partial` chunks, one per lecture, ≤ 3 |
| `NOT_COVERED` | `NO_MATCH`, no hits (catalog hit only for an in-scope course with no transcripts → `ENROLLED_MATCH`) | `IN_COURSE_NONE`, no hits |

`suggest` (player) = hits with `grade == "answers"` (replaces "`via_title` or score ≥ `TRANSCRIPT_THRESHOLD`"). Deep links, cards and the `navigate`/`suggest`/`sources` SSE shapes are unchanged. `Hit.via_title` is replaced by `Hit.grade` + `Hit.reason`.

**Files:**
- Modify: `backend/app/services/course_lookup.py` (`LookupCase`, `Hit`, `transcript_hit`, new `graded_hit`, `_catalog_hits`, `course_lookup`, `_in_course_lookup`, `render_facts`)
- Modify: `backend/app/services/chat_pipeline.py` (`course_lookup(..., history=)`, `_suggest_moments`)
- Modify: `backend/app/grounding/grounding_prompt.md`
- Modify: `backend/scripts/demo_check.py` (print grade instead of `via_title`)
- Test: `backend/tests/test_course_lookup.py`, `backend/tests/test_chat_pipeline.py`, `backend/tests/test_grounding_prompt.py`

**Interfaces:**
- Consumes: `pipeline.graded_search`, `pipeline.ask_scope`, `RetrievalResult.cited()`, `Outcome`, `Graded`, `decide` (Tasks 9, 12, 13).
- Produces:
  - `LookupCase.ENROLLED_RELATED = "enrolled_related"`
  - `Hit` fields: `grade: str = ""` (`"answers" | "partial"`, `""` for catalog/context hits), `reason: str = ""`; `via_title` removed.
  - `transcript_hit(chunk, score, enrolled_ids, grade="", reason="") -> Hit` (text = `text_clean or text`), `graded_hit(g: Graded, enrolled_ids) -> Hit`
  - `async course_lookup(question, student_id, scope=ChatScope(), history: Sequence[dict] = ()) -> CourseLookup`
  - COURSE FACTS match lines: player `"{i}. [THIS COURSE · STRONG|WEAK] {lecture} @ {mm:ss}"`, Ask `"{i}. [ENROLLED] …"` / `"{i}. [ENROLLED · PARTIAL] …"` (no score suffix), followed by `"   why: {reason}"` when there is a reason, then the excerpt line.

- [ ] **Step 1: Update and add tests**

`backend/tests/test_course_lookup.py` — new imports at the top:

```python
from app.retrieval import pipeline
from app.retrieval.base import Candidate
from app.retrieval.rerank import Graded, decide
```

Replace the `patch_sources` fixture (Ask) — transcripts are now `(chunk, grade)` pairs the reranked pipeline returns:

```python
@pytest.fixture
def patch_sources(monkeypatch):
    monkeypatch.setattr(cl, "CATALOG_THRESHOLD", 0.35)
    seen: dict = {"scopes": [], "questions": [], "kw": []}

    def apply(transcripts=(), catalog=(), enrolled_ids=(), enrollment_error=False):
        async def fake_graded(question, scope, **kw):
            seen["scopes"].append(tuple(scope))
            seen["questions"].append(question)
            seen["kw"].append(kw)
            graded = [Graded(Candidate(chunk=c, vec_score=0.6), g, f"why {c.lecture_title}")
                      for c, g in transcripts if c.course_id in scope]
            outcome, ordered = decide(graded)
            return pipeline.RetrievalResult(outcome, ordered, search_query=question)

        async def fake_catalog(query, top_k=5):
            return list(catalog)

        async def fake_enrolled(student_id):
            if enrollment_error:
                raise RuntimeError("db down")
            return [{"id": i, "title": f"course {i}", "purchased_at": "x"} for i in enrolled_ids]

        monkeypatch.setattr(pipeline, "graded_search", fake_graded)
        monkeypatch.setattr(cl.catalog_index, "search", fake_catalog)
        monkeypatch.setattr(enrollment_service, "get_enrolled_courses", fake_enrolled)

    apply.scopes, apply.seen = seen["scopes"], seen
    return apply
```

Mechanical conversion of every existing Ask call site: a transcript row `(CHUNK, score)` becomes `(CHUNK, "answers")` (under the old fixture every score ≥ 0.35 was a hit). `test_scores_below_threshold_mean_no_match` becomes:

```python
async def test_related_or_no_grades_mean_no_match(patch_sources):
    patch_sources(transcripts=[(NPM_CHUNK, "related")], catalog=[(NPM_MODULE, 0.58)], enrolled_ids=[2])
    out = await cl.course_lookup("q", "s")
    assert out.case == cl.LookupCase.NO_MATCH and out.hits == []      # custom-library has transcripts: no catalog
```

`test_lecture_title_steers_the_transcript_search_but_not_the_catalog` becomes (lecture context now goes to query understanding, never into the evidence query):

```python
async def test_ask_searches_the_bare_question_and_passes_the_lecture_as_context(patch_sources):
    patch_sources(transcripts=[], enrolled_ids=[2])
    scope = cl.ChatScope(course_slug="custom-library", lecture_title="1.1 - What is this course")
    await cl.course_lookup("Give me an example", "s", scope, history=[{"role": "user", "content": "hi"}])
    assert patch_sources.seen["questions"] == ["Give me an example"]
    assert patch_sources.seen["kw"][0] == {"history": [{"role": "user", "content": "hi"}],
                                           "lecture_title": "1.1 - What is this course"}
```

Delete `test_ask_scope_is_launched_and_owned_before_searching`'s old body and keep it with the new fixture (`(NPM_CHUNK, "answers"), (MEMO_CHUNK, "answers")`, assertions unchanged). Replace `test_ask_with_no_launched_owned_course_never_searches` with the Review Focus #1 test:

```python
async def test_ask_empty_scope_never_searches_or_reranks(patch_sources, monkeypatch):
    from app.retrieval import rerank as rr
    from app.services.embeddings import embedding_service
    patch_sources(transcripts=[(NPM_CHUNK, "answers")], enrolled_ids=[9, 11])   # the demo account

    async def boom(*a, **k):
        raise AssertionError("an empty Ask scope must not embed, search, rerank or read the catalog")

    monkeypatch.setattr(embedding_service, "embed", boom)
    monkeypatch.setattr(rr, "_complete", boom)
    monkeypatch.setattr(cl.catalog_index, "search", boom)
    out = await cl.course_lookup("how do I publish an npm library", "demo")
    assert out.case == cl.LookupCase.NO_MATCH and out.hits == [] and patch_sources.scopes == []
```

Add:

```python
async def test_partial_grades_are_enrolled_related_with_partial_labels(patch_sources):
    patch_sources(transcripts=[(NPM_CHUNK, "partial")], enrolled_ids=[2])
    out = await cl.course_lookup("q", "s")
    assert out.case == cl.LookupCase.ENROLLED_RELATED and [h.grade for h in out.hits] == ["partial"]
    facts = cl.render_facts(out, cl.ChatScope())
    assert "CASE: ENROLLED_RELATED" in facts and "[ENROLLED · PARTIAL] Build a Custom Library" in facts
    assert "   why: why 8.1 - The npm link command" in facts
    assert "the01.dev/course/2?chapter=7&sub=0&t=87" in facts


async def test_answers_rank_before_partial(patch_sources):
    other = _chunk("custom-library", "Build a Custom Library", "7.2 - Publishing to npm")
    patch_sources(transcripts=[(other, "partial"), (NPM_CHUNK, "answers")], enrolled_ids=[2])
    out = await cl.course_lookup("q", "s")
    assert out.case == cl.LookupCase.ENROLLED_MATCH and [h.grade for h in out.hits] == ["answers", "partial"]


async def test_catalog_is_used_only_for_in_scope_courses_without_transcripts(patch_sources, monkeypatch):
    from types import SimpleNamespace
    patch_sources(transcripts=[], catalog=[(NPM_MODULE, 0.58)], enrolled_ids=[2])
    monkeypatch.setattr(cl, "vector_store", SimpleNamespace(chunks=[NPM_CHUNK]))
    assert (await cl.course_lookup("q", "s")).hits == []                     # custom-library has transcripts
    monkeypatch.setattr(cl, "vector_store", SimpleNamespace(chunks=[MEMO_CHUNK]))
    out = await cl.course_lookup("q", "s")
    assert out.case == cl.LookupCase.ENROLLED_MATCH and [h.source for h in out.hits] == ["catalog"]
```

In `test_facts_and_cards` keep the assertions (`"[ENROLLED] Build a Custom Library"` still holds). Replace the `patch_in_course` fixture (player):

```python
@pytest.fixture
def patch_in_course(monkeypatch, patch_sources):
    seen = {"graded": [], "lecture": []}

    def apply(graded=(), context=None, enrolled_ids=()):
        """graded: [(chunk, grade)] in fused order, as the reranked pipeline returns them.
        context: [(chunk, score)] the current-lecture search can return (default: the graded chunks)."""
        patch_sources(enrolled_ids=enrolled_ids)

        async def fake_graded(question, scope, **kw):
            seen["graded"].append((question, tuple(scope), kw))
            gs = [Graded(Candidate(chunk=c, vec_score=0.5), g, f"why {g}") for c, g in graded]
            outcome, ordered = decide(gs)
            return pipeline.RetrievalResult(outcome, ordered, search_query=question)

        async def fake_lecture(query, course_slug, lecture_title):
            seen["lecture"].append(query)
            rows = context if context is not None else [(c, 0.5) for c, _ in graded]
            rows = [(c, s) for c, s in rows if cl._norm(c.lecture_title) == cl._norm(lecture_title)]
            return sorted(rows, key=lambda t: t[1], reverse=True)

        async def no_catalog(query, top_k=5):
            raise AssertionError("the player tutor must not search the catalog")

        monkeypatch.setattr(pipeline, "graded_search", fake_graded)
        monkeypatch.setattr(cl, "search_in_lecture", fake_lecture)
        monkeypatch.setattr(cl.catalog_index, "search", no_catalog)
        return seen
    return apply
```

Player test conversions (same names unless stated):
- `test_player_searches_only_this_course_with_the_lecture_title_and_skips_the_catalog`: `patch_in_course(graded=[(PUBLISH_CHUNK, "answers")])`; assert `seen["graded"][0][:2] == ("how do I publish", ("custom-library",))`, `seen["graded"][0][2]["lecture_title"] == "8.1 - The \`npm link\` command"`, `seen["lecture"] == ["8.1 - The \`npm link\` command how do I publish"]`; the case/hit assertions stay.
- `test_player_outcome_follows_the_best_in_course_score` → `test_player_outcome_follows_the_grade`, parametrized `[("answers", "IN_COURSE_MATCH", 1), ("partial", "IN_COURSE_RELATED", 1), ("related", "IN_COURSE_NONE", 0), ("no", "IN_COURSE_NONE", 0)]` with `patch_in_course(graded=[(PUBLISH_CHUNK, grade)])`.
- `test_player_match_keeps_only_match_strength_hits`: graded `[(PUBLISH_CHUNK, "answers"), (weak, "partial")]`; assert `[h.grade for h in out.hits] == ["answers"]`.
- `test_player_drops_any_other_course_chunk_even_if_search_returns_one`: graded `[(MEMO_CHUNK, "answers"), (PUBLISH_CHUNK, "partial")]`; expectations unchanged (`IN_COURSE_RELATED`, only custom-library) — the other course's `answers` must not make it a match.
- `test_player_does_not_sort_the_current_lecture_first`: graded `[(PUBLISH_CHUNK, "answers"), (here, "answers")]`.
- Delete `test_title_match_lifts_a_weak_chunk_to_match_citing_that_lecture` and `test_title_tag_is_set_even_when_the_bare_score_is_already_strong`; add:

```python
async def test_player_match_facts_show_band_and_reason_without_scores(patch_in_course):
    es = _chunk("custom-library", "Build a Custom Library", "10.1 - What Are ES Modules", "ECMAScript modules", start=251)
    patch_in_course(graded=[(es, "answers")])
    out = await cl.course_lookup("what are ES modules", "s", PLAYER)
    facts = cl.render_facts(out, PLAYER)
    assert "1. [THIS COURSE · STRONG] 10.1 - What Are ES Modules @ 04:11\n   why: why answers" in facts
    assert "score" not in facts.split("Matches:")[1]
```

- `test_off_topic_is_none_even_when_the_prefixed_search_scores_high` → `test_off_topic_is_none_and_keeps_the_current_lecture_context`: `patch_in_course(graded=[], context=[(here, 0.61)])`; keep the `IN_COURSE_NONE`, `current_excerpt`, CURRENT LECTURE and `"Matches:" not in facts` assertions; add `assert seen["graded"][0][0] == "how does the event loop work"`.
- `test_weak_band_is_related_with_a_weak_label`: graded `[(PUBLISH_CHUNK, "partial")]`; assert `"[THIS COURSE · WEAK] 11.1 - Publishing using \`np\` @ 03:20" in facts`.
- `test_one_best_chunk_per_lecture_and_at_most_three`: rows `(chunk, "answers")` (same chunks, same order) — expectation unchanged.
- `test_player_with_no_lecture_selected_searches_the_bare_question_in_this_course`: graded `[(PUBLISH_CHUNK, "partial")]`; assert `seen["graded"][0][:2] == ("how do I publish", ("custom-library",))`, `seen["graded"][0][2]["lecture_title"] is None`, `seen["lecture"] == []`.
- `test_current_lecture_excerpt_is_not_listed_under_matches_unless_it_is_a_hit`: `patch_in_course(graded=[(PUBLISH_CHUNK, "answers")], context=[(PUBLISH_CHUNK, 0.7), (here, 0.2)])`.
- `test_current_lecture_context_holds_top_three_passages_in_time_order` / `test_current_lecture_context_is_capped`: `patch_in_course(graded=[], context=rows)`; expectations unchanged.

Leave the title/prewarm/`_title_scores`/`search_in_course` tests in place — Task 15 deletes them together with the code.

`backend/tests/test_chat_pipeline.py`:
- Every fake `lookup(question, student_id, scope=cl.ChatScope())` gains `history=()`; in `wired` record it: `calls["lookup_history"] = list(history)`.
- `_chit(title, score, lecture_id, start, slug="custom-library", via_title=False)` → `_chit(title, grade, lecture_id, start, slug="custom-library")` building `cl.Hit(..., score=0.5, grade=grade, ...)`. `S1, S2, S3` become `"answers"`; in `test_match_emits_suggest_before_done_with_at_most_two_distinct_lectures` `dup` is `"answers"` and `weak` is `"partial"` (expected suggestion list unchanged).
- Replace `test_via_title_hit_counts_as_strong_and_weak_hits_never_suggest` with:

```python
async def test_only_answers_hits_are_suggested(wired, monkeypatch):
    _incourse(monkeypatch, cl.LookupCase.IN_COURSE_MATCH, _chit("8.1 - The `npm link` command", "answers", "l1", 0),
              _chit("9.1 - W", "partial", "l9", 5))
    events = await _player_events(monkeypatch, wired, TOK)
    assert events[-2]["moments"] == [{"lecture_title": "8.1 - The `npm link` command", "start_time": 0}]


async def test_history_reaches_the_lookup_scrubbed(wired, monkeypatch):
    _agent(monkeypatch, wired)
    hist = [{"role": "user", "content": "my email is a@b.co"}, {"role": "assistant", "content": "ok"}]
    [e async for e in chat_pipeline.chat_turn(_req(history=hist))]
    assert wired["lookup_history"][1] == {"role": "assistant", "content": "ok"}
    assert "a@b.co" not in wired["lookup_history"][0]["content"]
```

`backend/tests/test_grounding_prompt.py` — add:

```python
def test_prompt_has_the_enrolled_related_case_and_why_lines():
    text = " ".join(loader.read_grounding_prompt().split())
    assert "CASE: ENROLLED_RELATED" in text
    assert "Your course touches on this in {lecture} at {mm:ss} — {link}" in text
    assert 'may carry a "why:" line' in text
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `cd backend && .venv/bin/pytest tests/test_course_lookup.py tests/test_chat_pipeline.py tests/test_grounding_prompt.py -q`
Expected: FAIL — `AttributeError: ENROLLED_RELATED`, `Hit.__init__() got an unexpected keyword argument 'grade'`, lookups still calling the old search functions.

- [ ] **Step 3: Implement**

`backend/app/services/course_lookup.py`:

```python
class LookupCase(str, Enum):
    ENROLLED_MATCH = "enrolled_match"
    ENROLLED_RELATED = "enrolled_related"   # Ask: a launched+owned course only touches on it (graded partial)
    NOT_ENROLLED_MATCH = "not_enrolled_match"
    NO_MATCH = "no_match"
    # Player tutor only (ChatScope.in_player) — this course's transcripts, nothing else.
    IN_COURSE_MATCH = "in_course_match"
    IN_COURSE_RELATED = "in_course_related"
    IN_COURSE_NONE = "in_course_none"
```

In `Hit`, replace `via_title: bool = False …` with:

```python
    grade: str = ""                # reranker grade: "answers" | "partial" ("" = catalog hit or context passage)
    reason: str = ""               # reranker's one-line reason, shown to the model as "why:"
```

Add `import asyncio` (already imported), `from typing import Optional, Sequence`, `from app.retrieval.rerank import Graded, Outcome, decide`. Replace `transcript_hit` and add `graded_hit`, `_catalog_hits`, `_GRADE_RANK`:

```python
def transcript_hit(chunk: TranscriptChunk, score: float, enrolled_ids: set[int], grade: str = "",
                   reason: str = "") -> Hit:
    course = catalog_service.by_slug(chunk.course_id)
    cid = course["id"] if course else None
    return Hit(
        source="transcript", course_id=cid, course_slug=chunk.course_id, course_title=chunk.course_title,
        title=chunk.lecture_title, score=score, enrolled=cid in enrolled_ids, text=chunk.text_clean or chunk.text,
        lecture_id=chunk.lecture_id, start_time=chunk.start_time, end_time=chunk.end_time,
        url=course["url"] if course else None, grade=grade, reason=reason,
    )


def graded_hit(g: Graded, enrolled_ids: set[int]) -> Hit:
    return transcript_hit(g.candidate.chunk, g.candidate.vec_score or 0.0, enrolled_ids, g.grade, g.reason)


_GRADE_RANK = {"answers": 0, "": 0, "partial": 1}


async def _catalog_hits(question: str, scope_slugs: Sequence[str], enrolled_ids: set[int]) -> list[Hit]:
    """Catalog text is evidence only for an in-scope course we hold NO transcript of; for every other
    course the reranker's judgement of its transcripts decides (a vague catalog blurb must not cite)."""
    bare = set(scope_slugs) - {c.course_id for c in vector_store.chunks}
    if not bare:
        return []
    out: list[Hit] = []
    for entry, score in await catalog_index.search(question, top_k=5):
        if entry.course_slug not in bare or score < CATALOG_THRESHOLD or any(h.course_id == entry.course_id for h in out):
            continue
        course = catalog_service.get(entry.course_id)
        out.append(Hit(source="catalog", course_id=entry.course_id, course_slug=entry.course_slug,
                       course_title=entry.course_title, title=entry.module_title or entry.course_title, score=score,
                       enrolled=entry.course_id in enrolled_ids, text=entry.text,
                       url=course["url"] if course else None))
    return out
```

Replace `course_lookup` (Ask branch):

```python
async def course_lookup(question: str, student_id: str, scope: ChatScope = ChatScope(),
                        history: Sequence[dict] = ()) -> CourseLookup:
    enrolled_ids, enrolled_titles = await _enrollments(student_id)
    if scope.in_player:
        return await _in_course_lookup(question, scope, enrolled_ids, enrolled_titles, history)
    scope_slugs = pipeline.ask_scope(enrolled_ids)
    if not scope_slugs:  # F1: nothing launched AND owned -> nothing to search, rerank or cite
        return CourseLookup(case=LookupCase.NO_MATCH, hits=[], enrolled_titles=[])
    # The bare question is the evidence query; the lecture being watched and the history are context
    # for query understanding (Task 17), never folded into what the reranker judges.
    result = await pipeline.graded_search(question, scope_slugs, history=history, lecture_title=scope.lecture_title)
    hits = [graded_hit(g, enrolled_ids) for g in result.cited()]
    if result.outcome == Outcome.NOT_COVERED:
        hits = await _catalog_hits(question, scope_slugs, enrolled_ids)
    hits = [h for h in hits if ask_citable(h)]

    def rank(h: Hit):
        in_course = bool(scope.course_slug) and h.course_slug == scope.course_slug
        in_lecture = in_course and bool(scope.lecture_title) and _norm(h.title) == _norm(scope.lecture_title)
        return (_GRADE_RANK.get(h.grade, 2), not in_lecture, not in_course)

    hits = sorted(hits, key=rank)[:MAX_HITS]          # stable: fused order kept within a rank
    if not hits:
        case = LookupCase.NO_MATCH
    elif result.outcome == Outcome.PARTIAL:
        case = LookupCase.ENROLLED_RELATED
    else:
        case = LookupCase.ENROLLED_MATCH
    owned_titles = [c["title"] for i in sorted(enrolled_ids) if (c := catalog_service.get(i)) and c.get("launched")]
    return CourseLookup(case=case, hits=hits, enrolled_titles=owned_titles)
```

Replace `_in_course_lookup`:

```python
async def _in_course_lookup(question: str, scope: ChatScope, enrolled_ids: set[int], enrolled_titles: list[str],
                            history: Sequence[dict] = ()) -> CourseLookup:
    """Player tutor (spec §3.2): this course's transcripts only. The reranker judges the BARE question;
    the lecture being watched is context (passages for "this"/"here"), not evidence."""
    slug = scope.course_slug or ""
    course = catalog_service.by_slug(slug)
    cid = course["id"] if course else None

    def to_hit(c: TranscriptChunk, s: float, grade: str = "", reason: str = "") -> Hit:
        return Hit(source="transcript", course_id=cid, course_slug=slug, course_title=c.course_title,
                   title=c.lecture_title, score=s, enrolled=cid in enrolled_ids, text=c.text_clean or c.text,
                   lecture_id=c.lecture_id, start_time=c.start_time, end_time=c.end_time,
                   url=course["url"] if course else None, grade=grade, reason=reason)

    async def context():
        if not scope.lecture_title:
            return []
        return await search_in_lecture(f"{scope.lecture_title} {question}", slug, scope.lecture_title)

    result, ctx = await asyncio.gather(
        pipeline.graded_search(question, [slug], history=history, lecture_title=scope.lecture_title), context())
    outcome, graded = decide([g for g in result.graded if g.candidate.chunk.course_id == slug])
    case = {Outcome.COVERED: LookupCase.IN_COURSE_MATCH,
            Outcome.PARTIAL: LookupCase.IN_COURSE_RELATED}.get(outcome, LookupCase.IN_COURSE_NONE)
    want = {LookupCase.IN_COURSE_MATCH: "answers", LookupCase.IN_COURSE_RELATED: "partial"}.get(case)
    hits, seen = [], set()
    for g in graded:
        ch, key = g.candidate.chunk, _norm(g.candidate.chunk.lecture_title)
        if g.grade != want or key in seen:
            continue
        seen.add(key)
        hits.append(to_hit(ch, g.candidate.vec_score or 0.0, g.grade, g.reason))
        if len(hits) == IN_COURSE_K:
            break
    current, passages = None, []
    if ctx:
        current = to_hit(*ctx[0])
        passages = [to_hit(c, s) for c, s in sorted(ctx[:CURRENT_PASSAGES], key=lambda t: t[0].start_time)]
    return CourseLookup(case=case, hits=hits, enrolled_titles=enrolled_titles, current_excerpt=current,
                        current_passages=passages)
```

Delete `_best_per_lecture` (no remaining caller). In `render_facts`, replace the `Matches` loop:

```python
    if lookup.hits:
        lines.append("Matches:")
        for i, h in enumerate(lookup.hits, 1):
            if scope.in_player:
                band = "STRONG" if h.grade == "answers" else "WEAK"
                lines.append(f"{i}. [THIS COURSE · {band}] {h.title} @ {_mmss(h.start_time)}")
            else:
                label = ("ENROLLED" if h.enrolled else "NOT ENROLLED") + (" · PARTIAL" if h.grade == "partial" else "")
                where = f"{h.title} @ {_mmss(h.start_time)}" if h.source == "transcript" else h.title
                link = deep_link(h)
                page = f" — link: the01.dev{link}" if link else ""
                lines.append(f"{i}. [{label}] {h.course_title} → {where} ({h.source}){page}")
            if h.reason:
                lines.append(f"   why: {h.reason}")
            lines.append(f'   "{h.text[:600]}"')
```

`backend/app/services/chat_pipeline.py`:
- import line: `from app.services.course_lookup import (_norm, ChatScope, CourseLookup, LookupCase, course_lookup, render_facts, to_cards)` (drop `TRANSCRIPT_THRESHOLD`).
- `lookup = await course_lookup(question, req.student_id, req.scope, history=history_in)`
- `_suggest_moments`:

```python
def _suggest_moments(lookup, scope) -> list[dict]:
    """Up to 2 hits the reranker judged to ANSWER the question, of the watched course, one per lecture."""
    out, seen = [], set()
    for h in lookup.hits:
        if h.source != "transcript" or h.course_slug != scope.course_slug or h.grade != "answers" \
                or _norm(h.title) in seen:
            continue
        seen.add(_norm(h.title))
        out.append({"lecture_title": h.title, "start_time": int(h.start_time)})
        if len(out) == MAX_SUGGESTIONS:
            break
    return out
```

`backend/app/grounding/grounding_prompt.md` — insert after the `## CASE: ENROLLED_MATCH` section:

```markdown
## CASE: ENROLLED_RELATED
A course the student owns touches on this, but no lecture fully answers it (its Matches are marked PARTIAL).
- Give a solid general answer first, from your own knowledge.
- Then add one sentence pointing to the closest moment: "Your course touches on this in {lecture} at {mm:ss} — {link}",
  with the lecture, time and link taken verbatim from the first match.
- Don't say the course covers it fully.
```

Replace the whole `## CASE: IN_COURSE_RELATED` section with:

```markdown
## CASE: IN_COURSE_RELATED
WEAK matches are only the closest moments in this course: each was judged to touch on the question
without fully answering it (its "why:" line says how). Give a solid general answer first, then add one
sentence: "This course touches on it in {lecture} at {mm:ss}." Take the lecture and time from the first
match. Don't claim the course covers it fully.
```

and add this bullet as the first item under `## Every case`:

```markdown
- A match may carry a "why:" line: the search's one-line judgement of how that moment relates to the
  question. Use it to decide what to say about the match; never quote it.
```

`backend/scripts/demo_check.py` lines 146–147:

```python
                band = "STRONG" if h.grade == "answers" else "WEAK"
                print(f"  hit: {h.title} @ {h.start_time}s grade={h.grade or '-'} band={band} why={h.reason!r}")
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `cd backend && .venv/bin/pytest tests/test_course_lookup.py tests/test_chat_pipeline.py tests/test_grounding_prompt.py tests/test_ask_chat_route.py tests/test_player_tutor_route.py -q`
Expected: PASS. Then `bash backend/scripts/run_tests.sh` → `ALL PASSED`.

- [ ] **Step 5: Commit**

```bash
git add backend/app/services/course_lookup.py backend/app/services/chat_pipeline.py backend/app/grounding/grounding_prompt.md backend/scripts/demo_check.py backend/tests/test_course_lookup.py backend/tests/test_chat_pipeline.py backend/tests/test_grounding_prompt.py
git commit -m "feat(tutor): coverage decided by reranker grades — ENROLLED_RELATED for Ask, graded player cases, suggest only answers

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

### Task 15: `find_moment` + `search_course_content` on the graded pipeline; retire the thresholds

**Retired from the decision path — deleted from `backend/app/services/course_lookup.py`:** `TRANSCRIPT_THRESHOLD`, `RELATED_THRESHOLD`, `TITLE_THRESHOLD`, `MOMENT_THRESHOLD`, `TITLE_OFFSET`, `AGREE_TITLE`, `AGREE_CHUNK`, `MOMENT_LECTURE_FLOOR`, `TITLE_EMBED_TIMEOUT`, `TITLE_PREWARM_TIMEOUT`, `TITLE_COOLDOWN` and their calibration comments; the title machinery `_TITLE_STOPWORDS`, `_title_cache`, `_title_failed_until`, `_bare_title`, `_lecture_titles`, `_cosine`, `_words`, `_overlap_title_scores`, `_embed_titles`, `prewarm_titles`, `_title_scores`; the superseded searches `_transcript_hits`, `search_in_course`; the now-unused `math`/`time`/`embedding_service` imports. **Kept:** `CATALOG_THRESHOLD` (catalog-only courses, Task 14), `MAX_HITS`, `IN_COURSE_K`, `CURRENT_PASSAGES`, `CURRENT_CONTEXT_CHARS`, `DESCRIPTION_CHARS`, `search_in_lecture`, `_norm` (now `_norm = norm_title` from `app.retrieval.text`). None of the old thresholds is needed by the reranker fallback (it uses fused ranks only). Also deleted: `backend/scripts/calibrate_lookup.py`, `backend/scripts/calibrate_in_course.py` (superseded by `eval_retrieval.py`) and `LegacySystem` (its code paths no longer exist; its numbers stay in `reports/`).

**Files:**
- Modify: `backend/app/services/tutor_agent.py` (`search_course_content`, `_locate_moment`)
- Modify: `backend/app/services/course_lookup.py` (deletions above)
- Modify: `backend/app/main.py` (lifespan: drop the `prewarm_titles` block)
- Modify: `backend/app/eval/retrieval_systems.py` (delete `LegacySystem`), `backend/scripts/eval_retrieval.py` (`--system` default and only choice `v2`)
- Delete: `backend/scripts/calibrate_lookup.py`, `backend/scripts/calibrate_in_course.py`
- Test: `backend/tests/test_tutor_agent.py`, `backend/tests/test_course_lookup.py`, `backend/tests/test_vector_store_course_scope.py`, `backend/tests/test_eval_runner.py`

**Interfaces:**
- Consumes: `pipeline.graded_search`, `pipeline.ask_scope`, `RetrievalResult.cited()/best()`, `cl.graded_hit`, `cl.ask_citable`, `cl.to_cards` (Tasks 13–14).
- Produces: `tutor_agent._locate_moment(what: str, slug: str) -> Optional[tuple[TranscriptChunk, float]]` (same signature `demo_check.py` spies on) = best `answers` chunk of the watched course for `intent="navigate"`, else best `partial`, else `None`. `search_course_content` returns the same `(text, cards)` shapes as before; text lines for partial matches carry ` (touches on it)`.

- [ ] **Step 1: Update the tests**

`backend/tests/test_tutor_agent.py` — replace `_stub` with a graded-pipeline stub, and `_ask_tool_setup` with one that honours the scope:

```python
def _stub(monkeypatch, graded=(), calls=None):
    """graded: [(chunk, grade, cosine)] as the reranked pipeline returns them (fused order)."""
    from app.retrieval import pipeline
    from app.retrieval.base import Candidate
    from app.retrieval.rerank import Graded, decide

    async def fake_graded(question, scope, **kw):
        if calls is not None:
            calls.append((question, tuple(scope), kw))
        gs = [Graded(Candidate(chunk=c, vec_score=s), g, "r") for c, g, s in graded if c.course_id in scope]
        outcome, ordered = decide(gs)
        return pipeline.RetrievalResult(outcome, ordered, intent=kw.get("intent", "explain"), search_query=question)

    monkeypatch.setattr(pipeline, "graded_search", fake_graded)


def _ask_tool_setup(monkeypatch, enrolled_ids, rows, grade="answers"):
    """rows: [(slug, course_title, lecture_id, lecture_title, score)] the graded pipeline can return."""
    from types import SimpleNamespace

    from app.models import TranscriptChunk
    from app.services import enrollment_service

    chunks = [(TranscriptChunk(chunk_id=f"{s}-{i}", course_id=s, course_title=t, lecture_id=lid, lecture_title=lt,
                               text="body", start_time=87, end_time=117), grade, sc)
              for i, (s, t, lid, lt, sc) in enumerate(rows)]
    _stub(monkeypatch, chunks)

    async def fake_enrolled(student_id):
        assert student_id == "alice"
        return [{"id": i, "title": f"course {i}"} for i in enrolled_ids]

    monkeypatch.setattr(enrollment_service, "get_enrolled_courses", fake_enrolled)
    return SimpleNamespace(context=tutor_agent.ChatContext(student_id="alice"))
```

Keep `test_ask_tool_for_an_unlaunched_only_student_returns_nothing`, `test_ask_tool_keeps_only_launched_owned_courses_with_deep_links`, `test_ask_tool_enrollment_failure_cites_nothing` as they are (they now run through the stub). Replace `test_player_tool_path_is_unchanged_by_the_ask_policy`'s `fake_in_course` with `_stub(monkeypatch, [(chunk, "answers", 0.8)])` (assertions unchanged). Replace `test_follow_up_search_drops_results_below_the_transcript_threshold` with:

```python
async def test_follow_up_search_cites_only_answers_and_partial(monkeypatch):
    rt = _ask_tool_setup(monkeypatch, [2], [])
    from app.models import TranscriptChunk

    def chunk(cid, lecture):
        return TranscriptChunk(chunk_id=cid, course_id="custom-library", course_title="Build a Custom Library",
                               lecture_id=f"custom-library-{cid}", lecture_title=lecture, text="body",
                               start_time=0, end_time=30)

    _stub(monkeypatch, [(chunk("1-0", "9.9 - Unrelated"), "related", 0.3), (chunk("2-0", "4.1 - Close"), "partial", 0.5),
                        (chunk("3-0", "5.1 - Exact"), "answers", 0.7)])
    content, cards = await tutor_agent.search_course_content.coroutine(query="memo", runtime=rt)
    assert [c["lecture_title"] for c in cards] == ["5.1 - Exact", "4.1 - Close"]
    assert "9.9 - Unrelated" not in content and "4.1 - Close @ 00:00 (touches on it)" in content
    _stub(monkeypatch, [(chunk("1-0", "9.9 - Unrelated"), "related", 0.3)])
    assert await tutor_agent.search_course_content.coroutine(query="memo", runtime=rt) == \
        ("No matching course content.", [])
```

Replace `test_follow_up_search_in_the_player_stays_in_this_course` with:

```python
async def test_follow_up_search_in_the_player_stays_in_this_course(monkeypatch):
    calls = []
    _stub(monkeypatch, [(_moment_chunk(), "answers", 0.7),
                        (_moment_chunk(lecture="8.1 - The `npm link` command", start=10), "related", 0.3)], calls)
    content, cards = await tutor_agent.search_course_content.coroutine(query="np", runtime=_player_runtime())
    assert calls[0][1] == ("custom-library",)
    assert [c["lecture_title"] for c in cards] == [LECTURE]
    assert "[THIS COURSE]" in content and "ENROLLED" not in content
```

Delete `test_find_moment_ranks_lectures_by_chunk_or_title_minus_offset`, `test_find_moment_title_only_lecture_starts_at_zero`, `test_find_moment_weak_title_and_weak_chunk_is_not_found`, `test_find_moment_title_and_chunk_agreeing_narrowly_is_found`, `test_find_moment_agreement_needs_both_signals`, `test_find_moment_agreement_does_not_borrow_across_lectures`, and the `TRANSCRIPT_THRESHOLD` bound assertion (old line 205). Convert the rest and add the new behaviour:

```python
async def test_find_moment_returns_the_best_answers_chunk_and_says_it_is_navigation(monkeypatch):
    import json
    calls = []
    _stub(monkeypatch, [(_moment_chunk(start=50), "partial", 0.5), (_moment_chunk(), "answers", 0.66)], calls)
    content, artifact = await tutor_agent.find_moment.coroutine(what="publish with np", runtime=_player_runtime())
    body = json.loads(content)
    assert (body["lecture_title"], body["start_time"], body["end_time"], body["score"]) == (LECTURE, 200, 255, 0.66)
    assert 0 < len(body["excerpt"]) <= 400
    assert artifact == {"course_slug": "custom-library", "lecture_title": LECTURE, "start_time": 200}
    assert calls[0][:2] == ("publish with np", ("custom-library",)) and calls[0][2]["intent"] == "navigate"


async def test_find_moment_falls_back_to_the_best_partial_chunk(monkeypatch):
    _stub(monkeypatch, [(_moment_chunk(start=50), "related", 0.6), (_moment_chunk(start=90), "partial", 0.42)])
    _, artifact = await tutor_agent.find_moment.coroutine(what="virtualize the table", runtime=_player_runtime())
    assert artifact["start_time"] == 90


async def test_find_moment_related_only_is_not_found(monkeypatch):
    _stub(monkeypatch, [(_moment_chunk(), "related", 0.5)])
    assert await tutor_agent.find_moment.coroutine(what="x", runtime=_player_runtime()) == ('{"found": false}', None)


async def test_find_moment_never_returns_another_course(monkeypatch):
    other = _moment_chunk(course="react-perf", lecture="4.1 - React.memo")

    async def leaky(question, scope, **kw):        # even if a backend leaked another course's chunk
        from app.retrieval import pipeline
        from app.retrieval.base import Candidate
        from app.retrieval.rerank import Graded, Outcome
        return pipeline.RetrievalResult(Outcome.COVERED, [Graded(Candidate(chunk=other, vec_score=0.9), "answers", "r")])

    from app.retrieval import pipeline
    monkeypatch.setattr(pipeline, "graded_search", leaky)
    assert await tutor_agent.find_moment.coroutine(what="x", runtime=_player_runtime()) == ('{"found": false}', None)
```

In `test_find_moment_without_a_course_in_context_is_not_found` and `test_ask_stream_has_no_find_moment`, patch `app.retrieval.pipeline.graded_search` with `boom` instead of `course_lookup.search_in_course` / `_title_scores`. In `test_player_stream_yields_a_moment_event_from_find_moment`, use `_stub(monkeypatch, [(_moment_chunk(), "answers", 0.7)])`.

`backend/tests/test_course_lookup.py` — delete `test_search_in_course_goes_through_the_scoped_pipeline`, `test_title_scores_fall_back_to_word_overlap_without_embeddings`, `test_title_embedding_failure_falls_back_to_overlap_and_is_not_retried_in_the_cooldown`, `test_prewarm_titles_embeds_every_course_in_one_call_and_fills_the_cache`, `test_prewarm_failure_raises_but_sets_no_cooldown`, `test_question_embed_failure_does_not_trigger_the_title_cooldown`, `test_title_build_failure_still_sets_a_short_cooldown` and any helper only they use. Add:

```python
def test_threshold_and_title_machinery_is_gone():
    for name in ("TRANSCRIPT_THRESHOLD", "RELATED_THRESHOLD", "TITLE_THRESHOLD", "MOMENT_THRESHOLD", "TITLE_OFFSET",
                 "AGREE_TITLE", "AGREE_CHUNK", "MOMENT_LECTURE_FLOOR", "prewarm_titles", "_title_scores",
                 "search_in_course", "_transcript_hits"):
        assert not hasattr(cl, name), name
    assert cl.CATALOG_THRESHOLD and cl.IN_COURSE_K == 3
```

`backend/tests/test_vector_store_course_scope.py` — in `test_search_in_course_never_touches_other_courses_chunks`, replace the `cl.search_in_course(...)` call with:

```python
    cands = asyncio.run(pipeline.search("x", ["js-engine"], limit=pipeline.VEC_K + pipeline.LEX_K, per_lecture=None))
    out = [(c.chunk, c.vec_score) for c in cands]
```

(and drop the now-unused `from app.services import course_lookup as cl` import if nothing else uses it).

`backend/tests/test_eval_runner.py` — delete `test_legacy_player_mapping` and `test_legacy_ask_and_navigate_mapping`.

- [ ] **Step 2: Run the tests to verify they fail**

Run: `cd backend && .venv/bin/pytest tests/test_tutor_agent.py tests/test_course_lookup.py tests/test_vector_store_course_scope.py tests/test_eval_runner.py -q`
Expected: FAIL — find_moment/search tool still use the threshold code (`test_find_moment_falls_back_to_the_best_partial_chunk`, `test_follow_up_search_cites_only_answers_and_partial`, `test_threshold_and_title_machinery_is_gone` fail).

- [ ] **Step 3: Implement**

`backend/app/services/tutor_agent.py` — imports: remove `from app.services.course_lookup import TRANSCRIPT_THRESHOLD`; add `from app.retrieval import pipeline`. Replace `search_course_content`'s body:

```python
    in_course = runtime.context.in_course
    if in_course:  # player: this course only (spec §3.2), whoever owns it
        enrolled_ids, scope = set(), (in_course,)
    else:          # Ask: launched AND owned courses only (F1), exact-lecture deep links
        enrolled_ids = await _enrolled_ids(runtime.context.student_id)
        scope = pipeline.ask_scope(enrolled_ids)
    result = await pipeline.graded_search(query, scope)   # empty scope: NOT_COVERED, nothing searched
    cited = [g for g in result.cited() if g.candidate.chunk.course_id in scope][:5]
    if in_course:
        results = [SearchResult(chunk=g.candidate.chunk, score=g.candidate.vec_score or 0.0) for g in cited]
        cards = [c.model_dump() for c in grounding.build_sources(results)]
        rows = list(zip(cited, cards))
    else:
        kept = [(g, h) for g in cited if cl.ask_citable(h := cl.graded_hit(g, enrolled_ids))]
        cards = cl.to_cards(cl.CourseLookup(case=cl.LookupCase.ENROLLED_MATCH, hits=[h for _, h in kept],
                                            enrolled_titles=[]))
        rows = list(zip([g for g, _ in kept], cards))
    if not rows:
        return "No matching course content.", []
    text = "\n".join(
        f"{'[THIS COURSE] ' if in_course else ''}"
        f"{g.candidate.chunk.course_title} → {g.candidate.chunk.lecture_title} @ {c['timestamp']}"
        f"{' (touches on it)' if g.grade == 'partial' else ''}: {g.candidate.chunk.text_clean or g.candidate.chunk.text}"
        + (f" — link: the01.dev{c['url']}" if not in_course and c.get("url") else "")
        for g, c in rows
    )
    return text, cards
```

Replace `_locate_moment`:

```python
async def _locate_moment(what: str, slug: str):
    """(chunk, cosine) of the moment that shows `what` in the watched course, or None. find_moment only
    runs on an explicit "take me to ..." request, so the best `answers` chunk wins, else the best
    `partial` one (spec §2.5). Only a real chunk of THIS course is ever returned."""
    result = await pipeline.graded_search(what, [slug], intent="navigate")
    for g in (x for grade in ("answers", "partial") for x in result.graded if x.grade == grade):
        if g.candidate.chunk.course_id == slug:
            return g.candidate.chunk, g.candidate.vec_score or 0.0
    return None
```

`backend/app/services/course_lookup.py` — delete everything listed in "Retired" above. The import block becomes:

```python
import asyncio
import re
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional, Sequence

from app.models import TranscriptChunk
from app.retrieval import pipeline
from app.retrieval.rerank import Graded, Outcome, decide
from app.retrieval.text import norm_title
from app.services import catalog_index, catalog_service, enrollment_service
from app.services.vector_store import vector_store

CATALOG_THRESHOLD = 0.34  # catalog entries of in-scope courses with NO transcripts only (see _catalog_hits)
MAX_HITS = 5
IN_COURSE_K = 3
CURRENT_PASSAGES = 3         # player: passages of the watched lecture given as context
CURRENT_CONTEXT_CHARS = 1500  # ... capped in total
DESCRIPTION_CHARS = 600  # longest catalog description is 546; product-engineering's project sits near char 430

_norm = norm_title
```

and the module docstring's last paragraph becomes: "Coverage is decided by the retrieval pipeline's reranker (app/retrieval), not by score thresholds."

`backend/app/main.py` — delete the `try: … course_lookup.prewarm_titles() … except …` block in `lifespan` (keep `from app.services import course_lookup` only if something else in `main.py` still uses it; `ChatScope`/`_norm` imports stay).

`backend/app/eval/retrieval_systems.py` — delete the `LegacySystem` class. `backend/scripts/eval_retrieval.py`:

```python
    ap.add_argument("--system", default="v2", choices=["v2"])
```

and `make_system` returns `{"v2": rs.V2System}[name]()`.

Delete the calibration scripts:

```bash
git rm backend/scripts/calibrate_lookup.py backend/scripts/calibrate_in_course.py
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `bash backend/scripts/run_tests.sh`
Expected: `ALL PASSED`. Also `cd backend && grep -rn "TRANSCRIPT_THRESHOLD\|_title_scores\|prewarm_titles\|search_in_course\|via_title" app scripts tests` → no matches.

- [ ] **Step 5: Commit**

```bash
git add backend/app/services/tutor_agent.py backend/app/services/course_lookup.py backend/app/main.py backend/app/eval/retrieval_systems.py backend/scripts/eval_retrieval.py backend/tests/test_tutor_agent.py backend/tests/test_course_lookup.py backend/tests/test_vector_store_course_scope.py backend/tests/test_eval_runner.py
git commit -m "feat(tutor): find_moment and search_course_content use graded retrieval; retire threshold/title calibration

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

(The `git rm` in Step 3 already staged the two deletions; they are part of this commit.)

### Task 16: Phase 4 eval delta + real-model demo check

**Files:** generated `backend/eval/retrieval/reports/phase4-rerank.json`, `.md`; modify `HISTORY.md`.

- [ ] **Step 1: Run the eval**

```bash
cd backend && env OPENAI_API_KEY="$(grep '^OPENAI_API_KEY=' /Users/swanandkadam/Desktop/01dev-React-hermes/backend/.env | cut -d= -f2- | tr -d '"')" DATABASE_URL= .venv/bin/python scripts/eval_retrieval.py --system v2 --label phase4-rerank --compare phase1-baseline
```

Expected: coverage accuracy and false-cite rate move toward the targets; `hand-iife` is now `covered` citing `custom-library-5-2` (check: `grep -A6 '"row_id": "hand-iife"' backend/eval/retrieval/reports/phase4-rerank.json`); `fallback_rate` ≈ 0 (a high rate means the reranker is timing out or returning junk — read the `[rerank] fallback` log lines before going on); latency p95 is reported against the 1.5 s target.

- [ ] **Step 2: Demo check (real model, local only)**

```bash
cd backend && env OPENAI_API_KEY="$(grep '^OPENAI_API_KEY=' /Users/swanandkadam/Desktop/01dev-React-hermes/backend/.env | cut -d= -f2- | tr -d '"')" DATABASE_URL= .venv/bin/python scripts/demo_check.py demo-local --enroll 9,11
cd backend && env OPENAI_API_KEY="$(grep '^OPENAI_API_KEY=' /Users/swanandkadam/Desktop/01dev-React-hermes/backend/.env | cut -d= -f2- | tr -d '"')" DATABASE_URL= .venv/bin/python scripts/demo_check.py demo-local --enroll 2
cd backend && env OPENAI_API_KEY="$(grep '^OPENAI_API_KEY=' /Users/swanandkadam/Desktop/01dev-React-hermes/backend/.env | cut -d= -f2- | tr -d '"')" DATABASE_URL= .venv/bin/python scripts/demo_check.py demo-local --player --runs 1
```

Expected: exit 0 for all three — every question `NO_MATCH` with `--enroll 9,11`; the npm question `ENROLLED_MATCH` with a `/course/2?chapter=…&sub=…&t=…` link with `--enroll 2`; player cases jump only on explicit "take me to" requests and never name another course.

- [ ] **Step 3: Commit the numbers**

```bash
git add backend/eval/retrieval/reports/phase4-rerank.json backend/eval/retrieval/reports/phase4-rerank.md backend/eval/retrieval/reports/HISTORY.md
git commit -m "eval(retrieval): phase 4 delta — reranker decides coverage

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

# Phase 5 — Query understanding (rewrite + intent)

### Task 17: Query-understanding module

**Files:**
- Create: `backend/app/retrieval/understand.py`
- Test: `backend/tests/test_understand.py`

**Interfaces:**
- Consumes: `tokenize` (Task 8); `llm.generate_json`.
- Produces (`app.retrieval.understand`):
  - `INTENTS = ("explain", "navigate", "account", "off_topic")`, `UNDERSTAND_TIMEOUT_S = 2.5`, `HISTORY_TURNS = 4`, `HISTORY_CHARS = 400`
  - `@dataclass Understanding(search_query: str, keywords: list[str], intent: str, skipped: bool = False, fallback: bool = False, error: Optional[str] = None)`
  - `self_contained(question: str) -> bool`, `needs_rewrite(question, history, lecture_title) -> bool`
  - `build_user_prompt(question, history, lecture_title) -> str`, `parse_understanding(raw, question) -> Optional[Understanding]`
  - `async understand(question, history=(), lecture_title=None) -> Understanding`
  - module-level `async _complete(system, user) -> Optional[dict]` (tests monkeypatch it)

**Skip rule (spec §2.1):** the model is called only when there is context to fold in (history or a current lecture) **or** the question leans on missing context (a pronoun like "this/it/that/he", or it opens with a follow-up word like "and/so/what about"). A self-contained question with no context — including a bare acronym like "IIFE?" — is searched as typed with `intent="explain"`, no LLM call.

- [ ] **Step 1: Write the failing tests**

`backend/tests/test_understand.py`:

```python
import asyncio

import pytest

from app.retrieval import understand as un

HIST = [{"role": "user", "content": "what is the np package?"},
        {"role": "assistant", "content": "np is a tool that runs the publish checks. " + "x" * 600}]


@pytest.mark.parametrize("q", ["what is an IIFE?", "IIFE?", "np", "how do I publish an npm package with np"])
def test_acronym_question_is_self_contained(q):
    assert un.self_contained(q) and not un.needs_rewrite(q, [], None)


@pytest.mark.parametrize("q", ["what does this mean?", "and how do I use it?", "what about the second one he showed",
                               "so why?"])
def test_context_leaning_questions_need_a_rewrite_even_without_history(q):
    assert not un.self_contained(q) and un.needs_rewrite(q, [], None)


def test_any_context_means_a_rewrite():
    assert un.needs_rewrite("what is an IIFE?", HIST, None)
    assert un.needs_rewrite("what is an IIFE?", [], "6.5 - IIFE, To The Rescue")


def test_prompt_has_lecture_last_turns_truncated_and_message():
    long_hist = [{"role": "user", "content": f"q{i}"} for i in range(6)] + HIST
    text = un.build_user_prompt("how do I use it?", long_hist, "11.1 - Publishing using `np`")
    assert text.startswith("Current lecture: 11.1 - Publishing using `np`")
    assert "q3" not in text and "student: q4" in text                # only the last HISTORY_TURNS (4) turns
    assert "student: what is the np package?" in text and "tutor: np is a tool" in text
    assert "x" * un.HISTORY_CHARS not in text
    assert text.rstrip().endswith("New message: how do I use it?")
    assert "Current lecture: none" in un.build_user_prompt("q", [], None)


def test_parse_valid_and_cleaned():
    u = un.parse_understanding({"search_query": " How do I publish a package with np? ",
                                "keywords": ["np", "publish", "np", "", "a", "b", "c", "d", "e"],
                                "intent": "EXPLAIN"}, "how do I use it?")
    assert (u.search_query, u.keywords, u.intent) == ("How do I publish a package with np?",
                                                      ["np", "publish", "a", "b", "c", "d"], "explain")


@pytest.mark.parametrize("raw,expect", [
    ({"search_query": "q2", "keywords": [], "intent": "dance"}, ("q2", "explain")),
    ({"search_query": "", "keywords": [], "intent": "account"}, ("orig", "account")),
    ({"search_query": "y" * 400, "intent": "navigate"}, ("orig", "navigate")),
])
def test_parse_repairs_fields(raw, expect):
    u = un.parse_understanding(raw, "orig")
    assert (u.search_query, u.intent) == expect


@pytest.mark.parametrize("raw", [None, "text", []])
def test_parse_unusable_is_none(raw):
    assert un.parse_understanding(raw, "q") is None


async def test_skip_never_calls_the_model(monkeypatch):
    async def boom(system, user):
        raise AssertionError("self-contained, no context: no LLM call")

    monkeypatch.setattr(un, "_complete", boom)
    u = await un.understand("what is an IIFE?")
    assert u.skipped and (u.search_query, u.intent, u.keywords) == ("what is an IIFE?", "explain", [])


async def test_understand_rewrites_with_history(monkeypatch):
    async def fake(system, user):
        assert "New message: ok how do I use it to publish?" in user
        return {"search_query": "how do I publish a package with np?", "keywords": ["np"], "intent": "explain"}

    monkeypatch.setattr(un, "_complete", fake)
    u = await un.understand("ok how do I use it to publish?", HIST, None)
    assert not u.skipped and not u.fallback and u.search_query == "how do I publish a package with np?"


async def test_timeout_and_errors_fall_back_to_the_raw_question(monkeypatch, capsys):
    async def slow(system, user):
        await asyncio.sleep(1)

    monkeypatch.setattr(un, "UNDERSTAND_TIMEOUT_S", 0.01)
    monkeypatch.setattr(un, "_complete", slow)
    u = await un.understand("what does this mean?", HIST, None)
    assert u.fallback and u.error == "TimeoutError" and (u.search_query, u.intent) == ("what does this mean?", "explain")

    async def boom(system, user):
        raise RuntimeError("down")

    monkeypatch.setattr(un, "_complete", boom)
    assert (await un.understand("what does this mean?", HIST, None)).fallback
    assert "[understand] fallback" in capsys.readouterr().out
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `cd backend && .venv/bin/pytest tests/test_understand.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'app.retrieval.understand'`.

- [ ] **Step 3: Implement**

`backend/app/retrieval/understand.py`:

```python
"""Query understanding (spec §2.1): one cheap gpt-4.1-mini JSON call turns the raw message + recent
history + current lecture into {search_query, keywords, intent}. Skipped when the question is
self-contained and there is no context to fold in. Never decides scope or coverage."""
import asyncio
import re
from dataclasses import dataclass, field
from typing import Optional, Sequence

from app.retrieval.text import tokenize

INTENTS = ("explain", "navigate", "account", "off_topic")
UNDERSTAND_TIMEOUT_S = 2.5
HISTORY_TURNS = 4
HISTORY_CHARS = 400
MAX_QUERY_CHARS = 300

_DEICTIC = re.compile(r"\b(this|that|these|those|it|its|they|them|he|she|his|her|here|there|above|earlier|"
                      r"previous)\b", re.IGNORECASE)
_FOLLOW_UP = re.compile(r"^\s*(and|also|so|but|then|ok|okay|what about|how about)\b", re.IGNORECASE)

SYSTEM = """You turn a student's chat message into a search request over the01.dev's course video transcripts.

Given the recent conversation, the lecture the student is watching (if any) and the new message, return:
- search_query: the message rewritten as ONE standalone search question, resolving "this", "it", "that", "he" and follow-ups from the conversation or the current lecture. Keep the student's technical terms, acronyms, commands and code names exactly as written (IIFE, np, useMemo, npm link). Do not add topics the student did not ask about. If the message is already standalone, return it unchanged.
- keywords: 1 to 6 technical terms or names to match literally in transcripts, in their standard spelling.
- intent, exactly one of:
  - "explain": wants something explained, compared, debugged or shown how (the default)
  - "navigate": explicitly asks to be taken, jumped or shown to a place in the video ("take me to", "jump to", "where in the video")
  - "account": asks about their own courses, enrollment, progress, streak, quiz scores or strengths
  - "off_topic": not about software development or the course's subject at all (cooking, sports, trivia)
Return only JSON: {"search_query": "...", "keywords": ["..."], "intent": "explain|navigate|account|off_topic"}"""


@dataclass
class Understanding:
    search_query: str
    keywords: list[str] = field(default_factory=list)
    intent: str = "explain"
    skipped: bool = False
    fallback: bool = False
    error: Optional[str] = None


async def _complete(system: str, user: str) -> Optional[dict]:
    from app.services.llm import llm
    return await llm.generate_json(system, user, temperature=0.0, max_tokens=200)


def self_contained(question: str) -> bool:
    return bool(tokenize(question)) and not _DEICTIC.search(question) and not _FOLLOW_UP.search(question)


def needs_rewrite(question: str, history: Sequence[dict], lecture_title: Optional[str]) -> bool:
    return bool(history) or bool(lecture_title) or not self_contained(question)


def build_user_prompt(question: str, history: Sequence[dict], lecture_title: Optional[str]) -> str:
    turns = [t for t in history if t.get("role") in ("user", "assistant")][-HISTORY_TURNS:]
    convo = "\n".join(f"{'student' if t['role'] == 'user' else 'tutor'}: {str(t.get('content', ''))[:HISTORY_CHARS]}"
                      for t in turns) or "(none)"
    return (f"Current lecture: {lecture_title or 'none'}\nConversation (oldest first):\n{convo}\n"
            f"New message: {question}")


def parse_understanding(raw, question: str) -> Optional[Understanding]:
    if not isinstance(raw, dict):
        return None
    q = str(raw.get("search_query") or "").strip()
    if not q or len(q) > MAX_QUERY_CHARS:
        q = question
    keywords: list[str] = []
    for k in raw.get("keywords") if isinstance(raw.get("keywords"), list) else []:
        k = str(k).strip()
        if k and len(k) <= 40 and k not in keywords:
            keywords.append(k)
    intent = str(raw.get("intent") or "").strip().lower()
    return Understanding(q, keywords[:6], intent if intent in INTENTS else "explain")


def _fall_back(question: str, why: str) -> Understanding:
    print(f"[understand] fallback ({why}): {question[:80]!r}")
    return Understanding(question, [], "explain", fallback=True, error=why)


async def understand(question: str, history: Sequence[dict] = (), lecture_title: Optional[str] = None) -> Understanding:
    if not needs_rewrite(question, history, lecture_title):
        return Understanding(question, [], "explain", skipped=True)
    try:
        raw = await asyncio.wait_for(_complete(SYSTEM, build_user_prompt(question, history, lecture_title)),
                                     timeout=UNDERSTAND_TIMEOUT_S)
    except asyncio.TimeoutError:
        return _fall_back(question, "TimeoutError")
    except Exception as e:  # noqa: BLE001 — understanding is an optimisation; never fail the turn
        return _fall_back(question, repr(e))
    return parse_understanding(raw, question) or _fall_back(question, "unusable reply")
```

Check the parse test: keywords `["np", "publish", "np", "", "a", "b", "c", "d", "e"]` → dedupe/drop empty → `["np", "publish", "a", "b", "c", "d", "e"]` → first 6 → `["np", "publish", "a", "b", "c", "d"]`; "so why?" has no content token ("so", "why" are stopwords) → not self-contained.

- [ ] **Step 4: Run the tests to verify they pass**

Run: `cd backend && .venv/bin/pytest tests/test_understand.py -q`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add backend/app/retrieval/understand.py backend/tests/test_understand.py
git commit -m "feat(retrieval): query understanding — standalone rewrite, keywords, intent; skipped for self-contained questions

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

### Task 18: Understanding inside `graded_search` — parallel raw retrieval, multi-query fusion, intent bypass

**Latency design:** when a rewrite is needed, retrieval for the **raw** question starts immediately (`asyncio.create_task`) while the understanding call runs (≤ `UNDERSTAND_TIMEOUT_S` = 2.5 s, typically ~0.4–0.7 s). When the rewrite arrives, only the rewrite's own retrieval is added (one embedding + two scoped searches) and **all** lists are fused with RRF — the raw candidates are never thrown away, so a bad rewrite can't lose a good raw hit. Keywords join the lexical query only; an unchanged query with keywords adds a lexical list only (no extra embedding). Intent `account` (and `off_topic`, unless the caller forced `navigate`) returns `NOT_COVERED` with no rerank call. The reranker judges the standalone `search_query`. Budget per question: 1 understanding call (skipped for self-contained questions without context) + 1 rerank call (≤ 5 s cap) — p95 target for retrieval + rerank is 1.5 s (spec §6); the eval reports p50/p95 of the whole `graded_search` wall time, which is stricter.

**Files:**
- Modify: `backend/app/retrieval/pipeline.py` (`_lists`, `search`, `graded_search`)
- Modify: `backend/app/eval/retrieval_systems.py` (`V2System(simulate_lecture=False)`), `backend/scripts/eval_retrieval.py` (`--simulate-lecture`)
- Test: `backend/tests/test_retrieval_pipeline.py`, `backend/tests/test_eval_runner.py`

**Interfaces:**
- Consumes: `understand.needs_rewrite`, `understand.understand`, `understand.Understanding` (Task 17); `rrf_fuse`, `rerank`, `decide`.
- Produces: `graded_search(...)` signature unchanged (Task 13); `RetrievalResult.intent` is now the effective intent (caller's `navigate` wins, else the model's), `search_query` the standalone rewrite, `timings_ms` gains `"understand"` when the model was called. `pipeline._lists(queries, scope, lecture_id, terms=(), *, vector=True) -> tuple[list, list]` (internal). `V2System(simulate_lecture: bool = False)`.

- [ ] **Step 1: Write the failing tests**

Append to `backend/tests/test_retrieval_pipeline.py`:

```python
import asyncio

from app.retrieval import understand as un

HIST = [{"role": "user", "content": "what is the np package?"}]


def _understood(query, intent="explain", keywords=()):
    async def fake(system, user):
        return {"search_query": query, "keywords": list(keywords), "intent": intent}
    return fake


async def test_rewrite_is_fused_with_the_raw_retrieval_and_judged(mem, grader, monkeypatch):
    monkeypatch.setattr(un, "_complete", _understood("publish with np", keywords=["np"]))
    grader({1: "answers"})
    res = await pipeline.graded_search("how do I use it?", ["custom-library"], history=HIST)
    assert mem == ["how do I use it?", "publish with np"]          # raw first, then the rewrite
    assert grader.calls[0].startswith("Question: publish with np")
    assert res.search_query == "publish with np" and res.best().candidate.chunk.lecture_id == "cl-10-0"
    assert "understand" in res.timings_ms


async def test_raw_retrieval_starts_while_understanding_runs(mem, grader, monkeypatch):
    saw_raw = []

    async def waits_for_raw(system, user):
        for _ in range(200):
            if "what does this mean?" in mem:
                break
            await asyncio.sleep(0.001)
        saw_raw.append("what does this mean?" in mem)
        return {"search_query": "what does this mean?", "keywords": [], "intent": "explain"}

    monkeypatch.setattr(un, "_complete", waits_for_raw)
    grader({1: "partial"})
    await pipeline.graded_search("what does this mean?", ["custom-library"], lecture_title="6.5 - IIFE, To The Rescue")
    assert saw_raw == [True]
    assert mem == ["what does this mean?"]                         # unchanged rewrite: no second embedding


@pytest.mark.parametrize("intent", ["account", "off_topic"])
async def test_account_and_off_topic_bypass_rerank(mem, grader, monkeypatch, intent):
    monkeypatch.setattr(un, "_complete", _understood("what courses do I own", intent=intent))
    res = await pipeline.graded_search("what courses do I own?", ["custom-library"], history=HIST)
    assert (res.outcome, res.intent, res.graded) == (pipeline.Outcome.NOT_COVERED, intent, [])
    assert grader.calls == []


async def test_forced_navigate_beats_an_off_topic_guess(mem, grader, monkeypatch):
    monkeypatch.setattr(un, "_complete", _understood("IIFE", intent="off_topic"))
    grader({1: "answers"})
    res = await pipeline.graded_search("take me to it", ["custom-library"], intent="navigate", history=HIST)
    assert res.intent == "navigate" and res.outcome == pipeline.Outcome.COVERED
    assert "Intent: navigate" in grader.calls[0]


async def test_self_contained_question_without_context_skips_understanding(mem, grader, monkeypatch):
    async def boom(system, user):
        raise AssertionError("no understanding call expected")

    monkeypatch.setattr(un, "_complete", boom)
    grader({1: "answers"})
    res = await pipeline.graded_search("what is an IIFE?", ["custom-library"])
    assert res.outcome == pipeline.Outcome.COVERED and "understand" not in res.timings_ms
```

Append to `backend/tests/test_eval_runner.py`:

```python
async def test_v2_simulated_lecture_is_never_a_gold_lecture(monkeypatch):
    from types import SimpleNamespace

    from app.retrieval import pipeline
    from app.retrieval.rerank import Outcome
    from app.services import vector_store as vs_mod
    seen = {}

    async def fake_graded(question, scope, **kw):
        seen["lecture"] = kw["lecture_title"]
        return pipeline.RetrievalResult(Outcome.NOT_COVERED, [])

    monkeypatch.setattr(pipeline, "graded_search", fake_graded)
    monkeypatch.setattr(vs_mod, "vector_store", SimpleNamespace(chunks=[_chunk("custom-library-5-2"),
                                                                         _chunk("custom-library-9-0")]))
    await rs.V2System(simulate_lecture=True).predict(_row("a"), "player")       # gold: custom-library-5-2
    assert seen["lecture"] == "T custom-library-9-0"
    await rs.V2System(simulate_lecture=False).predict(_row("a"), "player")
    assert seen["lecture"] is None
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `cd backend && .venv/bin/pytest tests/test_retrieval_pipeline.py tests/test_eval_runner.py -q`
Expected: FAIL — no understanding call is made (`mem` holds only the raw question; account/off_topic still rerank); `V2System() takes no arguments`.

- [ ] **Step 3: Implement**

`backend/app/retrieval/pipeline.py` — add `from app.retrieval import understand as qu` and replace `search` / `graded_search`:

```python
async def _lists(queries: Sequence[str], scope: tuple[str, ...], lecture_id: Optional[str],
                 terms: Sequence[str] = (), *, vector: bool = True) -> tuple[list, list]:
    """Vector top VEC_K (one embedding per query) + lexical top LEX_K per query, all inside `scope`."""
    r = factory.get_retriever()
    joined = " ".join(terms)
    embeddings = await asyncio.gather(*(embedding_service.embed(q) for q in queries)) if vector else []
    lists = await asyncio.gather(
        *(r.vector_search(e, scope, VEC_K, lecture_id) for e in embeddings),
        *(r.lexical_search(tokenize(f"{q} {joined}"), scope, LEX_K, lecture_id) for q in queries))
    return list(lists[:len(embeddings)]), list(lists[len(embeddings):])


async def search(question: str, scope: Sequence[str], *, lecture_id: Optional[str] = None, limit: int = LIMIT,
                 per_lecture: Optional[int] = PER_LECTURE, extra_queries: Sequence[str] = (),
                 extra_terms: Sequence[str] = ()) -> list[Candidate]:
    scope = tuple(dict.fromkeys(s for s in scope if s))
    if not scope:
        return []
    await _ensure_loaded()
    queries = list(dict.fromkeys(q for q in (question, *extra_queries) if q and q.strip()))
    vec, lex = await _lists(queries, scope, lecture_id, extra_terms)
    return rrf_fuse(vec, lex, limit=limit, per_lecture=per_lecture)


def _same(a: str, b: str) -> bool:
    return " ".join(a.lower().split()) == " ".join(b.lower().split())


async def graded_search(question: str, scope: Sequence[str], *, intent: str = "explain",
                        lecture_id: Optional[str] = None, history: Sequence[dict] = (),
                        lecture_title: Optional[str] = None) -> RetrievalResult:
    """understand ∥ raw retrieval → (+ rewrite retrieval) → RRF → rerank → coverage decision."""
    t0 = time.perf_counter()
    scope = tuple(dict.fromkeys(s for s in scope if s))
    if not scope:
        return RetrievalResult(Outcome.NOT_COVERED, [], intent=intent, search_query=question)
    await _ensure_loaded()
    timings: dict = {}
    if qu.needs_rewrite(question, history, lecture_title):
        raw = asyncio.create_task(_lists([question], scope, lecture_id))   # starts now, runs alongside
        u = await qu.understand(question, history, lecture_title)
        timings["understand"] = _ms(t0)
        if u.intent == "account" or (u.intent == "off_topic" and intent != "navigate"):
            raw.cancel()
            timings["total"] = _ms(t0)
            return RetrievalResult(Outcome.NOT_COVERED, [], intent=u.intent, search_query=u.search_query,
                                   timings_ms=timings)
        vec, lex = await raw
        rewritten = not _same(u.search_query, question)
        if rewritten or u.keywords:
            v2, l2 = await _lists([u.search_query], scope, lecture_id, u.keywords, vector=rewritten)
            vec, lex = vec + v2, lex + l2
    else:
        u = qu.Understanding(question, [], "explain", skipped=True)
        vec, lex = await _lists([question], scope, lecture_id)
    cands = rrf_fuse(vec, lex, limit=LIMIT, per_lecture=PER_LECTURE)
    timings["retrieve"] = _ms(t0)
    effective = intent if intent != "explain" else u.intent
    t1 = time.perf_counter()
    rr = await rerank(u.search_query, cands, intent=effective)
    outcome, ordered = decide(rr.graded)
    timings["rerank"], timings["total"] = _ms(t1), _ms(t0)
    return RetrievalResult(outcome, ordered, intent=effective, search_query=u.search_query, fallback=rr.fallback,
                           timings_ms=timings)
```

`backend/app/eval/retrieval_systems.py` — `V2System` gains a constructor and uses it in the player branch:

```python
class V2System:
    """Phase 4+: graded_search (understand ∥ hybrid → rerank → decision); navigation via find_moment's locator.
    simulate_lecture: in player mode, rows without a lecture get the course's first NON-gold lecture as the
    one being watched, so query understanding runs as it does in the real player (always a lecture) without
    leaking the answer."""
    name = "v2"

    def __init__(self, simulate_lecture: bool = False):
        self.simulate_lecture = simulate_lecture

    def _lecture_for(self, row: Row, mode: str):
        if row.lecture_title or mode != "player" or not self.simulate_lecture:
            return row.lecture_title
        from app.services import vector_store as vs_mod
        return next((c.lecture_title for c in vs_mod.vector_store.chunks
                     if c.course_id == row.scope_course and c.lecture_id not in row.gold_lecture_ids), None)
```

and in `predict` pass `lecture_title=self._lecture_for(row, mode)` instead of `row.lecture_title`. In `backend/scripts/eval_retrieval.py` add `ap.add_argument("--simulate-lecture", action="store_true")` and change `make_system` to take it:

```python
def make_system(name: str, simulate_lecture: bool = False):
    from app.eval import retrieval_systems as rs
    return {"v2": rs.V2System}[name](simulate_lecture=simulate_lecture)
```

with `_main` calling `make_system(a.system, a.simulate_lecture)`. (The `_row` helper's `scope_course` is `custom-library` and `_chunk(lid)` makes `lecture_title="T <lid>"` and `course_id="custom-library"`, which the new eval-runner test relies on.)

- [ ] **Step 4: Run the tests to verify they pass**

Run: `cd backend && .venv/bin/pytest tests/test_retrieval_pipeline.py tests/test_understand.py tests/test_eval_runner.py -q`
Expected: PASS. Then `bash backend/scripts/run_tests.sh` → `ALL PASSED`.

- [ ] **Step 5: Commit**

```bash
git add backend/app/retrieval/pipeline.py backend/app/eval/retrieval_systems.py backend/scripts/eval_retrieval.py backend/tests/test_retrieval_pipeline.py backend/tests/test_eval_runner.py
git commit -m "feat(retrieval): query understanding in graded_search — raw retrieval in parallel, rewrite fused via RRF, account/off-topic bypass

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

### Task 19: Phase 5 eval delta

**Files:** generated `backend/eval/retrieval/reports/phase5-understand.json|.md`, `phase5-understand-lecture.json|.md`; modify `HISTORY.md`.

- [ ] **Step 1: Run both variants**

```bash
cd backend && env OPENAI_API_KEY="$(grep '^OPENAI_API_KEY=' /Users/swanandkadam/Desktop/01dev-React-hermes/backend/.env | cut -d= -f2- | tr -d '"')" DATABASE_URL= .venv/bin/python scripts/eval_retrieval.py --label phase5-understand --compare phase4-rerank
cd backend && env OPENAI_API_KEY="$(grep '^OPENAI_API_KEY=' /Users/swanandkadam/Desktop/01dev-React-hermes/backend/.env | cut -d= -f2- | tr -d '"')" DATABASE_URL= .venv/bin/python scripts/eval_retrieval.py --label phase5-understand-lecture --modes player --simulate-lecture --compare phase5-understand
```

Expected: the follow-up hand rows (`hand-followup-np`, `hand-followup-lecture`) are `covered` with the gold lecture; off-topic false-cite rate does not rise; the `-lecture` run shows the real-player latency (understanding on every question) — read its `latency_p95_ms` against the 1.5 s target and note it in the commit message.

- [ ] **Step 2: Commit the numbers**

```bash
git add backend/eval/retrieval/reports/phase5-understand.json backend/eval/retrieval/reports/phase5-understand.md backend/eval/retrieval/reports/phase5-understand-lecture.json backend/eval/retrieval/reports/phase5-understand-lecture.md backend/eval/retrieval/reports/HISTORY.md
git commit -m "eval(retrieval): phase 5 delta — query understanding (with and without a watched lecture)

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

# Phase 6 — PgRetriever + schema migration + HNSW/GIN + boot sync

### Task 20: Throwaway local Postgres for tests + idempotent `rag_chunks` migration

**Files:**
- Create: `backend/scripts/local_pg.py` (start/stop a throwaway cluster; used by tests and the Phase 6 eval)
- Create: `backend/app/retrieval/pg_schema.py` (migration part)
- Modify: `backend/app/services/db.py` (`_init_schema` runs the migration)
- Modify: `backend/tests/conftest.py` (session fixture `local_pg`, function fixture `pg_pool`)
- Test: `backend/tests/test_pg_schema.py`

**Interfaces:**
- Consumes: Homebrew `/opt/homebrew/opt/postgresql@17/bin/{initdb,pg_ctl}` and pgvector 0.8.2 (installed); `app.services.db._configure` (jsonb codec).
- Produces:
  - `scripts.local_pg`: `PG_BIN`, `start_cluster() -> tuple[str, Path]` (DSN `postgresql://postgres@127.0.0.1:<port>/postgres`, temp dir), `stop_cluster(tmp: Path) -> None`; CLI `start` prints `DSN=<dsn>` and `DIR=<dir>`, `stop <dir>`.
  - `app.retrieval.pg_schema`: `SCHEMA_SQL: list[str]`, `async migrate(conn_or_pool) -> None`.
  - tests: fixture `local_pg` (session; DSN; skips when Postgres/pgvector is unavailable) and `pg_pool` (function; asyncpg pool with the jsonb codec, fresh migrated `rag_chunks`).

**Migration SQL** (every statement idempotent; safe on Neon at every boot and on the existing prod table):

```sql
create extension if not exists vector;
create table if not exists rag_chunks (
    chunk_id  text primary key,
    text      text not null,
    meta      jsonb not null,
    embedding vector(1536)
);
alter table rag_chunks
    add column if not exists course_id     text,
    add column if not exists course_num_id integer,
    add column if not exists launched      boolean,
    add column if not exists lecture_id    text,
    add column if not exists lecture_title text,
    add column if not exists chapter       text,
    add column if not exists start_time    integer,
    add column if not exists end_time      integer,
    add column if not exists text_clean    text,
    add column if not exists embed_text    text,
    add column if not exists keywords      text[],
    add column if not exists search_tsv    tsvector,
    add column if not exists embed_model   text,
    add column if not exists content_hash  text,
    add column if not exists row_hash      text;
create index if not exists rag_chunks_embedding_hnsw on rag_chunks
    using hnsw (embedding vector_cosine_ops) with (m = 16, ef_construction = 64);
create index if not exists rag_chunks_search_tsv_gin on rag_chunks using gin (search_tsv);
create index if not exists rag_chunks_course_id_idx on rag_chunks (course_id);
create index if not exists rag_chunks_lecture_id_idx on rag_chunks (lecture_id);
```

(`row_hash` is one column beyond the spec's list: a hash of every non-embedding column, so boot sync can update metadata such as `launched` without re-embedding — Task 21.)

- [ ] **Step 1: Write the local cluster helper**

`backend/scripts/local_pg.py`:

```python
"""Throwaway local Postgres 17 + pgvector for integration tests and local evals. Never the real DB:
a fresh cluster in a temp dir, listening on 127.0.0.1 on a random free port, deleted on stop.

  .venv/bin/python scripts/local_pg.py start        # prints DSN=... and DIR=...
  .venv/bin/python scripts/local_pg.py stop <DIR>
"""
import os
import shutil
import socket
import subprocess
import sys
import tempfile
from pathlib import Path

PG_BIN = Path(os.getenv("PG_BIN", "/opt/homebrew/opt/postgresql@17/bin"))


def _free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def start_cluster() -> tuple[str, Path]:
    """Raises FileNotFoundError / subprocess.SubprocessError when Postgres can't be started."""
    initdb, pg_ctl = PG_BIN / "initdb", PG_BIN / "pg_ctl"
    if not initdb.exists() or not pg_ctl.exists():
        raise FileNotFoundError(f"postgresql binaries not found in {PG_BIN}")
    tmp = Path(tempfile.mkdtemp(prefix="rpg"))
    data, port = tmp / "data", _free_port()
    try:
        subprocess.run([str(initdb), "-D", str(data), "-U", "postgres", "-A", "trust", "-E", "UTF8", "--no-sync"],
                       check=True, capture_output=True, timeout=120)
        subprocess.run([str(pg_ctl), "-D", str(data), "-l", str(tmp / "server.log"), "-w", "-t", "60",
                        "-o", f"-p {port} -c listen_addresses=127.0.0.1 -k {tmp} -c fsync=off", "start"],
                       check=True, capture_output=True, timeout=90)
    except BaseException:
        shutil.rmtree(tmp, ignore_errors=True)
        raise
    return f"postgresql://postgres@127.0.0.1:{port}/postgres", tmp


def stop_cluster(tmp: Path) -> None:
    subprocess.run([str(PG_BIN / "pg_ctl"), "-D", str(Path(tmp) / "data"), "-m", "immediate", "stop"],
                   capture_output=True, timeout=60)
    shutil.rmtree(tmp, ignore_errors=True)


def main(argv=None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    if argv[:1] == ["start"]:
        dsn, tmp = start_cluster()
        print(f"DSN={dsn}\nDIR={tmp}")
        return 0
    if argv[:1] == ["stop"] and len(argv) == 2:
        stop_cluster(Path(argv[1]))
        return 0
    print(__doc__)
    return 2


if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 2: Add the fixtures**

Append to `backend/tests/conftest.py`:

```python
@pytest.fixture(scope="session")
def local_pg():
    """DSN of a throwaway local Postgres + pgvector cluster (temp dir, random port, 127.0.0.1).
    Skips the requesting test when Postgres or pgvector is unavailable. Never the real database."""
    import asyncio

    import asyncpg

    from scripts.local_pg import start_cluster, stop_cluster

    try:
        dsn, tmp = start_cluster()
    except Exception as e:  # noqa: BLE001 — no local Postgres: skip, don't fail
        pytest.skip(f"local Postgres unavailable: {e!r}")

    async def _vector_ok() -> bool:
        try:
            conn = await asyncpg.connect(dsn)
            try:
                await conn.execute("create extension if not exists vector")
                return True
            finally:
                await conn.close()
        except Exception:  # noqa: BLE001
            return False

    try:
        if not asyncio.run(_vector_ok()):
            pytest.skip("pgvector extension unavailable in the local Postgres")
        yield dsn
    finally:
        stop_cluster(tmp)


@pytest.fixture
async def pg_pool(local_pg):
    """Pool on the throwaway cluster with the app's jsonb codec and a fresh, migrated rag_chunks."""
    import asyncpg

    from app.retrieval import pg_schema
    from app.services import db

    pool = await asyncpg.create_pool(dsn=local_pg, min_size=1, max_size=3, init=db._configure)
    try:
        await pool.execute("drop table if exists rag_chunks")
        await pg_schema.migrate(pool)
        yield pool
    finally:
        await pool.close()
```

- [ ] **Step 3: Write the failing migration tests**

`backend/tests/test_pg_schema.py` (Task 21 appends the sync tests):

```python
"""rag_chunks migration + boot sync against a THROWAWAY local Postgres (skipped when unavailable)."""
from app.retrieval import pg_schema

NEW_COLUMNS = {"course_id", "course_num_id", "launched", "lecture_id", "lecture_title", "chapter", "start_time",
               "end_time", "text_clean", "embed_text", "keywords", "search_tsv", "embed_model", "content_hash",
               "row_hash"}


async def _columns(pool) -> set[str]:
    rows = await pool.fetch("select column_name from information_schema.columns where table_name = 'rag_chunks'")
    return {r["column_name"] for r in rows}


async def test_migration_creates_columns_and_indexes(pg_pool):
    assert NEW_COLUMNS | {"chunk_id", "text", "meta", "embedding"} <= await _columns(pg_pool)
    idx = {r["indexname"]: r["indexdef"] for r in await pg_pool.fetch(
        "select indexname, indexdef from pg_indexes where tablename = 'rag_chunks'")}
    assert "hnsw" in idx["rag_chunks_embedding_hnsw"] and "vector_cosine_ops" in idx["rag_chunks_embedding_hnsw"]
    assert "gin" in idx["rag_chunks_search_tsv_gin"]
    assert {"rag_chunks_course_id_idx", "rag_chunks_lecture_id_idx"} <= set(idx)


async def test_migration_is_idempotent_and_upgrades_the_old_table(pg_pool):
    await pg_pool.execute("drop table rag_chunks")
    await pg_pool.execute("create table rag_chunks (chunk_id text primary key, text text not null, "
                          "meta jsonb not null, embedding vector(1536))")
    await pg_pool.execute("insert into rag_chunks (chunk_id, text, meta) values ('old-1', 't', '{}'::jsonb)")
    await pg_schema.migrate(pg_pool)
    await pg_schema.migrate(pg_pool)
    assert NEW_COLUMNS <= await _columns(pg_pool)
    row = await pg_pool.fetchrow("select chunk_id, content_hash from rag_chunks")
    assert (row["chunk_id"], row["content_hash"]) == ("old-1", None)        # kept; sync will re-embed it
```

- [ ] **Step 4: Run the tests to verify they fail**

Run: `cd backend && .venv/bin/pytest tests/test_pg_schema.py -q -rs`
Expected: FAIL — `ModuleNotFoundError: No module named 'app.retrieval.pg_schema'` (not SKIPPED: if it says skipped, read the skip reason; the cluster must start on this machine).

- [ ] **Step 5: Implement the migration**

`backend/app/retrieval/pg_schema.py`:

```python
"""rag_chunks schema (spec §4): idempotent migration, run at every boot by db._init_schema.
Task 21 adds the boot sync (content_hash / row_hash) to this module."""

SCHEMA_SQL = [
    "create extension if not exists vector",
    """create table if not exists rag_chunks (
           chunk_id  text primary key,
           text      text not null,
           meta      jsonb not null,
           embedding vector(1536)
       )""",
    """alter table rag_chunks
           add column if not exists course_id     text,
           add column if not exists course_num_id integer,
           add column if not exists launched      boolean,
           add column if not exists lecture_id    text,
           add column if not exists lecture_title text,
           add column if not exists chapter       text,
           add column if not exists start_time    integer,
           add column if not exists end_time      integer,
           add column if not exists text_clean    text,
           add column if not exists embed_text    text,
           add column if not exists keywords      text[],
           add column if not exists search_tsv    tsvector,
           add column if not exists embed_model   text,
           add column if not exists content_hash  text,
           add column if not exists row_hash      text""",
    """create index if not exists rag_chunks_embedding_hnsw on rag_chunks
           using hnsw (embedding vector_cosine_ops) with (m = 16, ef_construction = 64)""",
    "create index if not exists rag_chunks_search_tsv_gin on rag_chunks using gin (search_tsv)",
    "create index if not exists rag_chunks_course_id_idx on rag_chunks (course_id)",
    "create index if not exists rag_chunks_lecture_id_idx on rag_chunks (lecture_id)",
]


async def migrate(conn) -> None:
    """conn: an asyncpg Connection or Pool."""
    for sql in SCHEMA_SQL:
        await conn.execute(sql)
```

`backend/app/services/db.py` — in `_init_schema`, replace the `create table if not exists rag_chunks (...)` `execute` call with:

```python
        from app.retrieval import pg_schema  # rag_chunks columns + HNSW/GIN indexes, idempotent
        await pg_schema.migrate(conn)
```

(the leading `create extension if not exists vector` and the `docs` table/index statements stay as they are).

- [ ] **Step 6: Run the tests to verify they pass**

Run: `cd backend && .venv/bin/pytest tests/test_pg_schema.py -q -rs`
Expected: 2 passed (no skips). Then `bash backend/scripts/run_tests.sh` → `ALL PASSED`.

- [ ] **Step 7: Commit**

```bash
git add backend/scripts/local_pg.py backend/app/retrieval/pg_schema.py backend/app/services/db.py backend/tests/conftest.py backend/tests/test_pg_schema.py
git commit -m "feat(retrieval): idempotent rag_chunks migration with HNSW + GIN indexes; throwaway local Postgres for tests

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

### Task 21: Boot sync by `content_hash` / `row_hash`

**Sync rules:** a chunk is **re-embedded** (≤ 100 inputs per embeddings call) when its id is new, its stored `content_hash` differs from the chunk's (enrichment, glossary, text or model changed — rows from before the migration have `NULL`), or it has no embedding; a chunk whose `row_hash` differs but `content_hash` matches gets a **metadata-only upsert** (embedding kept via `coalesce`); rows whose `chunk_id` is no longer in the seed are **deleted** (skipped when the seed is empty, so a broken load can never wipe the table). Each embedded batch is upserted before the next call, so a failure mid-way resumes on the next boot. Prod boot never calls the LLM — only embeddings for changed rows.

**Files:**
- Modify: `backend/app/retrieval/pg_schema.py` (add `UPSERT_SQL`, `row_values`, `sync_chunks`, `load_embeddings`)
- Modify: `backend/app/services/vector_store.py` (`_init_with_pgvector` delegates to the sync; `backend` attribute)
- Test: `backend/tests/test_pg_schema.py` (sync tests, local Postgres), `backend/tests/test_vector_store_batch.py` (pg-path tests replaced)

**Interfaces:**
- Consumes: `migrate` (Task 20); `lexical_fields` (Task 8); `embed_input` (Task 4); `catalog_service.all_courses()`; `_fmt_vec`, `_parse_vec`, `EMBED_BATCH` from `vector_store` (moved: `pg_schema` defines its own `fmt_vec`/`parse_vec` and `vector_store` imports them).
- Produces (`app.retrieval.pg_schema`):
  - `fmt_vec(v) -> str`, `parse_vec(s) -> list[float]`
  - `row_values(chunk, course_num_id: Optional[int], launched: bool) -> dict` (keys: every column below except `embedding`, plus `row_hash`)
  - `async sync_chunks(pool, chunks, embed_many, *, batch: int = 100) -> dict` → `{"new", "changed", "meta", "deleted", "unchanged"}`; `embed_many(texts, batch_size=100) -> list[list[float]]`
  - `async load_embeddings(pool) -> dict[str, list[float]]`
- `InMemoryVectorStore.backend: str` — `"pgvector"` after a successful sync, else `"memory"` (Task 23 reads it).

- [ ] **Step 1: Write the failing sync tests**

Append to `backend/tests/test_pg_schema.py`:

```python
import pytest

from app.models import TranscriptChunk
from app.retrieval.enrichment import apply_enrichment, embed_input
from app.services import catalog_service


def _chunks(n=250, tmp=None):
    raw = [TranscriptChunk(chunk_id=f"custom-library-0-0-{i}", course_id="custom-library",
                           course_title="Build a Custom Library", lecture_id="custom-library-0-0",
                           lecture_title="1.1 - Intro", text=f"passage {i} about np and IIFE",
                           start_time=60 * i, end_time=60 * i + 60) for i in range(n)]
    return apply_enrichment(raw, tmp / "e", tmp / "g")


class Embedder:
    def __init__(self):
        self.calls: list[list[str]] = []

    async def __call__(self, texts, batch_size=100):
        self.calls.append(list(texts))
        return [[1.0 + (hash(t) % 7)] + [0.0] * 1535 for t in texts]


async def test_first_sync_embeds_in_batches_of_100_and_fills_every_column(pg_pool, tmp_path):
    chunks, emb = _chunks(250, tmp_path), Embedder()
    stats = await pg_schema.sync_chunks(pg_pool, chunks, emb)
    assert [len(c) for c in emb.calls] == [100, 100, 50]
    assert stats == {"new": 250, "changed": 0, "meta": 0, "deleted": 0, "unchanged": 0}
    row = await pg_pool.fetchrow("select * from rag_chunks where chunk_id = 'custom-library-0-0-3'")
    assert (row["course_id"], row["course_num_id"], row["launched"]) == ("custom-library", 2, True)
    assert (row["start_time"], row["end_time"], row["text"]) == (180, 240, "passage 3 about np and IIFE")
    assert row["content_hash"] == chunks[3].content_hash and row["embed_text"] == chunks[3].embed_text
    assert row["meta"]["chunk_id"] == "custom-library-0-0-3"
    hit = await pg_pool.fetchval("select count(*) from rag_chunks where search_tsv @@ to_tsquery('simple', 'iife')")
    assert hit == 250
    assert len(await pg_schema.load_embeddings(pg_pool)) == 250


async def test_sync_is_idempotent(pg_pool, tmp_path):
    chunks = _chunks(5, tmp_path)
    await pg_schema.sync_chunks(pg_pool, chunks, Embedder())
    emb = Embedder()
    stats = await pg_schema.sync_chunks(pg_pool, chunks, emb)
    assert emb.calls == [] and stats["unchanged"] == 5


async def test_sync_reembeds_only_changed_rows(pg_pool, tmp_path):
    chunks = _chunks(5, tmp_path)
    await pg_schema.sync_chunks(pg_pool, chunks, Embedder())
    # the LAST chunk of the lecture: no later chunk carries its sentence as "Previously:" overlap
    raw = [c.model_copy(update={"text": "edited np text"}) if c.chunk_id.endswith("-4") else c for c in chunks]
    changed = apply_enrichment(raw, tmp_path / "e", tmp_path / "g")
    emb = Embedder()
    stats = await pg_schema.sync_chunks(pg_pool, changed, emb)
    assert emb.calls == [[embed_input(changed[4])]]
    assert (stats["changed"], stats["unchanged"]) == (1, 4)
    assert await pg_pool.fetchval("select text from rag_chunks where chunk_id = 'custom-library-0-0-4'") == "edited np text"


async def test_sync_updates_metadata_without_embedding(pg_pool, tmp_path, monkeypatch):
    chunks = _chunks(3, tmp_path)
    await pg_schema.sync_chunks(pg_pool, chunks, Embedder())
    courses = [dict(c, launched=False) if c["slug"] == "custom-library" else c for c in catalog_service.all_courses()]
    monkeypatch.setattr(catalog_service, "all_courses", lambda: courses)
    emb = Embedder()
    stats = await pg_schema.sync_chunks(pg_pool, chunks, emb)
    assert emb.calls == [] and stats["meta"] == 3
    assert await pg_pool.fetchval("select bool_or(launched) from rag_chunks") is False
    assert await pg_pool.fetchval("select count(*) from rag_chunks where embedding is null") == 0


async def test_sync_deletes_vanished_chunks(pg_pool, tmp_path):
    chunks = _chunks(4, tmp_path)
    await pg_schema.sync_chunks(pg_pool, chunks, Embedder())
    stats = await pg_schema.sync_chunks(pg_pool, chunks[:3], Embedder())
    assert stats["deleted"] == 1
    assert await pg_pool.fetchval("select count(*) from rag_chunks") == 3
    assert (await pg_schema.sync_chunks(pg_pool, [], Embedder()))["deleted"] == 0   # empty seed never wipes
    assert await pg_pool.fetchval("select count(*) from rag_chunks") == 3


async def test_rows_from_before_the_migration_are_reembedded(pg_pool, tmp_path):
    chunks = _chunks(2, tmp_path)
    await pg_pool.execute("insert into rag_chunks (chunk_id, text, meta, embedding) values ($1, $2, $3, $4::vector)",
                          chunks[0].chunk_id, chunks[0].text, {}, pg_schema.fmt_vec([1.0] + [0.0] * 1535))
    emb = Embedder()
    stats = await pg_schema.sync_chunks(pg_pool, chunks, emb)
    assert (stats["new"], stats["changed"]) == (1, 1) and len(emb.calls[0]) == 2
```

In `backend/tests/test_vector_store_batch.py`, delete the pg-path tests that drive `_init_with_pgvector` through `FakePool` (`test_250_missing_chunks_three_batches`, `test_no_missing_chunks_no_embed_calls`, `test_changed_text_is_reembedded_and_upserted`, `test_identical_text_not_reembedded`, `test_logged_counts_new_vs_changed`, `test_pg_path_reembeds_when_the_content_hash_changes` — their behaviour is now pinned against real Postgres above) and replace `test_failure_on_batch_two_keeps_batch_one_and_falls_back` with:

```python
def test_sync_failure_falls_back_to_in_memory(monkeypatch):
    client = FakeClient()
    _setup(monkeypatch, 0, client, FakePool())
    monkeypatch.setenv("DATABASE_URL", "postgres://stub")
    monkeypatch.delenv("RAG_EMBED_CACHE", raising=False)
    seed = [c.model_dump() for c in _chunks(250)]
    monkeypatch.setattr(vs, "json", SimpleNamespace(load=lambda f: seed))

    async def broken_sync(pool, chunks, embed_many, batch=100):
        raise RuntimeError("neon down")

    from app.retrieval import pg_schema
    monkeypatch.setattr(pg_schema, "sync_chunks", broken_sync)
    store = vs.InMemoryVectorStore()
    asyncio.run(store.initialize())
    assert store.backend == "memory"
    assert len(store._embeddings) == len(store.chunks) == 250


def test_successful_sync_marks_the_pgvector_backend(monkeypatch):
    _setup(monkeypatch, 0, FakeClient(), FakePool())
    monkeypatch.setenv("DATABASE_URL", "postgres://stub")
    seed = [c.model_dump() for c in _chunks(3)]
    monkeypatch.setattr(vs, "json", SimpleNamespace(load=lambda f: seed))
    from app.retrieval import pg_schema

    async def ok_sync(pool, chunks, embed_many, batch=100):
        return {"new": 0, "changed": 0, "meta": 0, "deleted": 0, "unchanged": len(chunks)}

    async def embs(pool):
        return {c["chunk_id"]: [0.5, 0.5] for c in seed}

    monkeypatch.setattr(pg_schema, "sync_chunks", ok_sync)
    monkeypatch.setattr(pg_schema, "load_embeddings", embs)
    store = vs.InMemoryVectorStore()
    asyncio.run(store.initialize())
    assert store.backend == "pgvector" and store._embeddings == [[0.5, 0.5]] * 3
```

(`FakePool` stays only as the object `get_pool` returns; its `fetch`/`executemany` are no longer exercised.)

- [ ] **Step 2: Run the tests to verify they fail**

Run: `cd backend && .venv/bin/pytest tests/test_pg_schema.py tests/test_vector_store_batch.py -q -rs`
Expected: FAIL — `AttributeError: module 'app.retrieval.pg_schema' has no attribute 'sync_chunks'`; `InMemoryVectorStore` has no `backend`.

- [ ] **Step 3: Implement**

Append to `backend/app/retrieval/pg_schema.py` (add imports at the top: `import hashlib`, `import json`, `from typing import Optional`, `from app.retrieval.enrichment import embed_input`, `from app.retrieval.text import lexical_fields`):

```python
EMBED_BATCH = 100
COLUMNS = ["chunk_id", "text", "meta", "embedding", "course_id", "course_num_id", "launched", "lecture_id",
           "lecture_title", "chapter", "start_time", "end_time", "text_clean", "embed_text", "keywords",
           "search_tsv", "embed_model", "content_hash", "row_hash"]

UPSERT_SQL = """
insert into rag_chunks (chunk_id, text, meta, embedding, course_id, course_num_id, launched, lecture_id,
                        lecture_title, chapter, start_time, end_time, text_clean, embed_text, keywords,
                        search_tsv, embed_model, content_hash, row_hash)
values ($1, $2, $3, $4::vector, $5, $6, $7, $8, $9, $10, $11, $12, $13, $14, $15,
        setweight(to_tsvector('simple', $16), 'A') || setweight(to_tsvector('simple', $17), 'B')
            || setweight(to_tsvector('simple', $18), 'C'),
        $19, $20, $21)
on conflict (chunk_id) do update set
    text = excluded.text, meta = excluded.meta,
    embedding = coalesce(excluded.embedding, rag_chunks.embedding),
    course_id = excluded.course_id, course_num_id = excluded.course_num_id, launched = excluded.launched,
    lecture_id = excluded.lecture_id, lecture_title = excluded.lecture_title, chapter = excluded.chapter,
    start_time = excluded.start_time, end_time = excluded.end_time, text_clean = excluded.text_clean,
    embed_text = excluded.embed_text, keywords = excluded.keywords, search_tsv = excluded.search_tsv,
    embed_model = excluded.embed_model, content_hash = excluded.content_hash, row_hash = excluded.row_hash
"""


def fmt_vec(v) -> str:
    """List -> pgvector text literal, e.g. '[0.1,0.2]'."""
    return "[" + ",".join(repr(float(x)) for x in v) + "]"


def parse_vec(s: str) -> list[float]:
    return [float(x) for x in s.strip("[]").split(",")] if s else []


def row_values(chunk, course_num_id: Optional[int], launched: bool) -> dict:
    a, b, c = lexical_fields(chunk)
    vals = {
        "chunk_id": chunk.chunk_id, "text": chunk.text, "meta": chunk.model_dump(exclude={"embedding"}),
        "course_id": chunk.course_id, "course_num_id": course_num_id, "launched": launched,
        "lecture_id": chunk.lecture_id, "lecture_title": chunk.lecture_title, "chapter": chunk.chapter,
        "start_time": chunk.start_time, "end_time": chunk.end_time, "text_clean": chunk.text_clean,
        "embed_text": chunk.embed_text, "keywords": list(chunk.keywords),
        "tsv_a": " ".join(a), "tsv_b": " ".join(b), "tsv_c": " ".join(c),
        "embed_model": chunk.embed_model, "content_hash": chunk.content_hash,
    }
    vals["row_hash"] = hashlib.sha256(json.dumps(vals, sort_keys=True, default=str).encode()).hexdigest()
    return vals


def _params(v: dict, embedding: Optional[list[float]]) -> tuple:
    return (v["chunk_id"], v["text"], v["meta"], fmt_vec(embedding) if embedding is not None else None,
            v["course_id"], v["course_num_id"], v["launched"], v["lecture_id"], v["lecture_title"], v["chapter"],
            v["start_time"], v["end_time"], v["text_clean"], v["embed_text"], v["keywords"],
            v["tsv_a"], v["tsv_b"], v["tsv_c"], v["embed_model"], v["content_hash"], v["row_hash"])


async def sync_chunks(pool, chunks, embed_many, *, batch: int = EMBED_BATCH) -> dict:
    from app.services import catalog_service
    courses = {c.get("slug"): (c.get("id"), bool(c.get("launched"))) for c in catalog_service.all_courses()}
    stored = {r["chunk_id"]: r for r in await pool.fetch(
        "select chunk_id, content_hash, row_hash, embedding is not null as has_embedding from rag_chunks")}
    values = {c.chunk_id: row_values(c, *courses.get(c.course_id, (None, False))) for c in chunks}
    stats = {"new": 0, "changed": 0, "meta": 0, "deleted": 0, "unchanged": 0}
    to_embed, meta_only = [], []
    for c in chunks:
        row = stored.get(c.chunk_id)
        if row is None:
            stats["new"] += 1
            to_embed.append(c)
        elif row["content_hash"] != c.content_hash or not row["has_embedding"]:
            stats["changed"] += 1
            to_embed.append(c)
        elif row["row_hash"] != values[c.chunk_id]["row_hash"]:
            stats["meta"] += 1
            meta_only.append(c)
        else:
            stats["unchanged"] += 1
    for i in range(0, len(to_embed), batch):          # each batch is stored before the next call: resumable
        part = to_embed[i:i + batch]
        embs = await embed_many([embed_input(c) for c in part], batch_size=batch)
        await pool.executemany(UPSERT_SQL, [_params(values[c.chunk_id], e) for c, e in zip(part, embs)])
    if meta_only:
        await pool.executemany(UPSERT_SQL, [_params(values[c.chunk_id], None) for c in meta_only])
    if chunks:                                         # an empty seed must never wipe the table
        status = await pool.execute("delete from rag_chunks where not (chunk_id = any($1::text[]))",
                                    [c.chunk_id for c in chunks])
        stats["deleted"] = int(status.split()[-1]) if status and status.startswith("DELETE") else 0
    return stats


async def load_embeddings(pool) -> dict[str, list[float]]:
    rows = await pool.fetch("select chunk_id, embedding::text as emb from rag_chunks where embedding is not null")
    return {r["chunk_id"]: parse_vec(r["emb"]) for r in rows}
```

`backend/app/services/vector_store.py`:
- Delete `_fmt_vec`/`_parse_vec` (now `pg_schema.fmt_vec`/`parse_vec`; grep shows no other user).
- In `__init__` add `self.backend = "memory"`; in `initialize()` set `self.backend = "memory"` right after loading the seed, and `self.backend = "pgvector"` right after `await self._init_with_pgvector()` succeeds (before `return`).
- Replace `_init_with_pgvector`:

```python
    async def _init_with_pgvector(self):
        """Boot sync (app/retrieval/pg_schema.py): re-embed only rows whose content_hash changed, update
        metadata-only changes, delete vanished chunks; then load the vectors for in-process consumers."""
        from app.retrieval import pg_schema
        from app.services.db import get_pool

        pool = await get_pool()
        stats = await pg_schema.sync_chunks(pool, self.chunks, embedding_service.embed_many, batch=EMBED_BATCH)
        stored = await pg_schema.load_embeddings(pool)
        self._embeddings = [stored[c.chunk_id] for c in self.chunks]
        print(f"Vector store ready — {len(self.chunks)} chunks ({stats['new']} new, {stats['changed']} changed, "
              f"{stats['meta']} metadata-only, {stats['deleted']} deleted, {stats['unchanged']} unchanged in pgvector).")
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `cd backend && .venv/bin/pytest tests/test_pg_schema.py tests/test_vector_store_batch.py -q -rs`
Expected: PASS, no skips. Then `bash backend/scripts/run_tests.sh` → `ALL PASSED`.

- [ ] **Step 5: Commit**

```bash
git add backend/app/retrieval/pg_schema.py backend/app/services/vector_store.py backend/tests/test_pg_schema.py backend/tests/test_vector_store_batch.py
git commit -m "feat(retrieval): boot sync by content_hash/row_hash — batched re-embeds, metadata-only updates, vanished-chunk deletes

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

### Task 22: `PgRetriever` — scoped SQL vector + full-text search, same contract

**Files:**
- Create: `backend/app/retrieval/pg.py`
- Modify: `backend/tests/test_retriever_contract.py` (add the `"pg"` backend)

**Interfaces:**
- Consumes: `Retriever` protocol (Task 9); `pg_schema.fmt_vec`, `sync_chunks`, `migrate` (Tasks 20–21); a pool created with `db._configure` (jsonb → dict).
- Produces: `app.retrieval.pg.PgRetriever(pool)` with `name = "pg"`, `vector_search`, `lexical_search` (contract of Task 9), `async ping() -> None` (raises when `rag_chunks` is unreachable), constants `EF_SEARCH = 100`.

**Scoped hybrid SQL** (two statements run concurrently by `pipeline._lists`; fusion stays in `rrf_fuse`):

```sql
-- vector (inside one transaction: SET LOCAL hnsw.ef_search = 100; SET LOCAL hnsw.iterative_scan = relaxed_order)
select meta, 1 - (embedding <=> $1::vector) as score
from rag_chunks
where course_id = any($2::text[])
  and ($3::text is null or lecture_id = $3)
  and embedding is not null
order by embedding <=> $1::vector
limit $4;

-- lexical (same tokens as BM25, 'simple' config, OR-query, weights A/B/C via ts_rank, length-normalised)
select meta, ts_rank(search_tsv, q, 1) as score
from rag_chunks, to_tsquery('simple', $1) as q
where course_id = any($2::text[])
  and ($3::text is null or lecture_id = $3)
  and search_tsv @@ q
order by score desc, chunk_id
limit $4;
```

`iterative_scan` (pgvector ≥ 0.8) makes HNSW keep scanning until `LIMIT` rows pass the scope filter, so a small course is never starved by a filter applied after a 40-row index probe; it is set inside a savepoint so an older pgvector just ignores it. With `relaxed_order` the rows are re-sorted by score in Python. The query string for `to_tsquery` is `" | ".join(tokens)` — tokens are `[a-z0-9]+` from `tokenize`, so no tsquery syntax can be injected.

- [ ] **Step 1: Extend the contract test to Postgres (fails until `pg.py` exists)**

In `backend/tests/test_retriever_contract.py` set `BACKENDS = ["memory", "pg"]` and replace `make_retriever` + the `retriever` fixture with:

```python
@pytest.fixture(params=BACKENDS)
async def retriever(request):
    if request.param == "memory":
        store = InMemoryVectorStore()
        store.chunks = [c for c, _ in CORPUS]
        store._embeddings = [e for _, e in CORPUS]
        yield MemoryRetriever(store)
        return
    import asyncpg

    from app.retrieval import pg_schema
    from app.retrieval.enrichment import embed_input
    from app.retrieval.pg import PgRetriever
    from app.services import db

    dsn = request.getfixturevalue("local_pg")          # skips the pg case when Postgres is unavailable
    pool = await asyncpg.create_pool(dsn=dsn, min_size=1, max_size=3, init=db._configure)
    try:
        await pool.execute("drop table if exists rag_chunks")
        await pg_schema.migrate(pool)
        by_text = {embed_input(c): e for c, e in CORPUS}

        async def embed_many(texts, batch_size=100):
            return [by_text[t] for t in texts]

        await pg_schema.sync_chunks(pool, [c for c, _ in CORPUS], embed_many)
        yield PgRetriever(pool)
    finally:
        await pool.close()
```

(`tests/test_retrieval_pipeline.py` imports only `CORPUS` and `vec` from this module, which are unchanged.)

Add one Postgres-specific test at the bottom:

```python
async def test_pg_rows_come_back_as_full_chunks(retriever):
    if retriever.name != "pg":
        pytest.skip("pg only")
    (chunk, score), *_ = await retriever.vector_search(vec(1, 0, 0, 0), ["custom-library"], 1)
    assert chunk.chunk_id == "cl-5-2-0" and chunk.lecture_title == "6.5 - IIFE, To The Rescue"
    assert chunk.start_time == 0 and chunk.end_time == 60 and chunk.embedding == []
```

- [ ] **Step 2: Run the contract tests to verify the pg cases fail**

Run: `cd backend && .venv/bin/pytest tests/test_retriever_contract.py -q -rs`
Expected: the `[memory]` cases PASS; the `[pg]` cases FAIL with `ModuleNotFoundError: No module named 'app.retrieval.pg'`.

- [ ] **Step 3: Implement**

`backend/app/retrieval/pg.py`:

```python
"""PgRetriever (spec §4): the Retriever contract in SQL — pgvector HNSW cosine search and weighted
full-text search over rag_chunks, both filtered by `course_id = ANY($scope)` inside the query, so
another course's chunk is never scored or returned. Prod uses it when DATABASE_URL is set."""
from typing import Optional, Sequence

import asyncpg

from app.models import TranscriptChunk
from app.retrieval.pg_schema import fmt_vec

EF_SEARCH = 100

VECTOR_SQL = """
select meta, 1 - (embedding <=> $1::vector) as score
from rag_chunks
where course_id = any($2::text[])
  and ($3::text is null or lecture_id = $3)
  and embedding is not null
order by embedding <=> $1::vector
limit $4
"""

LEXICAL_SQL = """
select meta, ts_rank(search_tsv, q, 1) as score
from rag_chunks, to_tsquery('simple', $1) as q
where course_id = any($2::text[])
  and ($3::text is null or lecture_id = $3)
  and search_tsv @@ q
order by score desc, chunk_id
limit $4
"""


def _chunk(meta: dict) -> TranscriptChunk:
    return TranscriptChunk(**{**meta, "embedding": []})


class PgRetriever:
    name = "pg"

    def __init__(self, pool):
        self.pool = pool

    async def ping(self) -> None:
        await self.pool.fetchval("select count(*) from rag_chunks where embedding is not null")

    async def vector_search(self, embedding: list[float], scope: Sequence[str], k: int,
                            lecture_id: Optional[str] = None) -> list[tuple[TranscriptChunk, float]]:
        if not scope or not embedding:
            return []
        async with self.pool.acquire() as conn:
            async with conn.transaction():
                await conn.execute(f"set local hnsw.ef_search = {int(EF_SEARCH)}")
                try:
                    async with conn.transaction():          # savepoint: older pgvector lacks this setting
                        await conn.execute("set local hnsw.iterative_scan = relaxed_order")
                except asyncpg.PostgresError:
                    pass
                rows = await conn.fetch(VECTOR_SQL, fmt_vec(embedding), list(scope), lecture_id, k)
        out = [(_chunk(r["meta"]), float(r["score"])) for r in rows]
        out.sort(key=lambda t: (-t[1], t[0].chunk_id))          # relaxed_order: re-sort exactly
        return out

    async def lexical_search(self, tokens: list[str], scope: Sequence[str], k: int,
                             lecture_id: Optional[str] = None) -> list[tuple[TranscriptChunk, float]]:
        terms = [t for t in dict.fromkeys(tokens) if t.isalnum()]
        if not scope or not terms:
            return []
        rows = await self.pool.fetch(LEXICAL_SQL, " | ".join(terms), list(scope), lecture_id, k)
        return [(_chunk(r["meta"]), float(r["score"])) for r in rows]
```

- [ ] **Step 4: Run the contract tests to verify they pass**

Run: `cd backend && .venv/bin/pytest tests/test_retriever_contract.py tests/test_retrieval_pipeline.py -q -rs`
Expected: every case passes for both `[memory]` and `[pg]`, no skips. If a `[pg]` ranking assertion differs from `[memory]`, fix the SQL (not the test): the contract is the spec.

- [ ] **Step 5: Commit**

```bash
git add backend/app/retrieval/pg.py backend/tests/test_retriever_contract.py
git commit -m "feat(retrieval): PgRetriever — scoped HNSW cosine + weighted full-text in SQL; contract tests on both backends

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

### Task 23: Prod switches to `PgRetriever` at startup; Phase 6 eval delta on Postgres

**Files:**
- Modify: `backend/app/retrieval/factory.py` (add `init_retriever`)
- Modify: `backend/app/main.py` (lifespan calls it; `/health` reports the retriever)
- Modify: `backend/scripts/eval_retrieval.py` (`--pg-dsn` for a LOCAL throwaway Postgres)
- Test: `backend/tests/test_retrieval_pipeline.py`
- Create (generated): `backend/eval/retrieval/reports/phase6-pg.json|.md`; modify `HISTORY.md`

**Interfaces:**
- Consumes: `PgRetriever(pool).ping()` (Task 22); `vector_store.backend` (Task 21); `db.get_pool`.
- Produces: `async factory.init_retriever() -> Retriever` — `PgRetriever` when `DATABASE_URL` is set **and** the boot sync succeeded (`vector_store.backend == "pgvector"`) **and** `ping()` works; otherwise `MemoryRetriever` (local dev, tests, a DB outage at boot). `/health` gains `"retriever": "pg" | "memory"`.

- [ ] **Step 1: Write the failing tests**

Append to `backend/tests/test_retrieval_pipeline.py`:

```python
class _Pool:
    def __init__(self, fail=False):
        self.fail = fail

    async def fetchval(self, sql, *a):
        if self.fail:
            raise RuntimeError("rag_chunks missing")
        return 1


@pytest.mark.parametrize("env,backend,pool,expect", [
    (None, "pgvector", _Pool(), "memory"),          # local dev / tests: no DATABASE_URL
    ("postgres://x", "memory", _Pool(), "memory"),  # boot sync failed -> rows may be stale
    ("postgres://x", "pgvector", _Pool(fail=True), "memory"),
    ("postgres://x", "pgvector", _Pool(), "pg"),
])
async def test_init_retriever_picks_pg_only_when_synced_and_reachable(monkeypatch, env, backend, pool, expect):
    from app.services import vector_store as vs_mod
    if env:
        monkeypatch.setenv("DATABASE_URL", env)
    else:
        monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.setattr(vs_mod.vector_store, "backend", backend, raising=False)

    async def get_pool():
        return pool

    monkeypatch.setattr("app.services.db.get_pool", get_pool)
    monkeypatch.setattr(factory, "_retriever", None)
    r = await factory.init_retriever()
    assert r.name == expect and factory.get_retriever() is r
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `cd backend && .venv/bin/pytest tests/test_retrieval_pipeline.py -q -k init_retriever`
Expected: FAIL — `AttributeError: module 'app.retrieval.factory' has no attribute 'init_retriever'`.

- [ ] **Step 3: Implement**

Append to `backend/app/retrieval/factory.py` (add `import os`):

```python
async def init_retriever() -> Retriever:
    """Startup (app.main lifespan, after vector_store.initialize()). Postgres serves search only when the
    boot sync just succeeded, so SQL never searches rows that are older than the seed."""
    from app.services.vector_store import vector_store
    if os.getenv("DATABASE_URL") and getattr(vector_store, "backend", "memory") == "pgvector":
        try:
            from app.retrieval.pg import PgRetriever
            from app.services.db import get_pool
            r = PgRetriever(await get_pool())
            await r.ping()
            set_retriever(r)
            print("[retrieval] PgRetriever: SQL vector + full-text search, scope-filtered")
            return r
        except Exception as e:  # noqa: BLE001 — never fail boot over the search backend
            print(f"[retrieval] PgRetriever unavailable ({e!r}); using MemoryRetriever")
    from app.retrieval.memory import MemoryRetriever
    r = MemoryRetriever()
    set_retriever(r)
    print("[retrieval] MemoryRetriever: in-process cosine + BM25")
    return r
```

`backend/app/main.py` — in `lifespan`, right after `await vector_store.initialize()`:

```python
    from app.retrieval import factory as retrieval_factory
    await retrieval_factory.init_retriever()
```

and in `/health` add `"retriever": retrieval_factory.get_retriever().name,` (import `from app.retrieval import factory as retrieval_factory` at module top instead of inside `lifespan`, and use it in both places).

`backend/scripts/eval_retrieval.py` — add the option and, in `_main` right after `await vector_store.initialize()`, the Postgres setup (it refuses any non-local host, and reuses the in-memory vectors so no extra embedding calls are made):

```python
    ap.add_argument("--pg-dsn", help="search with PgRetriever on this LOCAL throwaway Postgres (scripts/local_pg.py)")
```

```python
    if a.pg_dsn:
        from urllib.parse import urlsplit

        import asyncpg

        from app.retrieval import factory, pg_schema
        from app.retrieval.enrichment import embed_input
        from app.retrieval.pg import PgRetriever
        from app.services import db
        if urlsplit(a.pg_dsn).hostname not in ("127.0.0.1", "localhost"):
            print("Refusing: --pg-dsn must be a local throwaway cluster (127.0.0.1 / localhost)")
            return 2
        pool = await asyncpg.create_pool(dsn=a.pg_dsn, min_size=1, max_size=8, init=db._configure)
        await pg_schema.migrate(pool)
        known = {embed_input(c): e for c, e in zip(vector_store.chunks, vector_store._embeddings)}

        async def embed_many(texts, batch_size=100):
            return [known[t] for t in texts]

        print(await pg_schema.sync_chunks(pool, vector_store.chunks, embed_many))
        factory.set_retriever(PgRetriever(pool))
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `bash backend/scripts/run_tests.sh`
Expected: `ALL PASSED` (the Postgres tests run, not skip — check with `cd backend && .venv/bin/pytest tests/test_pg_schema.py tests/test_retriever_contract.py -q -rs`).

- [ ] **Step 5: Eval delta on Postgres (local throwaway cluster, real model)**

```bash
cd backend && .venv/bin/python scripts/local_pg.py start
```

Note the printed `DSN=…` and `DIR=…`, then (substitute the DSN):

```bash
cd backend && env OPENAI_API_KEY="$(grep '^OPENAI_API_KEY=' /Users/swanandkadam/Desktop/01dev-React-hermes/backend/.env | cut -d= -f2- | tr -d '"')" DATABASE_URL= .venv/bin/python scripts/eval_retrieval.py --label phase6-pg --pg-dsn "<DSN>" --compare phase5-understand
cd backend && .venv/bin/python scripts/local_pg.py stop "<DIR>"
```

Expected: the sync line `{'new': 1329, ...}`; recall/coverage within noise of `phase5-understand` (same vectors; lexical ranking now `ts_rank` instead of BM25 — a recall@5 drop of more than 0.02 means the two lexical rankers diverge and needs a look before deploy); latency p50/p95 reported. Record the numbers in the commit message.

- [ ] **Step 6: Final local checks (real model)**

```bash
cd backend && env OPENAI_API_KEY="$(grep '^OPENAI_API_KEY=' /Users/swanandkadam/Desktop/01dev-React-hermes/backend/.env | cut -d= -f2- | tr -d '"')" DATABASE_URL= .venv/bin/python scripts/demo_check.py demo-local --enroll 2 --full
cd backend && env OPENAI_API_KEY="$(grep '^OPENAI_API_KEY=' /Users/swanandkadam/Desktop/01dev-React-hermes/backend/.env | cut -d= -f2- | tr -d '"')" DATABASE_URL= .venv/bin/python scripts/demo_check.py demo-local --player --runs 1
```

Expected: exit 0 for both (deep links verbatim, no other course named, jumps only on explicit requests). First prod boot after deploy (not part of this plan) re-embeds all 1,329 rows once (14 embedding calls, ≈ $0.01) and builds the HNSW/GIN indexes; later boots embed only changed rows.

- [ ] **Step 7: Commit**

```bash
git add backend/app/retrieval/factory.py backend/app/main.py backend/scripts/eval_retrieval.py backend/tests/test_retrieval_pipeline.py backend/eval/retrieval/reports/phase6-pg.json backend/eval/retrieval/reports/phase6-pg.md backend/eval/retrieval/reports/HISTORY.md
git commit -m "feat(retrieval): prod searches in Postgres (PgRetriever) after a successful boot sync; phase 6 eval on local pg

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```
