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
    AskRequest, AskResponse, Course, QuizSubmit,
    AdaptiveStartRequest, AdaptiveAnswerRequest,
)
from app.services.vector_store import vector_store
from app.services.rag_service import ask, ask_stream
from app.services import (
    study_guide_service, question_service, quiz_service, adaptive_service,
    knowledge_graph_service, recommendation_service,
)

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


@app.get("/api/ai/questions/{course_id}")
async def questions_status(course_id: str):
    return await question_service.get_status(course_id)


@app.post("/api/ai/questions/{course_id}/generate")
async def questions_generate(course_id: str):
    _require_course(course_id)
    return await question_service.ensure_generated(course_id)


@app.post("/api/ai/quiz-session")
async def save_quiz_session(submit: QuizSubmit):
    session = await quiz_service.save_session(submit)
    # Completing a quiz changes performance → invalidate cached recommendations.
    await recommendation_service.invalidate(submit.user_id)
    return session


@app.get("/api/ai/quiz-sessions")
async def list_quiz_sessions(user_id: str):
    return await quiz_service.list_sessions(user_id)


@app.post("/api/ai/adaptive/start")
async def adaptive_start(req: AdaptiveStartRequest):
    _require_course(req.course_id)
    return await adaptive_service.start(req.user_id, req.course_id)


@app.post("/api/ai/adaptive/answer")
async def adaptive_answer(req: AdaptiveAnswerRequest):
    return await adaptive_service.answer(req.session_id, req.question_id, req.correct, req.concept)


@app.get("/api/ai/knowledge-graph/{course_id}")
async def knowledge_graph(course_id: str):
    return await knowledge_graph_service.get_graph(course_id)


@app.post("/api/ai/knowledge-graph/{course_id}/build")
async def knowledge_graph_build(course_id: str):
    _require_course(course_id)
    return await knowledge_graph_service.ensure_built(course_id)


@app.get("/api/ai/recommendations")
async def recommendations(user_id: str):
    return await recommendation_service.get_recommendations(user_id)


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
