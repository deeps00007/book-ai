export interface User {
  id: string;
  email: string;
  name: string;
  role: string;
}

export interface Chapter {
  id: string;
  book_id: string;
  title: string;
  order: number;
  start_page: number;
  end_page: number;
}

export interface Book {
  id: string;
  title: string;
  author?: string;
  total_pages: number;
  total_chunks: number;
  status: string;
  created_at: string;
}

export interface ChatSession {
  id: string;
  book_id: string;
  title: string;
  created_at: string;
  updated_at: string;
}

export interface ChatMessage {
  id: string;
  session_id: string;
  role: "user" | "assistant";
  content: string;
  sources?: any;
  provider?: string;
  model?: string;
  tokens_used?: number;
}

export interface ChatResponse {
  answer: string;
  session_id: string;
  sources: Array<{
    id: string;
    content: string;
    chunk_index: number;
    page_start: number;
    page_end: number;
    similarity: number;
  }>;
  provider: string;
  model: string;
  tokens_used: number;
  response_time_ms: number;
}

export interface GeneratedContent {
  content_id: string;
  content_type: string;
  title: string;
  content: Record<string, any>;
}
