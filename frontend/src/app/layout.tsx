import type { Metadata } from "next";
import "./globals.css";
import { Toaster } from "sonner";
import { AuthProvider } from "@/components/AuthProvider";

export const metadata: Metadata = {
  title: "AI Teaching Platform",
  description: "Upload books, chat with AI, generate worksheets, tests, and more.",
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="en">
      <body className="min-h-screen bg-gradient-to-br from-slate-50 to-blue-50">
        <AuthProvider>
          {children}
        </AuthProvider>
        <Toaster position="top-right" richColors />
      </body>
    </html>
  );
}
