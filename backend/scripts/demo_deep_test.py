"""
Deep pre-deploy test of the full concept graph on a COPY of production data (a read-only snapshot loaded into
the in-memory store; nothing is written to a real database):

1. data consistency: the student's numbers (progress, strengths, weak concepts, Lab topics) are identical before
   and after the graph load; the new graph is internally consistent (bank tags, link ends, no prerequisite loops);
   every concept the student has a score on still exists.
2. demo questions through the real tutor (live model), logging every graph/score lookup it makes.
3. practice + a live Quiz me on the full graph.

  cd backend && env OPENAI_API_KEY=... .venv/bin/python scripts/demo_deep_test.py SNAPSHOT.json
"""
import asyncio
import json
import os
import sys
import textwrap
from collections import defaultdict
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
PROBLEMS: list[str] = []

DEMO = [  # (where, course, lecture, question)
    ("Ask", None, None, "How am I doing overall?"),
    ("Ask", None, None, "What am I weak at, and what should I work on next?"),
    ("Player", JS, "6.1 - The Event Loop and Microtasks", "How am I doing in this course?"),
    ("Player", JS, "6.1 - The Event Loop and Microtasks", "How confident am I with the event loop?"),
    ("Player", JS, "6.1 - The Event Loop and Microtasks", "What should I learn before the microtask queue?"),
    ("Player", JS, "6.1 - The Event Loop and Microtasks", "Which topics in this course haven't I practised yet?"),
    ("Player", JS, "6.1 - The Event Loop and Microtasks", "What should I practise next?"),
    ("Player", JS, "2.3 - Closures: Functions That Remember Their Scope", "Am I ready for closures? What do they build on?"),
    ("Player", LIB, None, "How am I doing with npm link?"),
]


def check(ok: bool, what: str) -> None:
    print(("   OK   " if ok else "   FAIL ") + what)
    if not ok:
        PROBLEMS.append(what)


async def numbers(uid: str) -> dict:
    from app.services import journey_service, lab_topics
    out = {"progress_all": await journey_service.get_progress(uid),
           "progress_js": await journey_service.get_progress(uid, JS),
           "strengths": await journey_service.get_strengths_weaknesses(uid)}
    for slug in (JS, LIB, "react-perf", "web-apis"):
        out[f"weak_{slug}"] = await journey_service.weak_concepts_for_course(uid, slug)
    out["lab_topics"] = await lab_topics.topics(uid)
    return json.loads(json.dumps(out, default=str))


async def main(snapshot: Path) -> None:
    from app.services import (adaptive_service, catalog_service, chat_pipeline, journey_service,
                              knowledge_graph_service, quick_quiz_service, skill_graph_service)
    from app.services.course_lookup import ChatScope
    from app.services.store import InMemoryStore, store
    from load_full_graph import apply_to_store, build_docs
    assert isinstance(store, InMemoryStore), "refusing: not the in-memory store"

    for d in json.loads(snapshot.read_text()):
        await store.set(d["collection"], d["doc_id"], d["data"])
    print("loaded snapshot of production into memory")

    print("\n=== 1. data consistency")
    before = await numbers(UID)
    counts = await apply_to_store(store, build_docs())
    print("   graph load:", counts)
    after = await numbers(UID)
    for k in before:
        check(before[k] == after[k], f"unchanged by the graph load: {k}")
    concepts = defaultdict(set)
    for _, d in await store.list_all_with_ids("concepts"):
        if d.get("course_id"):
            concepts[d["course_id"]].add(d["name"])
    for _, b in await store.list_all_with_ids("questions"):
        bad = {q["concept"] for q in b["questions"]} - concepts[b["course_id"]]
        check(not bad, f"bank {b['course_id']}: every question's concept is in the graph {sorted(bad) or ''}")
    rels = [d for _, d in await store.list_all_with_ids("concept_relationships")]
    dangling = [r for r in rels if r["source"] not in concepts[r["course_id"]] or r["target"] not in concepts[r["course_id"]]]
    check(not dangling, f"all {len(rels)} links join existing concepts")
    prereq = defaultdict(set)
    for r in rels:
        if r["type"] == "prerequisite_of":
            prereq[(r["course_id"], r["source"])].add(r["target"])

    def cyclic(node, seen):
        return any(n in seen or cyclic(n, seen | {n}) for n in {(node[0], t) for t in prereq.get(node, ())})
    check(not any(cyclic(k, {k}) for k in list(prereq)), "no prerequisite loops")
    scored = {p["concept"] for p in await store.query("concept_performance", "user_id", UID) if p.get("attempts")}
    all_names = set().union(*concepts.values())
    check(scored <= all_names, f"every concept the student has a score on is in the graph {sorted(scored - all_names) or ''}")

    for mod, names in ((skill_graph_service, ("get_prerequisite_view",)),
                       (journey_service, ("get_strengths_report", "get_progress", "weak_concepts_for_course"))):
        for n in names:
            fn = getattr(mod, n)

            def wrap(fn=fn, n=n):
                async def w(*a, **k):
                    LOOKUPS.append(f"{n}({', '.join(str(x) for x in a[1:])}{', ' + str(k) if k else ''})")
                    return await fn(*a, **k)
                return w
            setattr(mod, n, wrap())

    print("\n=== 2. demo questions (live tutor)")
    prefs = (await store.get("student_profile", UID) or {}).get("learning_preferences")
    print("   saved learning preference:", repr(prefs))
    for where, slug, lecture, q in DEMO:
        LOOKUPS.clear()
        scope = (ChatScope(course_slug=slug, lecture_title=lecture, in_player=True, position=120.0)
                 if where == "Player" else ChatScope(course_slug=None))
        req = chat_pipeline.TurnRequest(question=q, student_id=UID, history=[], scope=scope,
                                        memory_slug=slug or "all-courses")
        out = [e["value"] async for e in chat_pipeline.chat_turn(req) if e.get("type") == "token"]
        print(f"\n [{where}{' ' + slug if slug else ''}] {q}\n   lookups: {LOOKUPS or 'none'}")
        print(textwrap.indent(textwrap.fill("".join(out)[:700], 108), "   "))

    print("\n=== 3. practice and Quiz me on the full graph")
    s = await adaptive_service.start(UID, JS)
    sid, served = s.get("session_id"), []
    for i in range(6):
        q = s.get("question")
        if not q:
            break
        served.append(f"{q['concept']}/{q['difficulty']}")
        s = await adaptive_service.answer(sid, q["id"], i % 2 == 1, q["concept"], 1000)
    print("   practice served:", served)
    course = catalog_service.by_slug(JS)
    quiz = await quick_quiz_service.create(UID, course, "1.3 - Execution Contexts and the Call Stack", None)
    stored = await store.get("quick_quizzes", quiz["quiz_id"])
    tags = [q.get("concept") for q in stored["questions"]]
    check(set(tags) <= concepts[JS], f"Quiz me tags are graph concepts: {tags}")
    await quick_quiz_service.submit(UID, quiz["quiz_id"], [q["correctIndex"] for q in stored["questions"]])
    await quick_quiz_service.record(UID, quiz["quiz_id"])
    v = await skill_graph_service.get_prerequisite_view(UID, JS, "event-loop")
    print("   event-loop prerequisites after the quiz:", [(p["concept"], p.get("attempted"), p.get("accuracy")) for p in v["prerequisites"]])

    print(f"\n=== RESULT: {len(PROBLEMS)} problem(s)" + "".join(f"\n   - {p}" for p in PROBLEMS))


if __name__ == "__main__":
    asyncio.run(main(Path(sys.argv[1])))
