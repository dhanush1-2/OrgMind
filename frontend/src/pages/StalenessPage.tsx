import { useEffect, useState } from "react";
import { get, post } from "../api";
import { Loader2, AlertCircle, RefreshCw } from "lucide-react";
import { BarChart, Bar, XAxis, YAxis, Tooltip, ResponsiveContainer, Cell } from "recharts";

interface Metrics {
  total: number;
  stale: number;
  active: number;
  avg_confidence: number;
  stale_pct: number;
}

interface StaleDecision {
  id: string;
  title: string;
  date: string;
  confidence: number;
  entities: string[];
}

export default function StalenessPage() {
  const [metrics, setMetrics] = useState<Metrics | null>(null);
  const [stale, setStale] = useState<StaleDecision[]>([]);
  const [loading, setLoading] = useState(true);
  const [running, setRunning] = useState(false);
  const [error, setError] = useState("");

  function load() {
    setLoading(true);
    get<{ metrics: Metrics; stale_decisions: StaleDecision[] }>("/staleness")
      .then((d) => {
        setMetrics(d.metrics);
        setStale(d.stale_decisions ?? []);
      })
      .catch((e) => setError(e.message))
      .finally(() => setLoading(false));
  }

  useEffect(load, []);

  async function runHealthCheck() {
    setRunning(true);
    try {
      await post("/staleness/run", {});
      load();
    } catch (e: unknown) {
      setError((e as Error).message);
    } finally {
      setRunning(false);
    }
  }

  if (loading)
    return (
      <div className="flex items-center justify-center h-full">
        <Loader2 className="animate-spin text-indigo-400" size={32} />
      </div>
    );

  if (error)
    return (
      <div className="p-8 text-red-400">
        <AlertCircle className="inline mr-2" size={16} />
        {error}
      </div>
    );

  const chartData = metrics
    ? [
        { name: "Active", value: metrics.active, fill: "#6366f1" },
        { name: "Stale", value: metrics.stale, fill: "#f59e0b" },
      ]
    : [];

  return (
    <div className="px-8 py-6">
      <div className="flex items-center justify-between mb-6">
        <div>
          <h1 className="text-xl font-semibold">Staleness Dashboard</h1>
          <p className="text-sm text-gray-400">
            Decisions older than 180 days are flagged stale
          </p>
        </div>
        <button
          onClick={runHealthCheck}
          disabled={running}
          className="flex items-center gap-2 bg-gray-800 hover:bg-gray-700 border border-gray-700 px-4 py-2 rounded-lg text-sm transition-colors disabled:opacity-50"
        >
          <RefreshCw size={14} className={running ? "animate-spin" : ""} />
          Run health check
        </button>
      </div>

      {/* Metrics */}
      {metrics && (
        <div className="grid grid-cols-4 gap-4 mb-8">
          {[
            { label: "Total", value: metrics.total, color: "text-gray-100" },
            { label: "Active", value: metrics.active, color: "text-indigo-400" },
            { label: "Stale", value: metrics.stale, color: "text-yellow-400" },
            {
              label: "Avg Confidence",
              value: `${(metrics.avg_confidence * 100).toFixed(1)}%`,
              color: "text-emerald-400",
            },
          ].map((m) => (
            <div
              key={m.label}
              className="bg-gray-800 border border-gray-700 rounded-xl p-4"
            >
              <p className="text-xs text-gray-500 mb-1">{m.label}</p>
              <p className={`text-2xl font-semibold ${m.color}`}>{m.value}</p>
            </div>
          ))}
        </div>
      )}

      {/* Chart */}
      <div className="bg-gray-800 border border-gray-700 rounded-xl p-4 mb-8" style={{ height: 200 }}>
        <ResponsiveContainer width="100%" height="100%">
          <BarChart data={chartData} barSize={48}>
            <XAxis dataKey="name" tick={{ fill: "#9ca3af", fontSize: 12 }} />
            <YAxis tick={{ fill: "#9ca3af", fontSize: 12 }} />
            <Tooltip
              contentStyle={{ background: "#1f2937", border: "none", borderRadius: 8 }}
              labelStyle={{ color: "#f3f4f6" }}
            />
            <Bar dataKey="value" radius={[4, 4, 0, 0]}>
              {chartData.map((entry, i) => (
                <Cell key={i} fill={entry.fill} />
              ))}
            </Bar>
          </BarChart>
        </ResponsiveContainer>
      </div>

      {/* Stale list */}
      <h2 className="text-sm font-medium text-gray-300 mb-3">
        Stale Decisions ({stale.length})
      </h2>
      {stale.length === 0 ? (
        <p className="text-gray-600 text-sm">No stale decisions — great!</p>
      ) : (
        <div className="space-y-2">
          {stale.map((d) => (
            <div
              key={d.id}
              className="bg-gray-800 border border-yellow-700/30 rounded-lg px-4 py-3 flex items-center justify-between"
            >
              <div>
                <p className="text-sm text-gray-200">{d.title}</p>
                <p className="text-xs text-gray-500 mt-0.5">{d.date}</p>
              </div>
              <div className="text-xs text-gray-600">
                {(d.confidence * 100).toFixed(0)}% conf
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
