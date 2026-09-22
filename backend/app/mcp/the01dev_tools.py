"""
MCP tool server exposing the01.dev capabilities to the Hermes agent.

BOUNDARY, NOT A SECOND HOME FOR LOGIC. Every tool here is a THIN WRAPPER that
imports and calls the backend's shared functions (`app.services.grounding`,
`app.services.content`, `app.services.chunker`) — no business logic is
re-implemented here or inside Hermes. One capability = one implementation.

Hermes launches this as a stdio MCP server (registered under `mcp_servers` in
~/.hermes/config.yaml).

Run standalone for a smoke test:  python -m app.mcp.the01dev_tools
"""

import os
import sys
from pathlib import Path

# Hermes launches this as its own process; make the `app` package importable
# and load the backend's .env so the OpenAI key + DATABASE_URL are available.
_BACKEND = Path(__file__).resolve().parents[2]  # .../backend
sys.path.insert(0, str(_BACKEND))

from dotenv import load_dotenv

load_dotenv(_BACKEND / ".env")

import contextlib

from fastmcp import FastMCP

# App modules print to stdout on import ("EmbeddingService: using OpenAI...").
# Hermes speaks JSON-RPC to this server over stdout, so any stray print corrupts
# the channel — redirect import-time output to stderr.
with contextlib.redirect_stdout(sys.stderr):
    from app.services.vector_store import vector_store
    from app.services.embeddings import embedding_service
    from app.services import grounding, content, memory_service, skill_graph_service
    from app.services import journey_service, knowledge_graph_service, enrollment_service
    from app.services.store import store

mcp = FastMCP("the01dev-tools")

_initialized = False


async def _ensure_index() -> None:
    """Load seed transcripts + embeddings once, on first retrieval tool call."""
    global _initialized
    if not _initialized:
        with contextlib.redirect_stdout(sys.stderr):
            await vector_store.initialize()
        _initialized = True




# ── Retrieval (unchanged) ─────────────────────────────────────────────────────
@mcp.tool()
async def search_course_content(query: str, student_id: str, top_k: int = 5) -> list[dict]:
    """Search the01.dev course transcripts for material relevant to a student's question.

    USE THIS FIRST for ANY question about a concept the course teaches (e.g. "what is
    the event loop?", "how does React.memo work?"). It is the default, correct tool for
    answering course questions — it grounds the answer in real lecture content. Do NOT
    use generate_notes / generate_quiz / process_pdf to answer a concept question.

    Returns excerpts with course, lecture, and the video timestamp (mm:ss + start_time
    in seconds) so answers can cite sources.

    Args:
        query: The student's question, or the concept to look up.
        student_id: This student's id — use the exact value you were given for
            this conversation, never a different one.
        top_k: How many transcript excerpts to return (default 5).
    """
    await _ensure_index()
    results = await grounding.retrieve(query, top_k=top_k)  # shared retrieval

    # Persisted so the FastAPI chat handler — which never sees this tool call,
    # since Hermes resolves tool use internally — can read the real citations
    # back out after the stream and hand the frontend clickable source cards
    # instead of the empty sources array it used to send unconditionally.
    if results:
        cards = [c.model_dump() for c in grounding.build_sources(results)]
        await store.set("chat_citations", student_id, {"cards": cards})

    excerpts: list[dict] = []
    for r in results:
        c = r.chunk
        m, s = divmod(c.start_time, 60)
        excerpts.append({
            "course": c.course_title,
            "lecture": c.lecture_title,
            "timestamp": f"{m:02d}:{s:02d}",
            "start_time": c.start_time,
            "text": c.text,
            "score": round(r.score, 3),
        })

    if not excerpts:
        return [{"note": "No matching course content found — the01.dev's course library "
                 "doesn't cover this. Still answer the question yourself from your own "
                 "general knowledge (accurately, no invented facts) — just make clear this "
                 "particular answer isn't backed by a the01.dev course citation."}]
    return excerpts


