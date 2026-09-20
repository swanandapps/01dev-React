"""
Deterministic, rule-based intent classification for the chat endpoint.

No ML here on purpose — PRIMARY_REPO_MIGRATION_PLAN.md §5 explicitly says
not to block the router contract on training infrastructure. High-precision
rules first; a learned classifier is a drop-in replacement behind the same
`classify(question) -> Intent` signature later, once there's a labeled
routing log to train it on.
"""
import re
from enum import Enum


class Intent(str, Enum):
    COURSE_QUESTION = "course_question"
    QUIZ_GENERATE = "quiz_generate"
    PROGRESS_LOOKUP = "progress_lookup"
    OUT_OF_SCOPE = "out_of_scope"


# Checked FIRST: "how did I do on my last quiz" mentions "quiz" but is a
# review of past performance, not a request to be quizzed. Progress rules
# must win that overlap, so they're matched before the quiz rules below.
_PROGRESS_PATTERNS = [
    re.compile(r"\bmy\s+\w+\s+(progress|journey|streak|strengths?|weakness(es)?)\b", re.I),
    re.compile(r"\bmy\s+(progress|journey|streak|strengths?|weakness(es)?)\b", re.I),
    re.compile(r"\bhow\s+(am\s+i|did\s+i)\s+(doing|do)\b", re.I),
    re.compile(r"\bam\s+i\s+(improving|getting\s+better)\b", re.I),
    re.compile(r"\bshow\s+me\s+my\s+\w+\s+(progress|journey|stats)\b", re.I),
    re.compile(r"\bshow\s+me\s+my\s+(progress|journey|stats)\b", re.I),
]

# Imperative "quiz/test me" patterns — deliberately narrow so a course
# question that merely mentions "test" (e.g. "unit tests vs integration
# tests") doesn't misfire into QUIZ_GENERATE.
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
    for pattern in _PROGRESS_PATTERNS:
        if pattern.search(q):
            return Intent.PROGRESS_LOOKUP
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
