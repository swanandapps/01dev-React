from pathlib import Path
from dotenv import load_dotenv

env_path = Path(__file__).parent.parent / ".env"
load_dotenv(env_path)

from contextlib import asynccontextmanager
import os

import razorpay
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from app.models import (
    AskRequest, AskResponse, Course, LectureInfo, QuizSubmit,
    AdaptiveStartRequest, AdaptiveAnswerRequest,
)
from app.services.vector_store import vector_store
from app.services.rag_service import ask, ask_stream
from app.services import study_guide_service, question_service, quiz_service, adaptive_service

RZP_KEY_ID = os.environ.get("RAZORPAY_KEY_ID", "")
RZP_KEY_SECRET = os.environ.get("RAZORPAY_KEY_SECRET", "")


class PaymentRequest(BaseModel):
    amount: str
    currency: str = "INR"
    courseId: int


@asynccontextmanager
async def lifespan(app: FastAPI):
    await vector_store.initialize()
    yield


app = FastAPI(title="RAG Learning Assistant API", version="1.0.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/health")
async def health():
    return {"status": "ok", "chunks_indexed": len(vector_store.chunks)}


@app.get("/api/courses", response_model=list[Course])
async def get_courses():
    return vector_store.get_all_courses()


@app.get("/api/lectures", response_model=list[LectureInfo])
async def get_lectures():
    """Lectures that have transcripts — the set AI features are scoped to."""
    return vector_store.list_lectures()


@app.get("/api/ai/study-guide/{lecture_id}")
async def study_guide_status(lecture_id: str):
    return await study_guide_service.get_status(lecture_id)


@app.post("/api/ai/study-guide/{lecture_id}/generate")
async def study_guide_generate(lecture_id: str):
    if not vector_store.get_lecture_meta(lecture_id):
        raise HTTPException(status_code=404, detail="Unknown lecture")
    return await study_guide_service.ensure_generated(lecture_id)


@app.get("/api/ai/questions/{lecture_id}")
async def questions_status(lecture_id: str):
    return await question_service.get_status(lecture_id)


@app.post("/api/ai/questions/{lecture_id}/generate")
async def questions_generate(lecture_id: str):
    if not vector_store.get_lecture_meta(lecture_id):
        raise HTTPException(status_code=404, detail="Unknown lecture")
    return await question_service.ensure_generated(lecture_id)


@app.post("/api/ai/quiz-session")
async def save_quiz_session(submit: QuizSubmit):
    return await quiz_service.save_session(submit)


@app.get("/api/ai/quiz-sessions")
async def list_quiz_sessions(user_id: str):
    return await quiz_service.list_sessions(user_id)


@app.post("/api/ai/adaptive/start")
async def adaptive_start(req: AdaptiveStartRequest):
    if not vector_store.get_lecture_meta(req.lecture_id):
        raise HTTPException(status_code=404, detail="Unknown lecture")
    return await adaptive_service.start(req.user_id, req.lecture_id)


@app.post("/api/ai/adaptive/answer")
async def adaptive_answer(req: AdaptiveAnswerRequest):
    return await adaptive_service.answer(req.session_id, req.question_id, req.correct, req.concept)


@app.post("/api/ai/ask", response_model=AskResponse)
async def ask_question(request: AskRequest):
    return await ask(request)


@app.post("/api/ai/ask/stream")
async def ask_question_stream(request: AskRequest):
    return StreamingResponse(
        ask_stream(request),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",  # disable proxy buffering so tokens flush immediately
        },
    )


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
