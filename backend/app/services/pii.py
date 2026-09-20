"""PII scrubbing — runs on free-form text BEFORE it is sent to a model, traced,
or persisted, so no student PII reaches any downstream surface.

The regex tier is dependency-free and catches the common, high-risk identifiers a
learner might paste into a question. Production upgrade: swap _PATTERNS for
Microsoft Presidio (adds NER for names / locations / orgs) behind the same scrub()
signature — callers do not change.

Contract: scrub() is idempotent (re-scrubbing redacted text is a no-op), so it is
safe to call at more than one layer (request entry AND storage) as defence in depth.
"""
import re

# ordered: match structured identifiers before the looser phone/number patterns
_PATTERNS = {
    "EMAIL": re.compile(r"\b[\w.+-]+@[\w-]+\.[\w.-]+\b"),
    "SSN":   re.compile(r"\b\d{3}-\d{2}-\d{4}\b"),
    "CARD":  re.compile(r"\b\d(?:[ -]?\d){12,15}\b"),
    "PHONE": re.compile(r"(?:\+?\d{1,3}[\s.-]?)?\(?\d{3}\)?[\s.-]?\d{3}[\s.-]?\d{4}\b"),
}


def scrub(text: str) -> tuple[str, list[str]]:
    """Redact PII in `text`. Returns (clean_text, kinds_found).

    `kinds_found` is for telemetry / the audit trail — log the KINDS, never the
    values. Empty list means the text was already clean.
    """
    if not text:
        return text, []
    found: list[str] = []
    for kind, rx in _PATTERNS.items():
        if rx.search(text):
            found.append(kind)
            text = rx.sub(f"[{kind}_REDACTED]", text)
    return text, found
