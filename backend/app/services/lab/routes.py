"""
Lab — the student content pipeline's HTTP surface.

The quiz flow speaks the same contract the frontend already knows
(`LessonView`), so the existing quiz UI drives it unchanged. This was
previously a standalone FastAPI app (lesson_service/main.py, never deployed);
it is now a router on the main backend so one service serves everything.

Phase 3 adds `/generate`: the student's output selection
(quiz/flashcards/summary/study_plan) fans out through artifacts_graph.py's
unified graph, then — if quiz was selected — hands off to the same lesson
graph the quiz-only /lessons endpoints already use, unchanged.

Phase 1 writes NOTHING to concept_performance or quiz_sessions — see the spec:
the external service this replaces writes nothing to the learner model, so a
parity migration must not either. That coupling lands in Phase 2 alongside the
concept resolver.
"""
import io
import os
import uuid

from fastapi import APIRouter, Depends, File, HTTPException, Request, UploadFile
from fastapi.concurrency import run_in_threadpool
from langgraph.types import Command
from pydantic import BaseModel

from app.deps import require_admin_key
from app.services.lab import artifact_store
from app.services.lab.artifacts_graph import build_lab_graph
from app.services.lab.generators import OUTPUT_TYPES
from app.services.lab.graph import build_graph
from app.services.lab.llm import tutor_answer

router = APIRouter(prefix="/api/lab", tags=["lab"])

GRAPH = build_graph()
LAB_GRAPH = build_lab_graph()
DOCS: dict[str, dict] = {}   # docId -> {"text","title"} — in-memory by design in Phase 1
AUDIT: list[dict] = []       # HITL decision trail (EU AI Act)

# Uploads are unauthenticated and DOCS/the LangGraph checkpointer keep document
# text in memory indefinitely (no eviction/TTL until the Postgres-checkpointer
# phase), so an accepted upload grows the RSS of the single-worker process that
# also serves chat/RAG/payments for the life of the process. These caps bound
# what we RETAIN. What we RECEIVE is only partly bounded: /upload rejects a
# declared Content-Length over MAX_PDF_BYTES before reading anything, but a
# chunked body with no Content-Length header has nothing to check upfront —
# it still falls through to the post-read len(data) check below, so it is
# fully materialized in memory before it can be rejected.
MAX_TEXT_CHARS = 200_000       # ~ a long set of study notes
MAX_PDF_BYTES = 10 * 1024 * 1024  # 10 MB, checked before parsing


class UploadTextReq(BaseModel):
    text: str
    title: str | None = None


class StartReq(BaseModel):
    docId: str


class ApproveReq(BaseModel):
    objectives: list[dict]
    questionsPerQuiz: int = 3


class SubmitReq(BaseModel):
    score: int
    total: int


class AskReq(BaseModel):
    question: str


class GenerateReq(BaseModel):
    docId: str
    outputs: list[str]
    student_id: str = ""


# Langfuse tracing for the graph run: one trace per lesson, span per node,
# grouped by session = lesson_id. Only active when LANGFUSE keys are present.
try:
    if os.getenv("LANGFUSE_PUBLIC_KEY") and os.getenv("LANGFUSE_SECRET_KEY"):
        from langfuse.langchain import CallbackHandler
        _LF_HANDLER = CallbackHandler()
    else:
        _LF_HANDLER = None
except Exception:  # noqa: BLE001 — never let observability break the lesson graph
    _LF_HANDLER = None


def _cfg(lesson_id: str) -> dict:
    cfg = {"configurable": {"thread_id": lesson_id}}
    if _LF_HANDLER is not None:
        cfg["callbacks"] = [_LF_HANDLER]
        cfg["metadata"] = {
            "langfuse_session_id": lesson_id,
            "langfuse_user_id": "the01dev-lab",
            "langfuse_tags": ["lab", "langgraph"],
        }
    return cfg


def _audit(event: str, lesson_id: str, **fields) -> None:
    AUDIT.append({"event": event, "lesson_id": lesson_id, **fields})


