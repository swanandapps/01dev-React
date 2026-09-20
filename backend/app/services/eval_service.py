"""
Evaluation harness for the tutor — the prerequisite for GEPA.

Runs the tutor over a fixed eval set with a GIVEN SOUL/prompt, and scores each
answer with an LLM-as-judge on groundedness + quality. This is the signal GEPA
needs to know whether an evolved SOUL is actually better than the current one.

Grounding is deterministic (a relevance threshold), same as the live tutor:
- out-of-corpus questions that correctly DECLINE score full marks;
- in-corpus questions are answered and then graded by the judge.
"""
import json
import os
from pathlib import Path

from pydantic import BaseModel, ValidationError, field_validator

from app.services.embeddings import embedding_service
from app.services.vector_store import vector_store
from app.services.eval_llm import eval_client_and_model


class JudgeScore(BaseModel):
    """Schema-validated judge output."""
    score: float = 3.0
    feedback: str = ""

    @field_validator("score")
    @classmethod
    def _clamp(cls, v) -> float:
        return max(1.0, min(5.0, float(v)))

    @field_validator("feedback")
    @classmethod
    def _trim(cls, v) -> str:
        return str(v or "")[:160]

_client, _MODEL = eval_client_and_model()
_THRESHOLD = float(os.getenv("HERMES_GROUNDING_THRESHOLD", "0.45"))
_EVAL_SET = Path(__file__).resolve().parents[1] / "eval" / "eval_set.json"

_GROUNDING_INSTRUCTION = (
    "\n\nAnswer the student's question using ONLY the course material below, and cite the "
    "lecture. If the material does not cover it, say so plainly.\n\n=== COURSE MATERIAL ===\n"
)


def load_eval_set() -> list[dict]:
    return json.loads(_EVAL_SET.read_text())


async def _run_tutor(soul: str, question: str) -> dict:
    """Run the tutor exactly like the live route: retrieve, threshold, generate."""
    emb = await embedding_service.embed(question)
    results = vector_store.search(emb, top_k=4, query_text=question)
    best = results[0].score if results else 0.0

    if best < _THRESHOLD:
        return {"scope": "declined", "answer": "(declined — not covered by the course)",
                "material": "", "best": round(best, 3)}

    material = "\n\n".join(
        f"[{r.chunk.course_title} — {r.chunk.lecture_title}]\n{r.chunk.text}" for r in results
    )
    resp = await _client.chat.completions.create(
        model=_MODEL, temperature=0.3, max_tokens=400,
        messages=[
            {"role": "system", "content": soul + _GROUNDING_INSTRUCTION + material},
            {"role": "user", "content": question},
        ],
    )
    return {"scope": "grounded", "answer": (resp.choices[0].message.content or "").strip(),
            "material": material, "best": round(best, 3)}


async def _judge(question: str, answer: str, material: str) -> dict:
    """LLM-as-judge: score 1-5 on grounded + accurate + clear + cites the lecture."""
    sys = (
        "You are a strict grader for a course tutor. Score the ANSWER from 1 to 5 on whether it "
        "is grounded in the MATERIAL, accurate, clear, and cites the lecture. Return ONLY JSON: "
        '{"score": <1-5>, "feedback": "<one short sentence on what to improve>"}'
    )
    user = f"QUESTION: {question}\n\nMATERIAL:\n{material[:2000]}\n\nANSWER:\n{answer[:1500]}"
    resp = await _client.chat.completions.create(
        model=_MODEL, temperature=0.1, max_tokens=200,
        response_format={"type": "json_object"},
        messages=[{"role": "system", "content": sys}, {"role": "user", "content": user}],
    )
    raw = (resp.choices[0].message.content or "{}").strip()
    try:
        s = JudgeScore.model_validate(json.loads(raw))
        return {"score": s.score, "feedback": s.feedback or "(no feedback)"}
    except (json.JSONDecodeError, ValidationError, TypeError):
        return {"score": 3.0, "feedback": "(judge output unparseable)"}


async def run_eval(soul: str) -> dict:
    """Score a candidate SOUL across the eval set. Returns {avg, cases:[...]}."""
    cases = []
    for item in load_eval_set():
        q, expect = item["question"], item.get("expect", "ground")
        r = await _run_tutor(soul, q)

        if expect == "decline":
            score = 5.0 if r["scope"] == "declined" else 1.0
            fb = "correctly declined (out of scope)" if score == 5 else "should have declined"
        elif r["scope"] == "declined":
            score, fb = 1.0, "wrongly declined an in-course question"
        else:
            j = await _judge(q, r["answer"], r["material"])
            score, fb = j["score"], j["feedback"]

        cases.append({
            "question": q, "expect": expect, "scope": r["scope"],
            "score": score, "feedback": fb, "answer_preview": r["answer"][:160],
        })

    avg = round(sum(c["score"] for c in cases) / len(cases), 2) if cases else 0.0
    return {"avg": avg, "cases": cases}


async def collect_rag_outputs(soul: str) -> list[dict]:
    """Run the tutor over the GROUNDED eval questions and return the raw RAG triples
    {question, answer, contexts[]} — the exact shape RAGAS scores (faithfulness /
    answer-relevancy / context-precision)."""
    out = []
    for item in load_eval_set():
        if item.get("expect") != "ground":
            continue
        q = item["question"]
        emb = await embedding_service.embed(q)
        results = vector_store.search(emb, top_k=4, query_text=q)
        if not results or results[0].score < _THRESHOLD:
            continue
        contexts = [r.chunk.text for r in results]
        material = "\n\n".join(
            f"[{r.chunk.course_title} — {r.chunk.lecture_title}]\n{r.chunk.text}" for r in results
        )
        resp = await _client.chat.completions.create(
            model=_MODEL, temperature=0.3, max_tokens=400,
            messages=[
                {"role": "system", "content": soul + _GROUNDING_INSTRUCTION + material},
                {"role": "user", "content": q},
            ],
        )
        out.append({
            "question": q,
            "answer": (resp.choices[0].message.content or "").strip(),
            "contexts": contexts,
        })
    return out
