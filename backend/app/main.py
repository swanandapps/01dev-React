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

from app.models import AskRequest, AskResponse, Course
from app.services.vector_store import vector_store
from app.services.rag_service import ask, ask_stream

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
