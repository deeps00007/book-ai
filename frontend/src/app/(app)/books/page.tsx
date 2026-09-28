"use client";

import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";
import { useAuth } from "@/components/AuthProvider";
import { getBooks } from "@/lib/api";
import { Book as BookType } from "@/lib/types";
import { Loader2, BookOpen, Plus, Upload, MessageSquare, Clock } from "lucide-react";
import { cn } from "@/lib/utils";
import { toast } from "sonner";

export default function BooksPage() {
  const { user, loading: authLoading } = useAuth();
  const router = useRouter();
  const [books, setBooks] = useState<BookType[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    if (authLoading) return;
    if (!user) { router.push("/login"); return; }
    getBooks().then(setBooks).finally(() => setLoading(false));
  }, [user, authLoading]);

  // Auto-poll while any book is still uploading/processing so the status
  // updates by itself — no manual refresh needed.
  useEffect(() => {
    const pending = books.some((b) => b.status !== "ready" && b.status !== "failed");
    if (!pending) return;
    const id = setInterval(() => {
      getBooks().then(setBooks).catch(() => {});
    }, 5000);
    return () => clearInterval(id);
  }, [books]);

  if (authLoading || loading) {
    return (
      <div className="flex-1 flex items-center justify-center">
        <Loader2 className="w-8 h-8 animate-spin text-brand-600" />
      </div>
    );
  }

  return (
    <main className="flex-1 overflow-y-auto p-8">
      <div className="max-w-5xl mx-auto">
          <div className="flex items-center justify-between mb-8">
            <div>
              <h1 className="text-3xl font-bold">My Books</h1>
              <p className="text-gray-500 mt-1">Manage your uploaded textbooks</p>
            </div>
            <button
              onClick={() => router.push("/books/upload")}
              className="flex items-center gap-2 px-4 py-2.5 bg-brand-600 text-white rounded-lg hover:bg-brand-700 transition-colors font-medium"
            >
              <Plus className="w-4 h-4" />
              Upload Book
            </button>
          </div>

          {books.length === 0 ? (
            <div className="text-center py-20">
              <BookOpen className="w-16 h-16 text-gray-300 mx-auto mb-4" />
              <h2 className="text-xl font-semibold text-gray-600 mb-2">No books yet</h2>
              <p className="text-gray-400 mb-4">Upload your first textbook to get started</p>
              <button
                onClick={() => router.push("/books/upload")}
                className="inline-flex items-center gap-2 px-6 py-3 bg-brand-600 text-white rounded-lg hover:bg-brand-700 transition-colors font-medium"
              >
                <Upload className="w-4 h-4" />
                Upload PDF
              </button>
            </div>
          ) : (
            <div className="grid gap-4">
              {books.map((book) => (
                <div
                  key={book.id}
                  className="p-5 rounded-xl border border-gray-200 bg-white hover:border-brand-300 transition-all"
                >
                  <div className="flex items-center justify-between">
                    <div className="flex items-center gap-4">
                      <div className="w-12 h-12 rounded-lg bg-brand-50 flex items-center justify-center">
                        <BookOpen className="w-6 h-6 text-brand-600" />
                      </div>
                      <div>
                        <h3 className="font-semibold text-gray-900">{book.title}</h3>
                        <p className="text-sm text-gray-500">
                          {book.total_pages} pages
                        </p>
                      </div>
                    </div>
                    <div className="flex items-center gap-3">
                      <span
                        className={cn(
                          "px-3 py-1 rounded-full text-xs font-medium inline-flex items-center gap-1.5",
                          book.status === "ready"
                            ? "bg-green-50 text-green-700"
                            : book.status === "processing" || book.status === "uploaded"
                            ? "bg-yellow-50 text-yellow-700"
                            : book.status === "failed"
                            ? "bg-red-50 text-red-700"
                            : "bg-gray-50 text-gray-600"
                        )}
                      >
                        {(book.status === "processing" || book.status === "uploaded") && (
                          <Loader2 className="w-3 h-3 animate-spin" />
                        )}
                        {book.status === "uploaded"
                          ? "Queued"
                          : book.status === "processing"
                          ? "Processing"
                          : book.status === "ready"
                          ? "Ready"
                          : book.status === "failed"
                          ? "Failed"
                          : book.status}
                      </span>
                      {book.status === "ready" && (
                        <button
                          onClick={() => router.push(`/books/${book.id}/chat`)}
                          className="flex items-center gap-2 px-4 py-2 bg-brand-600 text-white rounded-lg hover:bg-brand-700 text-sm font-medium transition-colors"
                        >
                          <MessageSquare className="w-4 h-4" />
                          Chat
                        </button>
                      )}
                      {(book.status === "processing" || book.status === "failed" || book.status === "uploaded") && (
                        <button
                          onClick={async () => {
                            try {
                              const token = localStorage.getItem("token");
                              const API = process.env.NEXT_PUBLIC_API_URL || "https://bookai-api-three.vercel.app/api/v1";
                              const res = await fetch(`${API}/books/${book.id}/process`, {
                                method: "POST",
                                headers: { Authorization: `Bearer ${token}` },
                              });
                              const data = await res.json().catch(() => ({}));
                              if (res.ok) {
                                toast.success(data.message || "Processing started");
                                getBooks().then(setBooks);
                              } else {
                                toast.error(data.message || "Processing failed");
                              }
                            } catch {
                              toast.error("Server busy — try again");
                            }
                          }}
                          className="flex items-center gap-2 px-4 py-2 bg-yellow-500 text-white rounded-lg hover:bg-yellow-600 text-sm font-medium transition-colors"
                        >
                          <Loader2 className="w-4 h-4" />
                          Process
                        </button>
                      )}
                    </div>
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>
    </main>
  );
}
