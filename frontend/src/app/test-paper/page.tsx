"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { Sidebar } from "@/components/Sidebar";
import { useAuth } from "@/components/AuthProvider";
import { getBooks, getChapters, generateTestPaper } from "@/lib/api";
import { Book, Chapter } from "@/lib/types";
import { Loader2, FileText, Plus, Trash2, Download, Layers, BookOpen, Clock, School, GraduationCap } from "lucide-react";
import { toast } from "sonner";

interface QuestionType {
  type: string;
  label: string;
  count: number;
  marks_per: number;
}

const DEFAULT_TYPES: QuestionType[] = [
  { type: "mcq", label: "MCQ", count: 5, marks_per: 2 },
  { type: "fill_blanks", label: "Fill in the Blanks", count: 5, marks_per: 2 },
  { type: "true_false", label: "True / False", count: 5, marks_per: 1 },
  { type: "short_answer", label: "Answer the following", count: 5, marks_per: 3 },
  { type: "long_answer", label: "Long Answer", count: 2, marks_per: 5 },
];

export default function TestPaperPage() {
  const { user, loading: authLoading } = useAuth();
  const router = useRouter();
  const [books, setBooks] = useState<Book[]>([]);
  const [chapters, setChapters] = useState<Chapter[]>([]);
  const [selectedBook, setSelectedBook] = useState("");
  const [selectedChapters, setSelectedChapters] = useState<string[]>([]);
  const [schoolName, setSchoolName] = useState("");
  const [className, setClassName] = useState("");
  const [subject, setSubject] = useState("");
  const [duration, setDuration] = useState("");
  const [topic, setTopic] = useState("");
  const [questionTypes, setQuestionTypes] = useState<QuestionType[]>(DEFAULT_TYPES);
  const [generating, setGenerating] = useState(false);
  const [loading, setLoading] = useState(true);

  const totalMarks = questionTypes.reduce((sum, qt) => sum + qt.count * qt.marks_per, 0);

  useEffect(() => {
    if (authLoading) return;
    if (!user) { router.push("/login"); return; }
    getBooks()
      .then((data) => setBooks(data.filter((b: Book) => b.status === "ready")))
      .finally(() => setLoading(false));
  }, [user, authLoading]);

  async function handleBookSelect(bookId: string) {
    setSelectedBook(bookId);
    setSelectedChapters([]);
    if (bookId) {
      try {
        const ch = await getChapters(bookId);
        setChapters(ch || []);
      } catch { setChapters([]); }
    } else {
      setChapters([]);
    }
  }

  function toggleChapter(chapterId: string) {
    setSelectedChapters((prev) =>
      prev.includes(chapterId) ? prev.filter((id) => id !== chapterId) : [...prev, chapterId]
    );
  }

  function updateQuestionType(index: number, field: keyof QuestionType, value: any) {
    setQuestionTypes((prev) => {
      const copy = [...prev];
      copy[index] = { ...copy[index], [field]: value };
      return copy;
    });
  }

  function addQuestionType() {
    setQuestionTypes((prev) => [
      ...prev,
      { type: "", label: "", count: 1, marks_per: 1 },
    ]);
  }

  function removeQuestionType(index: number) {
    if (questionTypes.length <= 1) return;
    setQuestionTypes((prev) => prev.filter((_, i) => i !== index));
  }

  async function handleGenerate() {
    if (!selectedBook || !schoolName || !className || !subject || !duration) {
      toast.error("Please fill in all required fields");
      return;
    }
    if (questionTypes.some((qt) => !qt.label || qt.count < 1 || qt.marks_per < 1)) {
      toast.error("All question types must have a label, count, and marks");
      return;
    }

    setGenerating(true);
    try {
      const blob = await generateTestPaper({
        book_id: selectedBook,
        chapter_ids: selectedChapters.length > 0 ? selectedChapters : [],
        school_name: schoolName,
        class_name: className,
        subject,
        duration,
        topic: topic || undefined,
        question_types: questionTypes.map((qt) => ({
          type: qt.type || qt.label.toLowerCase().replace(/\s+/g, "_"),
          label: qt.label,
          count: qt.count,
          marks_per: qt.marks_per,
        })),
      });

      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = `Test_Paper_${subject.replace(/\s+/g, "_")}.pdf`;
      document.body.appendChild(a);
      a.click();
      document.body.removeChild(a);
      URL.revokeObjectURL(url);
      toast.success("Test paper downloaded!");
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

  return (
    <div className="flex h-screen">
      <Sidebar />
      <main className="flex-1 overflow-y-auto p-8">
        <div className="max-w-3xl mx-auto">
          <h1 className="text-3xl font-bold mb-2">Generate Test Paper</h1>
          <p className="text-gray-500 mb-8">Create professional exam papers from your uploaded books</p>

          <div className="space-y-6">
            <div className="bg-white rounded-xl border border-gray-200 p-6">
              <h2 className="font-semibold mb-4 flex items-center gap-2">
                <School className="w-5 h-5 text-gray-500" />
                General Details
              </h2>
              <div className="grid grid-cols-2 gap-4">
                <div>
                  <label className="block text-sm font-medium text-gray-700 mb-1">School Name *</label>
                  <input type="text" value={schoolName} onChange={(e) => setSchoolName(e.target.value)}
                    className="w-full px-3 py-2.5 border border-gray-300 rounded-lg outline-none focus:ring-2 focus:ring-brand-500"
                    placeholder="Enter school name" />
                </div>
                <div>
                  <label className="block text-sm font-medium text-gray-700 mb-1">Class *</label>
                  <input type="text" value={className} onChange={(e) => setClassName(e.target.value)}
                    className="w-full px-3 py-2.5 border border-gray-300 rounded-lg outline-none focus:ring-2 focus:ring-brand-500"
                    placeholder="e.g. 10th Grade" />
                </div>
                <div>
                  <label className="block text-sm font-medium text-gray-700 mb-1">Subject *</label>
                  <input type="text" value={subject} onChange={(e) => setSubject(e.target.value)}
                    className="w-full px-3 py-2.5 border border-gray-300 rounded-lg outline-none focus:ring-2 focus:ring-brand-500"
                    placeholder="e.g. Science" />
                </div>
                <div>
                  <label className="block text-sm font-medium text-gray-700 mb-1">Duration *</label>
                  <input type="text" value={duration} onChange={(e) => setDuration(e.target.value)}
                    className="w-full px-3 py-2.5 border border-gray-300 rounded-lg outline-none focus:ring-2 focus:ring-brand-500"
                    placeholder="e.g. 2 hours" />
                </div>
              </div>
            </div>

            <div className="bg-white rounded-xl border border-gray-200 p-6">
              <h2 className="font-semibold mb-4 flex items-center gap-2">
                <BookOpen className="w-5 h-5 text-gray-500" />
                Content Source
              </h2>
              <div className="space-y-4">
                <div>
                  <label className="block text-sm font-medium text-gray-700 mb-1">Select Book</label>
                  <select value={selectedBook} onChange={(e) => handleBookSelect(e.target.value)}
                    className="w-full px-3 py-2.5 border border-gray-300 rounded-lg outline-none focus:ring-2 focus:ring-brand-500 bg-white">
                    <option value="">Select Book...</option>
                    {books.map((b) => (
                      <option key={b.id} value={b.id}>{b.title}</option>
                    ))}
                  </select>
                </div>

                {chapters.length > 1 && (
                  <div>
                    <label className="block text-sm font-medium text-gray-700 mb-1">Select Chapters (or leave empty for entire book)</label>
                    <div className="flex flex-wrap gap-2 max-h-32 overflow-y-auto p-2 border border-gray-200 rounded-lg bg-gray-50">
                      {chapters.map((ch) => (
                        <button key={ch.id} onClick={() => toggleChapter(ch.id)}
                          className={`px-3 py-1.5 rounded-full text-xs font-medium transition-colors ${
                            selectedChapters.includes(ch.id)
                              ? "bg-brand-600 text-white"
                              : "bg-white border border-gray-300 text-gray-600 hover:border-brand-400"
                          }`}>
                          {ch.title} (p.{ch.start_page})
                        </button>
                      ))}
                    </div>
                  </div>
                )}

                <div>
                  <label className="block text-sm font-medium text-gray-700 mb-1">Topic Focus (Optional)</label>
                  <input type="text" value={topic} onChange={(e) => setTopic(e.target.value)}
                    className="w-full px-3 py-2.5 border border-gray-300 rounded-lg outline-none focus:ring-2 focus:ring-brand-500"
                    placeholder="e.g. Chapter 5: Photosynthesis" />
                </div>
              </div>
            </div>

            <div className="bg-white rounded-xl border border-gray-200 p-6">
              <h2 className="font-semibold mb-4 flex items-center gap-2">
                <Layers className="w-5 h-5 text-gray-500" />
                Question Structure
              </h2>

              <div className="overflow-x-auto">
                <table className="w-full text-sm">
                  <thead>
                    <tr className="border-b border-gray-200">
                      <th className="text-left py-2 px-2 font-medium text-gray-500 text-xs uppercase">Question Type</th>
                      <th className="text-left py-2 px-2 font-medium text-gray-500 text-xs uppercase">No. of Questions</th>
                      <th className="text-left py-2 px-2 font-medium text-gray-500 text-xs uppercase">Marks per Q</th>
                      <th className="text-left py-2 px-2 font-medium text-gray-500 text-xs uppercase">Total Marks</th>
                      <th className="w-10"></th>
                    </tr>
                  </thead>
                  <tbody>
                    {questionTypes.map((qt, i) => (
                      <tr key={i} className="border-b border-gray-100">
                        <td className="py-2 px-2">
                          <input type="text" value={qt.label} onChange={(e) => updateQuestionType(i, "label", e.target.value)}
                            className="w-full px-2 py-1.5 border border-gray-200 rounded outline-none focus:ring-1 focus:ring-brand-500 text-sm"
                            placeholder="e.g. MCQ" />
                        </td>
                        <td className="py-2 px-2">
                          <input type="number" value={qt.count} min={1} max={50}
                            onChange={(e) => updateQuestionType(i, "count", parseInt(e.target.value) || 1)}
                            className="w-20 px-2 py-1.5 border border-gray-200 rounded outline-none focus:ring-1 focus:ring-brand-500 text-sm" />
                        </td>
                        <td className="py-2 px-2">
                          <input type="number" value={qt.marks_per} min={1} max={20}
                            onChange={(e) => updateQuestionType(i, "marks_per", parseInt(e.target.value) || 1)}
                            className="w-20 px-2 py-1.5 border border-gray-200 rounded outline-none focus:ring-1 focus:ring-brand-500 text-sm" />
                        </td>
                        <td className="py-2 px-2">
                          <span className="font-medium text-gray-700">{qt.count * qt.marks_per}</span>
                        </td>
                        <td className="py-2 px-2">
                          <button onClick={() => removeQuestionType(i)}
                            className="p-1 hover:bg-red-50 rounded text-gray-400 hover:text-red-500 transition-colors">
                            <Trash2 className="w-4 h-4" />
                          </button>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>

              <button onClick={addQuestionType}
                className="mt-3 flex items-center gap-1 text-sm text-brand-600 hover:text-brand-700 font-medium">
                <Plus className="w-4 h-4" />
                Add Question Type
              </button>

              <div className="mt-4 p-3 bg-gray-50 rounded-lg flex items-center justify-between">
                <span className="text-sm font-medium text-gray-700">Maximum Marks:</span>
                <span className="text-lg font-bold text-brand-700">{totalMarks}</span>
              </div>
            </div>

            <button onClick={handleGenerate} disabled={generating || !selectedBook || !schoolName || !className || !subject || !duration}
              className="w-full py-3.5 bg-brand-600 text-white rounded-xl font-semibold hover:bg-brand-700 transition-colors disabled:opacity-50 flex items-center justify-center gap-2 text-lg">
              {generating ? (
                <>
                  <Loader2 className="w-5 h-5 animate-spin" />
                  Generating Test Paper...
                </>
              ) : (
                <>
                  <Download className="w-5 h-5" />
                  Generate Test Paper
                </>
              )}
            </button>

            {(!selectedBook || !schoolName || !className || !subject || !duration) && (
              <p className="text-center text-sm text-gray-400">
                Please fill in all required fields to generate the test paper
              </p>
            )}
          </div>
        </div>
      </main>
    </div>
  );
}
