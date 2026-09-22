"""
The Lab's artifact generators — the outputs a student can ask for besides the
interactive quiz.

`quiz` is deliberately NOT here: it is the graph's interactive tail (objectives
→ approve → per-objective quiz with hints and a Socratic tutor), not a one-shot
document. It lives in llm.py/graph.py.

Each generator returns STRUCTURED data rather than a blob of markdown, so the
UI can render flashcards as actual cards and a study plan as actual steps.
"""
import json

from app.services.lab.llm import _get_client

OUTPUT_TYPES = ["quiz", "flashcards", "summary", "study_plan"]
# What the fan-out generates. `quiz` is the tail, not an artifact.
ARTIFACT_TYPES = ["flashcards", "summary", "study_plan"]


def _chat(system: str, document: str, max_tokens: int = 700) -> str:
    client, model = _get_client()
    resp = client.chat.completions.create(
        model=model,
        temperature=0.3,
        max_tokens=max_tokens,
        messages=[
            {"role": "system", "content": system},
            {"role": "user", "content": f"MATERIAL:\n{document[:4000]}"},
        ],
    )
    return (resp.choices[0].message.content or "").strip()


def _chat_json(system: str, document: str, max_tokens: int = 700) -> dict:
    raw = _chat(system, document, max_tokens)
    try:
        return json.loads(raw)
    except (json.JSONDecodeError, TypeError):
        # Try to salvage a JSON object embedded in prose.
        start, end = raw.find("{"), raw.rfind("}")
        if start != -1 and end > start:
            try:
                return json.loads(raw[start:end + 1])
            except json.JSONDecodeError:
                return {}
        return {}


def gen_flashcards(document: str) -> list[dict]:
    """5-10 front/back pairs. Malformed cards are dropped, not guessed at."""
    data = _chat_json(
        "You are a flashcard generator. Produce 5-10 flashcards from the material, "
        "each a question or term on the front and its answer on the back. Keep backs "
        'to one or two sentences. Return ONLY JSON: {"cards":[{"front":"...","back":"..."}]}',
        document,
    )
    out = []
    for c in data.get("cards", []) if isinstance(data, dict) else []:
        front = str(c.get("front", "")).strip()
        back = str(c.get("back", "")).strip()
        if front and back:
            out.append({"front": front, "back": back})
    return out[:10]


def gen_summary(document: str) -> str:
    """A 4-5 sentence "quick revision" summary as plain prose."""
    return _chat(
        "You are a study summarizer. Write a clear 4-5 sentence summary of the "
        "material that someone could read as quick revision. Plain prose, no "
        "headings, no preamble, no bullet points.",
        document,
        max_tokens=400,
    )


def gen_study_plan(document: str) -> list[dict]:
    """An ordered roadmap. Separate from the quiz's objectives by design — this
    is a standalone readable plan, not a rendering of what you'll be tested on."""
    data = _chat_json(
        "You are a study planner. Break the material into 4-6 ordered steps a "
        "student should work through, each with a short actionable detail. Order "
        'matters: earlier steps are prerequisites. Return ONLY JSON: '
        '{"steps":[{"title":"...","detail":"..."}]}',
        document,
    )
    out = []
    for i, s in enumerate(data.get("steps", []) if isinstance(data, dict) else [], start=1):
        title = str(s.get("title", "")).strip()
        if not title:
            continue
        out.append({"step": i, "title": title, "detail": str(s.get("detail", "")).strip()})
    return out[:6]


def generate(artifact_type: str, document: str):
    if artifact_type == "flashcards":
        return gen_flashcards(document)
    if artifact_type == "summary":
        return gen_summary(document)
    if artifact_type == "study_plan":
        return gen_study_plan(document)
    raise ValueError(f"unknown artifact type: {artifact_type!r}")
