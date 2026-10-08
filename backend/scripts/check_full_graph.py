"""
End-to-end check of the FULL concept graph, against an in-memory store (never a real database):
seed the demo student with --graph full, then run the real app code on it: skill graph, prerequisites,
adaptive practice (prerequisite gating), weak concepts, and a live Quiz me on the call-stack lecture.

  cd backend && env OPENAI_API_KEY=... .venv/bin/python scripts/check_full_graph.py
"""
import asyncio
import os
import sys
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

for var in ("DATABASE_URL", "FIREBASE_SERVICE_ACCOUNT_JSON", "GOOGLE_APPLICATION_CREDENTIALS",
            "LANGFUSE_HOST", "LANGFUSE_PUBLIC_KEY", "LANGFUSE_SECRET_KEY"):
    os.environ[var] = ""          # in-memory store only
BACKEND = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BACKEND))
sys.path.insert(0, str(BACKEND / "scripts"))

UID = "x94FcfXU7KRrobyOA4UHDukbRoC2"
JS = "javascript-deep-dive"


def line(title):
    print(f"\n=== {title}")


async def main() -> None:
    import seed_demo_account as seed
    from app.services import adaptive_service, journey_service, quick_quiz_service, skill_graph_service
    from app.services.store import InMemoryStore, store
    assert isinstance(store, InMemoryStore), "refusing: not the in-memory store"

    seed.GRAPH = "full"
    docs = seed.build_docs(UID, datetime.now(timezone.utc))
    await seed.write_all(store, docs)
    line("seeded (in memory)")
    concepts = Counter(d["course_id"] for d in docs["concepts"].values())
    print("concepts per course:", dict(concepts))
    print("links:", len(docs["concept_relationships"]), "| bank questions:",
          {s: len(b["questions"]) for s, b in docs["questions"].items()})

    line("skill graph rows for the student (JS Deep Dive)")
    added = await skill_graph_service.ensure_populated(UID, JS)
    rows = [r for r in await store.query("concept_performance", "user_id", UID)]
    print(f"backfilled {added} 'not tried' rows; {len(rows)} rows total; tried: "
          f"{sorted((r['concept'], round(r['accuracy'] * 100)) for r in rows if r['attempts'])}")

    line("prerequisites as the tutor sees them")
    for c in ("event-loop", "microtask-queue", "closure"):
        v = await skill_graph_service.get_prerequisite_view(UID, JS, c)
        print(f"  {c}: target={v.get('target', {}).get('confidence')} prereqs="
              f"{[(p['concept'], p.get('confidence')) for p in v.get('prerequisites', [])]}")

    line("weak concepts the tutor gets on every answer (JS)")
    print(" ", await journey_service.weak_concepts_for_course(UID, JS))

    line("adaptive practice: 8 answers, all wrong then right, JS")
    s = await adaptive_service.start(UID, JS)
    sid = s.get("session_id")
    seq = []
    for i in range(8):
        q = s.get("question") or {}
        if not q:
            print("  stopped:", s.get("status")); break
        seq.append((q.get("concept"), q.get("difficulty")))
        s = await adaptive_service.answer(sid, q["id"], i >= 4, q["concept"], 1000)
    print("  served (concept, difficulty):", seq)

    line("Quiz me on '1.3 - Execution Contexts and the Call Stack' (live model)")
    from app.services import catalog_service
    course = catalog_service.by_slug(JS)
    quiz = await quick_quiz_service.create(UID, course, "1.3 - Execution Contexts and the Call Stack", None)
    stored = await store.get("quick_quizzes", quiz["quiz_id"])
    print("  tagged concepts:", [q.get("concept") for q in stored["questions"]])
    result, fresh = await quick_quiz_service.submit(UID, quiz["quiz_id"], [q["correctIndex"] for q in stored["questions"]])
    await quick_quiz_service.record(UID, quiz["quiz_id"])
    after = {r["concept"]: (r["correct"], r["attempts"]) for r in await store.query("concept_performance", "user_id", UID)}
    print(f"  score {result['score']}/{result['total']}; concept rows now:",
          {c: after.get(c) for c in {q.get('concept') for q in stored['questions']}})
    new_nodes = [d for d in await store.list_all("concepts") if d.get("created_by") == "student_content"]
    print("  concepts created outside the graph:", [d["name"] for d in new_nodes] or "none")

    line("tutor (live): a student struggling with the microtask queue")
    import textwrap
    from app.services import chat_pipeline
    from app.services.course_lookup import ChatScope
    q = "I keep getting the microtask queue wrong. What should I work on first?"
    req = chat_pipeline.TurnRequest(question=q, student_id=UID, history=[], memory_slug=JS,
                                    scope=ChatScope(course_slug=JS, lecture_title="6.1 - The Event Loop and Microtasks",
                                                    in_player=True, position=30.0))
    out = [e["value"] async for e in chat_pipeline.chat_turn(req) if e.get("type") == "token"]
    print(textwrap.fill("".join(out)[:900], 110))


if __name__ == "__main__":
    asyncio.run(main())