# ── Grounded answer (thin wrapper over grounding.answer_grounded) ─────────────
@mcp.tool()
async def answer_question(question: str) -> dict:
    """Answer a course question, grounded ONLY in the01.dev course material, with citations.

    A one-shot shortcut: retrieves and returns a FINISHED answer. Prefer
    search_course_content when you want to explain in your own teaching voice (the
    tutoring default); use this only when a quick canned grounded answer is enough.
    If nothing is relevant it says so rather than guessing.

    Args:
        question: The student's question.
    """
    await _ensure_index()
    res = await grounding.answer_grounded(question, top_k=5)
    return {
        "answer": res["answer"],
        "insufficient_context": res["insufficient_context"],
        "sources": [s.model_dump() for s in res["sources"]],
    }


# ── Quiz (thin wrapper over content.generate_quiz) ────────────────────────────
@mcp.tool()
async def generate_quiz(text: str, num_questions: int = 3) -> list[dict]:
    """Generate multiple-choice questions from text the STUDENT has provided.

    Use ONLY when the student supplies their own material and explicitly asks for a
    quiz. Do NOT use this to answer a course question — for that, use
    search_course_content. Each question has 4 full-text options and one correct
    answer, with a concept tag.

    Args:
        text: The source material to build questions from.
        num_questions: How many questions (1-10, default 3).
    """
    return await content.generate_quiz(text, num_questions)


# ── Notes (thin wrapper over content.generate_notes) ──────────────────────────
@mcp.tool()
async def generate_notes(text: str) -> str:
    """Generate 6-10 concise markdown bullet-point study notes from text the STUDENT
    has provided.

    Use ONLY when the student supplies their own material and asks for notes or a
    summary. Do NOT use this to answer a concept question (e.g. "what is the event
    loop?") — for answering course questions, use search_course_content instead.

    Args:
        text: The source material to summarize into notes.
    """
    return await content.generate_notes(text)


# ── Cross-session memory search (thin wrapper over memory_service.search_history) ─
@mcp.tool()
async def search_history(query: str, student_id: str, top_k: int = 3) -> list[dict]:
    """Search THIS student's OWN past tutoring exchanges for ones relevant to `query`.

    Use ONLY when the student refers to a PAST conversation ("like you taught me
    closures", "what did we cover last time?"). Do NOT use it to answer a new concept
    question — use search_course_content for that. "Selection across time": reaches
    back into older sessions and returns only the most relevant slice. Strictly scoped
    to `student_id`.

    Args:
        query: What to look for in the student's history (e.g. "did we cover promises?").
        student_id: The student whose history to search (scoping is enforced).
        top_k: How many past exchanges to return (default 3).
    """
    rows = await memory_service.search_history(student_id, query, top_k)
    return [
        {
            "id": r["turn_id"],
            "date": str(r.get("created_at", ""))[:10],
            "course": r.get("course_slug"),
            "snippet": (f"Q: {r.get('question','')}\nA: {r.get('answer','')}")[:300],
            "rank": r.get("rank"),
        }
        for r in rows
    ]


# ── Prerequisite-aware confidence (thin wrapper over skill_graph_service) ─────
@mcp.tool()
async def get_concept_confidence(concept: str, course_id: str, student_id: str) -> dict:
    """Check how confident this student is on a concept AND on everything that
    concept depends on, in one call — use this BEFORE teaching something that has
    prerequisites, so you can address a shaky prerequisite instead of teaching on
    top of a gap the student doesn't know they have.

    Returns the target concept's accuracy/attempts, a list of its prerequisites
    with the same shape, and `weakest_prerequisite` (the lowest-accuracy
    prerequisite that has actually been attempted — `null` if none have been).
    `accuracy: null` on any entry means the student has never been graded on it
    yet, not that they scored zero — do not treat null as a bad score.

    Each entry also carries `chat_confidence`/`chat_confidence_note` — your own
    prior conversational impression, logged via record_skill_observation, if
    you (or a past session) logged one for that concept. `null` means no
    observation has been logged yet, not "weak". `chat_confidence` and
    `accuracy` are different signals — a chat impression vs. a real graded
    score — do not conflate them or treat one as a substitute for the other.

    Args:
        concept: The concept to check (must match a concept tag used in this course).
        course_id: The course's id/slug — use the exact value you were given for
            this conversation.
        student_id: This student's id — use the exact value you were given for
            this conversation, never a different one.
    """
    return await skill_graph_service.get_prerequisite_view(student_id, course_id, concept)


