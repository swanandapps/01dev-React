"""
Deterministic, rule-based intent classification for the chat endpoint.

No ML here on purpose — PRIMARY_REPO_MIGRATION_PLAN.md §5 explicitly says
not to block the router contract on training infrastructure. High-precision
rules first; a learned classifier is a drop-in replacement behind the same
`classify(question) -> Intent` signature later, once there's a labeled
routing log to train it on.

Deliberately narrow scope: this classifier ONLY exists to catch the two
cases that need to bypass Hermes's own reasoning entirely — QUIZ_GENERATE
(a hand-off to a separate app, QuizMe, not just a different answer) and
OUT_OF_SCOPE (empty/gibberish input, not worth an LLM call at all).
Everything else — course questions, "what's my progress"/"what am I good
at" style operational questions, and general technical questions outside
the course library — is a single COURSE_QUESTION bucket that reaches
Hermes's own agentic tool-calling loop. There used to be a third
short-circuit here (PROGRESS_LOOKUP, injecting one pre-computed
journey_service narrative that ignored the actual question and wasn't
really streamed) — removed once Hermes got its own tools
(get_learning_strengths, get_learning_metrics) to answer those questions
for real, per-question, actually streamed, with the same reasoning as
everything else.
"""
import re
from enum import Enum


class Intent(str, Enum):
    COURSE_QUESTION = "course_question"
    QUIZ_GENERATE = "quiz_generate"
    OUT_OF_SCOPE = "out_of_scope"


# Imperative "quiz/test me" patterns — deliberately narrow so a course
# question that merely mentions "test" (e.g. "unit tests vs integration
# tests") doesn't misfire into QUIZ_GENERATE. Also checked ahead of nothing
# else now (progress questions used to need to win this overlap — e.g. "how
# did I do on my last quiz" — that's now just a COURSE_QUESTION Hermes
# reasons about like anything else, so the ordering concern no longer
# applies).
_QUIZ_PATTERNS = [
    re.compile(r"\bquiz\s+me\b", re.I),
    re.compile(r"\b(make|create|give|build|generate)\s+(me\s+)?(a\s+)?(quick\s+)?(quiz|practice\s+quiz|test)\b", re.I),
    re.compile(r"\btest\s+(myself|me)\b", re.I),
    re.compile(r"\bcan\s+you\s+quiz\s+me\b", re.I),
]


def classify(question: str) -> Intent:
    q = (question or "").strip()
    if not q or not re.search(r"[a-zA-Z0-9]", q):
        return Intent.OUT_OF_SCOPE
    for pattern in _QUIZ_PATTERNS:
        if pattern.search(q):
            return Intent.QUIZ_GENERATE
    # Detect gibberish: single word, minimum 8 chars, and very low vowel ratio
    if " " not in q and len(q) >= 8:
        vowels = len(re.findall(r"[aeiouAEIOU]", q))
        vowel_ratio = vowels / len(q) if q else 0
        if vowel_ratio < 0.20:  # Less than 20% vowels in long single-word input suggests gibberish
            return Intent.OUT_OF_SCOPE
    return Intent.COURSE_QUESTION
