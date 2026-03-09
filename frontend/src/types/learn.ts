export interface Course {
  course_id: string;
  title: string;
  lecture_count: number;
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
  course_id: string;
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
  lecture: string;
}

export interface QuestionSet {
  course_id: string;
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
  lecture: string;
}

export interface QuizSubmit {
  user_id: string;
  course_id: string;
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
  course_id: string;
  course_title: string;
  score: number;
  total: number;
  answers: QuizAnswer[];
  concept_breakdown: ConceptScore[];
  completed_at: string;
}

// Adaptive practice
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

// Recommendations
export interface Recommendation {
  course_id: string;
  course_title: string;
  reason: string;
}

export interface RecommendationsResponse {
  user_id: string;
  recommendations: Recommendation[];
  generated_at: string;
  cached: boolean;
}

// Per-course "how you're doing" insight
export interface CourseInsight {
  summary: string;
  doing_well: string[];
  improve: string[];
  next_steps: string[];
}

// Learning-journey analytics (dashboard)
export interface JourneyMetrics {
  quizzes: number;
  questions_answered: number;
  avg_score: number;
  active_days: number;
  streak: number;
  courses_engaged: number;
  concepts_practiced: number;
  concepts_mastered: number;
  concepts_weak: number;
  practice_minutes: number;
  avg_seconds_per_question: number;
}

export interface HeatCell {
  date: string;
  count: number;
}

export interface ConceptStat {
  concept: string;
  accuracy: number;
  attempts: number;
}

export interface Journey {
  metrics: JourneyMetrics;
  heatmap: HeatCell[];
  strengths: ConceptStat[];
  weaknesses: ConceptStat[];
  ai: { narrative: string; insights: string[]; focus: string };
}

