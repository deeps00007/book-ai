"use client";

import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";
import { getMe } from "@/lib/api";
import { User } from "@/lib/types";

export default function HomePage() {
  const router = useRouter();
  const [checking, setChecking] = useState(true);

  useEffect(() => {
    const token = localStorage.getItem("token");
    if (!token) {
      router.push("/login");
      return;
    }
    getMe()
      .then((u) => {
        if (u) router.push("/dashboard");
        else router.push("/login");
      })
      .catch(() => router.push("/login"))
      .finally(() => setChecking(false));
  }, [router]);

  if (checking) {
    return (
      <div className="flex items-center justify-center min-h-screen">
        <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-brand-600" />
      </div>
    );
  }

  return null;
}
