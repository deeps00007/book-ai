"use client";

import { useRouter } from "next/navigation";
import { useAuth } from "@/components/AuthProvider";
import { BookOpen, LogOut, LayoutDashboard, Sparkles, FileText } from "lucide-react";
import { usePathname } from "next/navigation";
import { cn } from "@/lib/utils";
import Link from "next/link";

export function Sidebar() {
  const { user, logout } = useAuth();
  const router = useRouter();
  const pathname = usePathname();

  const navItems = [
    { icon: LayoutDashboard, label: "Dashboard", path: "/dashboard" },
    { icon: BookOpen, label: "My Books", path: "/books" },
    { icon: FileText, label: "Test Paper", path: "/test-paper" },
    { icon: Sparkles, label: "Generate", path: "/generate" },
  ];

  return (
    <aside className="w-64 bg-white border-r border-gray-200 flex flex-col h-screen sticky top-0">
      <div
        className="flex items-center gap-3 px-6 py-5 border-b border-gray-100 cursor-pointer"
        onClick={() => router.push("/dashboard")}
      >
        <BookOpen className="w-7 h-7 text-brand-600" />
        <span className="text-lg font-bold text-gray-900">AI Teacher</span>
      </div>

      <nav className="flex-1 px-3 py-4 space-y-1">
        {navItems.map((item) => (
          <Link
            key={item.path}
            href={item.path}
            className={cn(
              "flex items-center gap-3 w-full px-3 py-2.5 rounded-lg text-sm font-medium transition-colors",
              pathname === item.path || pathname.startsWith(item.path + "/")
                ? "bg-brand-50 text-brand-700"
                : "text-gray-600 hover:bg-gray-50"
            )}
          >
            <item.icon className="w-5 h-5" />
            {item.label}
          </Link>
        ))}
      </nav>

      <div className="px-3 py-4 border-t border-gray-100">
        <div className="flex items-center gap-3 px-3 mb-3">
          <div className="w-8 h-8 rounded-full bg-brand-100 flex items-center justify-center text-brand-700 font-medium text-sm">
            {user?.name?.[0]?.toUpperCase()}
          </div>
          <div className="flex-1 min-w-0">
            <p className="text-sm font-medium text-gray-900 truncate">{user?.name}</p>
            <p className="text-xs text-gray-500 truncate">{user?.email}</p>
          </div>
        </div>
        <button
          onClick={logout}
          className="flex items-center gap-3 w-full px-3 py-2 rounded-lg text-sm text-gray-600 hover:bg-red-50 hover:text-red-600 transition-colors"
        >
          <LogOut className="w-4 h-4" />
          Sign Out
        </button>
      </div>
    </aside>
  );
}
