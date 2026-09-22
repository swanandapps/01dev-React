"""
Single-source content primitives: ad-hoc quiz + notes from arbitrary text.

Business logic lives here ONCE. The MCP tools (`generate_quiz`, `generate_notes`)
are thin wrappers over these; any backend caller can reuse them too. They use the
shared OpenAI client (`app.services.llm`) — same model the product ships on.

Note on scope (honest): `question_service` (course-wide MCQ *bank* with dedupe /
difficulty mix) and `app.services.lab` (per-objective quiz, now merged into this
service — no separate process or venv) are distinct capabilities and are NOT
collapsed into these primitives — see the build notes. These primitives are the
single source for *ad-hoc text → quiz/notes*.
"""
from typing import List

from app.services.llm import llm, GEN_MODEL

_QUIZ_SYS = (
    "You are a quiz author. From the material, write exactly {n} multiple-choice questions, "
    "grounded ONLY in the material. Each question has exactly 4 options written out IN FULL "
    "(never single letters like 'a'/'b'), with exactly one correct. Return ONLY JSON: "
    '{{"questions":[{{"question":"<question>","options":["<full>","<full>","<full>","<full>"],'
    '"answer":"<the correct option text, copied verbatim from options>","concept":"<2-4 word tag>"}}]}}'
)

_NOTES_SYS = (
    "Produce 6-10 concise markdown bullet-point study notes from the material. "
    "Bullets only, no preamble."
)


async def generate_quiz(text: str, num_questions: int = 3) -> List[dict]:
    """text → schema-validated MCQs: {question, options[4], answer, concept}."""
    n = max(1, min(10, int(num_questions or 3)))
    if not llm.available:
        return []
    data = await llm.generate_json(_QUIZ_SYS.format(n=n), f"MATERIAL:\n{text[:4000]}", max_tokens=1300)
    raw = data.get("questions", []) if isinstance(data, dict) else []

    out: List[dict] = []
    for q in raw:
        opts = [str(o).strip() for o in q.get("options", []) if str(o).strip()]
        if len(opts) != 4:
            continue
        answer = str(q.get("answer", "")).strip()
        if answer not in opts:
            # tolerate an index-style answer ("2" or 2) → map to option text
            try:
                idx = int(answer)
                answer = opts[idx] if 0 <= idx < 4 else ""
            except (ValueError, TypeError):
                answer = ""
        if not answer:
            continue  # drop malformed items rather than emit a broken question
        out.append({
            "question": str(q.get("question", "")).strip(),
            "options": opts,
            "answer": answer,
            "concept": str(q.get("concept", "General")).strip() or "General",
        })
    return out[:n]


async def generate_notes(text: str) -> str:
    """text → 6-10 markdown bullet-point study notes."""
    if not llm.available:
        return "(notes unavailable: no LLM configured)"
    resp = await llm.client.chat.completions.create(
        model=GEN_MODEL,
        temperature=0.3,
        max_tokens=500,
        messages=[
            {"role": "system", "content": _NOTES_SYS},
            {"role": "user", "content": text[:4000]},
        ],
    )
    return (resp.choices[0].message.content or "").strip()
