"""Structured generators for the Lab LangGraph pipeline.

Generates objectives, per-objective quizzes, a Socratic tutor nudge, and a
final summary — each as one JSON-mode OpenAI chat-completion call.

Sync client on purpose: langgraph 1.2.x propagates the interrupt()/HITL config
context only on the synchronous graph path, so nodes (and thus these calls) are
sync. The FastAPI layer runs the graph in a threadpool, so blocking never stalls
the event loop.
"""

# Env: app.main loads backend/.env at import, before any of this package's
# code runs, so this module does no .env loading of its own.

import hashlib
import json
import os
import random
import uuid

from pydantic import ValidationError

from .schemas import Objective, PerObjective, Question, Summary


def _make_client():
    """OpenAI client + model (LESSON_MODEL, default gpt-4.1-mini).
    Uses the Langfuse-instrumented OpenAI drop-in when LANGFUSE keys are set, so
    every Lab model call is traced to Langfuse."""
    if os.getenv("LANGFUSE_PUBLIC_KEY") and os.getenv("LANGFUSE_SECRET_KEY"):
        from langfuse.openai import OpenAI  # drop-in → traces to Langfuse
    else:
        from openai import OpenAI

    client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"), timeout=60.0, max_retries=3)
    model = os.getenv("LESSON_MODEL", "gpt-4.1-mini")
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
    """One JSON-mode call to the model, with a single defensive retry."""
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
    """Draft 3-4 learning objectives from the material (the planner step)."""
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


def _shuffle_options(q: dict) -> dict:
    """The model tends to put the right answer first. Shuffle options
    deterministically (seeded by question text) and keep correctIndex pointing
    at the same option text."""
    opts = list(q["options"])
    correct = opts[q["correctIndex"]]
    seed = int(hashlib.sha256(q["question"].encode()).hexdigest()[:16], 16)
    random.Random(seed).shuffle(opts)
    return {**q, "options": opts, "correctIndex": opts.index(correct)}


# ── Quiz for one objective (a specialized generator) ────────────────────────
GIVEAWAY_RATIO = 1.25  # correct option longer than every other by this factor = guessable by length

_QUIZ_SYSTEM = (
    "You are a quiz author. Write multiple-choice questions testing the given "
    "objective, grounded in the material. Each question has exactly 4 answer options "
    "written out IN FULL as real answers (NEVER single letters like 'a'/'b'/'c'/'d'), "
    "with exactly one correct. Options are shuffled afterwards: never refer to an option by "
    "letter or position in the explanation. 'correctIndex' is the 0-based position of the correct "
    "option in the array.\n"
    "The options must not give the answer away:\n"
    "- Every option is 5 to 12 words. Write the correct option first in your head, count its words, then "
    "make EACH wrong option within 2 words of that count, in the same grammatical form and with the same "
    "level of detail. The correct option is never the longest or the most specific one.\n"
    "- Wrong options are believable mistakes a student who half-watched the material would make "
    "(a related idea, a reversed cause, the right term in the wrong place), each stated as confidently "
    "as the right one. No joke options and no obviously absurd claims.\n"
    "- Do not put absolute words (always, never, guarantees, automatically, completely) only in the "
    "wrong options.\n"
    'Return ONLY JSON: {"questions":[{"question":"<full question>",'
    '"options":["<full answer text>","<full answer text>","<full answer text>",'
    '"<full answer text>"],"correctIndex":<0-3>,"explanation":"<why that option is '
    'correct>","hint":"<nudge that does NOT reveal the answer>",'
    '"concept":"<2-4 word name of the single concept this question tests>"}]}'
)


def _is_giveaway(q: dict) -> bool:
    """The correct option is clearly longer than every wrong one (students learn to pick the longest)."""
    opts = q["options"]
    others = [len(o) for i, o in enumerate(opts) if i != q["correctIndex"]]
    return bool(others) and len(opts[q["correctIndex"]]) > GIVEAWAY_RATIO * max(others)


def _quiz_batch(document: str, objective: dict, n: int, note: str = "") -> list[dict]:
    user = (
        f"OBJECTIVE: {objective.get('title')} ({objective.get('difficulty')})\n"
        f"FOCUS: {objective.get('focus')}\n"
        f"NUMBER OF QUESTIONS: {n}\n{note}\nMATERIAL:\n{document[:4000]}"
    )
    data = _chat_json(_QUIZ_SYSTEM, user, max_tokens=1200)
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
    return out


def gen_quiz(document: str, objective: dict, n: int) -> list[dict]:
    """n multiple-choice questions for one objective, with explanation + hint. A batch where a correct option
    is clearly the longest is regenerated once and the batch with fewer such questions is kept whole (mixing
    batches would repeat topics: each one covers the material on its own)."""
    n = max(1, min(10, int(n or 3)))

    def worse(batch: list[dict]) -> tuple[int, int]:
        return (max(0, n - len(batch)), sum(_is_giveaway(q) for q in batch[:n]))

    pool = _quiz_batch(document, objective, n)
    if worse(pool) != (0, 0):
        second = _quiz_batch(document, objective, n, note=(
            "IMPORTANT: in your options the correct answer must be the same length as the wrong ones — "
            "make the wrong options as long and as specific as the right one.\n"))
        if worse(second) < worse(pool):
            pool = second
    out = pool[:n]
    if not out:
        out = [Question(
            question=f"Which best describes: {objective.get('title')}?",
            options=["See the material", "Unrelated", "None", "All"],
            correctIndex=0, explanation="Refer to the material for this objective.",
            hint="Focus on the objective's key idea.").model_dump()]
    return [_shuffle_options(q) for q in out]


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
