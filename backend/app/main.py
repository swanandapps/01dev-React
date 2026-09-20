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
from fastapi import Depends, FastAPI, Header, HTTPException, Request
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
    hermes_client, audit_service, memory_service,
    eval_service, gepa_service, context_builder, pii, llm,
    skill_graph_service,
)
from app.services.otel import get_tracer, init_tracing
from app.routing.intent import Intent, classify
from app.routing.quiz_handoff import build_handoff_message
from app.routing.progress_handoff import build_progress_message

# _TUTOR_PROVIDER only feeds /health's status field now — the chat endpoint always
# routes through Hermes (see hermes_chat's docstring for why the old direct-to-OpenAI
# path was retired).
_TUTOR_PROVIDER = os.getenv("TUTOR_PROVIDER", "openai" if os.getenv("OPENAI_API_KEY") else "ollama")
_MODEL_CONTEXT_LIMIT = int(os.getenv("MODEL_CONTEXT_LIMIT", "8192"))

RZP_KEY_ID = os.environ.get("RAZORPAY_KEY_ID", "")
RZP_KEY_SECRET = os.environ.get("RAZORPAY_KEY_SECRET", "")

# Admin/audit/compliance routes (audit log, memory transparency+erase, GEPA
# run/approve, eval history) have no per-user auth model yet — gate them
# with a shared secret instead of leaving them open on a public URL.
# Unset locally on purpose (dev convenience); Railway sets a real value.
_ADMIN_API_KEY = os.getenv("ADMIN_API_KEY", "")


