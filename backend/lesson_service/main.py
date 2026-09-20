"""QuizMe — a sovereign LangGraph microservice (:8090).

Drop-in re-implementation of the Mastra/Memorang V2 Notes-Quiz API: identical
endpoints and identical `LessonView` shapes, so the existing frontend drives it
by only changing VITE_NOTES_QUIZ_URL. Underlying stack: LangGraph + local model
instead of Mastra + cloud. Nothing leaves the box.

Contract (mirrors frontend/src/lib/notesQuizApi.ts):
  POST /upload-text {text,title?}            -> {docId}
  POST /upload  (multipart file)             -> {docId}          (PDF → text)
  POST /lessons {docId}                      -> LessonView (awaiting_approval)
  GET  /lessons/{id}                         -> LessonView (resume/poll)
  POST /lessons/{id}/approve {objectives,questionsPerQuiz} -> LessonView (quizzing)
  POST /lessons/{id}/submit  {score,total}   -> LessonView (quizzing | complete)
  POST /lessons/{id}/ask     {question}      -> {answer}
"""
import io
import os
import uuid

from fastapi import FastAPI, HTTPException, UploadFile, File
from fastapi.concurrency import run_in_threadpool
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from langgraph.types import Command

from .graph import build_graph
from .artifacts_graph import build_artifacts_graph
from .llm import tutor_answer

app = FastAPI(title="the01.dev QuizMe (LangGraph)", version="2.0.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

GRAPH = build_graph()
ARTIFACTS = build_artifacts_graph()
DOCS: dict[str, dict] = {}          # docId -> {"text","title"}
AUDIT: list[dict] = []              # HITL decision trail (EU AI Act)


# ── request models ──────────────────────────────────────────────────────────
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


class ArtifactsStartReq(BaseModel):
    docId: str
    types: list[str] | None = None   # subset of notes/summary/quiz/flashcards


class ArtifactsApproveReq(BaseModel):
    thread_id: str
    approved: bool = True
    types: list[str] | None = None


# ── helpers ─────────────────────────────────────────────────────────────────
# Langfuse tracing for the LangGraph run: one trace per lesson with a span per node
# (plan_objectives → generate_quiz → summarize), grouped by session = lesson_id. Only
# active when LANGFUSE keys are present (graceful — QuizMe still runs without them).
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
            "langfuse_session_id": lesson_id,       # groups a lesson's calls into one session
            "langfuse_user_id": "the01dev-tour",
            "langfuse_tags": ["quizme", "langgraph"],
        }
    return cfg


def _audit(event: str, lesson_id: str, **fields) -> None:
    AUDIT.append({"event": event, "lesson_id": lesson_id, **fields})


def lesson_view(lesson_id: str, v: dict) -> dict:
    """Build the exact LessonView the frontend expects from graph state values."""
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


# ── endpoints ───────────────────────────────────────────────────────────────
@app.get("/health")
async def health():
    return {"status": "ok", "service": "quizme", "orchestrator": "langgraph",
            "model": os.getenv("LESSON_MODEL", "qwen2.5:3b"),
            "provider": "ollama (local, sovereign)"}


@app.post("/upload-text")
async def upload_text(req: UploadTextReq):
    if not req.text.strip():
        raise HTTPException(status_code=400, detail="empty text")
    doc_id = uuid.uuid4().hex[:12]
    DOCS[doc_id] = {"text": req.text, "title": req.title or ""}
    return {"docId": doc_id}


@app.post("/upload")
async def upload_pdf(file: UploadFile = File(...)):
    data = await file.read()
    try:
        from pypdf import PdfReader
        reader = PdfReader(io.BytesIO(data))
        text = "\n".join((p.extract_text() or "") for p in reader.pages).strip()
    except Exception as e:  # noqa: BLE001
        raise HTTPException(status_code=400, detail=f"could not read PDF: {e}")
    if not text:
        raise HTTPException(status_code=400, detail="no extractable text in PDF")
    doc_id = uuid.uuid4().hex[:12]
    DOCS[doc_id] = {"text": text, "title": file.filename or ""}
    return {"docId": doc_id}


@app.post("/lessons")
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


@app.get("/lessons/{lesson_id}")
async def get_lesson(lesson_id: str):
    return lesson_view(lesson_id, _state_values(lesson_id))


@app.post("/lessons/{lesson_id}/approve")
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


@app.post("/lessons/{lesson_id}/submit")
async def submit_result(lesson_id: str, req: SubmitReq):
    _state_values(lesson_id)
    _audit("objective_submitted", lesson_id, score=req.score, total=req.total)
    values = await run_in_threadpool(
        GRAPH.invoke,
        Command(resume={"score": req.score, "total": req.total}),
        _cfg(lesson_id),
    )
    return lesson_view(lesson_id, values)


@app.post("/lessons/{lesson_id}/ask")
async def ask(lesson_id: str, req: AskReq):
    v = _state_values(lesson_id)
    answer = await run_in_threadpool(
        tutor_answer, v.get("doc", ""), v.get("current_objective"), req.question
    )
    return {"answer": answer}


@app.post("/artifacts/start")
async def artifacts_start(req: ArtifactsStartReq):
    """Planner proposes the artifacts; the graph SUSPENDS at HITL approval."""
    doc = DOCS.get(req.docId)
    if not doc:
        raise HTTPException(status_code=404, detail="Unknown docId")
    thread_id = uuid.uuid4().hex[:12]
    values = await run_in_threadpool(
        ARTIFACTS.invoke,
        {"document": doc["text"], "requested": req.types, "outputs": {}},
        _cfg(thread_id),
    )
    proposed = values.get("plan", [])
    interrupts = values.get("__interrupt__")
    if interrupts:
        proposed = getattr(interrupts[0], "value", {}).get("proposed_plan", proposed)
    _audit("artifacts_proposed", thread_id, plan=proposed)
    return {"thread_id": thread_id, "status": "awaiting_approval", "proposed_plan": proposed}


@app.post("/artifacts/approve")
async def artifacts_approve(req: ArtifactsApproveReq):
    """Resume from the checkpoint: fan out to the specialized generators."""
    values = await run_in_threadpool(
        ARTIFACTS.invoke,
        Command(resume={"approved": req.approved, "plan": req.types}),
        _cfg(req.thread_id),
    )
    _audit("artifacts_" + ("approved" if req.approved else "rejected"), req.thread_id, types=req.types)
    return {"thread_id": req.thread_id, "status": values.get("status"), "outputs": values.get("outputs", {})}


@app.get("/audit")
async def audit(limit: int = 20):
    """HITL decision trail — additive (not part of the Mastra contract)."""
    return list(reversed(AUDIT))[:limit]
