export type Difficulty = "beginner" | "intermediate" | "advanced";

export type Objective = {
  id: string;
  title: string;
  difficulty: Difficulty;
  focus: string;
};

export type Question = {
  question: string;
  options: string[];
  correctIndex: number;
  explanation: string;
  hint: string;
};

export type Quiz = { questions: Question[] };

export type Result = {
  objectiveId: string;
  objectiveTitle: string;
  score: number;
  total: number;
};

export type Summary = {
  overall: string;
  perObjective: { title: string; comment: string }[];
  studyTips: string[];
};

export type LessonStatus = "awaiting_approval" | "quizzing" | "complete";

export type LessonView = {
  id: string;
  status: LessonStatus;
  plan?: { objectives: Objective[] };
  objectives?: Objective[];
  objectiveIndex?: number;
  objectivesCount?: number;
  currentObjective?: Objective;
  quiz?: Quiz;
  results?: Result[];
  summary?: Summary;
};
