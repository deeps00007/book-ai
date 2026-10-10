"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { useDropzone } from "react-dropzone";
import { toast } from "sonner";
import {
  Loader2, Upload, FileText, BookOpen, X, Trash2, Download,
  Layers, RefreshCw, GraduationCap, Plus, Wand2, ChevronUp, ChevronDown,
  Sparkles, HelpCircle, Check, ClipboardList,
} from "lucide-react";
import {
  listBooks, getBook, uploadBook, deleteBook, processBook,
  generatePaperQuestions, buildPaperPdf, suggestPaper,
} from "@/lib/api";
import { Tour, type TourStep } from "@/components/Tour";

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
interface Q {
  type: string;
  question: string;
  marks: number;
  options?: Record<string, string>;
  answer?: string;
}

const FALLBACK_TYPES: QType[] = [
  { type: "mcq", label: "Multiple Choice Questions", count: 1, marks_per: 1 },
  { type: "fill_blank", label: "Fill in the Blanks", count: 1, marks_per: 1 },
  { type: "true_false", label: "True / False", count: 1, marks_per: 1 },
  { type: "very_short", label: "Very Short Answer Questions", count: 1, marks_per: 1 },
  { type: "short_answer", label: "Short Answer Questions", count: 1, marks_per: 2 },
  { type: "long_answer", label: "Long Answer Questions", count: 1, marks_per: 5 },
];

function classFromTitle(title: string): string {
  const m =
    title.match(/(?:class|grade|std|standard)\s*(\d{1,2})/i) ||
    title.match(/(\d{1,2})\s*(?:st|nd|rd|th)\b/i) ||
    title.match(/(\d{1,2})\s*$/);
  return m ? `Class ${m[1]}` : "";
}

