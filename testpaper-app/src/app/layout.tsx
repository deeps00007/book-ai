import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "Test Paper Generator",
  description: "Upload a textbook and generate chapter-wise test papers by class standard.",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <body className="min-h-screen bg-gradient-to-br from-slate-50 to-blue-50 text-gray-900">
        {children}
      </body>
    </html>
  );
}
