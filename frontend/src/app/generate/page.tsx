"use client";

import { useEffect, useState, Suspense } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import { Sidebar } from "@/components/Sidebar";
import { useAuth } from "@/components/AuthProvider";
import { getBooks, generateContent, getChapters } from "@/lib/api";
import { Book, Chapter } from "@/lib/types";
import { Loader2, Sparkles, FileText, BookOpen, ChevronRight, ArrowLeft, Layers } from "lucide-react";
import { toast } from "sonner";

const CONTENT_TYPES = [
  { type: "worksheet", label: "Worksheet", icon: FileText, desc: "Create practice worksheets" },
  { type: "lesson_plan", label: "Lesson Plan", icon: BookOpen, desc: "Generate structured lesson plans" },
  { type: "notes", label: "Study Notes", icon: BookOpen, desc: "Detailed study notes" },
  { type: "summary", label: "Summary", icon: FileText, desc: "Concise chapter summaries" },
  { type: "flashcards", label: "Flashcards", icon: BookOpen, desc: "Q&A flashcards for review" },
];

function GeneratePageInner() {
  const { user, loading: authLoading } = useAuth();
  const router = useRouter();
  const searchParams = useSearchParams();
  const preselectedBookId = searchParams.get("book_id");

  const [books, setBooks] = useState<Book[]>([]);
  const [selectedBook, setSelectedBook] = useState<string>(preselectedBookId || "");
  const [selectedType, setSelectedType] = useState("");
  const [chapters, setChapters] = useState<Chapter[]>([]);
  const [selectedChapter, setSelectedChapter] = useState<string>("");
  const [topic, setTopic] = useState("");
  const [gradeLevel, setGradeLevel] = useState("");
  const [instructions, setInstructions] = useState("");
  const [generating, setGenerating] = useState(false);
  const [result, setResult] = useState<any>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    if (authLoading) return;
    if (!user) { router.push("/login"); return; }
    getBooks()
      .then((data) => {
        setBooks(data.filter((b: Book) => b.status === "ready"));
        if (preselectedBookId && data.some((b: Book) => b.id === preselectedBookId)) {
          setSelectedBook(preselectedBookId);
        }
      })
      .finally(() => setLoading(false));
  }, [user, authLoading]);

  async function handleGenerate() {
    if (!selectedBook || !selectedType) return;
    setGenerating(true);
    setResult(null);
    try {
      const res = await generateContent({
        book_id: selectedBook,
        content_type: selectedType,
        topic: topic || undefined,
        grade_level: gradeLevel || undefined,
        additional_instructions: instructions || undefined,
        chapter_id: selectedChapter || undefined,
      });
      setResult(res);
      toast.success(`${res.title} generated!`);
    } catch (err: any) {
      toast.error(err.message || "Generation failed");
    } finally {
      setGenerating(false);
    }
  }

  if (authLoading || loading) {
    return (
      <div className="flex h-screen">
        <Sidebar />
        <div className="flex-1 flex items-center justify-center">
          <Loader2 className="w-8 h-8 animate-spin text-brand-600" />
        </div>
      </div>
    );
  }

  const selectedTypeLabel = CONTENT_TYPES.find((t) => t.type === selectedType)?.label;

  return (
    <div className="flex h-screen">
      <Sidebar />
      <main className="flex-1 overflow-y-auto p-8">
        <div className="max-w-4xl mx-auto">
          {preselectedBookId && (
            <button
              onClick={() => router.push(`/books/${selectedBook}/chat`)}
              className="flex items-center gap-2 text-sm text-gray-500 hover:text-gray-700 mb-6"
            >
              <ArrowLeft className="w-4 h-4" />
              Back to Chat
            </button>
          )}

          <h1 className="text-3xl font-bold mb-2">Generate Content</h1>
          <p className="text-gray-500 mb-8">Create worksheets, lesson plans, tests, and more from your books</p>

          <div className="grid gap-6">
            <div className="bg-white rounded-xl border border-gray-200 p-6">
              <h2 className="font-semibold mb-4">1. Select Book</h2>
              {books.length === 0 ? (
                <p className="text-sm text-gray-500">No processed books available. Upload a book first.</p>
              ) : (
                <div className="grid grid-cols-2 gap-3">
                  {books.map((book) => (
                    <button
                      key={book.id}
                      onClick={async () => { setSelectedBook(book.id); setSelectedChapter(""); try { const ch = await getChapters(book.id); setChapters(ch || []); } catch {} }}
                      className={`p-3 rounded-lg border text-left transition-all ${
                        selectedBook === book.id
                          ? "border-brand-500 bg-brand-50 ring-1 ring-brand-500"
                          : "border-gray-200 hover:border-gray-300"
                      }`}
                    >
                      <p className="text-sm font-medium truncate">{book.title}</p>
                      <p className="text-xs text-gray-500">{book.total_pages} pages</p>
                    </button>
                  ))}
                </div>
              )}
            </div>

            {selectedBook && (
              <div className="bg-white rounded-xl border border-gray-200 p-6">
                <h2 className="font-semibold mb-4">2. Choose Content Type</h2>
                <div className="grid grid-cols-3 gap-3">
                  {CONTENT_TYPES.map((ct) => (
                    <button
                      key={ct.type}
                      onClick={() => setSelectedType(ct.type)}
                      className={`p-4 rounded-lg border text-center transition-all ${
                        selectedType === ct.type
                          ? "border-purple-500 bg-purple-50 ring-1 ring-purple-500"
                          : "border-gray-200 hover:border-gray-300"
                      }`}
                    >
                      <ct.icon className="w-6 h-6 mx-auto mb-2 text-purple-600" />
                      <p className="text-sm font-medium">{ct.label}</p>
                      <p className="text-xs text-gray-400 mt-1">{ct.desc}</p>
                    </button>
                  ))}
                </div>
              </div>
            )}

            {selectedBook && chapters.length > 1 && (
              <div className="bg-white rounded-xl border border-gray-200 p-6">
                <h2 className="font-semibold mb-4 flex items-center gap-2">
                  <Layers className="w-4 h-4 text-gray-500" />
                  Chapter Selection (Optional)
                </h2>
                <select
                  value={selectedChapter}
                  onChange={(e) => setSelectedChapter(e.target.value)}
                  className="px-3 py-2 border border-gray-300 rounded-lg text-sm outline-none focus:ring-2 focus:ring-brand-500 bg-white w-full"
                >
                  <option value="">Entire Book</option>
                  {chapters.map((ch) => (
                    <option key={ch.id} value={ch.id}>
                      {ch.title} (Pages {ch.start_page}-{ch.end_page})
                    </option>
                  ))}
                </select>
              </div>
            )}

            {selectedBook && selectedType && (
              <div className="bg-white rounded-xl border border-gray-200 p-6">
                <h2 className="font-semibold mb-4">3. Customize (Optional)</h2>
                <div className="grid grid-cols-2 gap-4">
                  <div>
                    <label className="block text-sm font-medium text-gray-700 mb-1">Topic Focus</label>
                    <input
                      type="text"
                      value={topic}
                      onChange={(e) => setTopic(e.target.value)}
                      className="w-full px-3 py-2 border border-gray-300 rounded-lg outline-none focus:ring-2 focus:ring-brand-500"
                      placeholder="e.g. Photosynthesis"
                    />
                  </div>
                  <div>
                    <label className="block text-sm font-medium text-gray-700 mb-1">Grade Level</label>
                    <input
                      type="text"
                      value={gradeLevel}
                      onChange={(e) => setGradeLevel(e.target.value)}
                      className="w-full px-3 py-2 border border-gray-300 rounded-lg outline-none focus:ring-2 focus:ring-brand-500"
                      placeholder="e.g. Grade 10"
                    />
                  </div>
                  <div className="col-span-2">
                    <label className="block text-sm font-medium text-gray-700 mb-1">Additional Instructions</label>
                    <textarea
                      value={instructions}
                      onChange={(e) => setInstructions(e.target.value)}
                      rows={2}
                      className="w-full px-3 py-2 border border-gray-300 rounded-lg outline-none focus:ring-2 focus:ring-brand-500"
                      placeholder="Any specific requirements..."
                    />
                  </div>
                </div>
                <button
                  onClick={handleGenerate}
                  disabled={generating}
                  className="mt-4 w-full py-3 bg-purple-600 text-white rounded-lg font-medium hover:bg-purple-700 transition-colors disabled:opacity-50 flex items-center justify-center gap-2"
                >
                  <Sparkles className="w-4 h-4" />
                  {generating ? `Generating ${selectedTypeLabel}...` : `Generate ${selectedTypeLabel}`}
                </button>
              </div>
            )}

            {result && (
              <div className="bg-white rounded-xl border border-gray-200 p-6">
                <h2 className="font-semibold mb-4 flex items-center gap-2">
                  <Sparkles className="w-5 h-5 text-purple-600" />
                  Generated: {result.title}
                </h2>
                <pre className="bg-gray-50 rounded-lg p-4 text-sm overflow-auto max-h-96">
                  {JSON.stringify(result.content, null, 2)}
                </pre>
              </div>
            )}
          </div>
        </div>
      </main>
    </div>
  );
}

export default function GeneratePage() {
  return (
    <Suspense fallback={
      <div className="flex h-screen items-center justify-center">
        <Loader2 className="w-8 h-8 animate-spin text-brand-600" />
      </div>
    }>
      <GeneratePageInner />
    </Suspense>
  );
}
