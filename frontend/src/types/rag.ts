export interface RagSourceCard {
  course_id: string;
  course_title: string;
  lecture_id: string;
  lecture_title: string;
  timestamp: string;
  start_time: number;
  end_time: number;
  snippet: string;
  score: number;
}

export interface AskResponse {
  answer: string;
  sources: RagSourceCard[];
  insufficient_context: boolean;
  model: string;
}

export interface ChatMessage {
  id: string;
  role: "user" | "assistant";
  content: string;
  sources?: RagSourceCard[];
  insufficient_context?: boolean;
  timestamp: Date;
}

// Maps RAG course_id slugs to numeric platform course IDs
export const RAG_COURSE_MAP: Record<string, number> = {
  "custom-library": 2,
  "programming-language": 1,
  "product-engineering": 4,
  "state-management": 5,
  "web-framework": 6,
  "js-engine": 7,
  "real-time": 8,
};