def lesson_view(lesson_id: str, v: dict) -> dict:
    """Build the exact LessonView the frontend expects from graph state values.

    Moved verbatim from lesson_service/main.py — these keys are the contract
    the existing quiz UI reads. Do not rename them.
    """
    status = v.get("status")
    view: dict = {"id": lesson_id, "status": status}
    if status == "awaiting_approval":
        view["plan"] = {"objectives": v.get("proposed_objectives", [])}
    elif status == "quizzing":
        objectives = v.get("objectives", [])
        view["objectives"] = objectives
        view["objectiveIndex"] = v.get("objective_index", 0)
        view["objectivesCount"] = len(objectives)
        view["currentObjective"] = v.get("current_objective")
        view["quiz"] = v.get("quiz")
        view["results"] = v.get("results", [])
    elif status == "complete":
        view["objectives"] = v.get("objectives", [])
        view["results"] = v.get("results", [])
        view["summary"] = v.get("summary")
    return view


def _state_values(lesson_id: str) -> dict:
    snap = GRAPH.get_state(_cfg(lesson_id))
    if not snap or not snap.values:
        raise HTTPException(status_code=404, detail="Unknown lesson")
    return snap.values


@router.get("/health")
async def health():
    return {"status": "ok", "service": "lab", "orchestrator": "langgraph",
            "model": os.getenv("LESSON_MODEL", "gpt-4.1-mini"),
            "outputs_enabled": OUTPUT_TYPES}


@router.post("/upload-text")
async def upload_text(req: UploadTextReq):
    if not req.text.strip():
        raise HTTPException(status_code=400, detail="empty text")
    if len(req.text) > MAX_TEXT_CHARS:
        raise HTTPException(
            status_code=400,
            detail=f"text too long ({len(req.text)} chars; max {MAX_TEXT_CHARS})",
        )
    doc_id = uuid.uuid4().hex[:12]
    DOCS[doc_id] = {"text": req.text, "title": req.title or ""}
    return {"docId": doc_id}


def _extract_pdf_text(data: bytes) -> str:
    """Synchronous, CPU-bound PDF parsing — run via run_in_threadpool, never
    called directly from an async handler (it would block the event loop for
    the whole extraction, stalling /health, SSE chat streams, everything)."""
    from pypdf import PdfReader
    reader = PdfReader(io.BytesIO(data))
    return "\n".join((p.extract_text() or "") for p in reader.pages).strip()


@router.post("/upload")
async def upload_pdf(request: Request, file: UploadFile = File(...)):
    # Reject on the declared Content-Length before spooling the body into
    # memory, when the client declares one -- Starlette's max_file_size is a
    # spool threshold, not a limit, so without this an oversized POST is
    # fully materialized before len(data) below ever gets a chance to reject
    # it. This only covers requests that send Content-Length: a chunked body
    # with no declared length still falls through to that post-read check,
    # fully materialized first (see the module-level comment on MAX_PDF_BYTES).
    content_length = request.headers.get("content-length")
    if content_length is not None:
        try:
            declared = int(content_length)
        except ValueError:
            declared = None
        if declared is not None and declared > MAX_PDF_BYTES:
            raise HTTPException(
                status_code=400,
                detail=f"PDF too large ({declared} bytes; max {MAX_PDF_BYTES})",
            )
    data = await file.read()
    if len(data) > MAX_PDF_BYTES:
        raise HTTPException(
            status_code=400,
            detail=f"PDF too large ({len(data)} bytes; max {MAX_PDF_BYTES})",
        )
    try:
        text = await run_in_threadpool(_extract_pdf_text, data)
    except Exception as e:  # noqa: BLE001
        raise HTTPException(status_code=400, detail=f"could not read PDF: {e}")
    if not text:
        raise HTTPException(status_code=400, detail="no extractable text in PDF")
    doc_id = uuid.uuid4().hex[:12]
    DOCS[doc_id] = {"text": text, "title": file.filename or ""}
    return {"docId": doc_id}


@router.post("/lessons")
async def start_lesson(req: StartReq):
    doc = DOCS.get(req.docId)
    if not doc:
        raise HTTPException(status_code=404, detail="Unknown docId")
    lesson_id = uuid.uuid4().hex[:12]
    values = await run_in_threadpool(
        GRAPH.invoke,
        {"doc": doc["text"], "title": doc["title"], "results": []},
        _cfg(lesson_id),
    )
    return lesson_view(lesson_id, values)


@router.get("/lessons/{lesson_id}")
async def get_lesson(lesson_id: str):
    return lesson_view(lesson_id, _state_values(lesson_id))


@router.post("/lessons/{lesson_id}/approve")
async def approve_lesson(lesson_id: str, req: ApproveReq):
    _state_values(lesson_id)  # 404 if unknown
    _audit("plan_approved", lesson_id, objectives=len(req.objectives),
           questionsPerQuiz=req.questionsPerQuiz)
    values = await run_in_threadpool(
        GRAPH.invoke,
        Command(resume={"objectives": req.objectives, "questionsPerQuiz": req.questionsPerQuiz}),
        _cfg(lesson_id),
    )
    return lesson_view(lesson_id, values)


