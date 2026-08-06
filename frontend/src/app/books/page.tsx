"use client";

import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";
import { Sidebar } from "@/components/Sidebar";
import { useAuth } from "@/components/AuthProvider";
import { getBooks } from "@/lib/api";
import { Book as BookType } from "@/lib/types";
import { Loader2, BookOpen, Plus, Upload, MessageSquare, Clock } from "lucide-react";
import { cn } from "@/lib/utils";

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
                          {book.total_pages} pages &middot; {book.total_chunks} chunks
                        </p>
                      </div>
                    </div>
                    <div className="flex items-center gap-3">
                      <span
                        className={cn(
                          "px-3 py-1 rounded-full text-xs font-medium",
                          book.status === "ready"
                            ? "bg-green-50 text-green-700"
                            : book.status === "processing"
                            ? "bg-yellow-50 text-yellow-700"
                            : book.status === "failed"
                            ? "bg-red-50 text-red-700"
                            : "bg-gray-50 text-gray-600"
                        )}
                      >
                        {book.status}
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
                    </div>
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>
      </main>
    </div>
  );
}
