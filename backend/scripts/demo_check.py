"""Run before every demo: fixed questions through course_lookup (and optionally the
full tutor) for one student, printing case, top hits, answers and first-token latency.

LOCAL ONLY — run from backend/ with a blank DATABASE_URL so the in-memory store is
used and production data is never read or written:

  env DATABASE_URL= .venv/bin/python scripts/demo_check.py [student_id] [--enroll 9,11] [--full]

  --enroll 9,11  seed enrollments (catalog course ids) for the student first; refused
                 (exit 2) unless the in-memory store is active. 9,11 simulates the demo
                 account: JavaScript Deep Dive + React Performance Patterns, not
                 Build a Custom Library — and turns on the expected-case checks.
  --full         also run each question through the full tutor (real OpenAI key from
                 backend/.env) and print the answer (long ones cut to head … tail) and first-token latency.
  --whole        with --full, print whole answers, uncut.

Exits 1 if any expected case doesn't match.
"""
import asyncio
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
E, N, X = LookupCase.ENROLLED_MATCH, LookupCase.NOT_ENROLLED_MATCH, LookupCase.NO_MATCH
QUESTIONS = [
    # (question, scope, expected case with --enroll 9,11 — None = printed only)
    ("how do I publish an npm library", ChatScope(), N),
    ("does React.memo need useCallback", ChatScope(), E),
    ("explain the event loop and microtasks", ChatScope(), E),
    ("how do I write a lexer for my own language", ChatScope(), N),
    ("how do I bake sourdough bread", ChatScope(), X),
    ("what am I weak at?", ChatScope(), None),
    ("what does this mean?", ChatScope("react-perf", "4.1 - React.memo and useCallback"), None),
]


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

    if enroll_arg is not None:
        if not isinstance(store, InMemoryStore):
            print(f"demo_check: --enroll only runs against the in-memory store, not "
                  f"{type(store).__name__}. Re-run with `env DATABASE_URL= ...`.")
            sys.exit(2)
        ids = [int(x) for x in enroll_arg.split(",") if x.strip()]
        for cid in ids:
            course = catalog_service.get(cid)
            if not course:
                print(f"demo_check: no catalog course with id {cid}")
                sys.exit(2)
            await enrollment_service.enroll(uid, cid, course["title"])
    check = enroll_arg is not None and sorted(ids) == DEMO_ENROLL

    enrolled = await enrollment_service.get_enrolled_courses(uid)
    print(f"store: {type(store).__name__} · student {uid}")
    print(f"enrolled in: {[c['title'] for c in enrolled] or 'NOTHING'}")
    print(f"expected-case checks: {'on' if check else 'off (only with --enroll 9,11)'}\n")

    failures = 0
    for q, scope, expected in QUESTIONS:
        # Same query the chat uses: in the player the lecture title rides along.
        lookup_q = f"{scope.lecture_title} {q}" if scope.lecture_title else q
        lk = await course_lookup(lookup_q, uid, scope)
        ok = not check or expected is None or lk.case == expected
        failures += not ok
        top = f"{lk.hits[0].course_title} → {lk.hits[0].title} ({lk.hits[0].score:.2f})" if lk.hits else "-"
        exp = f" (expected {expected.value})" if not ok else ""
        print(f"[{'ok' if ok else 'FAIL'}] {lk.case.value:18} {q[:42]:42} top: {top}{exp}")
        if full:
            t0, first, text = time.perf_counter(), None, []
            req = chat_pipeline.TurnRequest(question=q, student_id=uid, scope=scope, history=[],
                                            memory_slug=scope.course_slug or "all-courses")
            async for e in chat_pipeline.chat_turn(req):
                if e["type"] == "token":
                    first = first or time.perf_counter() - t0
                    text.append(e["value"])
                elif e["type"] == "error":
                    text.append(f"[error: {e.get('message')}]")
            answer = " ".join("".join(text).split())
            if len(answer) > 600 and "--whole" not in sys.argv:
                answer = f"{answer[:330]} … {answer[-250:]}"  # keep the end: pointer / citation live there
            print(f"      first token {first or 0:.2f}s · {answer}\n")
    sys.exit(1 if failures else 0)


if __name__ == "__main__":
    asyncio.run(main())
