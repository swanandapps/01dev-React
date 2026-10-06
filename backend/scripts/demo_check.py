"""Run before every demo: fixed questions through course_lookup (and optionally the
full tutor) for one student, printing case, top hits, answers and first-token latency.

LOCAL ONLY — run from backend/ with a blank DATABASE_URL so the in-memory store is
used and production data is never read or written:

  env DATABASE_URL= .venv/bin/python scripts/demo_check.py [student_id] [--enroll 9,11] [--full]

  --enroll 9,11  seed enrollments (catalog course ids) for the student first. 9,11
                 simulates the demo account: JavaScript Deep Dive + React Performance
                 Patterns, neither launched — and turns on the expected-case checks.
                 Ask policy (F1): only launched AND enrolled courses are cited, so with
                 9,11 every question is NO_MATCH. --enroll 2 (Build a Custom Library,
                 the one launched course) is the other checked set: npm questions are
                 ENROLLED_MATCH with a deep link. Under --full the answer is also
                 checked: no course the student can't cite is named, and a course-2
                 answer carries the01.dev/course/2?chapter=..&sub=..&t=.. verbatim.
  --full         also run each question through the full tutor (real OpenAI key from
                 backend/.env) and print the answer (long ones cut to head … tail) and first-token latency.
  --player       instead of the Ask questions, run in-player tutor turns on Build a Custom
                 Library (real model, twice each): course-first answers, find_moment ->
                 navigate, no other course named. Records lookup case, hits, find_moment
                 calls, navigate, first-token latency and the full answer.
  --whole        with --full, print whole answers, uncut.

With --full every question runs as a fresh student ("<uid>-q1", "<uid>-q2", …, each
given the same --enroll), so no answer sees memory of an earlier question's turn.

--full and --enroll exit 2 unless the in-memory store is active. Lookup-only (no
flags) may run anywhere, but it is not strictly read-only: against a production
DATABASE_URL, retrieval may upsert missing chunk embeddings into rag_chunks
(idempotent — the same rows the app itself would write). Exits 1 if any expected
case doesn't match or, under --full, any turn ends in an error event.
"""
import asyncio
import re
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from dotenv import load_dotenv  # noqa: E402

load_dotenv(Path(__file__).resolve().parents[1] / ".env")

from app.services import catalog_service, chat_pipeline, enrollment_service  # noqa: E402
from app.services.course_lookup import ChatScope, LookupCase, course_lookup  # noqa: E402
from app.services.store import InMemoryStore, store  # noqa: E402

DEMO_UID = "x94FcfXU7KRrobyOA4UHDukbRoC2"
DEMO_ENROLL = [9, 11]
E, X = LookupCase.ENROLLED_MATCH, LookupCase.NO_MATCH
QUESTIONS = [
    # (question, scope, expected case with --enroll 9,11, expected case with --enroll 2; None = printed only)
    ("how do I publish an npm library", ChatScope(), X, E),
    ("does React.memo need useCallback", ChatScope(), X, None),
    ("explain the event loop and microtasks", ChatScope(), X, None),
    ("how do I write a lexer for my own language", ChatScope(), X, None),
    ("how do I bake sourdough bread", ChatScope(), X, X),
    ("what am I weak at?", ChatScope(), None, None),
    ("what does this mean?", ChatScope("react-perf", "4.1 - React.memo and useCallback"), None, None),
    # probes: where do Build a Custom Library topics land?
    ("how does npm link work", ChatScope(), X, E),
    ("what is an IIFE", ChatScope(), None, None),
    ("how do I hack the prototype to add a method", ChatScope(), X, None),
    ("what are ES modules", ChatScope(), X, None),
]


PLAYER_COURSE = "custom-library"
L11, L81, L11P, L101 = ("1.1 - What is this course", "8.1 - The `npm link` command",
                        "11.1 - Publishing using `np`", "10.1 - What Are ES Modules")
# (id, question, lecture on screen, expected navigate target or None = must not navigate)
PLAYER_QUESTIONS = [
    ("B1", "take me to where you publish the npm package", L11, L11P),
    ("B2", "how does the event loop work", L81, None),
    ("B3", "give me an example", L11, None),
    ("1", "take me to the part where you write the commands for publishing the npm library", L11, L11P),
    ("2", "how does the event loop work?", L81, None),
    ("3", "what are ES modules?", L81, None),
    ("4", "take me to ES modules", L81, L101),
    ("5", "explain React reconciliation", L81, None),
    ("6", "give me an example", L11, None),
    ("7", "what does np do that npm publish doesn't?", L11P, None),
]


