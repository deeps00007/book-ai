const API_BASE = process.env.NEXT_PUBLIC_API_URL || "https://bookai-api-three.vercel.app/api/v1";

const SUPABASE_URL = process.env.NEXT_PUBLIC_SUPABASE_URL || "https://ynltzrdihjycufniyvlk.supabase.co";
const SUPABASE_ANON_KEY =
  process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY ||
  "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6InlubHR6cmRpaGp5Y3Vmbml5dmxrIiwicm9sZSI6ImFub24iLCJpYXQiOjE3ODYwMDQ5NjcsImV4cCI6MjEwMTU4MDk2N30.uTYgwfvdjLnA_Ed0JIW6YnGm8q4TcUJdpwaNNTefZe0";

let _supabaseClient: any = null;
async function getSupabaseClient() {
  if (!_supabaseClient) {
    const { createClient } = await import("@supabase/supabase-js");
    _supabaseClient = createClient(SUPABASE_URL, SUPABASE_ANON_KEY, {
      auth: { persistSession: false },
    });
  }
  return _supabaseClient;
}

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

export async function uploadBook(
  file: File,
  title: string,
  author?: string,
  onProgress?: (pct: number, msg: string) => void
) {
  const token = localStorage.getItem("token");
  const supabase = await getSupabaseClient();

  const CHUNK_SIZE = 40 * 1024 * 1024; // 40MB per chunk (under 50MB limit)
  const totalChunks = Math.ceil(file.size / CHUNK_SIZE);
  const baseName = Date.now();
  const chunkUrls: string[] = [];

  for (let i = 0; i < totalChunks; i++) {
    const start = i * CHUNK_SIZE;
    const end = Math.min(start + CHUNK_SIZE, file.size);
    const blob = file.slice(start, end, "application/pdf");
    const chunkName = `chunks/${baseName}_part${i}.pdf`;

    if (totalChunks > 1) {
      onProgress?.(
        Math.round((i / totalChunks) * 90),
        `Uploading part ${i + 1}/${totalChunks} (${(blob.size / 1024 / 1024).toFixed(1)} MB)`
      );
    }

    const { data, error } = await supabase.storage
      .from("books")
      .upload(chunkName, blob, { cacheControl: "3600", upsert: false });

    if (error) {
      throw new Error(`Part ${i + 1} upload failed: ${error.message}`);
    }

    const url = supabase.storage.from("books").getPublicUrl(chunkName).data?.publicUrl || "";
    if (!url) throw new Error(`Failed to get public URL for part ${i + 1}`);
    chunkUrls.push(url);
  }

  if (totalChunks > 1) {
    onProgress?.(95, "Combining chunks...");
  }

  const res = await fetch(`${API_BASE}/books/upload`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      Authorization: `Bearer ${token}`,
    },
    body: JSON.stringify({
      title,
      author,
      storage_url: totalChunks === 1 ? chunkUrls[0] : "",
      storage_urls: totalChunks > 1 ? chunkUrls : undefined,
      file_size: file.size,
    }),
  });

  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: "Upload failed" }));
    throw new Error(err.detail);
  }

  const uploadResult = await res.json();

  if (uploadResult.status === "uploading" && uploadResult.book_id) {
    onProgress?.(98, "Processing book content...");
    const pRes = await fetch(`${API_BASE}/books/${uploadResult.book_id}/process`, {
      method: "POST",
      headers: { Authorization: `Bearer ${token}` },
    });
    const pResult = await pRes.json();
    if (!pRes.ok) throw new Error(pResult.message || "Processing failed");
    return pResult;
  }

  return uploadResult;
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
