"""Sovereign structured generators for the QuizMe LangGraph pipeline.

Faithful re-implementation of what the Mastra/Memorang V2 agents produced —
objectives, per-objective quizzes, a Socratic tutor nudge, and a final summary —
but every call hits the LOCAL model (Ollama, OpenAI-compatible). Swap base_url
to a vLLM GPU node for production; the interface is identical.

Sync client on purpose: langgraph 1.2.x propagates the interrupt()/HITL config
context only on the synchronous graph path, so nodes (and thus these calls) are
sync. The FastAPI layer runs the graph in a threadpool, so blocking never stalls
the event loop.
"""
import json
import os
import uuid
from pathlib import Path

from dotenv import load_dotenv

# QuizMe runs as its own process and didn't load the backend env before — so it
# never saw the OPENAI/LANGFUSE keys. Load them so it uses OpenAI and traces to Langfuse.
load_dotenv(Path(__file__).resolve().parents[1] / ".env")  # backend/.env

from pydantic import ValidationError

from .schemas import Objective, PerObjective, Question, Summary


def _make_client():
    """OpenAI in production; local model in dev (LESSON_PROVIDER=ollama).
    Uses the Langfuse-instrumented OpenAI drop-in when LANGFUSE keys are set, so
    every QuizMe model call is traced to Langfuse."""
    if os.getenv("LANGFUSE_PUBLIC_KEY") and os.getenv("LANGFUSE_SECRET_KEY"):
        from langfuse.openai import OpenAI  # drop-in → traces to Langfuse
    else:
        from openai import OpenAI

    use_openai = bool(os.getenv("OPENAI_API_KEY")) and os.getenv("LESSON_PROVIDER", "openai") != "ollama"
    if use_openai:
        client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"), timeout=60.0, max_retries=3)
        model = os.getenv("LESSON_MODEL", "gpt-4.1-mini")
    else:
        client = OpenAI(
            base_url=os.getenv("OLLAMA_URL", "http://localhost:11434/v1"),
            api_key=os.getenv("OLLAMA_KEY", "ollama"),
        )
        model = os.getenv("LESSON_MODEL", "qwen2.5:3b")
    return client, model


# Built on first use, not at import: importing a service module must not
# require credentials or do work. app/main.py now imports this transitively.
_CLIENT_CACHE: tuple | None = None


def _get_client() -> tuple:
    """(client, model), constructed once on first call and cached."""
    global _CLIENT_CACHE
    if _CLIENT_CACHE is None:
        _CLIENT_CACHE = _make_client()
    return _CLIENT_CACHE


DIFFICULTIES = {"beginner", "intermediate", "advanced"}


def _chat_json(system: str, user: str, max_tokens: int = 900) -> dict:
    """One JSON-mode call to the local model, with a single defensive retry."""
    for attempt in range(2):
        client, model = _get_client()
        resp = client.chat.completions.create(
            model=model,
            temperature=0.4 if attempt == 0 else 0.1,
            max_tokens=max_tokens,
            response_format={"type": "json_object"},
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
        )
        raw = (resp.choices[0].message.content or "").strip()
        try:
            return json.loads(raw)
        except json.JSONDecodeError:
            if attempt == 1:
                # Last resort: pull the outermost {...} and try once more.
                s, e = raw.find("{"), raw.rfind("}")
                if s != -1 and e > s:
                    try:
                        return json.loads(raw[s : e + 1])
                    except json.JSONDecodeError:
                        pass
                return {}
    return {}


# ── Objectives (the planner) ────────────────────────────────────────────────
def gen_objectives(document: str, title: str | None) -> list[dict]:
    """Draft 3-4 learning objectives from the material. Mirrors the Mastra planner."""
    sys = (
        "You are a study planner. From the material, propose 3-4 focused learning "
        "objectives ordered from foundational to advanced. Return ONLY JSON: "
        '{"objectives":[{"title":"...","difficulty":"beginner|intermediate|advanced",'
        '"focus":"one line on what it covers"}]}'
    )
    user = f"TITLE: {title or '(none)'}\n\nMATERIAL:\n{document[:4000]}"
    data = _chat_json(sys, user)
    raw = data.get("objectives") if isinstance(data, dict) else None
    out: list[dict] = []
    for o in raw or []:
        try:  # schema-validated: coerces types, drops invalid objectives
            out.append(Objective.model_validate(o).model_dump())
        except ValidationError:
            continue
    if not out:  # never hand the UI an empty plan
        out = [Objective(title=(title or "Key concepts").strip(),
                         focus="Core ideas from the material").model_dump()]
    return out[:6]


