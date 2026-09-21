"""
One-off seed: populates real progress/mastery/memory data for the operator's
own account so the demo has something real to query — grounded ONLY in the
actual seed transcript content (backend/app/data/seed_transcripts.json),
never invented facts, so nothing the tutor later says about this history is
fabricated.

Firestore enrollment (PrevCourses) is handled separately via the REST API +
gcloud access token, not here — this script only touches Postgres.

Two real Firebase accounts exist for the operator (swanandkadam828@gmail.com
and beingswanand@gmail.com) — seeded both since it wasn't clear which one a
given browser session is actually signed in as, and re-running is idempotent.

Run: backend/.venv/bin/python scripts/seed_demo_account.py <student_id>
"""
import asyncio
import sys
from datetime import datetime, timedelta, timezone

from dotenv import load_dotenv
load_dotenv()

from app.services.store import store  # noqa: E402

STUDENT_ID = sys.argv[1] if len(sys.argv) > 1 else "x94FcfXU7KRrobyOA4UHDukbRoC2"


def _iso(days_ago: float) -> str:
    return (datetime.now(timezone.utc) - timedelta(days=days_ago)).isoformat()


# ── React Performance Patterns — COMPLETE ──────────────────────────────────
REACT_PERF = "react-perf"
REACT_PERF_TITLE = "React Performance Patterns"
REACT_PERF_CONCEPTS = [
    {"name": "shallow-equality", "description": "Primitives compare by value; objects, arrays, and functions compare by reference."},
    {"name": "use-callback", "description": "useCallback keeps a function reference stable across renders as long as its dependencies don't change."},
    {"name": "use-memo", "description": "useMemo memoizes a computed value and only recomputes it when its dependencies change."},
    {"name": "react-memo", "description": "React.memo skips a component's re-render when its props are shallowly equal to the previous render."},
]
REACT_PERF_RELS = [
    ("shallow-equality", "react-memo", "prerequisite_of"),
    ("use-callback", "react-memo", "prerequisite_of"),
    ("use-memo", "use-callback", "related_to"),
]
# (concept, attempts, correct, days_ago last_seen) — mastered, history spread over ~3 weeks
REACT_PERF_PERF = [
    ("shallow-equality", 6, 5, 6),
    ("use-callback", 7, 6, 5),
    ("use-memo", 8, 7, 5),
    ("react-memo", 9, 8, 4),
]
REACT_PERF_TURNS = [
    (21, "Why does my component still re-render even though I wrapped it in React.memo?",
     "React.memo only skips a re-render when props are shallowly equal to the previous render. "
     "If a parent passes a new function or object literal as a prop on every render, React.memo "
     "sees a new reference and re-renders anyway — wrap that callback in useCallback so the "
     "reference stays stable. (React Performance Patterns, 4.1 - React.memo and useCallback)"),
    (14, "What's the difference between useMemo and useCallback?",
     "useMemo memoizes a computed value; useCallback memoizes the function reference itself. "
     "You reach for useCallback specifically when passing a callback into a child wrapped in "
     "React.memo, so the child doesn't see a new reference every render. "
     "(3.2 - Memoization and Computed State)"),
    (5, "When should I use useMemo for a filtered list?",
     "If a filtered/sorted list is derived from a large array and the filter criteria haven't "
     "changed since the last render, useMemo avoids redoing that work. "
     "(3.2 - Memoization and Computed State)"),
]

# ── JavaScript Deep Dive — IN PROGRESS ─────────────────────────────────────
JS_DEEP = "javascript-deep-dive"
JS_DEEP_TITLE = "JavaScript Deep Dive"
JS_DEEP_CONCEPTS = [
    {"name": "prototype-inheritance", "description": "Every object has an internal link to another object, its prototype, and property lookups walk that chain."},
    {"name": "class-syntax-sugar", "description": "The `class` keyword is syntactic sugar over the same prototype chain — Dog.prototype gets Animal.prototype as its prototype."},
    {"name": "v8-hidden-classes", "description": "V8 creates an internal hidden class describing an object's shape; adding properties in a different order produces a different hidden class."},
    {"name": "event-loop", "description": "A single call stack plus a macrotask queue (setTimeout, etc.) — the next macrotask runs once the stack empties."},
    {"name": "microtask-queue", "description": "Promises resolve into a separate, higher-priority microtask queue that fully drains before the next macrotask runs."},
]
JS_DEEP_RELS = [
    ("prototype-inheritance", "class-syntax-sugar", "prerequisite_of"),
    ("event-loop", "microtask-queue", "prerequisite_of"),
    ("v8-hidden-classes", "prototype-inheritance", "related_to"),
]
# Deliberately mixed + incomplete — mid-course, real gaps for the demo to surface
JS_DEEP_PERF = [
    ("prototype-inheritance", 6, 5, 0.3),   # strong, active today
    ("class-syntax-sugar", 4, 2, 0.4),      # weak, active today — despite a strong prerequisite
    ("event-loop", 5, 2, 1.2),              # weak, active yesterday
    # v8-hidden-classes, microtask-queue: not attempted yet — no row (accuracy reads as null)
]
JS_DEEP_TURNS = [
    (1.3, "How does the event loop decide what runs next?",
     "JS has a call stack plus a macrotask queue for things like setTimeout callbacks — once "
     "the stack empties, the next macrotask runs. (6.1 - The Event Loop and Microtasks)"),
    (0.5, "Why does my Promise .then() run before my setTimeout even though the timeout was 0ms?",
     "Promises resolve into the microtask queue, which fully drains after every task and before "
     "the next macrotask — so a resolved promise's .then always beats a setTimeout(fn, 0). "
     "(6.1 - The Event Loop and Microtasks)"),
    (0.2, "What even is prototype inheritance in JS?",
     "Every object has an internal link to another object, its prototype. A property lookup that "
     "misses on the object walks up this chain until it hits Object.prototype. "
     "(4.1 - Prototype Inheritance)"),
]

