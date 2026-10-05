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

Phase 2: a quiz submit by a signed-in student (Firebase token via
`optional_student`, never the request body) is graded server-side and written to
the learner model — concept_performance + one quiz_sessions row per objective,
with concepts canonicalised by concept_resolver. Anonymous submits write nothing.
"""
import io
import logging
import os
import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, File, HTTPException, Request, UploadFile
from fastapi.concurrency import run_in_threadpool
from langgraph.types import Command
from pydantic import BaseModel

from app.auth import current_student, optional_student
from app.deps import require_admin_key
from app.services import (
    adaptive_service, catalog_service, concept_resolver, enrollment_service, recommendation_service,
)
from app.services.lab import artifact_store
from app.services.lab.artifacts_graph import build_lab_graph
from app.services.lab.generators import OUTPUT_TYPES
from app.services.lab.graph import build_graph
from app.services.lab.llm import tutor_answer
from app.services.store import store
from app.services.vector_store import vector_store

log = logging.getLogger(__name__)

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


class UploadLectureReq(BaseModel):
    lecture_id: str


class StartReq(BaseModel):
    docId: str


class ApproveReq(BaseModel):
    objectives: list[dict]
    questionsPerQuiz: int = 3


class AnswerResult(BaseModel):
    """One answered question: the server grades it and looks up the concept."""
    question_index: int
    selected_index: int


class SubmitReq(BaseModel):
    score: int
    total: int
    # Index of the objective whose quiz is being submitted. A stale or repeated
    # submit (double-click, retry) names an objective the lesson already moved
    # past and is rejected with 409 before anything is resumed or written.
    objective_index: int = 0
    # First attempt per question, in any order. Optional so an older client that
    # sends only score/total keeps working (it just writes nothing to the
    # learner model). Identity is NEVER read from the body.
    answers: list[AnswerResult] = []


class AskReq(BaseModel):
    question: str


class GenerateReq(BaseModel):
    docId: str
    outputs: list[str]


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


def _breakdown(answers: list[dict]) -> list[dict]:
    agg: dict[str, dict] = {}
    for a in answers:
        row = agg.setdefault(a["concept"], {"attempts": 0, "correct": 0})
        row["attempts"] += 1
        row["correct"] += 1 if a["correct"] else 0
    out = [{"concept": c, "attempts": r["attempts"], "correct": r["correct"],
            "accuracy": round(r["correct"] / r["attempts"], 3)} for c, r in agg.items()]
    out.sort(key=lambda r: r["accuracy"])
    return out


async def _record_learner_model(student_id: str | None, lesson_id: str, v: dict,
                                answers: list[AnswerResult]) -> None:
    """Fold one submitted objective into the learner model.

    Grading is server-side: correctness is `selected_index == correctIndex` from
    graph state and the concept comes from graph state, so a client can't forge
    either. Writes the same two collections a course quiz does (concept_performance
    via adaptive_service, quiz_sessions) so Lab results move the same dashboard.
    Idempotent per objective: the session id is deterministic and an existing
    row means every write is skipped.
    """
    quiz = v.get("quiz")
    if not student_id or not answers or not quiz:
        return
    qs = quiz.get("questions", [])
    obj_index = v.get("objective_index", 0)
    session_id = f"lab-{lesson_id}-o{obj_index}"
    if await store.get("quiz_sessions", session_id):
        return

    fallback = (v.get("current_objective") or {}).get("title", "")
    seen: set[int] = set()
    graded: list[tuple[int, str, bool]] = []  # (question_index, raw_concept, correct)
    for a in answers:
        i = a.question_index
        if not 0 <= i < len(qs) or i in seen:
            continue
        seen.add(i)
        q = qs[i]
        raw = (q.get("concept") or "").strip() or fallback
        graded.append((i, raw, a.selected_index == q.get("correctIndex")))
    if not graded:
        return

    course_id = v.get("course_id")
    canonical: dict[str, str] = {}
    for _, raw, _ in graded:
        if raw not in canonical:
            canonical[raw] = await concept_resolver.resolve(raw, course_id)

    recs = [{"concept": canonical[raw], "correct": correct} for _, raw, correct in graded]
    await store.set("quiz_sessions", session_id, {
        "session_id": session_id,
        "user_id": student_id,
        "course_id": None,
        "course_title": v.get("title") or "Your own material",
        "source": "lecture" if course_id else "self_study",
        "doc_id": v.get("doc_id"),
        "doc_title": v.get("title") or "",
        "score": sum(1 for _, _, c in graded if c),
        "total": len(graded),
        "answers": [
            {"question_id": f"{lesson_id}-{i}", "concept": canonical[raw], "raw_concept": raw,
             "difficulty": "", "correct": correct, "time_taken_ms": 0, "lecture": ""}
            for i, raw, correct in graded
        ],
        "concept_breakdown": _breakdown(recs),
        "completed_at": datetime.now(timezone.utc).isoformat(),
    })
    # Write-first claim: the session row is the idempotency marker, so it goes
    # BEFORE the perf updates. A failure partway through under-counts (and is
    # logged by the caller) instead of double-counting on retry. Not atomic: the
    # store has no create-if-absent primitive, so two truly concurrent POSTs for
    # the same objective can still both pass the existence check above.
    for _, raw, correct in graded:
        await adaptive_service._update_perf(student_id, canonical[raw], correct)
    await recommendation_service.invalidate(student_id)


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
async def start_lesson(req: StartReq, uid: str | None = Depends(optional_student)):
    doc = DOCS.get(req.docId)
    if not doc:
        raise HTTPException(status_code=404, detail="Unknown docId")
    lesson_id = uuid.uuid4().hex[:12]
    values = await run_in_threadpool(
        GRAPH.invoke,
        {"doc": doc["text"], "title": doc["title"], "results": [],
         "doc_id": req.docId, "student_id": uid},
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
async def submit_result(lesson_id: str, req: SubmitReq,
                        uid: str | None = Depends(optional_student)):
    v = _state_values(lesson_id)  # captured BEFORE resuming: the graph moves on
    if req.objective_index != v.get("objective_index", 0):
        raise HTTPException(status_code=409, detail="Objective already submitted")
    if v.get("status") != "quizzing":
        raise HTTPException(status_code=409, detail="Lesson is not awaiting a quiz submission")
    _audit("objective_submitted", lesson_id, score=req.score, total=req.total)
    values = await run_in_threadpool(
        GRAPH.invoke,
        Command(resume={"score": req.score, "total": req.total}),
        _cfg(lesson_id),
    )
    owner = v.get("student_id")
    if uid and (not owner or owner == uid):
        try:
            await _record_learner_model(uid, lesson_id, v, req.answers)
        except Exception:  # noqa: BLE001 — never fail a quiz over analytics
            log.exception("lab learner-model write failed for lesson %s", lesson_id)
    return lesson_view(lesson_id, values)


@router.post("/lessons/{lesson_id}/ask")
async def ask(lesson_id: str, req: AskReq):
    v = _state_values(lesson_id)
    answer = await run_in_threadpool(
        tutor_answer, v.get("doc", ""), v.get("current_objective"), req.question
    )
    return {"answer": answer}


@router.get("/lectures")
async def list_course_lectures(course_id: str):
    """Which lectures of this course have transcripts the Lab can use (titles
    only). `course_id` is the transcript slug, e.g. "react-perf"."""
    return vector_store.get_course_lectures(course_id)


@router.post("/upload-lecture")
async def upload_lecture(req: UploadLectureReq, uid: str = Depends(current_student)):
    """Use an indexed course lecture as the material — no upload needed.

    Transcripts are paid content, so the caller must be signed in and enrolled
    in the lecture's course. Enrollments use the numeric catalog id while the
    transcript's course_id is the slug; catalog_service bridges the two.
    `course_id` is stored on the doc so a quiz built from it resolves concepts
    with the lecture's course as their origin.
    """
    # Unknown lecture and not-enrolled return the same 403 so lecture ids can't
    # be probed by a signed-in non-enrolled user.
    meta = vector_store.get_lecture_meta(req.lecture_id) or {}
    course = catalog_service.by_slug(meta.get("course_id") or "")
    enrolled = {c.get("id") for c in await enrollment_service.get_enrolled_courses(uid)}
    if not course or course["id"] not in enrolled:
        raise HTTPException(status_code=403, detail="Enroll in this course to use its lectures")
    text = (vector_store.get_lecture_transcript(req.lecture_id) or "").strip()
    if not text:
        raise HTTPException(status_code=400, detail="lecture has no transcript text")
    doc_id = uuid.uuid4().hex[:12]
    title = meta.get("lecture_title") or req.lecture_id
    DOCS[doc_id] = {"text": text[:MAX_TEXT_CHARS], "title": title,
                    "course_id": meta.get("course_id"), "source": "lecture"}
    return {"docId": doc_id, "title": title, "course_id": meta.get("course_id")}


@router.post("/generate")
async def generate_outputs(req: GenerateReq, uid: str | None = Depends(optional_student)):
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
         "student_id": uid or "", "outputs_requested": wanted, "artifacts": {}},
        _cfg(f"lab-{run_id}"),
    )
    artifacts = values.get("artifacts", {})
    for artifact_type, content in artifacts.items():
        await artifact_store.save(
            uid or "", req.docId, doc["title"], artifact_type, content,
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
    # doc_id and the verified student_id ride along so the submit route can
    # attribute the learner-model write to this document and owner.
    lesson_id = uuid.uuid4().hex[:12]
    lesson_values = await run_in_threadpool(
        GRAPH.invoke,
        {"doc": doc["text"], "title": doc["title"], "results": [], "doc_id": req.docId,
         "student_id": uid, "course_id": doc.get("course_id")},
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
