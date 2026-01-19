export interface Lecture {
  lecture_id: string;
  lecture_title: string;
  course_id: string;
  course_title: string;
}

export interface KeyConcept {
  name: string;
  description: string;
}

export interface PracticeQA {
  question: string;
  answer: string;
}

export interface StudyGuide {
  lecture_id: string;
  course_id: string;
  lecture_title: string;
  course_title: string;
  key_concepts: KeyConcept[];
  summary: string;
  practice_questions: PracticeQA[];
  misconceptions: string[];
  model: string;
  generated_at: string;
}

export interface StudyGuideStatus {
  status: "ready" | "generating" | "none";
  guide: StudyGuide | null;
}

export interface MCQQuestion {
  id: string;
  question: string;
  options: string[];
  correct_index: number;
  explanation: string;
  concept: string;
  difficulty: "easy" | "medium" | "hard";
}

export interface QuestionSet {
  lecture_id: string;
  course_id: string;
  lecture_title: string;
  course_title: string;
  questions: MCQQuestion[];
  model: string;
  generated_at: string;
}

export interface QuestionStatus {
  status: "ready" | "generating" | "none";
  questions: QuestionSet | null;
}

export interface QuizAnswer {
  question_id: string;
  concept: string;
  difficulty: string;
  correct: boolean;
  time_taken_ms: number;
}

export interface QuizSubmit {
  user_id: string;
  lecture_id: string;
  answers: QuizAnswer[];
}

export interface ConceptScore {
  concept: string;
  attempts: number;
  correct: number;
  accuracy: number;
}

export interface QuizSession {
  session_id: string;
  user_id: string;
  lecture_id: string;
  course_id: string;
  lecture_title: string;
  score: number;
  total: number;
  answers: QuizAnswer[];
  concept_breakdown: ConceptScore[];
  completed_at: string;
}

// Feature 5 — adaptive practice
export interface ConceptMastery {
  concept: string;
  accuracy: number;
  attempts: number;
  mastered: boolean;
}

export interface AdaptiveSummary {
  mastery: ConceptMastery[];
  revisit: string[];
}

export interface AdaptiveResponse {
  status: "preparing" | "active" | "done";
  session_id?: string;
  question?: MCQQuestion | null;
  progress?: { answered: number; cap: number };
  summary?: AdaptiveSummary | null;
}
