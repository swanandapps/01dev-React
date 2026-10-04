"""
RAG ACCURACY harness — measures accuracy against a labeled golden set.

Unlike faithfulness (answer ↔ retrieved context), this measures accuracy against
GROUND TRUTH:

  RETRIEVAL accuracy (deterministic, no LLM):
    recall@k  — is a gold chunk in the top-k retrieved?
    MRR       — how highly is the first gold chunk ranked?

  ANSWER accuracy (OpenAI LLM-judge vs the gold answer):
    fraction of answers judged to convey the gold answer's key point.

Run from backend/:   python3 app/eval/accuracy.py        (needs .env with OPENAI_API_KEY)
"""
import asyncio
import json
import os
import sys
from pathlib import Path

from dotenv import load_dotenv

_BACKEND = Path(__file__).resolve().parents[2]  # .../backend
sys.path.insert(0, str(_BACKEND))
load_dotenv(_BACKEND / ".env")

from app.services.embeddings import embedding_service  # noqa: E402
from app.services.vector_store import vector_store  # noqa: E402
from app.services.eval_llm import eval_client_and_model  # noqa: E402
from app.services.grounding import answer_grounded  # noqa: E402

_GOLDEN = Path(__file__).resolve().parent / "golden_set.json"
_client, _MODEL = eval_client_and_model()


def load_golden() -> list[dict]:
    return json.loads(_GOLDEN.read_text())


# ── Retrieval accuracy (deterministic) ───────────────────────────────────────
async def retrieval_metrics(golden: list[dict], k: int = 5) -> dict:
    hits = {1: 0, 3: 0, 5: 0}
    rr_sum = 0.0
    misses = []
    for item in golden:
        emb = await embedding_service.embed(item["question"])
        results = vector_store.search(emb, top_k=k, query_text=item["question"])
        ranked = [r.chunk.chunk_id for r in results]
        gold = set(item["gold_chunk_ids"])
        for n in (1, 3, 5):
            if gold & set(ranked[:n]):
                hits[n] += 1
        rank = next((i + 1 for i, c in enumerate(ranked) if c in gold), None)
        rr_sum += (1.0 / rank) if rank else 0.0
        if rank is None:
            misses.append(item["question"])
    n = len(golden)
    return {
        "recall@1": round(hits[1] / n, 3),
        "recall@3": round(hits[3] / n, 3),
        "recall@5": round(hits[5] / n, 3),
        "MRR": round(rr_sum / n, 3),
        "misses": misses,
    }


# ── Answer accuracy (LLM-judge vs gold) ──────────────────────────────────────
async def _answer(question: str) -> str:
    # Reuse the canonical grounded-answer path so eval measures the real product.
    res = await answer_grounded(question, top_k=4)
    return res["answer"]


async def _judge(question: str, gold: str, answer: str) -> tuple[bool, str]:
    resp = await _client.chat.completions.create(
        model=_MODEL, temperature=0.0, max_tokens=150,
        response_format={"type": "json_object"},
        messages=[
            {"role": "system", "content": "Grade the STUDENT answer against the GOLD answer. "
             "Mark it CORRECT if it contains the gold answer's key point (any wording). "
             "Extra correct detail is FINE and must NOT lower the grade. "
             "Mark it INCORRECT only if it MISSES the gold key point or CONTRADICTS it. "
             'Return ONLY JSON: {"correct": true|false, "reason": "short"}'},
            {"role": "user", "content": f"QUESTION: {question}\nGOLD: {gold}\nSTUDENT: {answer}"},
        ],
    )
    try:
        d = json.loads(resp.choices[0].message.content or "{}")
        return bool(d.get("correct")), str(d.get("reason", ""))[:90]
    except (json.JSONDecodeError, TypeError):
        return False, "(judge parse failed)"


async def answer_metrics(golden: list[dict]) -> dict:
    correct, wrong = 0, []
    for item in golden:
        ans = await _answer(item["question"])
        ok, reason = await _judge(item["question"], item["gold_answer"], ans)
        correct += ok
        if not ok:
            wrong.append({"q": item["question"], "reason": reason})
    return {"answer_accuracy": round(correct / len(golden), 3), "wrong": wrong}


async def main():
    await vector_store.initialize()
    golden = load_golden()
    print(f"Golden set: {len(golden)} labeled questions\n")

    r = await retrieval_metrics(golden)
    print("=== RETRIEVAL ACCURACY (deterministic, vs gold chunk) ===")
    print(f"  recall@1={r['recall@1']}  recall@3={r['recall@3']}  recall@5={r['recall@5']}  MRR={r['MRR']}")
    if r["misses"]:
        print("  gold chunk NOT in top-5 for:", r["misses"])
    print()

    a = await answer_metrics(golden)
    print("=== ANSWER ACCURACY (LLM judge vs gold answer) ===")
    print(f"  answer_accuracy={a['answer_accuracy']}")
    for w in a["wrong"]:
        print(f"   ✗ {w['q'][:50]} — {w['reason']}")

    from app.eval import results_store
    results_store.record("accuracy", {
        "recall@1": r["recall@1"], "recall@3": r["recall@3"], "recall@5": r["recall@5"],
        "MRR": r["MRR"], "answer_accuracy": a["answer_accuracy"],
    }, {"golden_n": len(golden), "model": _MODEL})
    print("\n(recorded → data/eval_results/history.jsonl)")


if __name__ == "__main__":
    asyncio.run(main())