async def player_checks(uid: str) -> int:
    from app.services import tutor_agent
    from app.services.vector_store import vector_store
    others = [c["title"] for c in catalog_service.all_courses() if c["slug"] != PLAYER_COURSE]
    calls: list[dict] = []
    orig = tutor_agent._locate_moment

    async def spy(what, slug):
        r = await orig(what, slug)
        calls.append({"what": what, "result": None if r is None else
                      {"lecture": r[0].lecture_title, "start": r[0].start_time, "score": round(r[1], 3)}})
        return r
    tutor_agent._locate_moment = spy
    failures = 0
    only = (_arg("--case") or "").split(",") if _arg("--case") else None
    runs = int(_arg("--runs") or 2)
    for cid, q, lecture, jump_to in PLAYER_QUESTIONS:
        if only and cid not in only:
            continue
        for run in range(1, runs + 1):
            student = f"{uid}-p{cid}-r{run}"
            scope = ChatScope(course_slug=PLAYER_COURSE, lecture_title=lecture, in_player=True)
            lk = await course_lookup(q, student, scope)
            calls.clear()
            req = chat_pipeline.TurnRequest(question=q, student_id=student, scope=scope, history=[],
                                            memory_slug=PLAYER_COURSE)
            t0, first, text, navs, problems = time.perf_counter(), None, [], [], []
            async for e in chat_pipeline.chat_turn(req):
                if e["type"] == "token":
                    first = first or time.perf_counter() - t0
                    text.append(e["value"])
                elif e["type"] == "navigate":
                    navs.append(e)
                elif e["type"] == "error":
                    problems.append(f"error event: {e.get('message')}")
            answer = "".join(text).strip()
            low = answer.lower()
            named = [t for t in others if t.lower() in low]
            if named:
                problems.append(f"names another course: {named}")
            if re.search(r"the01\.dev/course/(?!2\b)\d+", answer):
                problems.append("links another course page")
            if len(navs) > 1:
                problems.append(f"{len(navs)} navigate events")
            if jump_to is None and navs:
                problems.append(f"jumped when it should not: {navs[0]}")
            if jump_to is not None and not navs:
                problems.append("no navigate event")
            if jump_to is not None and navs and navs[-1]["lecture_title"] != jump_to:
                problems.append(f"jumped to {navs[-1]['lecture_title']!r}, expected {jump_to!r}")
            if navs and not any(c.course_id == PLAYER_COURSE and c.lecture_title == navs[-1]["lecture_title"]
                                and c.start_time == navs[-1]["start_time"] for c in vector_store.chunks):
                problems.append("navigate start_time is not a real chunk start")
            failures += bool(problems)
            print(f"=== case {cid} run {run} [{'auto-ok' if not problems else 'AUTO-FAIL'}] watching {lecture!r}")
            print(f"Q: {q}")
            print(f"LookupCase: {lk.case.value}")
            for h in lk.hits:
                band = "STRONG" if h.via_title or h.score >= 0.54 else "WEAK"
                print(f"  hit: {h.title} @ {h.start_time}s score={h.score:.3f} band={band} via_title={h.via_title}")
            cur = lk.current_excerpt
            print(f"  current: {cur.title + ' @ ' + str(cur.start_time) + 's ' + format(cur.score, '.3f') if cur else None}")
            print(f"find_moment calls: {calls or 'none'}")
            print(f"navigate: {navs or 'none'}")
            print(f"first token: {first or 0:.2f}s")
            for p in problems:
                print(f"  X {p}")
            print(f"ANSWER: {answer}\n")
    return failures


def _arg(flag: str) -> str | None:
    if flag in sys.argv:
        i = sys.argv.index(flag)
        return sys.argv[i + 1] if i + 1 < len(sys.argv) else ""
    return None


