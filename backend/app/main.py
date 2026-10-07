from pathlib import Path
from dotenv import load_dotenv

env_path = Path(__file__).parent.parent / ".env"
load_dotenv(env_path)

from contextlib import asynccontextmanager
import os
import hashlib

import razorpay
from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from app.models import (
    Course,
    AdaptiveStartRequest, AdaptiveAnswerRequest, CourseInsightRequest, TutorRequest,
    EnrolledCourse, EnrollRequest,
)
from app.services.vector_store import vector_store
from app.services import (
    study_guide_service, question_service, adaptive_service,
    course_insight_service,
    journey_service, enrollment_service,
    audit_service, memory_service,
    eval_service, pii, chat_pipeline,
    skill_graph_service, catalog_index, catalog_service,
)
from app.services.otel import get_tracer, init_tracing
from app.services import course_lookup
from app.retrieval import titles as title_index
from app.services.course_lookup import ChatScope, _norm as norm_title
from app.auth import current_student
from app.routing.intent import Intent, classify
from app.routing.quiz_handoff import build_handoff_message
from app.services.lab.routes import router as lab_router
# Admin/audit/compliance routes (audit log, memory transparency+erase, eval
# RAG outputs + history, lab audit) are gated behind a shared secret — see
# app/deps.py for require_admin_key and why it lives there, not here.
from app.deps import require_admin_key
from app.grounding import loader

RZP_KEY_ID = os.environ.get("RAZORPAY_KEY_ID", "")
RZP_KEY_SECRET = os.environ.get("RAZORPAY_KEY_SECRET", "")


class PaymentRequest(BaseModel):
    amount: str
    currency: str = "INR"
    courseId: int


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_tracing()  # OpenTelemetry → OTLP/SigNoz (no-op unless configured)
    await vector_store.initialize()
    try:
        await catalog_index.ensure_built()
    except Exception as e:  # noqa: BLE001 — built lazily on first lookup instead
        print(f"[startup] catalog index build failed, will retry on first lookup: {e}")
    try:  # lecture-title vectors for every course, so no player turn pays (or fails) the build
        n_titles, n_courses = await title_index.prewarm()
        print(f"[startup] title embeddings prewarmed: {n_titles} titles / {n_courses} courses")
    except Exception as e:  # noqa: BLE001 — non-fatal; titles are built lazily per course instead
        print(f"[startup] title embeddings prewarm failed: {e!r}")
    yield