# ── Quiz for one objective (a specialized generator) ────────────────────────
def gen_quiz(document: str, objective: dict, n: int) -> list[dict]:
    """n multiple-choice questions for one objective, with explanation + hint."""
    n = max(1, min(10, int(n or 3)))
    sys = (
        "You are a quiz author. Write multiple-choice questions testing the given "
        "objective, grounded in the material. Each question has exactly 4 answer options "
        "written out IN FULL as real answers (NEVER single letters like 'a'/'b'/'c'/'d'), "
        "with exactly one correct. 'correctIndex' is the 0-based position of the correct "
        'option in the array. Return ONLY JSON: {"questions":[{"question":"<full question>",'
        '"options":["<full answer text>","<full answer text>","<full answer text>",'
        '"<full answer text>"],"correctIndex":<0-3>,"explanation":"<why that option is '
        'correct>","hint":"<nudge that does NOT reveal the answer>"}]}'
    )
    user = (
        f"OBJECTIVE: {objective.get('title')} ({objective.get('difficulty')})\n"
        f"FOCUS: {objective.get('focus')}\n"
        f"NUMBER OF QUESTIONS: {n}\n\nMATERIAL:\n{document[:4000]}"
    )
    data = _chat_json(sys, user, max_tokens=1200)
    raw = data.get("questions") if isinstance(data, dict) else None
    out: list[dict] = []
    for q in raw or []:
        try:  # schema-validated: enforces 2-4 options, clamps correctIndex, drops bad ones
            vq = Question.model_validate(q).model_dump()
        except ValidationError:
            continue
        if all(o.strip().lower() in ("a", "b", "c", "d") for o in vq["options"]):
            continue  # model echoed placeholder letters, not real answers
        out.append(vq)
    if not out:
        out = [Question(
            question=f"Which best describes: {objective.get('title')}?",
            options=["See the material", "Unrelated", "None", "All"],
            correctIndex=0, explanation="Refer to the material for this objective.",
            hint="Focus on the objective's key idea.").model_dump()]
    return out[:n]


# ── Final summary ───────────────────────────────────────────────────────────
def gen_summary(document: str, objectives: list[dict], results: list[dict]) -> dict:
    scores = "; ".join(f"{r['objectiveTitle']}: {r['score']}/{r['total']}" for r in results)
    sys = (
        "You are a study coach. Given the objectives and the learner's scores, write an "
        "encouraging summary. Return ONLY JSON: "
        '{"overall":"2-3 sentences","perObjective":[{"title":"...","comment":"one line"}],'
        '"studyTips":["tip","tip","tip"]}'
    )
    user = f"SCORES: {scores}\n\nOBJECTIVES: {json.dumps([o['title'] for o in objectives])}"
    data = _chat_json(sys, user, max_tokens=700)
    try:  # schema-validated summary
        summary = Summary.model_validate(data if isinstance(data, dict) else {})
    except ValidationError:
        summary = Summary()
    per = summary.perObjective or [
        PerObjective(title=r["objectiveTitle"], comment=f"Scored {r['score']}/{r['total']}.")
        for r in results
    ]
    tips = summary.studyTips or [
        "Revisit any objective you scored below 70%.",
        "Re-explain each concept in your own words.",
        "Space your review over a few days.",
    ]
    return {
        "overall": summary.overall.strip()
        or "Nice work getting through the session — review the weaker objectives and try again.",
        "perObjective": [p.model_dump() for p in per],
        "studyTips": [str(t) for t in tips][:5],
    }


# ── Socratic tutor (a hint, not the answer) ─────────────────────────────────
def tutor_answer(document: str, objective: dict | None, question: str) -> str:
    sys = (
        "You are a Socratic tutor. Give a helpful nudge toward the answer WITHOUT stating "
        "it outright — ask a guiding question or point to the concept. 2-3 sentences, plain prose."
    )
    obj = objective.get("title") if objective else "the current topic"
    client, model = _get_client()
    resp = client.chat.completions.create(
        model=model,
        temperature=0.5,
        max_tokens=250,
        messages=[
            {"role": "system", "content": sys},
            {"role": "user", "content": f"OBJECTIVE: {obj}\nMATERIAL:\n{document[:2500]}\n\n"
                                        f"STUDENT ASKS: {question}"},
        ],
    )
    return (resp.choices[0].message.content or "").strip()


# ── One-shot document artifacts (notes / summary / quiz / flashcards) ─────────
# Backs the "converts documents into structured notes, summaries, quizzes and
# flashcards" capability — each artifact is produced by a specialized generator.
ARTIFACT_TYPES = ["notes", "summary", "quiz", "flashcards"]

_ARTIFACT_SYS = {
    "notes": (
        "You are a revision-notes generator. Produce 6-10 concise bullet-point notes "
        "covering the key ideas in the material. Markdown bullets only, no preamble."
    ),
    "summary": (
        "You are a study summarizer. Write a clear 4-5 sentence summary of the material. "
        "Plain prose, no preamble, no headings."
    ),
    "quiz": (
        "You are a quiz author. Write 3 multiple-choice questions testing the material. "
        "Each has 4 answer options written out in full (never single letters), one correct. "
        "Format each as:\nQ1. <question>\n  a) ...\n  b) ...\n  c) ...\n  d) ...\n  Answer: <letter>\n"
        "No preamble."
    ),
    "flashcards": (
        "You are a flashcard generator. Produce exactly 5 flashcards from the material, one "
        "per line, each as 'Front: <term/question> | Back: <answer>'. No preamble."
    ),
}


def gen_artifact(artifact_type: str, document: str) -> str:
    """Generate one document artifact (notes/summary/quiz/flashcards) as text."""
    system = _ARTIFACT_SYS.get(artifact_type, _ARTIFACT_SYS["summary"])
    client, model = _get_client()
    resp = client.chat.completions.create(
        model=model,
        temperature=0.3,
        max_tokens=600,
        messages=[
            {"role": "system", "content": system},
            {"role": "user", "content": f"MATERIAL:\n{document[:4000]}"},
        ],
    )
    return (resp.choices[0].message.content or "").strip()
