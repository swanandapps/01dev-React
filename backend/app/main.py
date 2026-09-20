from pathlib import Path
from dotenv import load_dotenv

env_path = Path(__file__).parent.parent / ".env"
load_dotenv(env_path)

import json
from contextlib import asynccontextmanager
import os
import hashlib

from opentelemetry import trace as otel_trace

import razorpay
from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from app.models import (
    AskRequest, AskResponse, Course, QuizSubmit,
    AdaptiveStartRequest, AdaptiveAnswerRequest, CourseInsightRequest, TutorRequest,
)
from app.services.vector_store import vector_store
from app.services.rag_service import ask, ask_stream, _build_sources
from app.services import (
    study_guide_service, question_service, quiz_service, adaptive_service,
    knowledge_graph_service, recommendation_service, course_insight_service,
    tutor_service, journey_service,
    hermes_client, ollama_client, openai_tutor, audit_service, memory_service,
    eval_service, gepa_service, grounding, context_builder, pii, llm,
)
from app.services.otel import get_tracer, init_tracing
from app.routing.intent import Intent, classify
from app.routing.quiz_handoff import build_handoff_message
from app.routing.progress_handoff import build_progress_message

# The reliable tutor talks to OpenAI in production (managed hosting has no local
# Ollama). Set TUTOR_PROVIDER=ollama to use the local sovereign model in dev.
_TUTOR_PROVIDER = os.getenv("TUTOR_PROVIDER", "openai" if os.getenv("OPENAI_API_KEY") else "ollama")
# CHAT_MODE=hermes → /chat runs full-Hermes (agentic) by default, no OpenAI.
# Grounding then flows through the search_course_content MCP tool, which uses the
# vector store's keyword fallback automatically when OpenAI embeddings are off.
_CHAT_MODE = os.getenv("CHAT_MODE", "").lower()
_GROUNDING_THRESHOLD = float(os.getenv("HERMES_GROUNDING_THRESHOLD", "0.45"))
_MODEL_CONTEXT_LIMIT = int(os.getenv("MODEL_CONTEXT_LIMIT", "8192"))

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
    db_ok = True
    if os.getenv("DATABASE_URL"):
        from app.services.db import ping
        db_ok = await ping()
    status = "ok" if db_ok else "degraded"
    return {
        "status": status,
        "chunks_indexed": len(vector_store.chunks),
        "db": ("ok" if db_ok else "unreachable") if os.getenv("DATABASE_URL") else "in-memory",
        "tutor_provider": _TUTOR_PROVIDER,
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
    return await adaptive_service.answer(
        req.session_id, req.question_id, req.correct, req.concept, req.time_taken_ms
    )


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


@app.get("/api/ai/journey")
async def journey(user_id: str):
    return await journey_service.get_journey(user_id)


@app.post("/api/ai/course-insight")
async def course_insight(req: CourseInsightRequest):
    if not vector_store.get_course_meta(req.course_id):
        raise HTTPException(status_code=404, detail="Unknown course")
    return await course_insight_service.generate(
        req.user_id, req.course_id, req.chat_questions, req.rewatched_lectures
    )


@app.post("/api/ai/tutor/stream")
async def tutor_stream_endpoint(req: TutorRequest):
    messages = [{"role": m.role, "content": m.content} for m in req.messages]
    return StreamingResponse(
        tutor_service.tutor_stream(req.user_id, req.course_id, messages, req.lecture),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "Connection": "keep-alive", "X-Accel-Buffering": "no"},
    )


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


