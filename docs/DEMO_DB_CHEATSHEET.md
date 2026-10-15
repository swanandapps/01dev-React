# Demo: showing the data

console.neon.tech → **the01dev** → **Tables** (left menu) → under `public`, click a view. No SQL needed.
Every view is read-only and built on two real tables: `docs` (all app data as JSON) and `rag_chunks`
(course passages + embeddings). My account is `x94FcfXU7KRrobyOA4UHDukbRoC2`.

## Click order

### 1. The course content (what the tutor answers from)
| View | Shows |
|---|---|
| `course_passages_v` | 1,350 timed passages: course, lecture, start–end, text, a 1536-number embedding each |

"Lectures are split into ~48-second passages, enriched with their course/chapter/lecture and a summary, then embedded."

### 2. Concepts and the knowledge graph (same for everyone)
| View | Shows |
|---|---|
| `concepts_v` | the 16 live concepts, with descriptions |
| `knowledge_graph_v` | the 11 live links (prerequisite_of / related_to) |
| `full_graph_concepts_v` | **preview:** 306 concepts across all 10 courses, by chapter, with the lectures that teach each |
| `full_graph_links_v` | **preview:** 502 links, e.g. call-stack → event-loop → microtask-queue → async-await |
| `question_bank_v` | the 96 practice questions: concept, difficulty, lecture, question, correct answer |

### 3. My account: what the platform knows about one student
| View | Shows |
|---|---|
| `my_courses_v` | the 4 courses they're enrolled in |
| `my_quizzes_v` | every graded quiz: when, course, type (course quiz / Quiz me / Lab topic), score |
| `my_quiz_answers_v` | every answer: concept, lecture, right/wrong. **This is the evidence that moves scores.** |
| `my_skill_graph_v` | **their skill graph:** score per concept, solid/shaky, the tutor's note, prerequisites |
| `my_skill_graph_full_v` | **preview:** the same student on the full graph (16 scored, the rest "not tried") |
| `my_chats_v` | every tutor conversation: Ask page or player, question, answer |
| `my_tutor_memory_v` | the tutor's memory: conversations, first/last seen, what they recently asked about, and **how they like to learn** |
| `my_lab_v` | flashcards / quizzes / notes they made in Lab |

### 4. Governance
| View | Shows |
|---|---|
| `ai_audit_log_v` | every AI answer: when, which student (shortened), where, question, model, risk level |

`docs` (one click) is the raw JSON underneath, which shows "this is how it's actually stored".
`skill_graph_v` is the skill graph for every student, not just mine.

## Talk track (observe → model → personalize)

- **Observe:** every graded answer (practice, Lab quizzes, Quiz me in the player) updates the concept's
  score. During chat, the tutor can also record an impression ("developing: explained the call stack
  but…"). It's stored beside the score and never changes it.
- **Model:** the scores sit on the course's knowledge graph, which gives one skill graph per student.
  solid ≥ 80%, otherwise shaky, or not tried.
- **Personalize:**
  - the tutor gets this student's weak concepts on every answer;
  - practice won't give a HARD question on a concept until its prerequisites are at least 70% (microtask queue
    stays at medium while event loop is 44%), and the tutor can say "this builds on the event loop, where you're at 44%";
  - only `prerequisite_of` links are used; `part_of` / `related_to` are stored for later;
  - Lab's "Start here" and the dashboard's "Needs work" come from the same data;
  - quiz questions are tagged with the course's own concept names, so results land on the graph.

Line for the preview graph: "Live, the app runs on the 16 concepts we have question banks for. This is the full
graph, extracted chapter by chapter from the transcripts. Next we generate questions for each concept and switch it on."

## Honest answers if asked

- **Coverage:** live graph = 4 courses, 16 concepts, 11 links. Full graph (306 concepts) is built but not
  live until each concept has practice questions.
- **Storage:** everything is JSON documents in one Postgres table (`docs`); the views are a read-only
  relational lens on it.
- **Preferences:** say "explain things with anime characters from now on" (or "in Hinglish", "I'm a backend dev")
  in either chat. A small background step saves it a few seconds after the answer, as one short paragraph
  (refresh `my_tutor_memory_v` → `how_they_like_to_learn`). Every later answer, in the player and on Ask,
  follows it. Only lasting preferences are kept; "explain it simpler" for one answer isn't. Students can't
  see or edit it in the app yet.
- **Don't type "quiz me" in either chat.** It returns an outdated hand-off message. Use the Quiz me button,
  the "Quiz me on …" chip, or Lab → topic → Practise this topic.
- **After "New chat", ask a question that names its topic.** Ask's history is the last 3 stored exchanges,
  even after New chat.
