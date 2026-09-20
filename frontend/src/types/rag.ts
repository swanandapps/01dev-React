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
  offer_general?: boolean;   // out of scope — show "answer from general knowledge" button
  general_prompt?: string;   // the question to re-ask with consent
  streaming?: boolean;
  timestamp: Date;
}

// Maps RAG course_id slugs (backend corpus) → numeric platform course IDs (tracks.ts),
// so a source card deep-links to /course/{id}?t={start_time} and seeks the video.
export const RAG_COURSE_MAP: Record<string, number> = {
  // Slugs the current transcript corpus actually emits → their course pages.
  "custom-library": 2, // Build a Custom Library (has recorded video → full seek)
  "javascript-deep-dive": 9, // JavaScript Deep Dive
  "web-apis": 10, // Web APIs and Real-Time
  "react-perf": 11, // React Performance Patterns
  // Other platform courses — mapped for when their transcripts are seeded.
  "programming-language": 1,
  "product-engineering": 4,
  "state-management": 5,
  "web-framework": 6,
  "js-engine": 7,
  "real-time": 8,
};