@app.post("/api/hermes/chat")
async def hermes_chat(req: Request):
    """Governance layer for the Hermes tutor: access gate + EU-AI-Act audit +
    session-spanning memory + streaming proxy to the Hermes agent (:8642), all on a
    LOCAL sovereign model. Two modes:

      - default (hybrid): retrieve course material here and inject it — reliable on 8GB.
      - agentic=true: let the Hermes agent drive the search_course_content MCP tool
        itself (the real ReAct loop; best on a GPU-hosted model).

    Either way the tutor REMEMBERS the student: prior turns are threaded (multi-turn)
    and a running profile is injected, then this exchange is persisted for next time.
    """
    body = await req.json()
    question = (body.get("question") or "").strip()
    student_id = body.get("user_id") or req.headers.get("X-Student-Id") or ""
    course_slug = body.get("course_slug") or req.headers.get("X-Course-Slug") or "js-fundamentals"
    agentic = bool(body.get("agentic", False)) or _CHAT_MODE == "hermes"

    # 1. Access gate.
    if not student_id:
        raise HTTPException(status_code=403, detail="Sign in to use the AI tutor")
    if not question:
        raise HTTPException(status_code=400, detail="Empty question")

    # PII scrub at request entry — the single choke point. The redacted question is
    # what we send to the model, embed, trace, audit, AND persist, so no student PII
    # reaches any downstream surface. (regex tier; Presidio is the drop-in upgrade.)
    question, pii_kinds = pii.scrub(question)

    intent = classify(question)

    # OTel parent span for the whole request (no-op unless tracing configured).
    # Started manually + ended in gen()'s finally so it spans the streamed generation.
    tracer = get_tracer()
    span = tracer.start_span("hermes_chat")
    span.set_attribute("course_slug", course_slug)
    span.set_attribute("agentic", agentic)
    span.set_attribute("intent", intent.value)
    span.set_attribute("student", hashlib.sha256(student_id.encode()).hexdigest()[:12])  # hashed, no PII
    if pii_kinds:  # audit trail: WHAT kinds were redacted, never the values
        span.set_attribute("pii_redacted", ",".join(pii_kinds))

    if intent in (Intent.QUIZ_GENERATE, Intent.PROGRESS_LOOKUP):
        if intent == Intent.QUIZ_GENERATE:
            outcome, model_label, audit_provider = "quiz_handoff", "rule-based-router", "none"
            message = build_handoff_message(course_slug)
        else:
            outcome, model_label, audit_provider = "progress_handoff", llm.GEN_MODEL, "openai"
            try:
                message = await build_progress_message(student_id)
            except Exception as e:  # noqa: BLE001 — journey lookup down → decline gracefully, no 500
                print(f"[hermes_chat] progress lookup failed: {e}")
                message = "I couldn't pull up your progress just now — try the Journey dashboard instead."

        span.set_attribute("outcome", outcome)
        await audit_service.log_event(
            student_id=student_id, course_slug=course_slug, question=question,
            model=model_label, provider=audit_provider,
        )

        async def gen_handoff():
            try:
                yield f"data: {json.dumps({'type': 'sources', 'sources': [], 'insufficient_context': False, 'offer_general': False})}\n\n"
                for word in message.split(" "):
                    yield f"data: {json.dumps({'type': 'token', 'value': word + ' '})}\n\n"
                yield f"data: {json.dumps({'type': 'done'})}\n\n"
            finally:
                span.end()

        return StreamingResponse(
            gen_handoff(),
            media_type="text/event-stream",
            headers={"Cache-Control": "no-cache", "Connection": "keep-alive", "X-Accel-Buffering": "no"},
        )

    # Resolve which engine answers — audit must record the TRUE model/provider.
    if agentic:
        tutor_client = hermes_client
        tutor_model, tutor_provider = os.getenv("HERMES_MODEL_LABEL", "gpt-4.1-mini"), "hermes (agent loop)"
    elif _TUTOR_PROVIDER == "ollama":
        tutor_client = ollama_client
        tutor_model, tutor_provider = ollama_client.TUTOR_MODEL, "ollama (local, sovereign)"
    else:
        tutor_client = openai_tutor
        tutor_model, tutor_provider = openai_tutor.TUTOR_MODEL, "openai"
    span.set_attribute("provider", tutor_provider)

    # 2. EU AI Act audit — before inference.
    await audit_service.log_event(
        student_id=student_id, course_slug=course_slug, question=question,
        model=tutor_model, provider=tutor_provider,
    )

    # 3. Session-spanning memory: what we remember + the last few turns (multi-turn).
    mem = await memory_service.memory_context(student_id, course_slug)
    prior = await memory_service.recent_turns(student_id, course_slug, limit=3)
    history: list[dict] = []
    for t in prior:
        history.append({"role": "user", "content": t.get("question", "")})
        history.append({"role": "assistant", "content": t.get("answer", "")})

    # Persona comes from the SOUL — the identity GEPA evolves (and the audit fingerprints).
    persona = gepa_service.read_soul() + f"\nYou are tutoring the '{course_slug}' course on the01.dev. "
    # Memory goes up front (prominent) so it isn't overridden by the material rule below.
    memory_block = (mem + "\n\n") if mem else ""

    # Deterministic grounding: only material at/above this similarity counts as "covered".
    # Below it, we DON'T trust the small model to decline — we decline in code, then offer
    # a general answer that the student must explicitly authorize (HITL consent).
    allow_general = bool(body.get("allow_general", False))
    threshold = _GROUNDING_THRESHOLD
    insufficient_context = False   # question is outside the course's scope
    offer_general = False          # …and we're offering an ungrounded general answer
    decline_msg = None

    if agentic:
        # Real agent loop: Hermes drives the MCP tool itself; no injected material.
        sources = []
        system = (
            persona + "\n\n" + memory_block +
            "Use the search_course_content tool to find relevant course material, then "
            "answer grounded in what it returns and cite the lecture. "
            "When the student refers to how you previously taught them something "
            "(e.g. 'like you taught me closures'), call the search_history tool to "
            "retrieve those past exchanges and mirror that explanation's style. "
            "For general facts about the student, use the STUDENT MEMORY above."
        )
        span.set_attribute("outcome", "agentic")
    else:
        try:
            with otel_trace.use_span(span, end_on_exit=False):
                results = await grounding.retrieve(question, top_k=4)  # embed + vector_search child spans
        except Exception as e:  # noqa: BLE001 — retrieval down → decline gracefully, no 500
            print(f"[hermes_chat] retrieval failed: {e}")
            results = []
        best = results[0].score if results else 0.0
        span.set_attribute("top_score", round(best, 3))
        span.set_attribute("n_results", len(results))
        span.set_attribute("in_scope", bool(best >= threshold))

        if best >= threshold:
            # In scope → grounded answer, cite the lectures.
            span.set_attribute("outcome", "grounded")
            sources = [s.model_dump() for s in _build_sources(results)]
            material = grounding.build_material(results)  # shared material block
            system = (
                persona + "\n\n" + memory_block +
                "Answer the student's question using ONLY the course material below and cite "
                "the lecture and timestamp. For questions about the student or what they have "
                "studied before, use the STUDENT MEMORY above and the conversation so far.\n\n"
                "=== COURSE MATERIAL ===\n" + material
            )
        elif allow_general:
            # Out of scope, but the student explicitly authorized a general answer (HITL).
            span.set_attribute("outcome", "general")
            sources = []
            system = (
                persona + "\n\n" + memory_block +
                "The course material does not cover this question, and the student has asked "
                "for a general answer. Begin by noting this is a GENERAL answer (not from the "
                "course), then answer helpfully and accurately from your own knowledge."
            )
        else:
            # Out of scope, no consent yet → decline in code, offer a general answer.
            span.set_attribute("outcome", "declined")
            sources = []
            insufficient_context = True
            offer_general = True
            system = None
            decline_msg = (
                f"That isn't covered in the '{course_slug}' course material. "
                "Would you like me to answer from general knowledge instead?"
            )

    # Context Builder — RESOLVE step: fit the prompt to the window, trimming the
    # OLDEST turns first so nothing is silently truncated. Reports what it dropped.
    history, _fit = context_builder.build(system or "", history, question, _MODEL_CONTEXT_LIMIT)
    span.set_attribute("context.prompt_tokens_est", _fit["prompt_tokens_est"])
    span.set_attribute("context.limit", _fit["limit"])
    span.set_attribute("context.fill_pct", _fit["fill_pct"])
    span.set_attribute("context.dropped_turns", _fit["dropped_turns"])
    span.set_attribute("context.over_limit", _fit["over_limit"])
    if _fit["fill_pct"] >= 80 or _fit["dropped_turns"]:
        print(f"[hermes_chat] context {_fit['fill_pct']}% "
              f"({_fit['prompt_tokens_est']}/{_fit['limit']} tok), dropped {_fit['dropped_turns']} old turn(s)"
              f"{' — essentials OVER limit' if _fit['over_limit'] else ''}")

    # 4. Stream, accumulate the answer, then persist the turn. The reliable tutor
    #    talks to the model DIRECTLY (Hermes's agent loop mangles multi-turn context
    #    on a small model — proven by A/B); agentic mode routes through Hermes.
    #    tutor_client was resolved above (OpenAI in prod, Ollama in dev, Hermes if agentic).

    async def gen():
        try:
            sources_payload = {
                "type": "sources", "sources": sources,
                "insufficient_context": insufficient_context, "offer_general": offer_general,
            }
            yield f"data: {json.dumps(sources_payload)}\n\n"
            answer_parts: list[str] = []
            if decline_msg is not None:
                # Deterministic decline — no model call at all, so grounding is guaranteed.
                for word in decline_msg.split(" "):
                    answer_parts.append(word + " ")
                    yield f"data: {json.dumps({'type': 'token', 'value': word + ' '})}\n\n"
                yield f"data: {json.dumps({'type': 'done'})}\n\n"
            else:
                # llm_generate span as an explicit child of the parent (manual parent
                # context avoids OTel current-context leakage across generator yields).
                gspan = tracer.start_span("llm_generate", context=otel_trace.set_span_in_context(span))
                gspan.set_attribute("provider", tutor_provider)
                try:
                    async for event in tutor_client.stream_chat(question, system=system, history=history):
                        if event.get("type") == "token":
                            answer_parts.append(event.get("value", ""))
                        yield f"data: {json.dumps(event)}\n\n"
                finally:
                    gspan.set_attribute("answer_chars", len("".join(answer_parts)))
                    gspan.end()
            try:
                await memory_service.record_turn(student_id, course_slug, question, "".join(answer_parts))
            except Exception:  # noqa: BLE001 — never fail the response over memory persistence
                pass
        finally:
            span.end()  # close the parent span after the full stream completes

    return StreamingResponse(
        gen(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "Connection": "keep-alive", "X-Accel-Buffering": "no"},
    )


