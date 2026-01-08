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
