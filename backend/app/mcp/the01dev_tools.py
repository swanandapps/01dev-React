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
    from app.services import grounding, content, memory_service
    from app.services.chunker import chunk_transcript

mcp = FastMCP("the01dev-tools")

_initialized = False

# SECURITY: an agent-driven filesystem is a real risk (path traversal, writing
# outside the project). read_file/write_file are hard-confined to this one dir.
_AGENT_FS = (_BACKEND / "data" / "agent_fs").resolve()


async def _ensure_index() -> None:
    """Load seed transcripts + embeddings once, on first retrieval tool call."""
    global _initialized
    if not _initialized:
        with contextlib.redirect_stdout(sys.stderr):
            await vector_store.initialize()
        _initialized = True


def _safe_path(rel: str) -> Path:
    """Resolve `rel` strictly inside _AGENT_FS. Reject absolute paths, `..`
    traversal, and symlinks — the sandbox is non-negotiable for an agent tool."""
    if os.path.isabs(rel):
        raise ValueError("absolute paths are not allowed")
    full = (_AGENT_FS / rel).resolve()
    if full != _AGENT_FS and not str(full).startswith(str(_AGENT_FS) + os.sep):
        raise ValueError("path escapes the sandbox")
    if full.is_symlink():
        raise ValueError("symlinks are not allowed")
    return full


# ── Retrieval (unchanged) ─────────────────────────────────────────────────────
@mcp.tool()
async def search_course_content(query: str, top_k: int = 5) -> list[dict]:
    """Search the01.dev course transcripts for material relevant to a student's question.

    USE THIS FIRST for ANY question about a concept the course teaches (e.g. "what is
    the event loop?", "how does React.memo work?"). It is the default, correct tool for
    answering course questions — it grounds the answer in real lecture content. Do NOT
    use generate_notes / generate_quiz / process_pdf to answer a concept question.

    Returns excerpts with course, lecture, and the video timestamp (mm:ss + start_time
    in seconds) so answers can cite sources.

    Args:
        query: The student's question, or the concept to look up.
        top_k: How many transcript excerpts to return (default 5).
    """
    await _ensure_index()
    results = await grounding.retrieve(query, top_k=top_k)  # shared retrieval

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
        return [{"note": "No matching course content found. Tell the student the "
                 "platform material does not cover this — do not answer from outside it."}]
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


# ── PDF (thin wrapper over PDF extraction + shared chunker) ───────────────────
@mcp.tool()
async def process_pdf(path: str) -> dict:
    """Extract text from a PDF and chunk it with the shared transcript chunker.

    Use ONLY when the student explicitly provides a PDF file path to ingest. Do NOT
    call this to answer a question — it needs a real PDF path, and course questions
    are answered with search_course_content.

    Returns {text, chunks, chars}. Requires `pypdf` (installed in this server's venv).

    Args:
        path: Filesystem path to the PDF.
    """
    try:
        from pypdf import PdfReader
    except ImportError:
        return {"error": "pypdf is not installed in this server's environment"}

    p = Path(path).expanduser()
    if not p.is_file():
        return {"error": f"not a file: {path}"}

    reader = PdfReader(str(p))
    text = "\n".join((page.extract_text() or "") for page in reader.pages).strip()
    chunks = chunk_transcript(
        text, course_id="pdf", course_title="PDF",
        lecture_id=p.stem, lecture_title=p.stem,
    )
    return {"text": text, "chunks": len(chunks), "chars": len(text)}


# ── Sandboxed filesystem (confined to backend/data/agent_fs/) ─────────────────
@mcp.tool()
async def read_file(path: str) -> dict:
    """Read a text file from the agent sandbox (backend/data/agent_fs/).

    Args:
        path: Path RELATIVE to the sandbox. Absolute paths / `..` / symlinks are rejected.
    """
    try:
        full = _safe_path(path)
    except ValueError as e:
        return {"ok": False, "error": str(e)}
    if not full.is_file():
        return {"ok": False, "error": "not found"}
    return {"ok": True, "content": full.read_text()[:20000]}


@mcp.tool()
async def write_file(path: str, content: str) -> dict:
    """Write a text file into the agent sandbox (backend/data/agent_fs/).

    Args:
        path: Path RELATIVE to the sandbox. Absolute paths / `..` / symlinks are rejected.
        content: The text to write.
    """
    try:
        full = _safe_path(path)
    except ValueError as e:
        return {"ok": False, "error": str(e)}
    full.parent.mkdir(parents=True, exist_ok=True)
    full.write_text(content)
    return {"ok": True, "path": str(full.relative_to(_AGENT_FS)), "bytes": len(content)}


if __name__ == "__main__":
    mcp.run(transport="stdio")
