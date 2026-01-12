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
