"""Lab topics: every chapter of a course the student owns is a topic, and its lectures are marked from the
student's own quiz answers on that lecture:
  solid      >= SOLID of the questions right (the dashboard's 'strengths' line)
  shaky      below that
  not_tried  no answers yet
Plain rules pick what to suggest: 'Start here' is the topic with the lowest share right among the ones that
have a shaky lecture; 'Keep it fresh' is an all-solid topic not practised for STALE_DAYS. No model call."""
from datetime import datetime, timedelta, timezone
from typing import Optional

from app.retrieval import pipeline
from app.retrieval.text import norm_title
from app.services import catalog_service, enrollment_service
from app.services.store import store
from app.services.vector_store import vector_store

SOLID = 0.8
STALE_DAYS = 7


def _has_transcripts(slug: str) -> bool:
    return any(c.course_id == slug for c in vector_store.chunks)


def _chapter_name(name: str) -> str:
    """'Chapter 5 - Goodbye Prototype' -> 'Goodbye Prototype'."""
    head, sep, rest = name.partition(" - ")
    return rest if sep and head.lower().startswith("chapter") else name


def _status(right: int, total: int) -> str:
    return "not_tried" if total == 0 else "solid" if right / total >= SOLID else "shaky"


async def owned_courses(student_id: str) -> list[dict]:
    await pipeline._ensure_loaded()
    owned = {c["id"] for c in await enrollment_service.get_enrolled_courses(student_id)}
    return [c for c in catalog_service.all_courses() if c["id"] in owned and _has_transcripts(c["slug"])]


async def _lecture_stats(student_id: str, courses: list[dict]) -> dict:
    """{(slug, normalized lecture title): {right, total, last}} from every quiz the student submitted."""
    where = {}  # normalized lecture title -> slug (titles are unique within a course; first course wins)
    for c in courses:
        for ch in c["chapters"]:
            for title in ch["subchapters"]:
                where.setdefault(norm_title(title), c["slug"])
    stats: dict = {}
    for s in await store.query("quiz_sessions", "user_id", student_id):
        session_lecture = (s.get("doc_title") or "").removeprefix("Lecture: ")
        for a in s.get("answers", []):
            key = norm_title(a.get("lecture") or session_lecture)
            slug = where.get(key)
            if not slug:
                continue
            row = stats.setdefault((slug, key), {"right": 0, "total": 0, "last": ""})
            row["total"] += 1
            row["right"] += 1 if a.get("correct") else 0
            row["last"] = max(row["last"], s.get("completed_at", ""))
    return stats


def _topic(course: dict, ci: int, stats: dict) -> dict:
    ch = course["chapters"][ci]
    lectures = []
    for si, title in enumerate(ch["subchapters"]):
        row = stats.get((course["slug"], norm_title(title)), {"right": 0, "total": 0, "last": ""})
        lectures.append({"title": title, "chapter": ci, "sub": si, "status": _status(row["right"], row["total"]),
                         "right": row["right"], "total": row["total"], "last": row["last"]})
    count = lambda st: sum(1 for l in lectures if l["status"] == st)
    return {"index": ci, "name": _chapter_name(ch["name"]), "lectures": lectures,
            "solid": count("solid"), "shaky": count("shaky"), "untried": count("not_tried"),
            "last_practised": max((l["last"] for l in lectures), default="")}


def _start_here(courses_out: list[dict]) -> Optional[dict]:
    best = None
    for c in courses_out:
        for t in c["topics"]:
            if not t["shaky"]:
                continue
            right = sum(l["right"] for l in t["lectures"])
            total = sum(l["total"] for l in t["lectures"])
            weakest = min((l for l in t["lectures"] if l["status"] == "shaky"), key=lambda l: l["right"] / l["total"])
            score = right / total
            if best is None or score < best[0]:
                best = (score, {"slug": c["slug"], "topic": t["index"],
                                "why": f"You got {weakest['right']} of {weakest['total']} right on {weakest['title']}."})
    return best[1] if best else None


def _keep_fresh(courses_out: list[dict], now: datetime) -> Optional[dict]:
    cutoff = (now - timedelta(days=STALE_DAYS)).isoformat()
    for c in courses_out:
        for t in c["topics"]:
            if t["lectures"] and t["solid"] == len(t["lectures"]) and t["last_practised"] and t["last_practised"] < cutoff:
                last = datetime.fromisoformat(t["last_practised"])
                days = (now - last).days
                return {"slug": c["slug"], "topic": t["index"],
                        "why": f"Last practised {days} days ago. A short review keeps it solid."}
    return None


async def topics(student_id: str, now: Optional[datetime] = None) -> dict:
    courses = await owned_courses(student_id)
    stats = await _lecture_stats(student_id, courses)
    out = [{"slug": c["slug"], "id": c["id"], "title": c["title"],
            "topics": [_topic(c, ci, stats) for ci in range(len(c["chapters"]))]} for c in courses]
    return {"courses": out, "start_here": _start_here(out),
            "keep_fresh": _keep_fresh(out, now or datetime.now(timezone.utc))}


async def lectures_to_practise(student_id: str, course: dict, chapter: int, limit: int) -> list[str]:
    """The chapter's lectures in the order they need work: shaky (weakest first), not tried, then solid."""
    stats = await _lecture_stats(student_id, [course])
    t = _topic(course, chapter, stats)
    order = {"shaky": 0, "not_tried": 1, "solid": 2}
    ranked = sorted(t["lectures"], key=lambda l: (order[l["status"]],
                                                   l["right"] / l["total"] if l["total"] else 0, l["sub"]))
    return [l["title"] for l in ranked][:limit]
