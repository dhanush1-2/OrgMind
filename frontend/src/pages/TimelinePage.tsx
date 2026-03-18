import { useEffect, useState } from "react";
import { get } from "../api";
import { AlertCircle, Loader2 } from "lucide-react";

interface Decision {
  id: string;
  decision: string;
  date: string;
  stale: boolean;
  confidence: number;
  source_url: string | null;
  entities: string[];
}

interface Conflict {
  source_id: string;
  target_id: string;
  source_title: string;
  target_title: string;
  reason: string;
  severity: string;
}

export default function TimelinePage() {
  const [decisions, setDecisions] = useState<Decision[]>([]);
  const [conflicts, setConflicts] = useState<Conflict[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  useEffect(() => {
    Promise.all([
      get<{ decisions: Decision[] }>("/timeline"),
      get<{ conflicts: Conflict[] }>("/conflicts"),
    ])
      .then(([t, c]) => {
        setDecisions(t.decisions ?? []);
        setConflicts(c.conflicts ?? []);
      })
      .catch((e) => setError(e.message))
      .finally(() => setLoading(false));
  }, []);

  const conflictIds = new Set(
    conflicts.flatMap((c) => [c.source_id, c.target_id])
  );

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

  return (
    <div className="px-8 py-6">
      <h1 className="text-xl font-semibold mb-1">Timeline & Conflicts</h1>
      <p className="text-sm text-gray-400 mb-6">
        {decisions.length} decisions · {conflicts.length} conflicts
      </p>

      {/* Conflicts banner */}
      {conflicts.length > 0 && (
        <div className="mb-6 space-y-2">
          <h2 className="text-sm font-medium text-yellow-400">
            ⚠ Active Conflicts
          </h2>
          {conflicts.map((c, i) => (
            <div
              key={i}
              className="bg-yellow-900/30 border border-yellow-700/50 rounded-lg px-4 py-2 text-sm"
            >
              <span className="text-yellow-300 font-medium">
                {c.source_title}
              </span>{" "}
              ↔{" "}
              <span className="text-yellow-300 font-medium">
                {c.target_title}
              </span>
              <span className="text-gray-400 ml-2">— {c.reason}</span>
              <span
                className={`ml-2 text-xs px-2 py-0.5 rounded-full ${
                  c.severity === "high"
                    ? "bg-red-900 text-red-300"
                    : "bg-yellow-900 text-yellow-300"
                }`}
              >
                {c.severity}
              </span>
            </div>
          ))}
        </div>
      )}

      {/* Timeline */}
      <div className="relative border-l-2 border-gray-700 pl-6 space-y-6">
        {decisions.map((d) => (
          <div key={d.id} className="relative">
            <div
              className={`absolute -left-[29px] w-3 h-3 rounded-full border-2 ${
                d.stale
                  ? "bg-gray-700 border-gray-500"
                  : conflictIds.has(d.id)
                  ? "bg-yellow-500 border-yellow-300"
                  : "bg-indigo-500 border-indigo-300"
              }`}
            />
            <div
              className={`bg-gray-800 rounded-xl p-4 border ${
                conflictIds.has(d.id)
                  ? "border-yellow-700/50"
                  : "border-gray-700"
              }`}
            >
              <div className="flex items-start justify-between gap-4">
                <p className="text-sm font-medium text-gray-100">{d.decision}</p>
                <span className="text-xs text-gray-500 whitespace-nowrap">
                  {d.date}
                </span>
              </div>
              <div className="flex flex-wrap gap-2 mt-2">
                {d.entities.map((e) => (
                  <span
                    key={e}
                    className="text-xs bg-gray-700 text-gray-300 px-2 py-0.5 rounded-full"
                  >
                    {e}
                  </span>
                ))}
                {d.stale && (
                  <span className="text-xs bg-gray-700 text-gray-500 px-2 py-0.5 rounded-full">
                    stale
                  </span>
                )}
                <span className="text-xs text-gray-600 ml-auto">
                  conf {(d.confidence * 100).toFixed(0)}%
                </span>
              </div>
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}
