"""What each tutor tool is for — the text the model reads to decide when to call it.
Written once; the web chat's LangChain tools use it now, the MCP tools in the
Hermes phase."""

SEARCH_COURSE_CONTENT = (
    "Search the01.dev lecture transcripts. Use only for a follow-up question the COURSE FACTS "
    "don't already cover. Returns excerpts with course, lecture and timestamp so you can cite them."
)
GET_ENROLLED_COURSES = (
    "Which courses this student owns. Use for 'what courses am I enrolled in / do I have access to'. "
    "An empty list means no enrollments yet — say so plainly."
)
GET_LEARNING_STRENGTHS = (
    "What this student is good and weak at overall, with each weakness's prerequisites and their "
    "accuracy. Use for 'what am I good at / weak at / where do I need work'. Empty means no graded "
    "activity yet — say so, don't guess."
)
GET_LEARNING_METRICS = (
    "Raw activity numbers: quiz count, streak, average score, active days, practice time. Use for "
    "'what's my streak', 'how many quizzes have I taken'. Zeros mean no graded activity yet."
)
GET_CONCEPT_CONFIDENCE = (
    "This student's accuracy on one concept and on its prerequisites, plus your earlier chat "
    "impressions. Use before teaching a concept that has prerequisites. accuracy null = never graded, "
    "not zero. course_id is the course slug, e.g. 'react-perf'."
)
SEARCH_HISTORY = (
    "Search this student's own past tutoring exchanges. Use only when they refer to a past "
    "conversation ('like you taught me closures', 'what did we cover last time')."
)
RECORD_SKILL_OBSERVATION = (
    "Log what the conversation showed about this student's grasp of a concept — not a quiz score. "
    "confidence must be exactly 'weak', 'developing' or 'strong'. Only for concrete signals. "
    "course_id is the course slug, e.g. 'react-perf'."
)