async def main() -> None:
    enroll_arg = _arg("--enroll")
    positional = [a for i, a in enumerate(sys.argv[1:], 1)
                  if not a.startswith("--") and sys.argv[i - 1] != "--enroll"]
    uid = positional[0] if positional else DEMO_UID
    full = "--full" in sys.argv

    # --full writes audit/memory/skill rows and --enroll writes enrollments: never outside
    # the in-memory store. Checked before any store or OpenAI call.
    player = "--player" in sys.argv
    if (full or player or enroll_arg is not None) and not isinstance(store, InMemoryStore):
        print(f"demo_check: --full, --player and --enroll only run against the in-memory store, not "
              f"{type(store).__name__}. Re-run with `env DATABASE_URL= ...`.")
        sys.exit(2)
    if player:
        assert isinstance(store, InMemoryStore)
        print(f"store: {type(store).__name__} · in-player checks on {PLAYER_COURSE}\n")
        sys.exit(1 if await player_checks(uid) else 0)

    ids: list[int] = []
    if enroll_arg is not None:
        try:
            ids = [int(x) for x in enroll_arg.split(",") if x.strip()]
        except ValueError:
            ids = []
        if not ids or any(catalog_service.get(cid) is None for cid in ids):
            print(f"demo_check: --enroll takes comma-separated catalog course ids, e.g. --enroll 9,11 "
                  f"(got {enroll_arg!r}; valid ids: {[c['id'] for c in catalog_service.all_courses()]})")
            sys.exit(2)
    check = enroll_arg is not None and sorted(ids) in (DEMO_ENROLL, [2])
    col = 2 if sorted(ids) == DEMO_ENROLL else 3

    async def seed(student: str) -> None:
        for cid in ids:
            await enrollment_service.enroll(student, cid, catalog_service.get(cid)["title"])

    await seed(uid)

    enrolled = await enrollment_service.get_enrolled_courses(uid)
    print(f"store: {type(store).__name__} · student {uid}")
    print(f"enrolled in: {[c['title'] for c in enrolled] or 'NOTHING'}")
    print(f"expected-case checks: {'on' if check else 'off (only with --enroll 9,11 or --enroll 2)'}")
    print(f"memory: {'fresh student per question (' + uid + '-qN)' if full else 'n/a (lookup only)'}\n")

    failures = 0
    for i, (q, scope, *exp_cols) in enumerate(QUESTIONS, 1):
        expected = exp_cols[col - 2]
        student = f"{uid}-q{i}" if full else uid
        if student != uid:
            await seed(student)
        # Same query the chat uses: in the player the lecture title rides along.
        lookup_q = f"{scope.lecture_title} {q}" if scope.lecture_title else q
        lk = await course_lookup(lookup_q, student, scope)
        ok = not check or expected is None or lk.case == expected
        failures += not ok
        top = f"{lk.hits[0].course_title} → {lk.hits[0].title} ({lk.hits[0].score:.2f})" if lk.hits else "-"
        exp = f" (expected {expected.value})" if not ok else ""
        print(f"[{'ok' if ok else 'FAIL'}] {lk.case.value:18} {q[:42]:42} top: {top}{exp}")
        if full:
            t0, first, text = time.perf_counter(), None, []
            req = chat_pipeline.TurnRequest(question=q, student_id=student, scope=scope, history=[],
                                            memory_slug=scope.course_slug or "all-courses")
            async for e in chat_pipeline.chat_turn(req):
                if e["type"] == "token":
                    first = first or time.perf_counter() - t0
                    text.append(e["value"])
                elif e["type"] == "error":
                    text.append(f"[error: {e.get('message')}]")
                    failures += 1
            answer = " ".join("".join(text).split())
            # F1/F2: never name a course the student can't be pointed at; owned answers carry the deep link.
            citable = {catalog_service.get(c)["title"] for c in ids if catalog_service.get(c)["launched"]}
            named = [c["title"] for c in catalog_service.all_courses()
                     if c["title"] not in citable and c["title"].lower() in answer.lower()]
            if named:
                print(f"      X names a course it must not cite: {named}")
                failures += 1
            if re.search(r"the01\.dev/course/(?!2\?chapter=\d+&sub=\d+&t=\d+)\S*", answer) or (
                    re.search(r"the01\.dev/course/\d", answer) and 2 not in ids):
                print("      X malformed or unowned course link")
                failures += 1
            if len(answer) > 600 and "--whole" not in sys.argv:
                answer = f"{answer[:330]} … {answer[-250:]}"  # keep the end: pointer / citation live there
            print(f"      first token {first or 0:.2f}s · {answer}\n")
    sys.exit(1 if failures else 0)


if __name__ == "__main__":
    asyncio.run(main())
