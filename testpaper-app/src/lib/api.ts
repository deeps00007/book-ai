const API_BASE =
  process.env.NEXT_PUBLIC_API_URL || "https://bookai-api-three.vercel.app/api/v1";

const SUPABASE_URL =
  process.env.NEXT_PUBLIC_SUPABASE_URL || "https://ynltzrdihjycufniyvlk.supabase.co";
const SUPABASE_ANON_KEY =
  process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY ||
  "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6InlubHR6cmRpaGp5Y3Vmbml5dmxrIiwicm9sZSI6ImFub24iLCJpYXQiOjE3ODYwMDQ5NjcsImV4cCI6MjEwMTU4MDk2N30.uTYgwfvdjLnA_Ed0JIW6YnGm8q4TcUJdpwaNNTefZe0";

let _supabase: any = null;
async function supabase() {
  if (!_supabase) {
    const { createClient } = await import("@supabase/supabase-js");
    _supabase = createClient(SUPABASE_URL, SUPABASE_ANON_KEY, {
      auth: { persistSession: false },
    });
  }
  return _supabase;
}

async function req(path: string, options: RequestInit = {}) {
  const res = await fetch(`${API_BASE}${path}`, options);
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: res.statusText }));
    throw new Error(err.detail || "Request failed");
  }
  return res.json();
}

export function listBooks() {
  return req("/public/books");
}

export function getBook(id: string) {
  return req(`/public/books/${id}`);
}

export function deleteBook(id: string) {
  return req(`/public/books/${id}`, { method: "DELETE" });
}

export function processBook(id: string) {
  return req(`/public/books/${id}/process`, { method: "POST" });
}

async function driveConfigured(): Promise<boolean> {
  try {
    const r = await fetch(`${API_BASE}/public/books/drive-session`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ filename: "probe.pdf", mime_type: "application/pdf" }),
    });
    return r.ok;
  } catch {
    return false;
  }
}

export async function uploadBook(
  file: File,
  title: string,
  author?: string,
  onProgress?: (pct: number, msg: string) => void
) {
  const useDrive = await driveConfigured();
  return useDrive
    ? uploadViaDrive(file, title, author, onProgress)
    : uploadViaStorage(file, title, author, onProgress);
}

async function uploadViaDrive(
  file: File,
  title: string,
  author?: string,
  onProgress?: (pct: number, msg: string) => void
) {
  onProgress?.(2, "Preparing Google Drive upload...");
  const sessRes = await fetch(`${API_BASE}/public/books/drive-session`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      filename: file.name,
      mime_type: "application/pdf",
      origin: typeof window !== "undefined" ? window.location.origin : "",
    }),
  });
  if (!sessRes.ok) {
    const err = await sessRes.json().catch(() => ({ detail: "Drive session failed" }));
    throw new Error(err.detail || "Could not start Drive upload");
  }
  const { upload_url } = await sessRes.json();

  const fileId: string = await new Promise((resolve, reject) => {
    const xhr = new XMLHttpRequest();
    xhr.open("PUT", upload_url, true);
    xhr.setRequestHeader("Content-Type", "application/pdf");
    xhr.upload.onprogress = (e) => {
      if (e.lengthComputable) {
        const pct = Math.round((e.loaded / e.total) * 85) + 5;
        const mb = (e.loaded / 1024 / 1024).toFixed(1);
        const totalMb = (e.total / 1024 / 1024).toFixed(1);
        onProgress?.(pct, `Uploading ${mb}/${totalMb} MB`);
      }
    };
    xhr.onload = () => {
      if (xhr.status >= 200 && xhr.status < 300) {
        try {
          resolve(JSON.parse(xhr.responseText).id);
        } catch {
          reject(new Error("Invalid response from Google Drive"));
        }
      } else {
        reject(new Error(`Upload failed (${xhr.status})`));
      }
    };
    xhr.onerror = () => reject(new Error("Upload network error"));
    xhr.send(file);
  });

  onProgress?.(92, "Processing book (chapters + index)...");
  return req("/public/books/upload-drive", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ title, author, drive_file_id: fileId, file_size: file.size }),
  });
}

async function uploadViaStorage(
  file: File,
  title: string,
  author?: string,
  onProgress?: (pct: number, msg: string) => void
) {
  const sb = await supabase();
  const CHUNK = 40 * 1024 * 1024;
  const total = Math.ceil(file.size / CHUNK);
  const base = Date.now();
  const urls: string[] = [];
  for (let i = 0; i < total; i++) {
    const blob = file.slice(i * CHUNK, Math.min((i + 1) * CHUNK, file.size), "application/pdf");
    const name = `chunks/${base}_part${i}.pdf`;
    onProgress?.(Math.round((i / total) * 90), `Uploading part ${i + 1}/${total}...`);
    const { error } = await sb.storage.from("books").upload(name, blob, { upsert: false });
    if (error) throw new Error(`Part ${i + 1} failed: ${error.message}`);
    urls.push(sb.storage.from("books").getPublicUrl(name).data?.publicUrl || "");
  }
  onProgress?.(95, "Processing book (chapters + index)...");
  return req("/public/books/upload", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      title,
      author,
      storage_url: total === 1 ? urls[0] : "",
      storage_urls: total > 1 ? urls : undefined,
      file_size: file.size,
    }),
  });
}

export function suggestPaper(class_name: string) {
  return req(`/public/test-paper/suggest?class_name=${encodeURIComponent(class_name)}`);
}

export async function generateTestPaper(payload: {
  book_id: string;
  chapter_ids: string[];
  school_name: string;
  class_name: string;
  subject: string;
  duration: string;
  topic?: string;
  difficulty?: string;
  question_types?: Array<{ type: string; label: string; count: number; marks_per: number }>;
}): Promise<Blob> {
  const res = await fetch(`${API_BASE}/public/test-paper`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: "Generation failed" }));
    throw new Error(err.detail || "Generation failed");
  }
  return res.blob();
}
