"""The tutor's grounding prompt: the rules every chat turn runs under.

Same for every student — personalization comes from learner state (COURSE FACTS,
memory), not from this file. Kept as a file so it can be read and reviewed like
code, and so the audit log can fingerprint the exact version that answered.
"""
import hashlib
from pathlib import Path

PROMPT_PATH = Path(__file__).resolve().parent / "grounding_prompt.md"

FALLBACK_PROMPT = (
    "You are Dev, the01.dev's AI tutor. Use the COURSE FACTS you are given: cite "
    "lectures the student owns, give a short answer plus a course pointer for courses "
    "they don't own, and label general-knowledge answers as not from a the01.dev course."
)


def read_grounding_prompt() -> str:
    try:
        text = PROMPT_PATH.read_text().strip()
        reason = "is empty"
    except OSError as e:
        text, reason = "", f"unreadable ({e.__class__.__name__})"
    if text:
        return text
    print(f"[grounding] WARNING: {PROMPT_PATH} {reason}; using FALLBACK_PROMPT", flush=True)
    return FALLBACK_PROMPT


def prompt_fingerprint() -> str:
    return hashlib.sha256(read_grounding_prompt().encode()).hexdigest()[:12]
