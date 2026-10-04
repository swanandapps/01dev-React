"""
RAGAS evaluation of the01.dev's RAG tutor, scored by an OpenAI judge model.

Pulls the tutor's {question, answer, contexts} from the backend, adds the gold
reference answers from the eval set, and scores them on the full RAGAS quadrant:
  - faithfulness       (are the answer's claims supported by the retrieved context?)
  - context precision  (were the retrieved chunks actually useful?)
  - answer relevancy   (does the answer actually address the question?)
  - context recall     (did retrieval surface everything the gold answer needs?)

These feed the same grounding signal the GEPA loop optimises.

Run (isolated venv):  .ragas-venv/bin/python ragas_eval.py
"""
import json
import os
import sys
import urllib.request
from pathlib import Path

# make the (stdlib-only) results store importable from this isolated venv
sys.path.insert(0, str(Path(__file__).resolve().parent / "app" / "eval"))

from ragas import EvaluationDataset, evaluate
from ragas.metrics import (
    Faithfulness,
    LLMContextPrecisionWithoutReference,
    ResponseRelevancy,
    LLMContextRecall,
)
from ragas.llms import LangchainLLMWrapper
from ragas.embeddings import LangchainEmbeddingsWrapper
from ragas.run_config import RunConfig
from langchain_openai import ChatOpenAI, OpenAIEmbeddings

BACKEND = os.getenv("BACKEND_URL", "http://localhost:8080")
# Judge with OpenAI (matches the shipped product).
MODEL = os.getenv("EVAL_MODEL", "gpt-4.1-mini")

# 1. the tutor's RAG outputs (question, answer, retrieved contexts)
raw = json.load(urllib.request.urlopen(f"{BACKEND}/api/hermes/eval/rag-outputs", timeout=180))

# gold reference answers (for context-recall), keyed by question, from the eval set
_EVAL_SET = Path(__file__).resolve().parent / "app" / "eval" / "eval_set.json"
_REFERENCE = {it["question"]: it.get("reference", "") for it in json.loads(_EVAL_SET.read_text())}

samples = [
    {
        "user_input": r["question"],
        "response": r["answer"],
        "retrieved_contexts": r["contexts"],
        "reference": _REFERENCE.get(r["question"], ""),
    }
    for r in raw
]
dataset = EvaluationDataset.from_list(samples)
print(f"Scoring {len(samples)} tutor answers with RAGAS — judge model = {MODEL}\n")

# 2. Judge model + embeddings — OpenAI (matches production).
#    answer-relevancy needs an embeddings model; context-recall needs the gold reference above.
judge = LangchainLLMWrapper(ChatOpenAI(model=MODEL, temperature=0))
embeddings = LangchainEmbeddingsWrapper(
    OpenAIEmbeddings(model=os.getenv("EVAL_EMBED_MODEL", "text-embedding-3-small")))

# 3. score
result = evaluate(
    dataset=dataset,
    metrics=[
        Faithfulness(),
        LLMContextPrecisionWithoutReference(),
        ResponseRelevancy(),   # answer relevancy — needs the embeddings model
        LLMContextRecall(),    # needs the gold reference answer
    ],
    llm=judge,
    embeddings=embeddings,
    # one judge call at a time, with a generous per-call timeout.
    run_config=RunConfig(timeout=600, max_workers=1),
)

print("=== RAGAS scores (0-1, higher is better) ===")
print(result)

# df column → friendly label (drives both the per-question view and the recorded trend)
_COLS = {
    "faithfulness": "faithfulness",
    "llm_context_precision_without_reference": "context_precision",
    "answer_relevancy": "answer_relevancy",
    "context_recall": "context_recall",
}
try:
    df = result.to_pandas()
    present = [(c, label) for c, label in _COLS.items() if c in df]
    print("\nper-question:")
    for _, row in df.iterrows():
        scores = "  ".join(f"{label}={row[c]:.2f}" for c, label in present if row.get(c) == row.get(c))
        print(f"  {str(row.get('user_input',''))[:46]:46} {scores}")
    metrics = {label: round(float(df[c].dropna().mean()), 3) for c, label in present if df[c].notna().any()}
    import results_store
    results_store.record("ragas", metrics, {"model": MODEL, "n": len(samples)})
    print("\n(recorded → data/eval_results/history.jsonl)")
except Exception as e:  # noqa: BLE001
    print("(could not record ragas result:", e, ")")
