"use client";

import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";
import { Sidebar } from "@/components/Sidebar";
import { useAuth } from "@/components/AuthProvider";
import { getBooks, uploadBook, askQuestion } from "@/lib/api";
import { getChatSessions } from "@/lib/api";
import { Book, ChatSession } from "@/lib/types";
import { Loader2, Upload, Plus, BookOpen, MessageSquare, Sparkles, ArrowRight, Clock } from "lucide-react";
import { toast } from "sonner";
import { cn } from "@/lib/utils";

export default function DashboardPage() {
  const { user, loading: authLoading } = useAuth();
  const router = useRouter();
  const [books, setBooks] = useState<Book[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    if (authLoading) return;
    if (!user) {
      router.push("/login");
      return;
    }
    loadBooks();
  }, [user, authLoading]);

  async function loadBooks() {
    try {
      const data = await getBooks();
      setBooks(data);
    } catch (err) {
      toast.error("Failed to load books");
    } finally {
      setLoading(false);
    }
  }

  const quickActions = [
    { icon: Plus, label: "Upload Book", path: "/books/upload", color: "bg-blue-50 text-blue-600" },
    { icon: MessageSquare, label: "Chat with Book", path: "/books", color: "bg-green-50 text-green-600" },
    { icon: Sparkles, label: "Generate Content", path: "/generate", color: "bg-purple-50 text-purple-600" },
  ];

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
          <h1 className="text-3xl font-bold mb-2">Welcome, {user?.name?.split(" ")[0]}</h1>
          <p className="text-gray-500 mb-8">Your AI-powered teaching dashboard</p>

          <div className="grid grid-cols-3 gap-4 mb-10">
            {quickActions.map((action) => (
              <button
                key={action.path}
                onClick={() => router.push(action.path)}
                className="p-6 rounded-xl border border-gray-200 bg-white hover:border-brand-300 hover:shadow-md transition-all text-left group"
              >
                <div className={cn("w-10 h-10 rounded-lg flex items-center justify-center mb-3", action.color)}>
                  <action.icon className="w-5 h-5" />
                </div>
                <h3 className="font-semibold text-gray-900 group-hover:text-brand-600 transition-colors">
                  {action.label}
                </h3>
              </button>
            ))}
          </div>

          <div>
            <div className="flex items-center justify-between mb-4">
              <h2 className="text-xl font-semibold">Your Books</h2>
              <button
                onClick={() => router.push("/books")}
                className="text-sm text-brand-600 hover:text-brand-700 font-medium flex items-center gap-1"
              >
                View All <ArrowRight className="w-4 h-4" />
              </button>
            </div>

            {books.length === 0 ? (
              <div
                onClick={() => router.push("/books/upload")}
                className="border-2 border-dashed border-gray-300 rounded-xl p-12 text-center cursor-pointer hover:border-brand-400 hover:bg-brand-50/50 transition-all"
              >
                <Upload className="w-12 h-12 text-gray-400 mx-auto mb-3" />
                <h3 className="text-lg font-medium text-gray-600 mb-1">Upload your first book</h3>
                <p className="text-sm text-gray-400">PDF textbooks, study materials, notes</p>
              </div>
            ) : (
              <div className="grid grid-cols-2 gap-4">
                {books.slice(0, 4).map((book) => (
                  <button
                    key={book.id}
                    onClick={() => router.push(`/books/${book.id}/chat`)}
                    className="p-4 rounded-xl border border-gray-200 bg-white hover:border-brand-300 hover:shadow-sm transition-all text-left"
                  >
                    <div className="flex items-center gap-3 mb-2">
                      <BookOpen className="w-8 h-8 text-brand-600" />
                      <div className="flex-1 min-w-0">
                        <h3 className="font-medium text-gray-900 truncate">{book.title}</h3>
                        <p className="text-xs text-gray-500">
                          {book.total_pages} pages &middot; {book.status}
                        </p>
                      </div>
                    </div>
                    <div className="flex items-center gap-2 text-xs">
                      <span
                        className={cn(
                          "px-2 py-0.5 rounded-full font-medium",
                          book.status === "ready"
                            ? "bg-green-50 text-green-700"
                            : book.status === "processing"
                            ? "bg-yellow-50 text-yellow-700"
                            : "bg-red-50 text-red-700"
                        )}
                      >
                        {book.status}
                      </span>
                      <span className="text-gray-400 flex items-center gap-1">
                        <Clock className="w-3 h-3" />
                        {new Date(book.created_at).toLocaleDateString()}
                      </span>
                    </div>
                  </button>
                ))}
              </div>
            )}
          </div>
        </div>
      </main>
    </div>
  );
}