# ── Course-agnostic strengths/weaknesses (thin wrapper over journey_service) ──
@mcp.tool()
async def get_learning_strengths(student_id: str) -> dict:
    """What this student is good/bad at OVERALL — use this for broad questions like
    "what am I good at?", "what am I weak on?", "where do I need work?" that don't
    name one specific concept or course. Do NOT use get_concept_confidence for these —
    that tool needs one concept AND a course_id already in hand; this one needs neither.

    Each weakness includes its prerequisites (from the course knowledge graph) with
    their own accuracy, so you can connect the dots for the student — e.g. "you're
    weak on X, and its prerequisite Y is shaky too, so start there" — the same
    reasoning get_concept_confidence gives for one concept, applied across all of them.

    Returns `strengths`/`weaknesses` (accuracy >= 0.8 counts as a strength) and
    `concepts_attempted`. An empty result means no graded activity yet — say so
    plainly, don't guess.

    Args:
        student_id: This student's id — use the exact value you were given for
            this conversation, never a different one.
    """
    data = await journey_service.get_strengths_weaknesses(student_id)

    enriched_weaknesses = []
    for w in data["weaknesses"]:
        course_id = await knowledge_graph_service.find_course_for_concept(w["concept"])
        prerequisites = []
        if course_id:
            view = await skill_graph_service.get_prerequisite_view(student_id, course_id, w["concept"])
            prerequisites = view["prerequisites"]
        enriched_weaknesses.append({**w, "course_id": course_id, "prerequisites": prerequisites})

    return {
        "strengths": data["strengths"],
        "weaknesses": enriched_weaknesses,
        "concepts_attempted": data["concepts_attempted"],
    }


# ── Dashboard metrics (thin wrapper over journey_service.get_metrics) ─────────
@mcp.tool()
async def get_learning_metrics(student_id: str) -> dict:
    """Raw activity numbers for this student — quiz count, streak, average score,
    active days, practice time. Use this for "what's my streak", "how many quizzes
    have I taken", "how am I doing overall" — anything asking for the numbers
    themselves rather than which concepts are strong/weak (use get_learning_strengths
    for that instead). `streak` counts consecutive days including today/yesterday;
    0 quizzes/0 streak means no graded activity yet — say so plainly, don't guess.

    Args:
        student_id: This student's id — use the exact value you were given for
            this conversation, never a different one.
    """
    return await journey_service.get_metrics(student_id)


# ── Enrollment (thin wrapper over enrollment_service) ─────────────────────────
@mcp.tool()
async def get_enrolled_courses(student_id: str) -> list[dict]:
    """Which courses this student actually has access to (purchased/enrolled).
    Use this for "what courses am I enrolled in / do I have access to" — you DO
    have this data now, don't decline or guess. An empty list means genuinely
    no enrollments yet, not that you lack access to check — say that plainly.

    Args:
        student_id: This student's id — use the exact value you were given for
            this conversation, never a different one.
    """
    return await enrollment_service.get_enrolled_courses(student_id)


# ── Skill observation write (thin wrapper over skill_graph_service.record_observation) ─
@mcp.tool()
async def record_skill_observation(
    concept: str, course_id: str, student_id: str, confidence: str, note: str,
) -> dict:
    """Log what you've noticed about this student's grasp of a concept from the
    conversation — NOT a quiz score. Call this whenever the conversation makes
    their understanding clear either way (they explained it correctly unprompted,
    or they were clearly confused/wrong about it) — you don't need to ask
    permission, this is internal bookkeeping, not a consequential action.

    confidence must be exactly one of: "weak", "developing", "strong".
    Do not call this for vague or ambiguous signals — only when the
    conversation actually showed you something concrete.

    Args:
        concept: The concept this observation is about.
        course_id: The course's id/slug — use the exact value you were given
            for this conversation.
        student_id: This student's id — use the exact value you were given
            for this conversation, never a different one.
        confidence: "weak" | "developing" | "strong".
        note: One sentence — what you actually observed, in plain language.
    """
    try:
        return await skill_graph_service.record_observation(student_id, course_id, concept, confidence, note)
    except ValueError as e:
        return {"error": str(e)}


if __name__ == "__main__":
    mcp.run(transport="stdio")
