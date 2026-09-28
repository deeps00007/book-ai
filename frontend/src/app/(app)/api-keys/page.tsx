"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { useAuth } from "@/components/AuthProvider";
import { Loader2, Key, Plus, Trash2, CheckCircle, XCircle, Activity } from "lucide-react";
import { toast } from "sonner";

const API_BASE = process.env.NEXT_PUBLIC_API_URL || "https://bookai-api-three.vercel.app/api/v1";

interface ApiKey {
  id: string;
  label: string;
  provider: string;
  status: string;
  error_count: number;
  last_error: string | null;
  last_used: string | null;
}

export default function ApiKeysPage() {
  const { user, loading: authLoading } = useAuth();
  const router = useRouter();
  const [keys, setKeys] = useState<ApiKey[]>([]);
  const [activeCount, setActiveCount] = useState(0);
  const [newKey, setNewKey] = useState("");
  const [newLabel, setNewLabel] = useState("");
  const [adding, setAdding] = useState(false);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    if (authLoading) return;
    if (!user) { router.push("/login"); return; }
    loadKeys();
  }, [user, authLoading]);

  async function loadKeys() {
    try {
      const token = localStorage.getItem("token");
      const res = await fetch(`${API_BASE}/api-keys`, {
        headers: { Authorization: `Bearer ${token}` },
      });
      const data = await res.json();
      setKeys(data.keys || []);
      setActiveCount(data.active_count || 0);
    } catch {
      toast.error("Failed to load keys");
    } finally {
      setLoading(false);
    }
  }

  async function handleAdd() {
    if (!newKey.trim()) return;
    setAdding(true);
    try {
      const token = localStorage.getItem("token");
      const res = await fetch(`${API_BASE}/api-keys`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          Authorization: `Bearer ${token}`,
        },
        body: JSON.stringify({ api_key: newKey.trim(), label: newLabel.trim() }),
      });
      if (!res.ok) {
        const err = await res.json().catch(() => ({ detail: "Failed" }));
        throw new Error(err.detail);
      }
      toast.success("API key added!");
      setNewKey("");
      setNewLabel("");
      loadKeys();
    } catch (err: any) {
      toast.error(err.message || "Failed to add key");
    } finally {
      setAdding(false);
    }
  }

  async function handleDelete(id: string) {
    try {
      const token = localStorage.getItem("token");
      await fetch(`${API_BASE}/api-keys/${id}`, {
        method: "DELETE",
        headers: { Authorization: `Bearer ${token}` },
      });
      toast.success("Key removed");
      loadKeys();
    } catch {
      toast.error("Failed to delete");
    }
  }

  async function handleRefresh() {
    toast.success("Refreshing...");
    loadKeys();
  }

  if (authLoading || loading) {
    return (
      <div className="flex-1 flex items-center justify-center">
        <Loader2 className="w-8 h-8 animate-spin text-brand-600" />
      </div>
    );
  }

  return (
    <main className="flex-1 overflow-y-auto p-8">
      <div className="max-w-3xl mx-auto">
          <h1 className="text-3xl font-bold mb-2">API Keys</h1>
          <p className="text-gray-500 mb-6">
            Add multiple Fireworks API keys — they rotate automatically when one gets exhausted
          </p>

          <div className="bg-white rounded-xl border border-gray-200 p-6 mb-6">
            <h2 className="font-semibold mb-4 flex items-center gap-2">
              <Plus className="w-5 h-5 text-brand-600" />
              Add New Key
            </h2>
            <div className="flex gap-3 mb-3">
              <input
                type="text" value={newLabel}
                onChange={(e) => setNewLabel(e.target.value)}
                placeholder="Label (e.g. Account 2)"
                className="flex-1 px-3 py-2.5 border border-gray-300 rounded-lg outline-none focus:ring-2 focus:ring-brand-500 text-sm"
              />
              <input
                type="text" value={newKey}
                onChange={(e) => setNewKey(e.target.value)}
                placeholder="fw_xxx..."
                className="flex-[2] px-3 py-2.5 border border-gray-300 rounded-lg outline-none focus:ring-2 focus:ring-brand-500 text-sm font-mono"
              />
              <button
                onClick={handleAdd}
                disabled={adding || !newKey.trim()}
                className="px-6 py-2.5 bg-brand-600 text-white rounded-lg hover:bg-brand-700 disabled:opacity-50 font-medium text-sm flex items-center gap-2"
              >
                {adding ? <Loader2 className="w-4 h-4 animate-spin" /> : <Plus className="w-4 h-4" />}
                Add
              </button>
            </div>
          </div>

          {keys.length === 0 ? (
            <div className="text-center py-12 bg-white rounded-xl border border-gray-200">
              <Key className="w-12 h-12 text-gray-300 mx-auto mb-3" />
              <p className="text-gray-500">No API keys added yet.</p>
              <p className="text-sm text-gray-400 mt-1">
                Add keys above to enable automatic failover when one gets exhausted.
              </p>
            </div>
          ) : (
            <div className="space-y-3">
              <div className="flex items-center justify-between mb-2">
                <span className="text-sm text-gray-500">
                  <span className="font-medium text-green-600">{activeCount}</span> active
                  / <span className="font-medium text-red-600">{keys.length - activeCount}</span> exhausted
                </span>
              </div>
              {keys.map((k) => (
                <div
                  key={k.id}
                  className={`p-4 rounded-xl border ${
                    k.status === "active"
                      ? "border-green-200 bg-green-50/30"
                      : "border-red-200 bg-red-50/20"
                  }`}
                >
                  <div className="flex items-center justify-between">
                    <div className="flex items-center gap-3">
                      {k.status === "active" ? (
                        <CheckCircle className="w-5 h-5 text-green-600" />
                      ) : (
                        <XCircle className="w-5 h-5 text-red-500" />
                      )}
                      <div>
                        <p className="font-medium text-gray-900 flex items-center gap-2">
                          {k.label || "Unnamed key"}
                          <span
                            className={`text-xs px-2 py-0.5 rounded-full ${
                              k.status === "active"
                                ? "bg-green-100 text-green-700"
                                : "bg-red-100 text-red-700"
                            }`}
                          >
                            {k.status}
                          </span>
                        </p>
                        <p className="text-xs text-gray-500 font-mono">
                          {k.provider} | errors: {k.error_count}
                          {k.last_used && ` | used: ${new Date(k.last_used).toLocaleTimeString()}`}
                        </p>
                        {k.last_error && (
                          <p className="text-xs text-red-500 mt-1 truncate max-w-md">{k.last_error}</p>
                        )}
                      </div>
                    </div>
                    <button
                      onClick={() => handleDelete(k.id)}
                      className="p-2 hover:bg-red-100 rounded-lg text-gray-400 hover:text-red-500 transition-colors"
                    >
                      <Trash2 className="w-4 h-4" />
                    </button>
                  </div>
                </div>
              ))}
            </div>
          )}

          {activeCount === 0 && keys.length > 0 && (
            <div className="mt-4 p-4 bg-amber-50 border border-amber-200 rounded-xl text-sm text-amber-700">
              No active keys! Upload processing will fail until you add a working key.
            </div>
          )}
        </div>
    </main>
  );
}