@app.get("/api/hermes/audit")
async def hermes_audit(limit: int = 20):
    """Recent EU-AI-Act audit records — the compliance/inspection view."""
    return await audit_service.recent(limit)


@app.get("/api/hermes/memory/{student_id}")
async def hermes_memory(student_id: str):
    """Transparency: exactly what the tutor remembers about a student."""
    return await memory_service.recall(student_id)


@app.delete("/api/hermes/memory/{student_id}")
async def hermes_memory_erase(student_id: str):
    """GDPR right-to-erasure — delete everything the tutor stored for a student."""
    return await memory_service.erase(student_id)


@app.post("/api/hermes/gepa/run")
async def gepa_run():
    """Run one GEPA evolution round → a human-reviewable proposal. Applies nothing."""
    return await gepa_service.run_round()


@app.post("/api/hermes/gepa/approve")
async def gepa_approve(req: Request):
    """HUMAN gate — apply an approved SOUL evolution (the only path that mutates the SOUL)."""
    body = await req.json()
    return await gepa_service.approve(body.get("proposal_id", ""))


@app.get("/api/hermes/gepa/proposals")
async def gepa_proposals():
    """The evolution history — proposals, their before/after scores, and what was applied."""
    return gepa_service.proposals()


@app.get("/api/hermes/eval/rag-outputs")
async def eval_rag_outputs():
    """The tutor's RAG triples {question, answer, contexts} over the eval set — the input the
    isolated RAGAS harness scores (faithfulness / answer-relevancy / context-precision)."""
    return await eval_service.collect_rag_outputs(gepa_service.read_soul())


@app.get("/api/hermes/eval/history")
async def eval_history(kind: str | None = None, limit: int = 50):
    """The recorded eval / RAGAS / GEPA results over time — the quality trend."""
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
