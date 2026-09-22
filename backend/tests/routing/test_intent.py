import pytest

from app.routing.intent import Intent, classify

QUIZ_EXAMPLES = [
    "Can you quiz me on closures?",
    "Make a quiz on React hooks",
    "quiz me",
    "Create a test for the useEffect lecture",
    "I want to test myself on this course",
    "give me a practice quiz about async/await",
]

COURSE_QUESTION_EXAMPLES = [
    "What is a closure in JavaScript?",
    "Explain useCallback vs useMemo",
    "Can you summarize lecture 4.1?",
    "why does my component re-render every time",
    "what did we cover last week",
    # Operational/"dashboard" questions are COURSE_QUESTION now too — Hermes
    # reasons about these itself via get_learning_strengths/get_learning_metrics,
    # there's no separate PROGRESS_LOOKUP short-circuit anymore.
    "What's my progress so far?",
    "How am I doing in this course?",
    "show me my learning journey",
    "what are my strengths and weaknesses",
    "am I improving",
    "what's my quiz streak",
]

OUT_OF_SCOPE_EXAMPLES = [
    "",
    "   ",
    "asdkjaslkdj",
]


@pytest.mark.parametrize("question", QUIZ_EXAMPLES)
def test_classifies_quiz_requests(question):
    assert classify(question) == Intent.QUIZ_GENERATE


@pytest.mark.parametrize("question", COURSE_QUESTION_EXAMPLES)
def test_classifies_course_questions(question):
    assert classify(question) == Intent.COURSE_QUESTION


@pytest.mark.parametrize("question", OUT_OF_SCOPE_EXAMPLES)
def test_classifies_empty_or_junk_as_out_of_scope(question):
    assert classify(question) == Intent.OUT_OF_SCOPE


def test_quiz_keyword_inside_a_real_question_does_not_misfire():
    # "test" appears, but this is a course question about testing, not a
    # request to BE quizzed — the rule must key off the imperative pattern,
    # not the bare word.
    assert classify("What's the difference between unit tests and integration tests?") == Intent.COURSE_QUESTION


def test_reviewing_past_quiz_performance_does_not_misfire_into_quiz_generate():
    # "quiz" appears, but this is asking to REVIEW past performance, not to
    # be quizzed — must not match the imperative _QUIZ_PATTERNS.
    assert classify("how did I do on my last quiz") == Intent.COURSE_QUESTION