@router.post("/lessons/{lesson_id}/submit")
async def submit_result(lesson_id: str, req: SubmitReq):
    _state_values(lesson_id)
    _audit("objective_submitted", lesson_id, score=req.score, total=req.total)
    values = await run_in_threadpool(
        GRAPH.invoke,
        Command(resume={"score": req.score, "total": req.total}),
        _cfg(lesson_id),
    )
    return lesson_view(lesson_id, values)


@router.post("/lessons/{lesson_id}/ask")
async def ask(lesson_id: str, req: AskReq):
    v = _state_values(lesson_id)
    answer = await run_in_threadpool(
        tutor_answer, v.get("doc", ""), v.get("current_objective"), req.question
    )
    return {"answer": answer}


@router.post("/generate")
async def generate_outputs(req: GenerateReq):
    """Fan out to the selected artifacts, persist them, then start the quiz
    if it was chosen.

    Persistence is this route's job, not the graph's: the `_gen` nodes in
    artifacts_graph.py deliberately do no I/O (see that module's docstring —
    bridging their async `artifact_store.save` into a sync node via
    `asyncio.run()` breaks the process-wide asyncpg pool's event-loop
    affinity in production). So here, on the route's own already-running
    event loop, we run the graph, read the artifacts back out of state, and
    await `artifact_store.save` directly -- once per artifact, before the
    quiz tail (if any) begins.

    Returns artifacts plus, when the quiz was selected, a `lesson_id` and the
    proposed objectives -- so the client goes straight into the existing
    objectives-approval screen.
    """
    doc = DOCS.get(req.docId)
    if not doc:
        raise HTTPException(status_code=404, detail="Unknown docId")
    if not req.outputs:
        raise HTTPException(status_code=400, detail="choose at least one output")
    unknown = [t for t in req.outputs if t not in OUTPUT_TYPES]
    if unknown:
        raise HTTPException(status_code=400, detail=f"unknown output(s): {unknown}")
    wanted = req.outputs

    run_id = uuid.uuid4().hex[:12]
    values = await run_in_threadpool(
        LAB_GRAPH.invoke,
        {"document": doc["text"], "doc_id": req.docId, "doc_title": doc["title"],
         "student_id": req.student_id, "outputs_requested": wanted, "artifacts": {}},
        _cfg(f"lab-{run_id}"),
    )
    artifacts = values.get("artifacts", {})
    for artifact_type, content in artifacts.items():
        await artifact_store.save(
            req.student_id, req.docId, doc["title"], artifact_type, content,
        )

    # Chosen failure semantics, not yet made idempotent: artifacts are
    # committed above, before the quiz tail runs. If the quiz tail below
    # raises, the 500 carries no run_id/lesson_id for the client to key a
    # retry off of, so a naive retry re-runs generate() and duplicates these
    # rows in lab_artifacts. Accepted for now -- see task review for Phase 3
    # task 4; revisit if duplicate-artifact reports show up.
    body: dict = {
        "run_id": run_id,
        "status": "complete",
        "artifacts": artifacts,
        "lesson_id": None,
    }
    if "quiz" not in wanted:
        return body

    # Quiz selected: start the lesson graph, which owns the objectives HITL gate.
    # Deliberately passes doc_id, which start_lesson()'s GRAPH.invoke() above
    # (the production /lessons call) does not: that LessonState channel exists
    # specifically so this Lab flow can carry provenance through to the quiz
    # tail. Its absence from /lessons is the production baseline, not an
    # oversight here -- this is an intentional divergence, not a drift.
    lesson_id = uuid.uuid4().hex[:12]
    lesson_values = await run_in_threadpool(
        GRAPH.invoke,
        {"doc": doc["text"], "title": doc["title"], "results": [], "doc_id": req.docId},
        _cfg(lesson_id),
    )
    view = lesson_view(lesson_id, lesson_values)
    body["status"] = view["status"]
    body["lesson_id"] = lesson_id
    body["proposed_objectives"] = view.get("plan", {}).get("objectives", [])
    return body


@router.get("/audit", dependencies=[Depends(require_admin_key)])
async def audit(limit: int = 20):
    """HITL decision trail — additive, not part of the Lab response contract."""
    return list(reversed(AUDIT))[:limit]
