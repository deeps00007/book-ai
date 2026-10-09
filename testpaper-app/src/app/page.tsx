"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { useDropzone } from "react-dropzone";
import {
  Loader2, Upload, FileText, BookOpen, X, Check, Trash2, Download,
  Layers, RefreshCw, GraduationCap,
} from "lucide-react";
import { listBooks, getBook, uploadBook, deleteBook, processBook, generateTestPaper } from "@/lib/api";

interface BookItem {
  id: string;
  title: string;
  author?: string | null;
  status: string;
  total_pages: number;
  total_chunks: number;
  error_message?: string | null;
}
interface ChapterItem {
  id: string;
  title: string;
  order: number;
  start_page: number;
  end_page: number;
}

function classFromTitle(title: string): string {
  const m = title.match(/(?:class|grade|std|standard)\s*(\d{1,2})/i) || title.match(/(\d{1,2})\s*(?:st|nd|rd|th)\b/i) || title.match(/(\d{1,2})\s*$/);
  return m ? `Class ${m[1]}` : "";
}

export default function Home() {
  const [books, setBooks] = useState<BookItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [selected, setSelected] = useState<BookItem | null>(null);
  const [chapters, setChapters] = useState<ChapterItem[]>([]);
  const [loadingBook, setLoadingBook] = useState(false);
  const [selectedChapters, setSelectedChapters] = useState<string[]>([]);
  const [allChapters, setAllChapters] = useState(true);

  const [school, setSchool] = useState("Examination");
  const [className, setClassName] = useState("");
  const [subject, setSubject] = useState("");
  const [duration, setDuration] = useState("1 Hour");
  const [generating, setGenerating] = useState(false);

  const [file, setFile] = useState<File | null>(null);
  const [title, setTitle] = useState("");
  const [author, setAuthor] = useState("");
  const [uploading, setUploading] = useState(false);
  const [progress, setProgress] = useState(0);
  const [progressMsg, setProgressMsg] = useState("");
  const fileInputRef = useRef<HTMLInputElement>(null);

  const load = useCallback(async () => {
    try {
      setBooks(await listBooks());
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { load(); }, [load]);

  // poll while any book is still processing
  useEffect(() => {
    if (!books.some((b) => b.status !== "ready" && b.status !== "failed")) return;
    const id = setInterval(() => { load(); }, 5000);
    return () => clearInterval(id);
  }, [books, load]);

  async function openBook(b: BookItem) {
    setSelected(b);
    setChapters([]);
    setSelectedChapters([]);
    setAllChapters(true);
    setSubject(b.title);
    setClassName(classFromTitle(b.title) || "Class 8");
    setLoadingBook(true);
    try {
      const detail = await getBook(b.id);
      setChapters(detail.chapters || []);
    } finally {
      setLoadingBook(false);
    }
  }

  const onDrop = useCallback((accepted: File[]) => {
    const f = accepted[0];
    if (!f) return;
    setFile(f);
    setTitle(f.name.replace(/\.pdf$/i, "").replace(/[_-]/g, " "));
  }, []);

  const { getRootProps, getInputProps, isDragActive } = useDropzone({
    onDrop,
    accept: { "application/pdf": [".pdf"] },
    maxFiles: 1,
  });

  async function handleUpload() {
    if (!file || !title) return;
    setUploading(true);
    setProgress(0);
    setProgressMsg("Starting...");
    try {
      const result = await uploadBook(file, title, author, (pct, msg) => {
        setProgress(pct);
        setProgressMsg(msg);
      });
      setProgress(100);
      setProgressMsg(result?.status === "ready" ? "Ready!" : "Queued for processing...");
      setFile(null);
      setTitle("");
      setAuthor("");
      await load();
    } catch (e: any) {
      setProgressMsg(e.message || "Upload failed");
    } finally {
      setUploading(false);
    }
  }

  async function handleDelete(b: BookItem) {
    if (!confirm(`Delete "${b.title}"?`)) return;
    await deleteBook(b.id);
    if (selected?.id === b.id) setSelected(null);
    load();
  }

  async function handleProcess(b: BookItem) {
    try {
      await processBook(b.id);
      load();
    } catch (e: any) {
      alert(e.message || "Processing failed");
    }
  }

  async function handleGenerate() {
    if (!selected) return;
    setGenerating(true);
    try {
      const blob = await generateTestPaper({
        book_id: selected.id,
        chapter_ids: allChapters ? [] : selectedChapters,
        school_name: school,
        class_name: className,
        subject: subject || selected.title,
        duration,
        topic: subject || selected.title,
      });
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = `Test_Paper_${(subject || "paper").replace(/\s+/g, "_")}.pdf`;
      a.click();
      URL.revokeObjectURL(url);
    } catch (e: any) {
      alert(e.message || "Generation failed");
    } finally {
      setGenerating(false);
    }
  }

  const readyBooks = useMemo(() => books.filter((b) => b.status === "ready"), [books]);

  return (
    <div className="max-w-5xl mx-auto px-6 py-10">
      <header className="flex items-center gap-3 mb-8">
        <div className="w-11 h-11 rounded-xl bg-brand-600 flex items-center justify-center">
          <GraduationCap className="w-6 h-6 text-white" />
        </div>
        <div>
          <h1 className="text-2xl font-bold">Test Paper Generator</h1>
          <p className="text-sm text-gray-500">Upload a textbook, pick chapters, generate a class-appropriate paper.</p>
        </div>
      </header>

      {/* Upload */}
      <section className="bg-white rounded-2xl border border-gray-200 p-6 mb-8">
        <h2 className="font-semibold mb-4 flex items-center gap-2">
          <Upload className="w-5 h-5 text-brand-600" /> Upload a book
        </h2>

        {!file ? (
          <div
            {...getRootProps()}
            className={`border-2 border-dashed rounded-xl p-10 text-center cursor-pointer transition-colors ${
              isDragActive ? "border-brand-500 bg-brand-50" : "border-gray-300 hover:border-brand-400 hover:bg-brand-50/40"
            }`}
          >
            <input {...getInputProps()} ref={fileInputRef} />
            <Upload className="w-10 h-10 text-gray-400 mx-auto mb-3" />
            <p className="text-gray-600 font-medium">
              {isDragActive ? "Drop your PDF here" : "Drag & drop a PDF, or click to browse"}
            </p>
          </div>
        ) : (
          <div className="space-y-4">
            <div className="flex items-center gap-4 p-3 bg-gray-50 rounded-lg">
              <FileText className="w-9 h-9 text-brand-600 shrink-0" />
              <div className="flex-1 min-w-0">
                <p className="font-medium truncate">{file.name}</p>
                <p className="text-sm text-gray-500">{(file.size / 1024 / 1024).toFixed(1)} MB</p>
              </div>
              {!uploading && (
                <button onClick={() => setFile(null)} className="p-1 hover:bg-gray-200 rounded">
                  <X className="w-5 h-5 text-gray-400" />
                </button>
              )}
            </div>
            <div className="grid sm:grid-cols-2 gap-4">
              <div>
                <label className="block text-sm font-medium text-gray-700 mb-1">Title *</label>
                <input value={title} onChange={(e) => setTitle(e.target.value)} disabled={uploading}
                  className="w-full px-3 py-2.5 border border-gray-300 rounded-lg outline-none focus:ring-2 focus:ring-brand-500"
                  placeholder="e.g. Chemistry Class 6" />
              </div>
              <div>
                <label className="block text-sm font-medium text-gray-700 mb-1">Author (optional)</label>
                <input value={author} onChange={(e) => setAuthor(e.target.value)} disabled={uploading}
                  className="w-full px-3 py-2.5 border border-gray-300 rounded-lg outline-none focus:ring-2 focus:ring-brand-500"
                  placeholder="e.g. NCERT" />
              </div>
            </div>
            {uploading && (
              <div className="space-y-2">
                <div className="flex justify-between text-sm text-gray-600">
                  <span>{progressMsg}</span><span className="font-medium text-brand-600">{progress}%</span>
                </div>
                <div className="w-full h-2.5 bg-gray-200 rounded-full overflow-hidden">
                  <div className="h-full bg-brand-600 rounded-full transition-all" style={{ width: `${progress}%` }} />
                </div>
              </div>
            )}
            <button onClick={handleUpload} disabled={!title || uploading}
              className="w-full py-3 bg-brand-600 text-white rounded-lg font-medium hover:bg-brand-700 disabled:opacity-50 flex items-center justify-center gap-2">
              {uploading ? <><Loader2 className="w-4 h-4 animate-spin" /> Uploading...</> : <><Upload className="w-4 h-4" /> Upload & Process</>}
            </button>
          </div>
        )}
      </section>

      {/* Books */}
      <section className="mb-8">
        <h2 className="font-semibold mb-4 flex items-center gap-2">
          <BookOpen className="w-5 h-5 text-brand-600" /> Your books
          <button onClick={load} className="ml-auto text-gray-400 hover:text-gray-600" title="Refresh">
            <RefreshCw className="w-4 h-4" />
          </button>
        </h2>
        {loading ? (
          <div className="flex justify-center py-10"><Loader2 className="w-6 h-6 animate-spin text-brand-600" /></div>
        ) : books.length === 0 ? (
          <p className="text-center text-gray-400 py-8">No books yet — upload one above.</p>
        ) : (
          <div className="grid gap-3">
            {books.map((b) => (
              <div key={b.id}
                className={`flex items-center gap-4 p-4 rounded-xl border bg-white transition-all ${
                  selected?.id === b.id ? "border-brand-400 ring-1 ring-brand-200" : "border-gray-200 hover:border-brand-300"
                }`}>
                <button onClick={() => b.status === "ready" && openBook(b)} className="flex items-center gap-4 flex-1 text-left min-w-0">
                  <div className="w-10 h-10 rounded-lg bg-brand-50 flex items-center justify-center shrink-0">
                    <BookOpen className="w-5 h-5 text-brand-600" />
                  </div>
                  <div className="min-w-0">
                    <p className="font-medium truncate">{b.title}</p>
                    <p className="text-xs text-gray-500">
                      {b.total_pages} pages · <span className={
                        b.status === "ready" ? "text-green-600" : b.status === "failed" ? "text-red-600" : "text-amber-600"
                      }>{b.status}</span>
                    </p>
                  </div>
                </button>
                {b.status !== "ready" && b.status !== "failed" && <Loader2 className="w-4 h-4 animate-spin text-amber-500" />}
                {(b.status === "failed" || b.status === "uploaded") && (
                  <button onClick={() => handleProcess(b)} className="text-xs px-3 py-1.5 bg-amber-500 text-white rounded-lg hover:bg-amber-600">
                    Process
                  </button>
                )}
                <button onClick={() => handleDelete(b)} className="p-1.5 text-gray-400 hover:text-red-500" title="Delete">
                  <Trash2 className="w-4 h-4" />
                </button>
              </div>
            ))}
          </div>
        )}
      </section>

      {/* Generate */}
      {selected && (
        <section className="bg-white rounded-2xl border border-gray-200 p-6">
          <h2 className="font-semibold mb-4 flex items-center gap-2">
            <Layers className="w-5 h-5 text-brand-600" /> Generate test paper — {selected.title}
          </h2>

          {loadingBook ? (
            <div className="flex justify-center py-8"><Loader2 className="w-6 h-6 animate-spin text-brand-600" /></div>
          ) : (
            <>
              <div className="mb-5">
                <div className="flex items-center justify-between mb-2">
                  <label className="text-sm font-medium text-gray-700">Chapters</label>
                  <label className="flex items-center gap-2 text-sm text-gray-600">
                    <input type="checkbox" checked={allChapters} onChange={(e) => setAllChapters(e.target.checked)} />
                    Whole book
                  </label>
                </div>
                {!allChapters && (
                  <div className="max-h-48 overflow-y-auto border border-gray-200 rounded-lg divide-y">
                    {chapters.map((c) => (
                      <label key={c.id} className="flex items-center gap-3 px-3 py-2 text-sm hover:bg-gray-50 cursor-pointer">
                        <input type="checkbox"
                          checked={selectedChapters.includes(c.id)}
                          onChange={(e) => setSelectedChapters((prev) =>
                            e.target.checked ? [...prev, c.id] : prev.filter((x) => x !== c.id))} />
                        <span className="flex-1 truncate">{c.title}</span>
                        <span className="text-xs text-gray-400">p. {c.start_page}–{c.end_page}</span>
                      </label>
                    ))}
                  </div>
                )}
              </div>

              <div className="grid sm:grid-cols-2 gap-4 mb-5">
                <div>
                  <label className="block text-sm font-medium text-gray-700 mb-1">Class / Standard</label>
                  <input value={className} onChange={(e) => setClassName(e.target.value)}
                    className="w-full px-3 py-2.5 border border-gray-300 rounded-lg outline-none focus:ring-2 focus:ring-brand-500"
                    placeholder="e.g. Class 6" />
                  <p className="text-xs text-gray-400 mt-1">Difficulty is set automatically for this class.</p>
                </div>
                <div>
                  <label className="block text-sm font-medium text-gray-700 mb-1">Subject</label>
                  <input value={subject} onChange={(e) => setSubject(e.target.value)}
                    className="w-full px-3 py-2.5 border border-gray-300 rounded-lg outline-none focus:ring-2 focus:ring-brand-500" />
                </div>
                <div>
                  <label className="block text-sm font-medium text-gray-700 mb-1">School / Institute</label>
                  <input value={school} onChange={(e) => setSchool(e.target.value)}
                    className="w-full px-3 py-2.5 border border-gray-300 rounded-lg outline-none focus:ring-2 focus:ring-brand-500" />
                </div>
                <div>
                  <label className="block text-sm font-medium text-gray-700 mb-1">Duration</label>
                  <input value={duration} onChange={(e) => setDuration(e.target.value)}
                    className="w-full px-3 py-2.5 border border-gray-300 rounded-lg outline-none focus:ring-2 focus:ring-brand-500" />
                </div>
              </div>

              <button onClick={handleGenerate} disabled={generating || (!allChapters && selectedChapters.length === 0)}
                className="w-full py-3 bg-brand-600 text-white rounded-lg font-medium hover:bg-brand-700 disabled:opacity-50 flex items-center justify-center gap-2">
                {generating ? <><Loader2 className="w-4 h-4 animate-spin" /> Generating paper...</> : <><Download className="w-4 h-4" /> Generate & Download PDF</>}
              </button>
            </>
          )}
        </section>
      )}
    </div>
  );
}