app = FastAPI(title="RAG Learning Assistant API", version="1.0.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Lab — the student content pipeline (Phase 1: quiz flow only, at /api/lab/*).
app.include_router(lab_router)


@app.get("/health")
async def health():
    db_ok = True
    if os.getenv("DATABASE_URL"):
        from app.services.db import ping
        db_ok = await ping()
    status = "ok" if db_ok else "degraded"
    return {
        "status": status,
        "chunks_indexed": len(vector_store.chunks),
        "db": ("ok" if db_ok else "unreachable") if os.getenv("DATABASE_URL") else "in-memory",
        "tutor_provider": "langchain-agent",
    }


@app.get("/api/courses", response_model=list[Course])
async def get_courses():
    return vector_store.get_all_courses()


def _require_course(course_id: str):
    if not vector_store.get_course_meta(course_id):
        raise HTTPException(status_code=404, detail="Unknown course")


@app.get("/api/ai/study-guide/{course_id}")
async def study_guide_status(course_id: str):
    return await study_guide_service.get_status(course_id)


@app.post("/api/ai/study-guide/{course_id}/generate")
async def study_guide_generate(course_id: str):
    _require_course(course_id)
    return await study_guide_service.ensure_generated(course_id)


@app.post("/api/ai/questions/{course_id}/generate")
async def questions_generate(course_id: str):
    _require_course(course_id)
    return await question_service.ensure_generated(course_id)


@app.post("/api/ai/adaptive/start")
async def adaptive_start(req: AdaptiveStartRequest):
    _require_course(req.course_id)
    return await adaptive_service.start(req.user_id, req.course_id)


@app.post("/api/ai/adaptive/answer")
async def adaptive_answer(req: AdaptiveAnswerRequest):
    return await adaptive_service.answer(
        req.session_id, req.question_id, req.correct, req.concept, req.time_taken_ms
    )


@app.get("/api/ai/journey")
async def journey(user_id: str):
    return await journey_service.get_journey(user_id)


@app.get("/api/enrollment/{student_id}", response_model=list[EnrolledCourse])
async def get_enrollment(student_id: str):
    return await enrollment_service.get_enrolled_courses(student_id)


@app.post("/api/enrollment", response_model=list[EnrolledCourse])
async def post_enrollment(req: EnrollRequest):
    return await enrollment_service.enroll(req.student_id, req.course_id, req.course_title)


@app.post("/api/ai/course-insight")
async def course_insight(req: CourseInsightRequest):
    if not vector_store.get_course_meta(req.course_id):
        raise HTTPException(status_code=404, detail="Unknown course")
    return await course_insight_service.generate(
        req.user_id, req.course_id, req.chat_questions, req.rewatched_lectures
    )


@app.post("/api/ai/tutor/stream")
async def tutor_stream_endpoint(req: TutorRequest, student_id: str = Depends(current_student)):
    """The tutor inside the video player: same pipeline as the Ask page, scoped to
    the course + lecture being watched. History is the running message list the
    client sends; req.user_id is ignored (identity comes from the login token)."""
    headers = {"Cache-Control": "no-cache", "Connection": "keep-alive", "X-Accel-Buffering": "no"}

    async def one(event: dict):
        yield chat_pipeline.sse(event)

    course = catalog_service.by_slug(req.course_id)
    if not course:
        return StreamingResponse(one({"type": "error", "message": "Unknown course"}),
                                 media_type="text/event-stream", headers=headers)
    msgs = [{"role": m.role, "content": m.content} for m in req.messages if m.role in ("user", "assistant")]
    if not msgs or msgs[-1]["role"] != "user" or not msgs[-1]["content"].strip():
        return StreamingResponse(one({"type": "error", "message": "Ask a question first"}),
                                 media_type="text/event-stream", headers=headers)

    # CoursePlayerPage sends the course title as `lecture` when no lecture is selected.
    lecture = req.lecture.strip()
    if lecture and norm_title(lecture) == norm_title(course.get("title", "")):
        lecture = ""
    turn = chat_pipeline.TurnRequest(
        question=msgs[-1]["content"], student_id=student_id,
        scope=ChatScope(course_slug=req.course_id, lecture_title=lecture or None, in_player=True,
                        position=req.position if req.position is not None and req.position >= 0 else None),
        history=msgs[:-1][-12:], memory_slug=req.course_id,
    )
    tracer = get_tracer()

    async def gen():
        span = tracer.start_span("chat_turn")
        span.set_attribute("route", "player")
        span.set_attribute("student", hashlib.sha256(student_id.encode()).hexdigest()[:12])
        try:
            async for event in chat_pipeline.chat_turn(turn):
                yield chat_pipeline.sse(event)
        finally:
            span.end()

    return StreamingResponse(gen(), media_type="text/event-stream", headers=headers)


@app.post("/api/hermes/chat")
async def hermes_chat(req: Request, student_id: str = Depends(current_student)):
    """The Ask page chat. URL kept for frontend compatibility (rename later).

    Fixed-answer intents (quiz hand-off, empty/gibberish) answer here; everything else
    runs chat_pipeline.chat_turn: course lookup in code first, then the tutor agent.
    Identity comes from the verified login token, never the request body.
    """
    body = await req.json()
    question = (body.get("question") or "").strip()
    course_slug = body.get("course_slug") or "all-courses"
    if not question:
        raise HTTPException(status_code=400, detail="Empty question")

    scrubbed, _ = pii.scrub(question)
    intent = classify(scrubbed)
    headers = {"Cache-Control": "no-cache", "Connection": "keep-alive", "X-Accel-Buffering": "no"}

    if intent in (Intent.QUIZ_GENERATE, Intent.OUT_OF_SCOPE):
        message = (build_handoff_message(course_slug) if intent == Intent.QUIZ_GENERATE
                   else "Hey, I'm Dev — ask me about a course or a technical concept and I'll help!")
        try:
            await audit_service.log_event(student_id=student_id, course_slug=course_slug, question=scrubbed,
                                          model="rule-based-router", provider="none")
        except Exception as e:  # noqa: BLE001 — audit is best-effort, same as chat_turn
            print(f"[hermes_chat] audit failed: {e!r}")

        async def gen_handoff():
            yield chat_pipeline.sse({"type": "sources", "sources": [], "insufficient_context": False,
                                     "offer_general": False})
            for word in message.split(" "):
                yield chat_pipeline.sse({"type": "token", "value": word + " "})
            yield chat_pipeline.sse({"type": "done"})

        return StreamingResponse(gen_handoff(), media_type="text/event-stream", headers=headers)

    try:
        await skill_graph_service.ensure_populated(student_id, course_slug)
    except Exception as e:  # noqa: BLE001 — back-fill never breaks a chat turn
        print(f"[hermes_chat] ensure_populated failed: {e}")

    prior = await memory_service.recent_turns(student_id, course_slug, limit=3)
    history: list[dict] = []
    for t in prior:
        history += [{"role": "user", "content": t.get("question", "")},
                    {"role": "assistant", "content": t.get("answer", "")}]

    turn = chat_pipeline.TurnRequest(
        question=question, student_id=student_id,
        scope=ChatScope(course_slug=None if course_slug == "all-courses" else course_slug),
        history=history, memory_slug=course_slug,
    )
    tracer = get_tracer()

    async def gen():
        span = tracer.start_span("chat_turn")
        span.set_attribute("route", "ask")
        span.set_attribute("student", hashlib.sha256(student_id.encode()).hexdigest()[:12])
        try:
            async for event in chat_pipeline.chat_turn(turn):
                yield chat_pipeline.sse(event)
        finally:
            span.end()

    return StreamingResponse(gen(), media_type="text/event-stream", headers=headers)


@app.get("/api/hermes/audit", dependencies=[Depends(require_admin_key)])
async def hermes_audit(limit: int = 20):
    """Recent EU-AI-Act audit records — the compliance/inspection view."""
    return await audit_service.recent(limit)


@app.get("/api/hermes/memory/{student_id}", dependencies=[Depends(require_admin_key)])
async def hermes_memory(student_id: str):
    """Transparency: exactly what the tutor remembers about a student."""
    return await memory_service.recall(student_id)


@app.delete("/api/hermes/memory/{student_id}", dependencies=[Depends(require_admin_key)])
async def hermes_memory_erase(student_id: str):
    """GDPR right-to-erasure — delete everything the tutor stored for a student."""
    return await memory_service.erase(student_id)


@app.get("/api/hermes/eval/rag-outputs", dependencies=[Depends(require_admin_key)])
async def eval_rag_outputs():
    """The tutor's RAG triples {question, answer, contexts} over the eval set — the input the
    isolated RAGAS harness scores (faithfulness / answer-relevancy / context-precision)."""
    return await eval_service.collect_rag_outputs(loader.read_grounding_prompt())


@app.get("/api/hermes/eval/history", dependencies=[Depends(require_admin_key)])
async def eval_history(kind: str | None = None, limit: int = 50):
    """The recorded eval / RAGAS results over time — the quality trend."""
    from app.eval import results_store
    return results_store.history(kind, limit)


@app.post("/api/paymentRZ")
async def create_payment(req: PaymentRequest):
    try:
        client = razorpay.Client(auth=(RZP_KEY_ID, RZP_KEY_SECRET))
        order = client.order.create({
            "amount": int(req.amount),
            "currency": req.currency,
            "receipt": f"course_{req.courseId}",
        })
        return {"id": order["id"], "amount": order["amount"], "currency": order["currency"]}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
