"use client";

import { useState, useCallback } from "react";
import { useRouter } from "next/navigation";
import { Sidebar } from "@/components/Sidebar";
import { uploadBook } from "@/lib/api";
import { Upload, FileText, X, Loader2, ArrowLeft } from "lucide-react";
import { useDropzone } from "react-dropzone";
import { toast } from "sonner";

export default function UploadPage() {
  const router = useRouter();
  const [file, setFile] = useState<File | null>(null);
  const [title, setTitle] = useState("");
  const [author, setAuthor] = useState("");
  const [uploading, setUploading] = useState(false);

  const onDrop = useCallback((acceptedFiles: File[]) => {
    const f = acceptedFiles[0];
    if (f) {
      setFile(f);
      const name = f.name.replace(".pdf", "").replace(/_/g, " ").replace(/-/g, " ");
      setTitle(name);
    }
  }, []);

  const { getRootProps, getInputProps, isDragActive } = useDropzone({
    onDrop,
    accept: { "application/pdf": [".pdf"] },
    maxFiles: 1,
  });

  const handleUpload = async () => {
    if (!file || !title) return;
    setUploading(true);
    try {
      const result = await uploadBook(file, title, author);
      toast.success("Book uploaded! Processing has started.");
      router.push("/books");
    } catch (err: any) {
      toast.error(err.message || "Upload failed");
    } finally {
      setUploading(false);
    }
  };

  return (
    <div className="flex h-screen">
      <Sidebar />
      <main className="flex-1 overflow-y-auto p-8">
        <div className="max-w-2xl mx-auto">
          <button
            onClick={() => router.push("/books")}
            className="flex items-center gap-2 text-sm text-gray-500 hover:text-gray-700 mb-6"
          >
            <ArrowLeft className="w-4 h-4" />
            Back to Books
          </button>

          <h1 className="text-3xl font-bold mb-2">Upload Book</h1>
          <p className="text-gray-500 mb-8">Upload a PDF textbook to chat with</p>

          {!file ? (
            <div
              {...getRootProps()}
              className={`border-2 border-dashed rounded-xl p-16 text-center cursor-pointer transition-all
                ${isDragActive ? "border-brand-500 bg-brand-50" : "border-gray-300 hover:border-brand-400 hover:bg-brand-50/50"}`}
            >
              <input {...getInputProps()} />
              <Upload className="w-16 h-16 text-gray-400 mx-auto mb-4" />
              <h3 className="text-lg font-medium text-gray-600 mb-2">
                {isDragActive ? "Drop your PDF here" : "Drag & drop your PDF"}
              </h3>
              <p className="text-sm text-gray-400">or click to browse</p>
            </div>
          ) : (
            <div className="space-y-6">
              <div className="flex items-center gap-4 p-4 bg-gray-50 rounded-lg">
                <FileText className="w-10 h-10 text-brand-600" />
                <div className="flex-1">
                  <p className="font-medium text-gray-900">{file.name}</p>
                  <p className="text-sm text-gray-500">
                    {(file.size / (1024 * 1024)).toFixed(1)} MB
                  </p>
                  {file.size > 50 * 1024 * 1024 && (
                    <p className="text-xs text-red-500 mt-1">
                      Over 50MB limit — please compress this PDF first (e.g. Smallpdf / Adobe)
                    </p>
                  )}
                </div>
                <button
                  onClick={() => setFile(null)}
                  className="p-1 hover:bg-gray-200 rounded"
                >
                  <X className="w-5 h-5 text-gray-400" />
                </button>
              </div>

              <div>
                <label className="block text-sm font-medium text-gray-700 mb-1">
                  Book Title *
                </label>
                <input
                  type="text"
                  value={title}
                  onChange={(e) => setTitle(e.target.value)}
                  className="w-full px-4 py-3 border border-gray-300 rounded-lg focus:ring-2 focus:ring-brand-500 focus:border-transparent outline-none"
                  placeholder="e.g. Physics Grade 10"
                />
              </div>

              <div>
                <label className="block text-sm font-medium text-gray-700 mb-1">
                  Author (optional)
                </label>
                <input
                  type="text"
                  value={author}
                  onChange={(e) => setAuthor(e.target.value)}
                  className="w-full px-4 py-3 border border-gray-300 rounded-lg focus:ring-2 focus:ring-brand-500 focus:border-transparent outline-none"
                  placeholder="e.g. NCERT"
                />
              </div>

              <button
                onClick={handleUpload}
                disabled={!title || uploading}
                className="w-full py-3 bg-brand-600 text-white rounded-lg font-medium hover:bg-brand-700 transition-colors disabled:opacity-50 flex items-center justify-center gap-2"
              >
                {uploading ? (
                  <>
                    <Loader2 className="w-4 h-4 animate-spin" />
                    Uploading...
                  </>
                ) : (
                  <>
                    <Upload className="w-4 h-4" />
                    Upload & Process
                  </>
                )}
              </button>
            </div>
          )}
        </div>
      </main>
    </div>
  );
}
