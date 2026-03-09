"""
Learning-journey analytics for the dashboard.

Turns the student's raw activity (quiz sessions + per-concept performance) into
meaningful metrics, an activity heatmap, strengths/weaknesses, and an AI-written
narrative that surfaces patterns they might not notice themselves.
"""

from collections import Counter, defaultdict
from datetime import datetime, timezone, timedelta

from app.services.llm import llm
from app.services.store import store

HEATMAP_DAYS = 84  # 12 weeks


def _today():
    return datetime.now(timezone.utc).date()


def _parse_date(iso: str):
    try:
        return datetime.fromisoformat(iso)
    except (ValueError, TypeError):
        return None


def _streak(dates: set) -> int:
    if not dates:
        return 0
    cur = max(dates)
    # Only count as a "current" streak if the last activity was today or yesterday.
    if (_today() - cur).days > 1:
        return 0
    streak = 0
    while cur in dates:
        streak += 1
        cur = cur - timedelta(days=1)
    return streak


def _part_of_day(hour: int) -> str:
    if 5 <= hour < 12:
        return "mornings"
    if 12 <= hour < 17:
        return "afternoons"
    if 17 <= hour < 22:
        return "evenings"
    return "late nights"


async def get_journey(user_id: str) -> dict:
    sessions = await store.query("quiz_sessions", "user_id", user_id)
    perf = await store.query("concept_performance", "user_id", user_id)

    dts = [d for d in (_parse_date(s.get("completed_at", "")) for s in sessions) if d]
    day_set = {d.date() for d in dts}

    # ---- metrics ----
    total_q = sum(s.get("total", 0) for s in sessions)
    total_correct = sum(s.get("score", 0) for s in sessions)
    total_ms = sum(a.get("time_taken_ms", 0) for s in sessions for a in s.get("answers", []))
    avg_score = round(total_correct / total_q, 3) if total_q else 0.0

    practiced = [p for p in perf if p.get("attempts", 0) > 0]
    mastered = [p for p in practiced if p["accuracy"] >= 0.8]
    weak = [p for p in practiced if p["accuracy"] < 0.6]

    metrics = {
        "quizzes": len(sessions),
        "questions_answered": total_q,
        "avg_score": avg_score,
        "active_days": len(day_set),
        "streak": _streak(day_set),
        "courses_engaged": len({s.get("course_id") for s in sessions}),
        "concepts_practiced": len(practiced),
        "concepts_mastered": len(mastered),
        "concepts_weak": len(weak),
        "practice_minutes": round(total_ms / 60000, 1),
        "avg_seconds_per_question": round(total_ms / 1000 / total_q, 1) if total_q and total_ms else 0,
    }

    # ---- activity heatmap (last HEATMAP_DAYS) ----
    by_day = Counter(d.date().isoformat() for d in dts)
    start = _today() - timedelta(days=HEATMAP_DAYS - 1)
    heatmap = [
        {"date": (start + timedelta(days=i)).isoformat(), "count": by_day.get((start + timedelta(days=i)).isoformat(), 0)}
        for i in range(HEATMAP_DAYS)
    ]

    # ---- strengths / weaknesses ----
    strengths = sorted([p for p in practiced if p["accuracy"] >= 0.8], key=lambda p: -p["accuracy"])[:6]
    weaknesses = sorted([p for p in practiced if p["accuracy"] < 0.8], key=lambda p: p["accuracy"])[:6]
    fmt = lambda p: {"concept": p["concept"], "accuracy": p["accuracy"], "attempts": p["attempts"]}

    # ---- AI insights ----
    ai = await _ai_insights(metrics, strengths, weaknesses, dts, sessions)

    return {
        "metrics": metrics,
        "heatmap": heatmap,
        "strengths": [fmt(p) for p in strengths],
        "weaknesses": [fmt(p) for p in weaknesses],
        "ai": ai,
    }


SYSTEM_PROMPT = """You are an insightful learning analyst for the 0.1% Dev platform.
Given a student's learning-journey data, write a short, motivating narrative and surface
PATTERNS they likely haven't noticed themselves (not just restating the numbers). Be specific
and honest. If there's little data, encourage them to start and say what you'll track.

Return a JSON object with EXACTLY this shape:
{
  "narrative": "2-3 sentence story of their journey so far",
  "insights": ["a non-obvious pattern or observation", ...],   // 2-4 items
  "focus": "the single most useful thing to do next, one sentence"
}"""


async def _ai_insights(metrics, strengths, weaknesses, dts, sessions) -> dict:
    lines = [
        f"Quizzes taken: {metrics['quizzes']}, questions: {metrics['questions_answered']}, "
        f"avg score: {round(metrics['avg_score']*100)}%.",
        f"Active on {metrics['active_days']} day(s), current streak {metrics['streak']}, "
        f"{metrics['practice_minutes']} min practiced, ~{metrics['avg_seconds_per_question']}s per question.",
        f"Concepts: {metrics['concepts_mastered']} mastered, {metrics['concepts_weak']} weak.",
    ]
    if strengths:
        lines.append("Strong: " + ", ".join(f"{p['concept']} ({round(p['accuracy']*100)}%)" for p in strengths))
    if weaknesses:
        lines.append("Weak: " + ", ".join(f"{p['concept']} ({round(p['accuracy']*100)}%)" for p in weaknesses))
    if dts:
        peak_hour = Counter(d.hour for d in dts).most_common(1)[0][0]
        lines.append(f"Practices mostly in the {_part_of_day(peak_hour)}.")
        # accuracy trend: first half vs second half of sessions (chronological)
        chron = sorted(sessions, key=lambda s: s.get("completed_at", ""))
        if len(chron) >= 2:
            half = len(chron) // 2
            def avg(xs):
                tot = sum(x.get("total", 0) for x in xs)
                return sum(x.get("score", 0) for x in xs) / tot if tot else 0
            early, late = avg(chron[:half]), avg(chron[half:])
            trend = "improving" if late > early + 0.05 else "declining" if late < early - 0.05 else "steady"
            lines.append(f"Score trend: {trend} ({round(early*100)}% → {round(late*100)}%).")

    data = await llm.generate_json(SYSTEM_PROMPT, "\n".join(lines), max_tokens=600)
    if not data:
        return {
            "narrative": "Your journey is just getting started. Take an adaptive quiz on any course to begin building your map.",
            "insights": [],
            "focus": "Run your first adaptive practice session.",
        }
    return {
        "narrative": data.get("narrative", ""),
        "insights": data.get("insights", []),
        "focus": data.get("focus", ""),
    }
