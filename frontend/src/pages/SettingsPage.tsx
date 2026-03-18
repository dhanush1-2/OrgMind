import { useEffect, useState } from "react";
import { get } from "../api";
import { Loader2, CheckCircle, XCircle, AlertCircle } from "lucide-react";

interface IntegrationStatus {
  status: string;
  [key: string]: unknown;
}

interface IntegrationsResponse {
  integrations: Record<string, IntegrationStatus>;
  all_healthy: boolean;
}

interface ReviewItem {
  id: string;
  decision_id: string;
  flags: string[];
  status: string;
  flagged_at: string;
}

export default function SettingsPage() {
  const [integrations, setIntegrations] = useState<IntegrationsResponse | null>(null);
  const [reviewItems, setReviewItems] = useState<ReviewItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  useEffect(() => {
    Promise.all([
      get<IntegrationsResponse>("/integrations"),
      get<{ items: ReviewItem[] }>("/review-queue?status=pending"),
    ])
      .then(([int, rq]) => {
        setIntegrations(int);
        setReviewItems(rq.items ?? []);
      })
      .catch((e) => setError(e.message))
      .finally(() => setLoading(false));
  }, []);

  async function handleAction(id: string, action: string) {
    await fetch(`/api/v1/review-queue/${id}`, {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ action }),
    });
    setReviewItems((prev) => prev.filter((i) => i.id !== id));
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

  const STATUS_ICON: Record<string, React.ReactNode> = {
    connected: <CheckCircle size={14} className="text-emerald-400" />,
    unavailable: <AlertCircle size={14} className="text-yellow-400" />,
    error: <XCircle size={14} className="text-red-400" />,
  };

  return (
    <div className="px-8 py-6 space-y-8">
      <div>
        <h1 className="text-xl font-semibold mb-1">Settings & Integrations</h1>
        <p className="text-sm text-gray-400">
          Live status for all connected services
        </p>
      </div>

      {/* Integrations */}
      <section>
        <h2 className="text-sm font-medium text-gray-300 mb-3">
          Connected Services
        </h2>
        <div className="grid grid-cols-2 gap-3">
          {integrations &&
            Object.entries(integrations.integrations).map(([name, info]) => (
              <div
                key={name}
                className="bg-gray-800 border border-gray-700 rounded-xl px-4 py-3 flex items-center justify-between"
              >
                <div>
                  <p className="text-sm font-medium capitalize">{name}</p>
                  {Object.entries(info)
                    .filter(([k]) => k !== "status")
                    .map(([k, v]) => (
                      <p key={k} className="text-xs text-gray-500">
                        {k}: {String(v)}
                      </p>
                    ))}
                </div>
                <div className="flex items-center gap-1.5">
                  {STATUS_ICON[info.status] ?? STATUS_ICON.error}
                  <span className="text-xs text-gray-400">{info.status}</span>
                </div>
              </div>
            ))}
        </div>
      </section>

      {/* Review Queue */}
      <section>
        <h2 className="text-sm font-medium text-gray-300 mb-3">
          Review Queue{" "}
          <span className="text-gray-600">({reviewItems.length} pending)</span>
        </h2>
        {reviewItems.length === 0 ? (
          <p className="text-sm text-gray-600">Queue is clear.</p>
        ) : (
          <div className="space-y-2">
            {reviewItems.map((item) => (
              <div
                key={item.id}
                className="bg-gray-800 border border-gray-700 rounded-xl px-4 py-3 flex items-center justify-between"
              >
                <div>
                  <p className="text-sm text-gray-200">
                    Decision{" "}
                    <code className="text-xs bg-gray-700 px-1 rounded">
                      {item.decision_id}
                    </code>
                  </p>
                  <div className="flex gap-1 mt-1">
                    {item.flags.map((f) => (
                      <span
                        key={f}
                        className="text-xs bg-gray-700 text-yellow-300 px-2 py-0.5 rounded-full"
                      >
                        {f}
                      </span>
                    ))}
                  </div>
                </div>
                <div className="flex gap-2">
                  <button
                    onClick={() => handleAction(item.id, "approve")}
                    className="text-xs bg-emerald-900 hover:bg-emerald-800 text-emerald-300 px-3 py-1 rounded-lg transition-colors"
                  >
                    Approve
                  </button>
                  <button
                    onClick={() => handleAction(item.id, "reject")}
                    className="text-xs bg-red-900 hover:bg-red-800 text-red-300 px-3 py-1 rounded-lg transition-colors"
                  >
                    Reject
                  </button>
                </div>
              </div>
            ))}
          </div>
        )}
      </section>
    </div>
  );
}
