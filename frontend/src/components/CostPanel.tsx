import React, { useEffect, useState } from "react";

type CostSummary = {
  month: string;
  query_cost_usd: number;
  indexing_cost_usd: number;
  total_usd: number;
};

type CostPanelProps = {
  token: string;
  onAuthExpired?: () => void;
};

export const CostPanel: React.FC<CostPanelProps> = ({ token, onAuthExpired }) => {
  const [summary, setSummary] = useState<CostSummary | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const load = async () => {
    if (!token) return;
    setLoading(true);
    setError(null);
    try {
      const res = await fetch("/api/costs/summary", { headers: { Authorization: `Bearer ${token}` } });
      if (res.status === 401 || res.status === 403) {
        setSummary(null);
        onAuthExpired?.();
        return;
      }
      if (res.ok) {
        setSummary(await res.json());
        setError(null);
      } else {
        setSummary(null);
        setError("Unable to load cost summary. Please retry.");
      }
    } catch (err) {
      console.warn("Cost summary fetch failed", err);
      setSummary(null);
      setError("Unable to load cost summary. Please retry.");
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    load();
    const id = setInterval(load, 30000); // refresh every 30s so monthly cost stays current
    return () => clearInterval(id);
  }, [token]);

  if (!summary && !error) return null;
  return (
    <div className="border border-border rounded-lg p-3 space-y-2">
      <div className="flex items-center justify-between">
        <h4 className="text-sm font-semibold">This Month's Cost</h4>
        <button
          onClick={load}
          className="text-xs text-muted-foreground hover:text-foreground"
          disabled={loading}
        >
          {loading ? "Refreshing..." : "Refresh"}
        </button>
      </div>
      {error ? (
        <div className="text-xs text-red-500 bg-red-50 dark:bg-red-950/40 border border-red-200 dark:border-red-900 rounded p-2">
          {error}
        </div>
      ) : null}
      {!summary ? null : (
      <div className="text-xs space-y-1 text-muted-foreground">
        <div>Month: {summary.month}</div>
        <div>Queries: ${summary.query_cost_usd.toFixed(6)}</div>
        <div>Indexing: ${summary.indexing_cost_usd.toFixed(6)}</div>
        <div className="font-bold text-foreground">Total: ${summary.total_usd.toFixed(6)}</div>
      </div>
      )}
    </div>
  );
};
