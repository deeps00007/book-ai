"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { useDropzone } from "react-dropzone";
import {
  Loader2, Upload, FileText, BookOpen, X, Trash2, Download,
  Layers, RefreshCw, GraduationCap, Plus, Wand2,
} from "lucide-react";
import {
  listBooks, getBook, uploadBook, deleteBook, processBook,
  generateTestPaper, suggestPaper,
} from "@/lib/api";

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
interface QType {
  type: string;
  label: string;
  count: number;
  marks_per: number;
}

function classFromTitle(title: string): string {
  const m =
    title.match(/(?:class|grade|std|standard)\s*(\d{1,2})/i) ||
    title.match(/(\d{1,2})\s*(?:st|nd|rd|th)\b/i) ||
    title.match(/(\d{1,2})\s*$/);
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

  const [mode, setMode] = useState<"auto" | "custom">("auto");
  const [catalog, setCatalog] = useState<QType[]>([]);
  const [suggested, setSuggested] = useState<QType[]>([]);
  const [questionTypes, setQuestionTypes] = useState<QType[]>([]);
  const [addType, setAddType] = useState("");
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

  useEffect(() => {
    if (!books.some((b) => b.status !== "ready" && b.status !== "failed")) return;
    const id = setInterval(() => { load(); }, 5000);
    return () => clearInterval(id);
  }, [books, load]);

  // Refresh the auto-suggestion whenever the class standard changes.
  useEffect(() => {
    if (!selected) return;
    const t = setTimeout(async () => {
      try {
        const s = await suggestPaper(className || "Class 8");
        setCatalog(s.catalog || []);
        setSuggested(s.question_types || []);
      } catch {}
    }, 400);
    return () => clearTimeout(t);
  }, [className, selected]);

  async function openBook(b: BookItem) {
    setSelected(b);
    setChapters([]);
    setSelectedChapters([]);
    setAllChapters(true);
    setSubject(b.title);
    const cls = classFromTitle(b.title) || "Class 8";
    setClassName(cls);
    setMode("auto");
    setLoadingBook(true);
    try {
      const [detail, s] = await Promise.all([getBook(b.id), suggestPaper(cls)]);
      setChapters(detail.chapters || []);
      setCatalog(s.catalog || []);
      setSuggested(s.question_types || []);
      setQuestionTypes(s.question_types || []);
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

  function updateQType(type: string, patch: Partial<QType>) {
    setQuestionTypes((prev) => prev.map((q) => (q.type === type ? { ...q, ...patch } : q)));
  }

  function addSelected() {
    const c = catalog.find((x) => x.type === addType);
    if (!c) return;
    setQuestionTypes((prev) => [...prev, { ...c, count: 5 }]);
    setAddType("");
  }

  const activeTypes = mode === "custom" ? questionTypes : suggested;
  const totalQuestions = activeTypes.reduce((a, q) => a + (q.count || 0), 0);
  const totalMarks = activeTypes.reduce((a, q) => a + (q.count || 0) * (q.marks_per || 0), 0);

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
        question_types: mode === "custom" ? questionTypes : undefined,
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

              {/* Question setup */}
              <div className="mb-5">
                <div className="flex items-center gap-2 mb-3">
                  <label className="text-sm font-medium text-gray-700">Question paper setup</label>
                  <div className="ml-auto inline-flex rounded-lg border border-gray-300 overflow-hidden text-sm">
                    <button onClick={() => setMode("auto")}
                      className={mode === "auto" ? "bg-brand-600 text-white px-3 py-1.5 flex items-center gap-1" : "px-3 py-1.5 text-gray-600"}>
                      <Wand2 className="w-3.5 h-3.5" /> Auto
                    </button>
                    <button onClick={() => setMode("custom")}
                      className={mode === "custom" ? "bg-brand-600 text-white px-3 py-1.5" : "px-3 py-1.5 text-gray-600"}>
                      Custom
                    </button>
                  </div>
                </div>

                {mode === "auto" ? (
                  <div className="border border-gray-200 rounded-lg p-4 bg-gray-50">
                    <p className="text-xs text-gray-500 mb-2">Auto-suggested for {className || "this class"}:</p>
                    <div className="space-y-1">
                      {suggested.length === 0 && <p className="text-sm text-gray-400">Set a class to see the suggestion.</p>}
                      {suggested.map((q) => (
                        <div key={q.type} className="flex justify-between text-sm">
                          <span>{q.label}</span>
                          <span className="text-gray-500">{q.count} × {q.marks_per} = {q.count * q.marks_per} marks</span>
                        </div>
                      ))}
                    </div>
                    <div className="flex justify-between text-sm font-medium mt-2 pt-2 border-t border-gray-200">
                      <span>Total</span>
                      <span>{totalQuestions} questions · {totalMarks} marks</span>
                    </div>
                  </div>
                ) : (
                  <div className="border border-gray-200 rounded-lg p-4 space-y-3">
                    {questionTypes.length === 0 && <p className="text-sm text-gray-400">Add question types below.</p>}
                    {questionTypes.map((q) => (
                      <div key={q.type} className="flex items-center gap-3">
                        <span className="flex-1 text-sm truncate">{q.label}</span>
                        <div className="flex items-center gap-1">
                          <input type="number" min={1} value={q.count}
                            onChange={(e) => updateQType(q.type, { count: Math.max(1, parseInt(e.target.value) || 1) })}
                            className="w-16 px-2 py-1.5 border border-gray-300 rounded-lg text-sm outline-none focus:ring-2 focus:ring-brand-500" />
                          <span className="text-xs text-gray-400">×</span>
                          <input type="number" min={1} value={q.marks_per}
                            onChange={(e) => updateQType(q.type, { marks_per: Math.max(1, parseInt(e.target.value) || 1) })}
                            className="w-16 px-2 py-1.5 border border-gray-300 rounded-lg text-sm outline-none focus:ring-2 focus:ring-brand-500" />
                          <span className="text-xs text-gray-400">marks</span>
                        </div>
                        <button onClick={() => setQuestionTypes((prev) => prev.filter((x) => x.type !== q.type))}
                          className="p-1 text-gray-400 hover:text-red-500">
                          <Trash2 className="w-4 h-4" />
                        </button>
                      </div>
                    ))}
                    <div className="flex flex-wrap gap-2 pt-1">
                      <select value={addType} onChange={(e) => setAddType(e.target.value)}
                        className="flex-1 min-w-[180px] px-3 py-2 border border-gray-300 rounded-lg text-sm outline-none focus:ring-2 focus:ring-brand-500">
                        <option value="">Add a question type…</option>
                        {catalog.filter((c) => !questionTypes.some((q) => q.type === c.type)).map((c) => (
                          <option key={c.type} value={c.type}>{c.label}</option>
                        ))}
                      </select>
                      <button onClick={addSelected} disabled={!addType}
                        className="px-3 py-2 bg-brand-50 text-brand-700 rounded-lg text-sm font-medium hover:bg-brand-100 disabled:opacity-50 flex items-center gap-1">
                        <Plus className="w-4 h-4" /> Add
                      </button>
                      <button onClick={() => setQuestionTypes(suggested)}
                        className="px-3 py-2 text-gray-600 rounded-lg text-sm hover:bg-gray-100 flex items-center gap-1">
                        <Wand2 className="w-4 h-4" /> Use suggested
                      </button>
                    </div>
                    <div className="flex justify-between text-sm font-medium pt-2 border-t border-gray-200">
                      <span>Total</span>
                      <span>{totalQuestions} questions · {totalMarks} marks</span>
                    </div>
                  </div>
                )}
              </div>

              <button onClick={handleGenerate}
                disabled={generating || (mode === "custom" && questionTypes.length === 0)}
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
