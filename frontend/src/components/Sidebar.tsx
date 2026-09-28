"use client";

import { useEffect, useState } from "react";
import { useRouter, usePathname } from "next/navigation";
import { useAuth } from "@/components/AuthProvider";
import {
  BookOpen, LogOut, LayoutDashboard, Sparkles, FileText, Key, BarChart3,
  ChevronLeft, ChevronRight,
} from "lucide-react";
import { cn } from "@/lib/utils";
import Link from "next/link";

const NAV_ITEMS = [
  { icon: LayoutDashboard, label: "Dashboard", path: "/dashboard" },
  { icon: BookOpen, label: "My Books", path: "/books" },
  { icon: FileText, label: "Test Paper", path: "/test-paper" },
  { icon: Sparkles, label: "Generate", path: "/generate" },
  { icon: Key, label: "API Keys", path: "/api-keys" },
  { icon: BarChart3, label: "Usage & Cost", path: "/usage" },
];

export function Sidebar() {
  const { user, logout } = useAuth();
  const router = useRouter();
  const pathname = usePathname();
  const [collapsed, setCollapsed] = useState(false);

  useEffect(() => {
    const saved = localStorage.getItem("sidebar-collapsed");
    if (saved !== null) setCollapsed(saved === "1");
    else if (window.innerWidth < 1024) setCollapsed(true);
  }, []);

  function toggle() {
    setCollapsed((c) => {
      localStorage.setItem("sidebar-collapsed", c ? "0" : "1");
      return !c;
    });
  }

  return (
    <aside
      className={cn(
        "bg-white border-r border-gray-200 flex flex-col h-screen sticky top-0 shrink-0 z-20",
        "transition-[width] duration-200 ease-in-out",
        collapsed ? "w-[68px]" : "w-64"
      )}
    >
      {/* Brand + collapse toggle */}
      <div className="flex items-center gap-3 px-3 py-4 border-b border-gray-100 h-[69px]">
        <div
          className="flex items-center gap-3 flex-1 min-w-0 cursor-pointer"
          onClick={() => router.push("/dashboard")}
        >
          <BookOpen className="w-7 h-7 text-brand-600 shrink-0" />
          {!collapsed && (
            <span className="text-lg font-bold text-gray-900 truncate">AI Teacher</span>
          )}
        </div>
        {!collapsed && (
          <button
            onClick={toggle}
            title="Collapse sidebar"
            className="p-1.5 rounded-lg text-gray-400 hover:bg-gray-100 hover:text-gray-600 transition-colors"
          >
            <ChevronLeft className="w-4 h-4" />
          </button>
        )}
      </div>

      {/* Expand button when collapsed */}
      {collapsed && (
        <button
          onClick={toggle}
          title="Expand sidebar"
          className="mx-auto mt-2 p-1.5 rounded-lg text-gray-400 hover:bg-gray-100 hover:text-gray-600 transition-colors"
        >
          <ChevronRight className="w-4 h-4" />
        </button>
      )}

      <nav className="flex-1 px-2 py-4 space-y-1 overflow-y-auto">
        {NAV_ITEMS.map((item) => {
          const active =
            pathname === item.path || pathname.startsWith(item.path + "/");
          return (
            <Link
              key={item.path}
              href={item.path}
              title={collapsed ? item.label : undefined}
              className={cn(
                "flex items-center gap-3 rounded-lg text-sm font-medium transition-colors",
                collapsed ? "justify-center px-0 py-2.5" : "px-3 py-2.5",
                active
                  ? "bg-brand-50 text-brand-700"
                  : "text-gray-600 hover:bg-gray-50"
              )}
            >
              <item.icon className="w-5 h-5 shrink-0" />
              {!collapsed && <span className="truncate">{item.label}</span>}
            </Link>
          );
        })}
      </nav>

      <div className={cn("py-4 border-t border-gray-100", collapsed ? "px-2" : "px-3")}>
        <div className={cn("flex items-center gap-3 mb-3", collapsed && "justify-center px-0")}>
          <div
            className="w-8 h-8 rounded-full bg-brand-100 flex items-center justify-center text-brand-700 font-medium text-sm shrink-0"
            title={user?.name}
          >
            {user?.name?.[0]?.toUpperCase()}
          </div>
          {!collapsed && (
            <div className="flex-1 min-w-0">
              <p className="text-sm font-medium text-gray-900 truncate">{user?.name}</p>
              <p className="text-xs text-gray-500 truncate">{user?.email}</p>
            </div>
          )}
        </div>
        <button
          onClick={logout}
          title={collapsed ? "Sign Out" : undefined}
          className={cn(
            "flex items-center gap-3 w-full rounded-lg text-sm text-gray-600 hover:bg-red-50 hover:text-red-600 transition-colors",
            collapsed ? "justify-center px-0 py-2" : "px-3 py-2"
          )}
        >
          <LogOut className="w-4 h-4 shrink-0" />
          {!collapsed && <span>Sign Out</span>}
        </button>
      </div>
    </aside>
  );
}
