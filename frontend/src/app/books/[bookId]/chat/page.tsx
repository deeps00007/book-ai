"use client";

import { useEffect, useState, useRef } from "react";
import { useParams, useRouter } from "next/navigation";
import { Sidebar } from "@/components/Sidebar";
import { useAuth } from "@/components/AuthProvider";
import { getBook, getChatStreamUrl, getChatSessions, getChapters } from "@/lib/api";
import { Book, Chapter, ChatSession } from "@/lib/types";
import { Loader2, Send, BookOpen, Bot, User, ArrowLeft, Sparkles, ChevronDown, Layers } from "lucide-react";
import { toast } from "sonner";

interface Message {
  role: "user" | "assistant";
  content: string;
  sources?: any;
}

export default function ChatPage() {
  const { user, loading: authLoading } = useAuth();
  const router = useRouter();
  const params = useParams();
  const bookId = params?.bookId as string;

  const [book, setBook] = useState<Book | null>(null);
  const [chapters, setChapters] = useState<Chapter[]>([]);
  const [selectedChapter, setSelectedChapter] = useState<string>("");
  const [sessions, setSessions] = useState<ChatSession[]>([]);
  const [sessionId, setSessionId] = useState<string | null>(null);
  const [messages, setMessages] = useState<Message[]>([]);
  const [input, setInput] = useState("");
  const [streaming, setStreaming] = useState(false);
  const [loading, setLoading] = useState(true);
  const messagesEndRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (authLoading) return;
    if (!user) { router.push("/login"); return; }
    loadBook();
  }, [user, authLoading, bookId]);

  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages]);

  async function loadBook() {
    try {
      const [bookData, sessionsData, chaptersData] = await Promise.all([
        getBook(bookId),
        getChatSessions(bookId),
        getChapters(bookId),
      ]);
      setBook(bookData);
      setSessions(sessionsData);
      setChapters(chaptersData || []);
    } catch (err) {
      toast.error("Failed to load book");
      router.push("/books");
    } finally {
      setLoading(false);
    }
  }

  async function handleSend() {
    if (!input.trim() || streaming || !bookId) return;
    const question = input.trim();
    setInput("");
    setMessages((prev) => [...prev, { role: "user", content: question }]);
    setStreaming(true);

    const assistantMessage: Message = { role: "assistant", content: "" };
    setMessages((prev) => [...prev, assistantMessage]);

    try {
      const { url, options } = getChatStreamUrl(bookId, question, sessionId, selectedChapter || undefined);
      const response = await fetch(url, options);
      const reader = response.body?.getReader();
      const decoder = new TextDecoder();

      if (!reader) throw new Error("No reader");

      let buffer = "";
      while (true) {
        const { done, value } = await reader.read();
        if (done) break;
        buffer += decoder.decode(value, { stream: true });
        const lines = buffer.split("\n");
        buffer = lines.pop() || "";

        for (const line of lines) {
          if (line.startsWith("data: ")) {
            try {
              const data = JSON.parse(line.slice(6));
              if (data.done) {
                if (data.session_id) setSessionId(data.session_id);
                if (data.sources) {
                  setMessages((prev) => {
                    const newMsgs = [...prev];
                    const last = { ...newMsgs[newMsgs.length - 1] };
                    if (last.role === "assistant") {
                      last.sources = data.sources;
                      newMsgs[newMsgs.length - 1] = last;
                    }
                    return newMsgs;
                  });
                }
              } else if (data.content) {
                setMessages((prev) => {
                  const newMsgs = [...prev];
                  const last = { ...newMsgs[newMsgs.length - 1] };
                  if (last.role === "assistant") {
                    last.content += data.content;
                    newMsgs[newMsgs.length - 1] = last;
                  }
                  return newMsgs;
                });
              }
            } catch {}
          }
        }
      }
    } catch (err: any) {
      toast.error(err.message || "Chat failed");
    } finally {
      setStreaming(false);
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
      <main className="flex-1 flex flex-col h-screen">
        <header className="px-6 py-4 border-b border-gray-200 bg-white flex items-center justify-between shrink-0">
          <div className="flex items-center gap-3">
            <button
              onClick={() => router.push("/books")}
              className="p-1.5 hover:bg-gray-100 rounded-lg"
            >
              <ArrowLeft className="w-5 h-5 text-gray-500" />
            </button>
            <BookOpen className="w-6 h-6 text-brand-600" />
            <div>
              <h1 className="font-semibold text-gray-900">{book?.title}</h1>
              <p className="text-xs text-gray-500">{book?.total_pages} pages &middot; {book?.total_chunks} chunks</p>
            </div>
          </div>
          {chapters.length > 1 && (
            <div className="flex items-center gap-2">
              <Layers className="w-4 h-4 text-gray-400" />
              <select
                value={selectedChapter}
                onChange={(e) => {
                  setSelectedChapter(e.target.value);
                  setMessages([]);
                  setSessionId(null);
                }}
                className="px-3 py-1.5 border border-gray-300 rounded-lg text-sm outline-none focus:ring-2 focus:ring-brand-500 bg-white"
              >
                <option value="">All Chapters</option>
                {chapters.map((ch) => (
                  <option key={ch.id} value={ch.id}>
                    {ch.title} (p. {ch.start_page}-{ch.end_page})
                  </option>
                ))}
              </select>
            </div>
          )}
          <button
            onClick={() => router.push(`/generate?book_id=${bookId}`)}
            className="flex items-center gap-2 px-4 py-2 text-sm bg-purple-50 text-purple-700 rounded-lg hover:bg-purple-100 font-medium transition-colors"
          >
            <Sparkles className="w-4 h-4" />
            Generate Content
          </button>
        </header>

        <div className="flex-1 overflow-y-auto p-6">
          <div className="max-w-3xl mx-auto space-y-6">
            {messages.length === 0 && (
              <div className="text-center py-20">
                <Bot className="w-16 h-16 text-brand-200 mx-auto mb-4" />
                <h2 className="text-xl font-semibold text-gray-600 mb-2">
                  Chat with {book?.title}
                </h2>
                <p className="text-gray-400">Ask questions about the book content</p>
              </div>
            )}

            {messages.map((msg, i) => (
              <div key={i} className={`flex gap-3 ${msg.role === "user" ? "justify-end" : ""}`}>
                {msg.role === "assistant" && (
                  <div className="w-8 h-8 rounded-full bg-brand-100 flex items-center justify-center shrink-0 mt-1">
                    <Bot className="w-4 h-4 text-brand-600" />
                  </div>
                )}
                <div
                  className={`max-w-[80%] rounded-2xl px-4 py-3 ${
                    msg.role === "user"
                      ? "bg-brand-600 text-white rounded-br-md"
                      : "bg-gray-100 text-gray-900 rounded-bl-md"
                  }`}
                >
                  <p className="text-sm whitespace-pre-wrap leading-relaxed">
                    {msg.content || (streaming && msg === messages[messages.length - 1] ? (
                      <span className="inline-flex gap-1">
                        <span className="w-1.5 h-1.5 bg-gray-400 rounded-full animate-bounce" style={{ animationDelay: "0ms" }} />
                        <span className="w-1.5 h-1.5 bg-gray-400 rounded-full animate-bounce" style={{ animationDelay: "150ms" }} />
                        <span className="w-1.5 h-1.5 bg-gray-400 rounded-full animate-bounce" style={{ animationDelay: "300ms" }} />
                      </span>
                    ) : null)}
                  </p>
                  {msg.sources?.length > 0 && (
                    <details className="mt-2">
                      <summary className="text-xs text-gray-400 cursor-pointer hover:text-gray-500">
                        Sources ({msg.sources.length} chunks)
                      </summary>
                      <div className="mt-2 space-y-1">
                        {msg.sources.slice(0, 3).map((s: any, idx: number) => (
                          <p key={idx} className="text-xs text-gray-400 bg-white/50 p-2 rounded">
                            {(s.content || "").slice(0, 150)}...
                          </p>
                        ))}
                      </div>
                    </details>
                  )}
                </div>
                {msg.role === "user" && (
                  <div className="w-8 h-8 rounded-full bg-brand-600 flex items-center justify-center shrink-0 mt-1">
                    <User className="w-4 h-4 text-white" />
                  </div>
                )}
              </div>
            ))}
            <div ref={messagesEndRef} />
          </div>
        </div>

        <div className="p-4 border-t border-gray-200 bg-white">
          <div className="max-w-3xl mx-auto flex gap-3">
            <input
              type="text"
              value={input}
              onChange={(e) => setInput(e.target.value)}
              onKeyDown={(e) => e.key === "Enter" && !e.shiftKey && handleSend()}
              placeholder="Ask a question about this book..."
              className="flex-1 px-4 py-3 border border-gray-300 rounded-xl focus:ring-2 focus:ring-brand-500 focus:border-transparent outline-none text-sm"
              disabled={streaming}
            />
            <button
              onClick={handleSend}
              disabled={!input.trim() || streaming}
              className="px-5 py-3 bg-brand-600 text-white rounded-xl hover:bg-brand-700 transition-colors disabled:opacity-50"
            >
              <Send className="w-5 h-5" />
            </button>
          </div>
        </div>
      </main>
    </div>
  );
}
