"""
Does the app actually USE the concept graph? Seeds an in-memory store with the demo or the full graph, then
asks the live tutor real questions and logs every graph/score lookup it makes, plus practice for two students.

  cd backend && env OPENAI_API_KEY=... .venv/bin/python scripts/probe_full_graph.py full|demo
"""
import asyncio
import os
import sys
import textwrap
from datetime import datetime, timezone
from pathlib import Path

for var in ("DATABASE_URL", "FIREBASE_SERVICE_ACCOUNT_JSON", "GOOGLE_APPLICATION_CREDENTIALS",
            "LANGFUSE_HOST", "LANGFUSE_PUBLIC_KEY", "LANGFUSE_SECRET_KEY"):
    os.environ[var] = ""
BACKEND = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BACKEND))
sys.path.insert(0, str(BACKEND / "scripts"))

UID = "x94FcfXU7KRrobyOA4UHDukbRoC2"
JS, LIB = "javascript-deep-dive", "custom-library"
LOOKUPS: list[str] = []

QUESTIONS = [
    (JS, "What should I learn before closures?"),
    (JS, "What does the event loop depend on? What should I know first?"),
    (JS, "What am I weak at in this course, and what should I practise next?"),
    (JS, "How confident am I with the call stack?"),
    (JS, "Which topics in this course haven't I practised yet?"),
    (LIB, "What should I understand before npm link?"),
]


def _log(name, fn):
    async def wrapped(*a, **k):
        out = await fn(*a, **k)
        LOOKUPS.append(f"{name}({', '.join(str(x) for x in a[1:])})")
        return out
    return wrapped


async def main(graph: str) -> None:
    import seed_demo_account as seed
    from app.services import (adaptive_service, chat_pipeline, journey_service, knowledge_graph_service,
                              skill_graph_service)
    from app.services.course_lookup import ChatScope
    from app.services.store import InMemoryStore, store
    assert isinstance(store, InMemoryStore)
    seed.GRAPH = graph
    await seed.write_all(store, seed.build_docs(UID, datetime.now(timezone.utc)))
    from app.services import enrollment_service     # the seed never writes enrollments; prod has these 4
    for cid, title in ((11, "React Performance Patterns"), (9, "JavaScript Deep Dive"),
                       (10, "Web APIs and Real-Time"), (2, "Build a Custom Library")):
        await enrollment_service.enroll(UID, cid, title)

    for mod, names in ((skill_graph_service, ("get_prerequisite_view",)),
                       (journey_service, ("get_strengths_weaknesses", "get_progress", "weak_concepts_for_course")),
                       (knowledge_graph_service, ("get_graph",))):
        for n in names:
            setattr(mod, n, _log(n, getattr(mod, n)))

    print(f"######## GRAPH = {graph}")
    for slug, q in QUESTIONS:
        LOOKUPS.clear()
        req = chat_pipeline.TurnRequest(question=q, student_id=UID, history=[], memory_slug=slug,
                                        scope=ChatScope(course_slug=slug, in_player=True))
        out = [e["value"] async for e in chat_pipeline.chat_turn(req) if e.get("type") == "token"]
        print(f"\nQ [{slug}]: {q}\n   lookups: {LOOKUPS or 'none'}")
        print(textwrap.indent(textwrap.fill("".join(out)[:600], 105), "   "))

    print("\n--- practice: first 6 concepts served")
    for who, setup in (("brand-new student", {}),
                       ("event loop solid, microtask weak", {"event-loop": (9, 10), "call-stack": (8, 10),
                                                              "execution-context": (8, 10), "microtask-queue": (2, 10)})):
        uid = "probe-" + who.replace(" ", "-").replace(",", "")
        for c, (ok, n) in setup.items():
            await store.set("concept_performance", f"{uid}__{c}",
                            {"user_id": uid, "concept": c, "attempts": n, "correct": ok, "accuracy": ok / n})
        s = await adaptive_service.start(uid, JS)
        sid, seq = s.get("session_id"), []
        for _ in range(6):
            q = s.get("question")
            if not q:
                break
            seq.append(q["concept"])
            s = await adaptive_service.answer(sid, q["id"], True, q["concept"], 1000)
        print(f"   {who}: {seq}")


if __name__ == "__main__":
    asyncio.run(main(sys.argv[1] if len(sys.argv) > 1 else "full"))
