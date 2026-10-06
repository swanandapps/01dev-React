"""What each tutor tool is for — the text the model reads to decide when to call it.
Written once; the web chat's LangChain tools use it now, the MCP tools in the
Hermes phase. Guidance is the MCP docstrings' with only the student_id-passing
sentences removed (the web tools don't take a student_id)."""

SEARCH_COURSE_CONTENT = (
    "Search the01.dev lecture transcripts. Use only for a follow-up question the COURSE FACTS "
    "don't already cover. Returns excerpts with course, lecture and timestamp so you can cite them. "
    "On the Ask page only the student's own launched courses are searched, so every excerpt is "
    "citable: cite it with its lecture, time and the link given. No result means none of the "
    "student's courses covers it — say so; never name another course."
)
GET_ENROLLED_COURSES = (
    "Which courses this student actually has access to (purchased/enrolled). Use for 'what courses "
    "am I enrolled in / do I have access to' — you DO have this data, don't decline or guess. An "
    "empty list means genuinely no enrollments yet, not that you lack access to check — say so plainly."
)
GET_LEARNING_STRENGTHS = (
    "What this student is good and weak at OVERALL — use this for broad questions like 'what am I "
    "good at?', 'what am I weak on?', 'where do I need work?' that don't name one specific concept "
    "or course. Do NOT use get_concept_confidence for these — that tool needs one concept AND a "
    "course_id already in hand; this one needs neither. Each weakness includes its prerequisites "
    "(from the course knowledge graph) with their own accuracy, so you can connect the dots — e.g. "
    "\"you're weak on X, and its prerequisite Y is shaky too, so start with Y\". Returns "
    "strengths/weaknesses (accuracy >= 0.8 counts as a strength) and concepts_attempted. An empty "
    "result means no graded activity yet — say so plainly, don't guess."
)
GET_LEARNING_METRICS = (
    "Raw activity numbers for this student — quiz count, streak, average score, active days, "
    "practice time. Use for 'what's my streak', 'how many quizzes have I taken', 'how am I doing "
    "overall' — anything asking for the numbers themselves rather than which concepts are "
    "strong/weak (use get_learning_strengths for that). streak counts consecutive days including "
    "today/yesterday; 0 quizzes/0 streak means no graded activity yet — say so plainly, don't guess."
)
GET_CONCEPT_CONFIDENCE = (
    "Check how confident this student is on a concept AND on everything that concept depends on, in "
    "one call — use this BEFORE teaching something that has prerequisites, so you can address a "
    "shaky prerequisite instead of teaching on top of a gap. Returns the concept's "
    "accuracy/attempts, its prerequisites with the same shape, and weakest_prerequisite (the "
    "lowest-accuracy prerequisite that has actually been attempted — null if none have been). "
    "accuracy null on any entry means never graded yet, not a zero score — don't treat null as bad. "
    "Each entry also carries chat_confidence/chat_confidence_note — your own prior conversational "
    "impression logged via record_skill_observation. chat_confidence null means no observation has "
    "been logged yet, not \"weak\". chat_confidence and accuracy are different signals — a chat "
    "impression vs. a real graded score — do not conflate them or treat one as a substitute for the "
    "other. concept must match a concept tag used in that course; course_id is the course slug, "
    "e.g. 'react-perf'."
)
SEARCH_HISTORY = (
    "Search this student's own past tutoring exchanges. Use ONLY when they refer to a past "
    "conversation ('like you taught me closures', 'what did we cover last time?'). Do NOT use it to "
    "answer a new concept question — use search_course_content for that."
)
RECORD_SKILL_OBSERVATION = (
    "Log what you've noticed about this student's grasp of a concept from the conversation — NOT a "
    "quiz score. Call this whenever the conversation makes their understanding clear either way "
    "(they explained it correctly unprompted, or they were clearly confused/wrong about it) — you "
    "don't need to ask permission, this is internal bookkeeping, not a consequential action. "
    "confidence must be exactly one of 'weak', 'developing', 'strong'. Do not call this for vague "
    "or ambiguous signals — only when the conversation actually showed you something concrete. "
    "course_id is the course slug, e.g. 'react-perf'."
)

EXPLAIN_CONCEPT = (
    "WHERE the student's score on one concept came from — use this when they ask \"why is this my "
    "strong/weak topic?\", \"I never took a course on this, why does it say I'm good at it?\", or "
    "otherwise question a number you reported. Returns total attempts/correct/accuracy plus sources: "
    "one entry per course or per piece of the student's own uploaded material (Lab), each with its own "
    "attempts/correct. source is \"course\", \"lecture\" (a course lecture studied in the Lab) or \"self_study\" — say which, plainly, because a student may "
    "not remember quizzing themselves on their own notes. merged_tags lists loosely-named tags (with "
    "counts) that were treated as THIS concept (e.g. their notes said \"useCallback hook\"). Mention them "
    "when explaining a surprising score; if the student says those are different things, tell them "
    "that's useful and worth flagging. matched_concepts names the stored concepts that were counted (a loose "
    "name like \"React.memo\" can cover several, e.g. react-memo-purpose and react-memo-behavior) — name "
    "them. If attempts is 0 and known_concepts is present, the name didn't match: call again with the "
    "closest name from known_concepts before saying there are no attempts. concept is the name as "
    "reported by get_learning_strengths."
)

FIND_MOMENT = (
    "Video player only. Find the moment in THIS course where something is shown or said, so the "
    "player can jump there. Call it ONLY when the student explicitly asks to be taken, jumped or shown to "
    "a place in the video (\"take me to\", \"jump to\", \"show me where\", \"where in the video\", "
    "\"go to the part\"). For questions about content use search_course_content (or the COURSE FACTS) "
    "instead; never call it to look something up, because the player jumps by itself when it finds a moment. "
    "Pass `what` as "
    "the specific thing to find, in the words the instructor would say on screen: the command, tool, "
    "function or term (e.g. 'npm publish command', 'npm link', 'IIFE syntax'). Drop request filler such as "
    "'take me to the part where'. Prefer the concrete command or term over a description of the goal. Returns "
    "the lecture title, start/end second, an excerpt and a score — or {\"found\": false} when this "
    "course has no such part. When found, the player jumps there by itself: tell the student in one "
    "or two sentences what is there, naming that lecture and time exactly as returned. Never invent "
    "a lecture or a time."
)