async def require_admin_key(x_admin_key: str = Header(default="")) -> None:
    if not _ADMIN_API_KEY:
        return  # no key configured (local dev) — leave routes open, same as today
    if x_admin_key != _ADMIN_API_KEY:
        raise HTTPException(status_code=401, detail="Missing or invalid X-Admin-Key")


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
    session-spanning memory + streaming proxy to the Hermes agent (:8642).

    Every question that isn't one of the two fixed-answer intents (quiz hand-off,
    progress lookup) goes to Hermes. Hermes drives its own retrieval via the
    search_course_content/search_history MCP tools and decides for itself how many
    tool calls a question needs — that decision used to be made here (a client-supplied
    `agentic` flag, plus a backend similarity-score threshold deciding whether to
    answer or decline) when Hermes ran on a local model too slow/unreliable for
    real-time chat. Hermes now runs on the same OpenAI model either way, so that
    split no longer has a reason to exist; SOUL.md's own "don't answer outside the
    course material" instruction is the guardrail now, not a backend score check.

    Either way the tutor REMEMBERS the student: prior turns are threaded (multi-turn)
    and a running profile is injected, then this exchange is persisted for next time.
    """
    body = await req.json()
    question = (body.get("question") or "").strip()
    student_id = body.get("user_id") or req.headers.get("X-Student-Id") or ""
    course_slug = body.get("course_slug") or req.headers.get("X-Course-Slug") or "js-fundamentals"

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

    # Every remaining intent goes to Hermes — see the docstring for why there's no
    # longer a separate direct-to-OpenAI path here.

    # Back-fill the skill graph only for intents that actually touch it
    # (COURSE_QUESTION/fallthrough) — QUIZ_GENERATE/PROGRESS_LOOKUP already
    # returned above and never reach here. Runs inside the traced span (4
    # sequential DB queries in steady state) so its latency shows up if chat
    # latency regresses, instead of being invisible before the span started.
    try:
        created = await skill_graph_service.ensure_populated(student_id, course_slug)
        span.set_attribute("skill_graph.backfilled_concepts", created)
    except Exception as e:  # noqa: BLE001 — back-fill is never allowed to break a chat turn
        print(f"[hermes_chat] ensure_populated failed for {student_id}/{course_slug}: {e}")

    tutor_client = hermes_client
    tutor_model, tutor_provider = os.getenv("HERMES_MODEL_LABEL", "gpt-4.1-mini"), "hermes (agent loop)"
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
    # SOUL.md's own "Avoid" section carries the "don't answer outside the course
    # material" guardrail; Hermes enforces that itself now, not a backend score check.
    #
    # "all-courses" is a frontend sentinel (the global Ask page has no course
    # selector) meaning "no specific course chosen" — NOT a real course name.
    # Interpolating it into "You are tutoring the 'all-courses' course" was
    # confusing the model into treating it as an actual enrolled course (it
    # answered "you're enrolled in the course called all-courses" when asked).
    # Also: this backend has no enrollment data source at all (enrollment
    # currently only lives in Firestore, unread here) — the model should
    # decline enrollment questions honestly, not guess.
    if course_slug == "all-courses":
        persona = gepa_service.read_soul() + (
            "\nYou help students with ANY course on the01.dev — you are not scoped to a "
            "single course in this conversation. Use search_course_content freely across "
            "all courses and mention which course an answer came from. If asked what "
            "courses the student is enrolled in, say plainly that you don't have access "
            "to enrollment records — do not guess or invent a course name."
        )
    else:
        persona = gepa_service.read_soul() + f"\nYou are tutoring the '{course_slug}' course on the01.dev. "
    # NOTE: this deliberately puts the raw student_id (currently the student's
    # actual email) in the LLM-bound prompt, verbatim, OUTSIDE the pii.scrub()
    # choke point above ("no student PII reaches any downstream surface" per
    # that comment — this line is the one exception). Accepted for now because
    # this is a single known user and the only downstream party is the LLM
    # provider itself, not a third party beyond it. Revisit before multi-tenant.
    persona += (
        f"\nFor any tool that takes student_id or course_id, use exactly "
        f"student_id=\"{student_id}\" and course_id=\"{course_slug}\" — never guess or ask the "
        f"student for these, you already have them."
    )
    # Memory goes up front (prominent) so it isn't overridden by the tool-use rule below.
    memory_block = (mem + "\n\n") if mem else ""

    # No structured source list here — Hermes cites lectures inline in its answer
    # text (verified: "React Performance Patterns, lecture 4.1 at 01:13"), but the
    # actual retrieval happens inside its own tool call, not in this backend, so
    # there's nothing to build a citations array FROM at this layer anymore.
    sources: list[dict] = []
    system = (
        persona + "\n\n" + memory_block +
        "Use the search_course_content tool to find relevant course material, then "
        "answer grounded in what it returns and cite the lecture. "
        "When the student refers to how you previously taught them something "
        "(e.g. 'like you taught me closures'), call the search_history tool to "
        "retrieve those past exchanges and mirror that explanation's style. "
        "For general facts about the student, use the STUDENT MEMORY above."
    )
    span.set_attribute("outcome", "hermes")

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

    # 4. Stream, accumulate the answer, then persist the turn.

    async def gen():
        try:
            sources_payload = {
                "type": "sources", "sources": sources,
                "insufficient_context": False, "offer_general": False,
            }
            yield f"data: {json.dumps(sources_payload)}\n\n"
            answer_parts: list[str] = []
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


@app.post("/api/hermes/gepa/run", dependencies=[Depends(require_admin_key)])
async def gepa_run():
    """Run one GEPA evolution round → a human-reviewable proposal. Applies nothing."""
    return await gepa_service.run_round()


@app.post("/api/hermes/gepa/approve", dependencies=[Depends(require_admin_key)])
async def gepa_approve(req: Request):
    """HUMAN gate — apply an approved SOUL evolution (the only path that mutates the SOUL)."""
    body = await req.json()
    return await gepa_service.approve(body.get("proposal_id", ""))


@app.get("/api/hermes/gepa/proposals", dependencies=[Depends(require_admin_key)])
async def gepa_proposals():
    """The evolution history — proposals, their before/after scores, and what was applied."""
    return gepa_service.proposals()


@app.get("/api/hermes/eval/rag-outputs", dependencies=[Depends(require_admin_key)])
async def eval_rag_outputs():
    """The tutor's RAG triples {question, answer, contexts} over the eval set — the input the
    isolated RAGAS harness scores (faithfulness / answer-relevancy / context-precision)."""
    return await eval_service.collect_rag_outputs(gepa_service.read_soul())


@app.get("/api/hermes/eval/history", dependencies=[Depends(require_admin_key)])
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