function Section({
  id,
  icon,
  title,
  action,
  children,
}: {
  id?: string;
  icon: React.ReactNode;
  title: string;
  action?: React.ReactNode;
  children: React.ReactNode;
}) {
  return (
    <section id={id} className="bg-white rounded-2xl border border-gray-200 shadow-sm p-6 scroll-mt-24">
      <div className="flex items-center gap-3 mb-5">
        <div className="w-9 h-9 rounded-xl bg-brand-50 flex items-center justify-center text-brand-600">
          {icon}
        </div>
        <h2 className="font-semibold text-gray-900">{title}</h2>
        {action && <div className="ml-auto">{action}</div>}
      </div>
      {children}
    </section>
  );
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
  const [building, setBuilding] = useState(false);
  const [paper, setPaper] = useState<Q[] | null>(null);
  const [preview, setPreview] = useState<{ url: string; name: string } | null>(null);
  const [tourOpen, setTourOpen] = useState(false);

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
    } catch {
      toast.error("Couldn't load books");
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

  // first-visit tour
  useEffect(() => {
    try {
      if (!localStorage.getItem("tp_tour_v1")) setTourOpen(true);
    } catch {}
  }, []);
  function closeTour() {
    try { localStorage.setItem("tp_tour_v1", "1"); } catch {}
    setTourOpen(false);
  }

  async function openBook(b: BookItem) {
    setSelected(b);
    setChapters([]);
    setSelectedChapters([]);
    setAllChapters(true);
    setSubject(b.title);
    setPaper(null);
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
    } catch {
      toast.error("Couldn't open that book");
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
      toast.success(result?.status === "ready" ? "Book is ready!" : "Uploaded — processing started");
      setFile(null);
      setTitle("");
      setAuthor("");
      await load();
    } catch (e: any) {
      toast.error(e.message || "Upload failed");
    } finally {
      setUploading(false);
    }
  }

  async function handleDelete(b: BookItem) {
    if (!confirm(`Delete "${b.title}"?`)) return;
    await deleteBook(b.id);
    if (selected?.id === b.id) setSelected(null);
    toast.success("Book deleted");
    load();
  }

  async function handleProcess(b: BookItem) {
    try {
      await processBook(b.id);
      toast.success("Processing started");
      load();
    } catch (e: any) {
      toast.error(e.message || "Processing failed");
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
    setPaper(null);
    try {
      const data = await generatePaperQuestions({
        book_id: selected.id,
        chapter_ids: allChapters ? [] : selectedChapters,
        school_name: school,
        class_name: className,
        subject: subject || selected.title,
        duration,
        topic: subject || selected.title,
        question_types: mode === "custom" ? questionTypes : undefined,
      });
      setPaper(data.questions || []);
      toast.success(`Generated ${(data.questions || []).length} questions`);
      setTimeout(() => document.getElementById("editor")?.scrollIntoView({ behavior: "smooth" }), 100);
    } catch (e: any) {
      toast.error(e.message || "Generation failed");
    } finally {
      setGenerating(false);
    }
  }

  function setQ(i: number, patch: Partial<Q>) {
    setPaper((p) => (p ? p.map((q, j) => (j === i ? { ...q, ...patch } : q)) : p));
  }
  function setOption(i: number, key: string, val: string) {
    setPaper((p) => (p ? p.map((q, j) => (j === i ? { ...q, options: { ...(q.options || {}), [key]: val } } : q)) : p));
  }
  function moveQ(i: number, dir: number) {
    setPaper((p) => {
      if (!p) return p;
      const j = i + dir;
      if (j < 0 || j >= p.length) return p;
      const copy = [...p];
      [copy[i], copy[j]] = [copy[j], copy[i]];
      return copy;
    });
  }
  function removeQ(i: number) {
    setPaper((p) => (p ? p.filter((_, j) => j !== i) : p));
  }
  function addQ() {
    setPaper((p) => [...(p || []), { type: "short_answer", question: "", marks: 2 }]);
  }
  const editableTypes = catalog.length ? catalog : FALLBACK_TYPES;

  async function previewPdf() {
    if (!paper) return;
    setBuilding(true);
    try {
      const data = {
        school_name: school,
        class_name: className,
        subject: subject || selected?.title || "",
        duration,
        questions: paper.map((q, i) => ({ ...q, number: i + 1 })),
      };
      const blob = await buildPaperPdf(data);
      const url = URL.createObjectURL(blob);
      setPreview({ url, name: `Test_Paper_${(subject || "paper").replace(/\s+/g, "_")}.pdf` });
    } catch (e: any) {
      toast.error(e.message || "PDF build failed");
    } finally {
      setBuilding(false);
    }
  }

  function closePreview() {
    if (preview) URL.revokeObjectURL(preview.url);
    setPreview(null);
  }

  const paperMarks = useMemo(
    () => (paper || []).reduce((a, q) => a + (Number(q.marks) || 0), 0),
    [paper]
  );

  const hasReady = books.some((b) => b.status === "ready");
  const currentStep = paper ? 4 : selected ? 3 : hasReady ? 2 : 1;
  const stepLabels = ["Upload", "Select book", "Configure", "Generate & edit"];

  const tourSteps: TourStep[] = [
    { target: "tour-upload", title: "Upload a textbook", body: "Drop a PDF here. We store it and break it into chapters automatically." },
    { target: "tour-books", title: "Choose your book", body: "Processed books show up here. Click one to start building a paper from it." },
    ...(selected
      ? [
          { target: "tour-config", title: "Chapters & class", body: "Pick the whole book or specific chapters, and set the class — the difficulty adapts automatically." } as TourStep,
          { target: "tour-questions", title: "Set the paper format", body: "Keep the AI-suggested mix, or switch to Custom to choose question types, counts and marks." } as TourStep,
          { target: "tour-generate", title: "Generate", body: "Create the questions, then fine-tune each one before downloading." } as TourStep,
        ]
      : []),
    { title: "Edit, preview & download", body: "After generating, edit any question inline, reorder or delete them, then preview the PDF before downloading." },
  ];

  return (
    <div className="min-h-screen">
      {/* Header */}
      <header className="sticky top-0 z-40 bg-white/80 backdrop-blur border-b border-gray-200">
        <div className="max-w-6xl mx-auto px-6 h-16 flex items-center gap-3">
          <div className="w-9 h-9 rounded-xl bg-gradient-to-br from-brand-500 to-indigo-600 flex items-center justify-center shadow-sm">
            <GraduationCap className="w-5 h-5 text-white" />
          </div>
          <div className="leading-tight">
            <p className="font-bold text-gray-900">Test Paper Generator</p>
            <p className="text-xs text-gray-500">Chapter-wise papers from any textbook</p>
          </div>
          <button
            onClick={() => setTourOpen(true)}
            className="ml-auto flex items-center gap-1.5 px-3.5 py-2 rounded-xl text-sm font-medium text-gray-700 hover:bg-gray-100 border border-gray-200"
          >
            <HelpCircle className="w-4 h-4" /> How it works
          </button>
        </div>
      </header>

      <div className="max-w-6xl mx-auto px-6 py-8 space-y-8">
        {/* Hero + stepper */}
        <section className="rounded-2xl p-6 sm:p-8 text-white bg-gradient-to-r from-brand-600 via-brand-600 to-indigo-600 shadow-sm">
          <h1 className="text-2xl sm:text-3xl font-bold">Create a class-ready question paper in minutes</h1>
          <p className="text-white/85 mt-2 max-w-2xl">
            Upload a textbook, choose the chapters and class standard, and let AI draft a paper you can fully edit before downloading.
          </p>
          <div className="flex flex-wrap items-center gap-x-6 gap-y-3 mt-6">
            {stepLabels.map((label, idx) => {
              const n = idx + 1;
              const done = n < currentStep;
              const active = n === currentStep;
              return (
                <div key={label} className="flex items-center gap-2">
                  <span className={`w-6 h-6 rounded-full flex items-center justify-center text-xs font-semibold ${
                    active ? "bg-white text-brand-700" : done ? "bg-white/90 text-brand-700" : "bg-white/20 text-white"
                  }`}>
                    {done ? <Check className="w-3.5 h-3.5" /> : n}
                  </span>
                  <span className={`text-sm ${active ? "font-semibold" : "text-white/80"}`}>{label}</span>
                  {n < stepLabels.length && <span className="hidden sm:inline text-white/40 ml-4">—</span>}
                </div>
              );
            })}
          </div>
        </section>

        {/* Upload */}
        <Section id="tour-upload" icon={<Upload className="w-5 h-5" />} title="Upload a book">
          {!file ? (
            <div
              {...getRootProps()}
              className={`rounded-2xl p-10 text-center cursor-pointer transition-all border-2 border-dashed ${
                isDragActive ? "border-brand-500 bg-brand-50" : "border-gray-300 hover:border-brand-400 hover:bg-brand-50/40"
              }`}
            >
              <input {...getInputProps()} ref={fileInputRef} />
              <div className="w-14 h-14 rounded-2xl bg-brand-50 flex items-center justify-center mx-auto mb-3">
                <Upload className="w-7 h-7 text-brand-600" />
              </div>
              <p className="font-medium text-gray-700">
                {isDragActive ? "Drop your PDF here" : "Drag & drop a PDF, or click to browse"}
              </p>
              <p className="text-sm text-gray-400 mt-1">PDF textbooks, notes, study material</p>
            </div>
          ) : (
            <div className="space-y-4">
              <div className="flex items-center gap-4 p-4 bg-gray-50 rounded-xl border border-gray-200">
                <FileText className="w-9 h-9 text-brand-600 shrink-0" />
                <div className="flex-1 min-w-0">
                  <p className="font-medium truncate">{file.name}</p>
                  <p className="text-sm text-gray-500">{(file.size / 1024 / 1024).toFixed(1)} MB</p>
                </div>
                {!uploading && (
                  <button onClick={() => setFile(null)} className="p-1.5 hover:bg-gray-200 rounded-lg">
                    <X className="w-5 h-5 text-gray-400" />
                  </button>
                )}
              </div>
              <div className="grid sm:grid-cols-2 gap-4">
                <div>
                  <label className="block text-sm font-medium text-gray-700 mb-1.5">Title *</label>
                  <input value={title} onChange={(e) => setTitle(e.target.value)} disabled={uploading}
                    className="w-full px-3.5 py-2.5 border border-gray-300 rounded-xl outline-none focus:ring-2 focus:ring-brand-500"
                    placeholder="e.g. Chemistry Class 6" />
                </div>
                <div>
                  <label className="block text-sm font-medium text-gray-700 mb-1.5">Author (optional)</label>
                  <input value={author} onChange={(e) => setAuthor(e.target.value)} disabled={uploading}
                    className="w-full px-3.5 py-2.5 border border-gray-300 rounded-xl outline-none focus:ring-2 focus:ring-brand-500"
                    placeholder="e.g. NCERT" />
                </div>
              </div>
              {uploading && (
                <div className="space-y-2">
                  <div className="flex justify-between text-sm text-gray-600">
                    <span>{progressMsg}</span><span className="font-medium text-brand-600">{progress}%</span>
                  </div>
                  <div className="w-full h-2.5 bg-gray-200 rounded-full overflow-hidden">
                    <div className="h-full bg-gradient-to-r from-brand-500 to-indigo-600 rounded-full transition-all" style={{ width: `${progress}%` }} />
                  </div>
                </div>
              )}
              <button onClick={handleUpload} disabled={!title || uploading}
                className="w-full py-3 bg-brand-600 text-white rounded-xl font-medium hover:bg-brand-700 disabled:opacity-50 flex items-center justify-center gap-2 transition-colors">
                {uploading ? <><Loader2 className="w-4 h-4 animate-spin" /> Uploading...</> : <><Upload className="w-4 h-4" /> Upload &amp; Process</>}
              </button>
            </div>
          )}
        </Section>

        {/* Books */}
        <Section id="tour-books" icon={<BookOpen className="w-5 h-5" />} title="Your books"
          action={<button onClick={load} className="p-2 text-gray-400 hover:text-gray-600 hover:bg-gray-100 rounded-lg" title="Refresh"><RefreshCw className="w-4 h-4" /></button>}>
          {loading ? (
            <div className="grid gap-3">
              {[0, 1].map((i) => <div key={i} className="h-16 rounded-xl bg-gray-100 animate-pulse" />)}
            </div>
          ) : books.length === 0 ? (
            <div className="text-center py-10">
              <BookOpen className="w-10 h-10 text-gray-300 mx-auto mb-3" />
              <p className="text-gray-500">No books yet</p>
              <p className="text-sm text-gray-400">Upload one above to get started.</p>
            </div>
          ) : (
            <div className="grid gap-3">
              {books.map((b) => (
                <div key={b.id}
                  className={`flex items-center gap-4 p-4 rounded-xl border bg-white transition-all ${
                    selected?.id === b.id ? "border-brand-400 ring-2 ring-brand-100" : "border-gray-200 hover:border-brand-300 hover:shadow-sm"
                  }`}>
                  <button onClick={() => b.status === "ready" && openBook(b)} className="flex items-center gap-4 flex-1 text-left min-w-0">
                    <div className="w-10 h-10 rounded-xl bg-brand-50 flex items-center justify-center shrink-0">
                      <BookOpen className="w-5 h-5 text-brand-600" />
                    </div>
                    <div className="min-w-0">
                      <p className="font-medium truncate">{b.title}</p>
                      <p className="text-xs text-gray-500">
                        {b.total_pages} pages ·{" "}
                        <span className={b.status === "ready" ? "text-green-600" : b.status === "failed" ? "text-red-600" : "text-amber-600"}>
                          {b.status}
                        </span>
                      </p>
                    </div>
                  </button>
                  {b.status !== "ready" && b.status !== "failed" && <Loader2 className="w-4 h-4 animate-spin text-amber-500" />}
                  {(b.status === "failed" || b.status === "uploaded") && (
                    <button onClick={() => handleProcess(b)} className="text-xs px-3 py-1.5 bg-amber-500 text-white rounded-lg hover:bg-amber-600">
                      Process
                    </button>
                  )}
                  {b.status === "ready" && selected?.id !== b.id && (
                    <button onClick={() => openBook(b)} className="text-xs px-3 py-1.5 bg-brand-50 text-brand-700 rounded-lg hover:bg-brand-100 font-medium">
                      Select
                    </button>
                  )}
                  <button onClick={() => handleDelete(b)} className="p-1.5 text-gray-400 hover:text-red-500 hover:bg-red-50 rounded-lg" title="Delete">
                    <Trash2 className="w-4 h-4" />
                  </button>
                </div>
              ))}
            </div>
          )}
        </Section>

        {/* Configure */}
        {selected && (
          <Section id="tour-config" icon={<Layers className="w-5 h-5" />} title={`Configure — ${selected.title}`}>
            {loadingBook ? (
              <div className="flex justify-center py-8"><Loader2 className="w-6 h-6 animate-spin text-brand-600" /></div>
            ) : (
              <>
                <div className="mb-6">
                  <div className="flex items-center justify-between mb-2">
                    <label className="text-sm font-medium text-gray-700">Chapters</label>
                    <label className="flex items-center gap-2 text-sm text-gray-600 cursor-pointer">
                      <input type="checkbox" className="accent-brand-600" checked={allChapters} onChange={(e) => setAllChapters(e.target.checked)} />
                      Whole book
                    </label>
                  </div>
                  {!allChapters && (
                    <div className="max-h-52 overflow-y-auto border border-gray-200 rounded-xl divide-y divide-gray-100">
                      {chapters.map((c) => (
                        <label key={c.id} className="flex items-center gap-3 px-4 py-2.5 text-sm hover:bg-gray-50 cursor-pointer">
                          <input type="checkbox" className="accent-brand-600"
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

                <div className="grid sm:grid-cols-2 gap-4 mb-6">
                  <div>
                    <label className="block text-sm font-medium text-gray-700 mb-1.5">Class / Standard</label>
                    <input value={className} onChange={(e) => setClassName(e.target.value)}
                      className="w-full px-3.5 py-2.5 border border-gray-300 rounded-xl outline-none focus:ring-2 focus:ring-brand-500"
                      placeholder="e.g. Class 6" />
                    <p className="text-xs text-gray-400 mt-1.5 flex items-center gap-1">
                      <Sparkles className="w-3 h-3" /> Difficulty is set automatically for this class.
                    </p>
                  </div>
                  <div>
                    <label className="block text-sm font-medium text-gray-700 mb-1.5">Subject</label>
                    <input value={subject} onChange={(e) => setSubject(e.target.value)}
                      className="w-full px-3.5 py-2.5 border border-gray-300 rounded-xl outline-none focus:ring-2 focus:ring-brand-500" />
                  </div>
                  <div>
                    <label className="block text-sm font-medium text-gray-700 mb-1.5">School / Institute</label>
                    <input value={school} onChange={(e) => setSchool(e.target.value)}
                      className="w-full px-3.5 py-2.5 border border-gray-300 rounded-xl outline-none focus:ring-2 focus:ring-brand-500" />
                  </div>
                  <div>
                    <label className="block text-sm font-medium text-gray-700 mb-1.5">Duration</label>
                    <input value={duration} onChange={(e) => setDuration(e.target.value)}
                      className="w-full px-3.5 py-2.5 border border-gray-300 rounded-xl outline-none focus:ring-2 focus:ring-brand-500" />
                  </div>
                </div>

                <div id="tour-questions" className="scroll-mt-24">
                  <div className="flex items-center gap-2 mb-3">
                    <label className="text-sm font-medium text-gray-700">Question paper format</label>
                    <div className="ml-auto inline-flex rounded-xl border border-gray-300 overflow-hidden text-sm">
                      <button onClick={() => setMode("auto")}
                        className={mode === "auto" ? "bg-brand-600 text-white px-3.5 py-1.5 flex items-center gap-1.5" : "px-3.5 py-1.5 text-gray-600 hover:bg-gray-50"}>
                        <Wand2 className="w-3.5 h-3.5" /> Auto
                      </button>
                      <button onClick={() => setMode("custom")}
                        className={mode === "custom" ? "bg-brand-600 text-white px-3.5 py-1.5" : "px-3.5 py-1.5 text-gray-600 hover:bg-gray-50"}>
                        Custom
                      </button>
                    </div>
                  </div>

                  {mode === "auto" ? (
                    <div className="border border-gray-200 rounded-xl p-4 bg-gray-50">
                      <p className="text-xs text-gray-500 mb-2">Auto-suggested for {className || "this class"}:</p>
                      <div className="space-y-1.5">
                        {suggested.length === 0 && <p className="text-sm text-gray-400">Set a class to see the suggestion.</p>}
                        {suggested.map((q) => (
                          <div key={q.type} className="flex justify-between text-sm">
                            <span className="text-gray-700">{q.label}</span>
                            <span className="text-gray-500">{q.count} × {q.marks_per} = {q.count * q.marks_per} marks</span>
                          </div>
                        ))}
                      </div>
                      <div className="flex justify-between text-sm font-semibold mt-3 pt-3 border-t border-gray-200">
                        <span>Total</span>
                        <span>{totalQuestions} questions · {totalMarks} marks</span>
                      </div>
                    </div>
                  ) : (
                    <div className="border border-gray-200 rounded-xl p-4 space-y-3">
                      {questionTypes.length === 0 && <p className="text-sm text-gray-400">Add question types below.</p>}
                      {questionTypes.map((q) => (
                        <div key={q.type} className="flex items-center gap-3">
                          <span className="flex-1 text-sm truncate text-gray-700">{q.label}</span>
                          <div className="flex items-center gap-1.5">
                            <input type="number" min={1} value={q.count}
                              onChange={(e) => updateQType(q.type, { count: Math.max(1, parseInt(e.target.value) || 1) })}
                              className="w-16 px-2.5 py-1.5 border border-gray-300 rounded-lg text-sm outline-none focus:ring-2 focus:ring-brand-500" />
                            <span className="text-xs text-gray-400">×</span>
                            <input type="number" min={1} value={q.marks_per}
                              onChange={(e) => updateQType(q.type, { marks_per: Math.max(1, parseInt(e.target.value) || 1) })}
                              className="w-16 px-2.5 py-1.5 border border-gray-300 rounded-lg text-sm outline-none focus:ring-2 focus:ring-brand-500" />
                            <span className="text-xs text-gray-400">marks</span>
                          </div>
                          <button onClick={() => setQuestionTypes((prev) => prev.filter((x) => x.type !== q.type))}
                            className="p-1.5 text-gray-400 hover:text-red-500 hover:bg-red-50 rounded-lg">
                            <Trash2 className="w-4 h-4" />
                          </button>
                        </div>
                      ))}
                      <div className="flex flex-wrap gap-2 pt-1">
                        <select value={addType} onChange={(e) => setAddType(e.target.value)}
                          className="flex-1 min-w-[180px] px-3 py-2.5 border border-gray-300 rounded-xl text-sm outline-none focus:ring-2 focus:ring-brand-500">
                          <option value="">Add a question type…</option>
                          {catalog.filter((c) => !questionTypes.some((q) => q.type === c.type)).map((c) => (
                            <option key={c.type} value={c.type}>{c.label}</option>
                          ))}
                        </select>
                        <button onClick={addSelected} disabled={!addType}
                          className="px-3.5 py-2.5 bg-brand-50 text-brand-700 rounded-xl text-sm font-medium hover:bg-brand-100 disabled:opacity-50 flex items-center gap-1.5">
                          <Plus className="w-4 h-4" /> Add
                        </button>
                        <button onClick={() => setQuestionTypes(suggested)}
                          className="px-3.5 py-2.5 text-gray-600 rounded-xl text-sm hover:bg-gray-100 flex items-center gap-1.5">
                          <Wand2 className="w-4 h-4" /> Use suggested
                        </button>
                      </div>
                      <div className="flex justify-between text-sm font-semibold pt-3 border-t border-gray-200">
                        <span>Total</span>
                        <span>{totalQuestions} questions · {totalMarks} marks</span>
                      </div>
                    </div>
                  )}
                </div>

                <button id="tour-generate" onClick={handleGenerate}
                  disabled={generating || (mode === "custom" && questionTypes.length === 0)}
                  className="mt-6 w-full py-3.5 bg-gradient-to-r from-brand-600 to-indigo-600 text-white rounded-xl font-semibold hover:opacity-95 disabled:opacity-50 flex items-center justify-center gap-2 transition shadow-sm">
                  {generating ? <><Loader2 className="w-4 h-4 animate-spin" /> Generating questions...</> : <><Wand2 className="w-4 h-4" /> Generate questions</>}
                </button>
              </>
            )}
          </Section>
        )}

        {/* Editor */}
        {paper && (
          <section id="editor" className="bg-white rounded-2xl border border-gray-200 shadow-sm p-6 scroll-mt-24">
            <div className="flex items-center gap-3 mb-5">
              <div className="w-9 h-9 rounded-xl bg-brand-50 flex items-center justify-center text-brand-600">
                <ClipboardList className="w-5 h-5" />
              </div>
              <h2 className="font-semibold text-gray-900">Edit paper</h2>
              <span className="ml-auto text-sm text-gray-500">{paper.length} questions · {paperMarks} marks</span>
            </div>

            <div className="space-y-3 mb-5">
              {paper.map((q, i) => (
                <div key={i} className="border border-gray-200 rounded-xl p-4 bg-gray-50/60 hover:border-gray-300 transition-colors">
                  <div className="flex items-center gap-2 mb-2.5">
                    <span className="w-6 text-sm font-semibold text-gray-700">{i + 1}.</span>
                    <select value={q.type} onChange={(e) => setQ(i, { type: e.target.value })}
                      className="text-xs px-2.5 py-1.5 border border-gray-300 rounded-lg bg-white outline-none focus:ring-2 focus:ring-brand-500">
                      {editableTypes.map((t) => <option key={t.type} value={t.type}>{t.label}</option>)}
                    </select>
                    <div className="flex items-center gap-1 ml-auto">
                      <input type="number" min={1} value={q.marks}
                        onChange={(e) => setQ(i, { marks: Math.max(1, parseInt(e.target.value) || 1) })}
                        className="w-16 px-2.5 py-1.5 border border-gray-300 rounded-lg text-sm outline-none focus:ring-2 focus:ring-brand-500" />
                      <span className="text-xs text-gray-400 mr-2">marks</span>
                      <button onClick={() => moveQ(i, -1)} disabled={i === 0}
                        className="p-1.5 text-gray-400 hover:text-gray-700 hover:bg-gray-200 rounded-lg disabled:opacity-30" title="Move up">
                        <ChevronUp className="w-4 h-4" />
                      </button>
                      <button onClick={() => moveQ(i, 1)} disabled={i === paper.length - 1}
                        className="p-1.5 text-gray-400 hover:text-gray-700 hover:bg-gray-200 rounded-lg disabled:opacity-30" title="Move down">
                        <ChevronDown className="w-4 h-4" />
                      </button>
                      <button onClick={() => removeQ(i)} className="p-1.5 text-gray-400 hover:text-red-500 hover:bg-red-50 rounded-lg" title="Delete">
                        <Trash2 className="w-4 h-4" />
                      </button>
                    </div>
                  </div>
                  <textarea value={q.question} rows={2}
                    onChange={(e) => setQ(i, { question: e.target.value })}
                    className="w-full px-3.5 py-2.5 border border-gray-300 rounded-xl text-sm outline-none focus:ring-2 focus:ring-brand-500 resize-y bg-white"
                    placeholder="Question text..." />
                  {(q.type === "mcq" || q.type === "assertion_reason") && (
                    <div className="grid grid-cols-2 gap-2 mt-2.5">
                      {["A", "B", "C", "D"].map((k) => (
                        <input key={k} value={(q.options || {})[k] || ""}
                          onChange={(e) => setOption(i, k, e.target.value)}
                          placeholder={`Option ${k}`}
                          className="px-3.5 py-2 border border-gray-300 rounded-xl text-sm outline-none focus:ring-2 focus:ring-brand-500 bg-white" />
                      ))}
                    </div>
                  )}
                </div>
              ))}
            </div>

            <div className="flex flex-wrap gap-3">
              <button onClick={addQ}
                className="px-4 py-2.5 border border-gray-300 rounded-xl text-sm font-medium hover:bg-gray-50 flex items-center gap-1.5">
                <Plus className="w-4 h-4" /> Add question
              </button>
              <button onClick={handleGenerate}
                className="px-4 py-2.5 border border-gray-300 rounded-xl text-sm font-medium hover:bg-gray-50 flex items-center gap-1.5">
                <RefreshCw className="w-4 h-4" /> Regenerate
              </button>
              <button onClick={previewPdf} disabled={building || paper.length === 0}
                className="ml-auto px-5 py-2.5 bg-brand-600 text-white rounded-xl text-sm font-semibold hover:bg-brand-700 disabled:opacity-50 flex items-center gap-2 transition-colors">
                {building ? <><Loader2 className="w-4 h-4 animate-spin" /> Building...</> : <><Download className="w-4 h-4" /> Preview &amp; Download</>}
              </button>
            </div>
          </section>
        )}

        <footer className="text-center text-xs text-gray-400 py-6">
          Test Paper Generator · books stored securely in your Google Drive
        </footer>
      </div>

      {/* Preview modal */}
      {preview && (
        <div className="fixed inset-0 z-50 bg-black/50 flex items-center justify-center p-4" onClick={closePreview}>
          <div className="bg-white rounded-2xl w-full max-w-3xl h-[92vh] flex flex-col overflow-hidden shadow-xl" onClick={(e) => e.stopPropagation()}>
            <div className="flex items-center justify-between px-4 py-3 border-b border-gray-200">
              <span className="font-semibold flex items-center gap-2">
                <FileText className="w-4 h-4 text-brand-600" /> Preview
              </span>
              <div className="flex items-center gap-2">
                <a href={preview.url} download={preview.name}
                  className="px-3.5 py-2 bg-brand-600 text-white rounded-xl text-sm font-medium hover:bg-brand-700 flex items-center gap-1.5">
                  <Download className="w-4 h-4" /> Download
                </a>
                <button onClick={closePreview} className="p-2 text-gray-500 hover:bg-gray-100 rounded-xl" title="Close">
                  <X className="w-5 h-5" />
                </button>
              </div>
            </div>
            <iframe src={preview.url} title="Test paper preview" className="flex-1 w-full bg-gray-100" />
          </div>
        </div>
      )}

      <Tour steps={tourSteps} open={tourOpen} onClose={closeTour} />
    </div>
  );
}
