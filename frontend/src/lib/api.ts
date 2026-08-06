const API_BASE = process.env.NEXT_PUBLIC_API_URL || "https://bookai-api-three.vercel.app/api/v1";

const SUPABASE_URL = process.env.NEXT_PUBLIC_SUPABASE_URL || "https://ynltzrdihjycufniyvlk.supabase.co";
const SUPABASE_ANON_KEY =
  process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY ||
  "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6InlubHR6cmRpaGp5Y3Vmbml5dmxrIiwicm9sZSI6ImFub24iLCJpYXQiOjE3ODYwMDQ5NjcsImV4cCI6MjEwMTU4MDk2N30.uTYgwfvdjLnA_Ed0JIW6YnGm8q4TcUJdpwaNNTefZe0";

async function request(path: string, options: RequestInit = {}) {
  const token = typeof window !== "undefined" ? localStorage.getItem("token") : null;
  const headers: Record<string, string> = {
    ...(options.headers as Record<string, string>),
  };
  if (token) headers["Authorization"] = `Bearer ${token}`;

  const res = await fetch(`${API_BASE}${path}`, { ...options, headers });
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: res.statusText }));
    throw new Error(err.detail || "Request failed");
  }
  return res.json();
}

export async function login(data: { email: string; password: string }) {
  return request("/auth/login", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(data),
  });
}

export async function register(data: { name: string; email: string; password: string }) {
  return request("/auth/register", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(data),
  });
}

export async function getMe() {
  return request("/auth/me");
}

export async function getBooks() {
  return request("/books");
}

export async function getBook(bookId: string) {
  return request(`/books/${bookId}`);
}

export async function getChapters(bookId: string) {
  return request(`/books/${bookId}/chapters`);
}

export async function uploadBook(file: File, title: string, author?: string) {
  const token = localStorage.getItem("token");

  const safeName = `${Date.now()}_${file.name.replace(/[^\w.\-]/g, "_")}`;
  const storageUrl = `${SUPABASE_URL}/storage/v1/object/books/${safeName}`;

  const upRes = await fetch(storageUrl, {
    method: "POST",
    headers: {
      Authorization: `Bearer ${SUPABASE_ANON_KEY}`,
      "Content-Type": "application/pdf",
      "x-upsert": "false",
    },
    body: file,
  });

  if (!upRes.ok) {
    const errText = await upRes.text().catch(() => "Storage upload failed");
    throw new Error(`Storage upload failed: ${upRes.status}`);
  }

  const publicUrl = `${SUPABASE_URL}/storage/v1/object/public/books/${safeName}`;

  const res = await fetch(`${API_BASE}/books/upload`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      Authorization: `Bearer ${token}`,
    },
    body: JSON.stringify({ title, author, storage_url: publicUrl, file_size: file.size }),
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: "Upload failed" }));
    throw new Error(err.detail);
  }
  return res.json();
}

export async function askQuestion(bookId: string, question: string, sessionId?: string, chapterId?: string) {
  return request("/chat", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ book_id: bookId, question, session_id: sessionId, chapter_id: chapterId }),
  });
}

export function getChatStreamUrl(bookId: string, question: string, sessionId?: string, chapterId?: string) {
  const token = localStorage.getItem("token");
  return {
    url: `${API_BASE}/chat/stream`,
    options: {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        Authorization: `Bearer ${token}`,
      },
      body: JSON.stringify({ book_id: bookId, question, session_id: sessionId, chapter_id: chapterId }),
    },
  };
}

export async function getChatSessions(bookId: string) {
  return request(`/chat/sessions/${bookId}`);
}

export async function generateTestPaper(data: {
  book_id: string;
  chapter_ids: string[];
  school_name: string;
  class_name: string;
  subject: string;
  duration: string;
  question_types: Array<{ type: string; label: string; count: number; marks_per: number }>;
  topic?: string;
}): Promise<Blob> {
  const token = localStorage.getItem("token");
  const res = await fetch(`${API_BASE}/test-paper`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      Authorization: `Bearer ${token}`,
    },
    body: JSON.stringify(data),
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: "Generation failed" }));
    throw new Error(err.detail);
  }
  return res.blob();
}

export async function generateContent(data: {
  book_id: string;
  content_type: string;
  topic?: string;
  grade_level?: string;
  additional_instructions?: string;
  chapter_id?: string;
}) {
  return request("/generate", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(data),
  });
}