QUIZ_SESSIONS = [
    # (course_id, course_title, days_ago, breakdown[(concept, attempts, correct)])
    (REACT_PERF, REACT_PERF_TITLE, 14, [
        ("shallow-equality", 3, 2), ("use-callback", 3, 3), ("use-memo", 3, 2), ("react-memo", 3, 3),
    ]),
    (REACT_PERF, REACT_PERF_TITLE, 4, [
        ("shallow-equality", 3, 3), ("use-callback", 4, 3), ("use-memo", 5, 5), ("react-memo", 6, 5),
    ]),
    (JS_DEEP, JS_DEEP_TITLE, 1.2, [
        ("prototype-inheritance", 6, 5), ("class-syntax-sugar", 4, 2), ("event-loop", 5, 2),
    ]),
]


async def seed_knowledge_graph(course_id: str, concepts: list[dict], rels: list[tuple]) -> None:
    for c in concepts:
        doc_id = f"{course_id}::{c['name']}"
        await store.set("concepts", doc_id, {"course_id": course_id, **c})
    for source, target, rel_type in rels:
        doc_id = f"{course_id}::{source}->{target}"
        await store.set("concept_relationships", doc_id, {
            "course_id": course_id, "source": source, "target": target, "type": rel_type,
        })
    print(f"  concepts + relationships seeded for {course_id}")


async def seed_perf_by_days(rows: list[tuple]) -> None:
    for concept, attempts, correct, days_ago in rows:
        doc_id = f"{STUDENT_ID}__{concept}"
        await store.set("concept_performance", doc_id, {
            "user_id": STUDENT_ID, "concept": concept,
            "attempts": attempts, "correct": correct,
            "accuracy": round(correct / attempts, 3),
            "last_seen": _iso(days_ago),
        })
    print(f"  concept_performance seeded ({len(rows)} concepts)")


async def seed_turns(course_slug: str, turns: list[tuple]) -> None:
    topics: list[str] = []
    first_seen = None
    last_seen = None
    for days_ago, question, answer in turns:
        ts = _iso(days_ago)
        if first_seen is None or ts < first_seen:
            first_seen = ts
        if last_seen is None or ts > last_seen:
            last_seen = ts
        await store.set("student_turns", f"{STUDENT_ID}__{ts}", {
            "student_id": STUDENT_ID, "course_slug": course_slug,
            "question": question[:500], "answer": answer[:1500],
            "created_at": ts, "pii_redacted": [],
        })
        topics.append(question[:80])

    prof = await store.get("student_profile", STUDENT_ID) or {"first_seen": first_seen, "turn_count": 0, "topics": []}
    merged_topics = (prof.get("topics", []) + topics)[-8:]
    await store.set("student_profile", STUDENT_ID, {
        "student_id": STUDENT_ID,
        "first_seen": min(prof.get("first_seen", first_seen), first_seen),
        "last_seen": max(prof.get("last_seen", last_seen), last_seen),
        "turn_count": int(prof.get("turn_count", 0)) + len(turns),
        "topics": merged_topics,
    })
    print(f"  {len(turns)} memory turns seeded for {course_slug}")


async def seed_quiz_sessions() -> None:
    for i, (course_id, course_title, days_ago, breakdown_raw) in enumerate(QUIZ_SESSIONS):
        session_id = f"seed-{course_id}-{i}"
        breakdown = [
            {"concept": c, "attempts": a, "correct": k, "accuracy": round(k / a, 3)}
            for c, a, k in breakdown_raw
        ]
        breakdown.sort(key=lambda b: b["accuracy"])
        answers = []
        for c, a, k in breakdown_raw:
            for n in range(a):
                answers.append({
                    "question_id": f"{session_id}-{c}-{n}", "concept": c, "difficulty": "",
                    "correct": n < k, "time_taken_ms": 8000 + n * 500, "lecture": "",
                })
        score = sum(1 for x in answers if x["correct"])
        await store.set("quiz_sessions", session_id, {
            "session_id": session_id, "user_id": STUDENT_ID, "course_id": course_id,
            "course_title": course_title, "score": score, "total": len(answers),
            "answers": answers, "concept_breakdown": breakdown,
            "completed_at": _iso(days_ago),
        })
    print(f"  {len(QUIZ_SESSIONS)} quiz_sessions seeded")


async def main():
    print(f"Seeding demo data for student_id={STUDENT_ID}")

    print(f"\n[{REACT_PERF}] complete course")
    await seed_knowledge_graph(REACT_PERF, REACT_PERF_CONCEPTS, REACT_PERF_RELS)
    await seed_perf_by_days(REACT_PERF_PERF)
    await seed_turns(REACT_PERF, REACT_PERF_TURNS)

    print(f"\n[{JS_DEEP}] in-progress course")
    await seed_knowledge_graph(JS_DEEP, JS_DEEP_CONCEPTS, JS_DEEP_RELS)
    await seed_perf_by_days([(c, a, k, d) for c, a, k, d in JS_DEEP_PERF])
    await seed_turns(JS_DEEP, JS_DEEP_TURNS)

    print("\n[quiz_sessions]")
    await seed_quiz_sessions()

    print("\nDone.")


if __name__ == "__main__":
    asyncio.run(main())
