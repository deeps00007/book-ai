import type { Metadata } from "next";
import "./globals.css";
import { Toaster } from "sonner";

export const metadata: Metadata = {
  title: "Test Paper Generator",
  description: "Upload a textbook and generate chapter-wise test papers by class standard.",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <body className="min-h-screen bg-slate-50 text-gray-900 antialiased">
        {children}
        <Toaster position="top-right" richColors />
      </body>
    </html>
  );
}
