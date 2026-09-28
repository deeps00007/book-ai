"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { useAuth } from "@/components/AuthProvider";
import { getUsageSummary, getUsageDaily, getUsageByModel } from "@/lib/api";
import { Loader2, Activity, Zap, Coins, Database, TrendingDown, Clock } from "lucide-react";
import { toast } from "sonner";

export default function UsagePage() {
  const { user, loading: authLoading } = useAuth();
  const router = useRouter();
  const [summary, setSummary] = useState<any>(null);
  const [daily, setDaily] = useState<any[]>([]);
  const [byModel, setByModel] = useState<any[]>([]);
  const [loading, setLoading] = useState(true);
  const [days, setDays] = useState(30);

  useEffect(() => {
    if (authLoading) return;
    if (!user) { router.push("/login"); return; }
    load();
  }, [user, authLoading, days]);

  async function load() {
    setLoading(true);
    try {
      const [s, d, m] = await Promise.all([
        getUsageSummary(days),
        getUsageDaily(Math.min(days, 30)),
        getUsageByModel(days),
      ]);
      setSummary(s);
      setDaily(d || []);
      setByModel(m || []);
    } catch {
      toast.error("Failed to load usage");
    } finally {
      setLoading(false);
    }
  }

  if (authLoading || loading) {
    return (
      <div className="flex-1 flex items-center justify-center">
        <Loader2 className="w-8 h-8 animate-spin text-brand-600" />
      </div>
    );
  }

  const maxCost = Math.max(...daily.map((d) => d.cost), 0.000001);
  const maxReq = Math.max(...daily.map((d) => d.requests), 1);

  const cards = [
    { icon: Activity, label: "AI Requests", value: summary?.total_requests ?? 0, sub: `last ${days} days`, color: "text-blue-600 bg-blue-50" },
    { icon: Database, label: "Cache Hits", value: summary?.cached_requests ?? 0, sub: `${summary?.cache_hit_rate ?? 0}% of requests`, color: "text-green-600 bg-green-50" },
    { icon: Zap, label: "Tokens Used", value: (summary?.total_tokens ?? 0).toLocaleString(), sub: `${(summary?.tokens_in ?? 0).toLocaleString()} in / ${(summary?.tokens_out ?? 0).toLocaleString()} out`, color: "text-purple-600 bg-purple-50" },
    { icon: Coins, label: "Estimated Cost", value: `$${(summary?.estimated_cost_usd ?? 0).toFixed(4)}`, sub: `₹${(summary?.estimated_cost_inr ?? 0).toFixed(2)}`, color: "text-amber-600 bg-amber-50" },
    { icon: TrendingDown, label: "Saved by Cache", value: `$${(summary?.estimated_savings_usd ?? 0).toFixed(4)}`, sub: "estimated", color: "text-emerald-600 bg-emerald-50" },
    { icon: Clock, label: "Avg Response", value: `${((summary?.avg_response_ms ?? 0) / 1000).toFixed(1)}s`, sub: "per request", color: "text-gray-600 bg-gray-100" },
  ];

  return (
    <main className="flex-1 overflow-y-auto p-8">
      <div className="max-w-5xl mx-auto">
          <div className="flex items-center justify-between mb-6">
            <div>
              <h1 className="text-3xl font-bold mb-1">Usage & Cost</h1>
              <p className="text-gray-500">AI usage, estimated cost and cache savings</p>
            </div>
            <select
              value={days}
              onChange={(e) => setDays(parseInt(e.target.value))}
              className="px-3 py-2 border border-gray-300 rounded-lg text-sm outline-none focus:ring-2 focus:ring-brand-500 bg-white"
            >
              <option value={7}>Last 7 days</option>
              <option value={30}>Last 30 days</option>
              <option value={90}>Last 90 days</option>
            </select>
          </div>

          <div className="grid grid-cols-3 gap-4 mb-8">
            {cards.map((c) => (
              <div key={c.label} className="bg-white rounded-xl border border-gray-200 p-5">
                <div className={`w-9 h-9 rounded-lg flex items-center justify-center mb-3 ${c.color}`}>
                  <c.icon className="w-5 h-5" />
                </div>
                <p className="text-2xl font-bold text-gray-900">{c.value}</p>
                <p className="text-sm font-medium text-gray-600">{c.label}</p>
                <p className="text-xs text-gray-400 mt-0.5">{c.sub}</p>
              </div>
            ))}
          </div>

          <div className="bg-white rounded-xl border border-gray-200 p-6 mb-6">
            <h2 className="font-semibold mb-4">Daily Cost</h2>
            {daily.length === 0 ? (
              <p className="text-sm text-gray-400 py-8 text-center">No usage yet</p>
            ) : (
              <div className="flex items-end gap-2 h-40">
                {daily.map((d) => (
                  <div key={d.date} className="flex-1 flex flex-col items-center gap-1 group">
                    <div className="relative w-full flex justify-center" style={{ height: "120px" }}>
                      <div
                        className="w-full bg-brand-500 rounded-t group-hover:bg-brand-600 transition-all"
                        style={{ height: `${Math.max((d.cost / maxCost) * 120, 2)}px`, alignSelf: "flex-end" }}
                        title={`$${d.cost.toFixed(4)} · ${d.requests} requests`}
                      />
                    </div>
                    <span className="text-[10px] text-gray-400 rotate-45 origin-left whitespace-nowrap">{d.date.slice(5)}</span>
                  </div>
                ))}
              </div>
            )}
          </div>

          <div className="bg-white rounded-xl border border-gray-200 p-6">
            <h2 className="font-semibold mb-4">Usage by Model</h2>
            {byModel.length === 0 ? (
              <p className="text-sm text-gray-400 py-6 text-center">No data</p>
            ) : (
              <table className="w-full text-sm">
                <thead>
                  <tr className="border-b border-gray-200 text-left text-xs text-gray-500 uppercase">
                    <th className="py-2">Model</th>
                    <th className="py-2 text-right">Requests</th>
                    <th className="py-2 text-right">Tokens</th>
                    <th className="py-2 text-right">Cost</th>
                  </tr>
                </thead>
                <tbody>
                  {byModel.map((m) => (
                    <tr key={m.model} className="border-b border-gray-100">
                      <td className="py-2 font-mono text-xs">{m.model}</td>
                      <td className="py-2 text-right">{m.requests}</td>
                      <td className="py-2 text-right">{m.tokens.toLocaleString()}</td>
                      <td className="py-2 text-right">${m.cost.toFixed(4)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            )}
          </div>

          <p className="text-xs text-gray-400 mt-4">
            Costs are estimates based on published per-token rates and may differ from your invoice.
            Cached answers cost $0.
          </p>
        </div>
    </main>
  );
}
