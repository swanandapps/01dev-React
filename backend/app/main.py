from contextlib import asynccontextmanager

import razorpay
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from app.models import AskRequest, AskResponse, Course
from app.services.vector_store import vector_store
from app.services.rag_service import ask

RZP_KEY_ID = "RAZORPAY_KEY_ID_REMOVED"
RZP_KEY_SECRET = "RAZORPAY_SECRET_REMOVED"


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
