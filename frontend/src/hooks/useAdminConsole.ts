import { useCallback, useEffect, useMemo, useState } from "react";

export type AdminUser = {
  id: number;
  email: string;
  is_admin: boolean;
  is_active: boolean;
  admin_notes?: string | null;
  monthly_limit_usd?: number | null;
  created_at: string;
};

export type AuditEntry = {
  id: number;
  admin_user_id: number | null;
  action: string;
  target_type?: string | null;
  target_id?: string | null;
  metadata_json?: string | null;
  created_at: string;
};

export type SystemSummary = {
  users: number;
  stores: number;
  documents: number;
};

type UseAdminConsoleArgs = {
  token: string;
  onAuthExpired: () => void;
};

type WatchdogResult = {
  reset_count: number;
};

const RATE_LIMIT_MESSAGE = "You are doing that too fast. Please wait.";

export function useAdminConsole({ token, onAuthExpired }: UseAdminConsoleArgs) {
  const [users, setUsers] = useState<AdminUser[]>([]);
  const [audits, setAudits] = useState<AuditEntry[]>([]);
  const [summary, setSummary] = useState<SystemSummary | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const headers = useMemo(
    () => ({
      Authorization: `Bearer ${token}`,
      "X-Requested-With": "XMLHttpRequest",
      "Content-Type": "application/json",
    }),
    [token],
  );

  const handleUnauthorized = useCallback(() => {
    onAuthExpired();
    setUsers([]);
    setAudits([]);
    setSummary(null);
  }, [onAuthExpired]);

  const fetchJson = useCallback(
    async <T,>(path: string): Promise<T> => {
      const res = await fetch(path, { headers });
      if (res.status === 401 || res.status === 403) {
        handleUnauthorized();
        throw new Error("Admin access required");
      }
      if (res.status === 429) {
        throw new Error(RATE_LIMIT_MESSAGE);
      }
      if (!res.ok) {
        const msg = await res.text().catch(() => res.statusText);
        throw new Error(msg || res.statusText);
      }
      return res.json() as Promise<T>;
    },
    [headers, handleUnauthorized],
  );

  const refresh = useCallback(async () => {
    if (!token) {
      setUsers([]);
      setAudits([]);
      setSummary(null);
      setError(null);
      return;
    }
    setLoading(true);
    setError(null);
    try {
      const [userData, auditData, summaryData] = await Promise.all([
        fetchJson<AdminUser[]>("/api/admin/users?limit=100"),
        fetchJson<AuditEntry[]>("/api/admin/audit?limit=20"),
        fetchJson<SystemSummary>("/api/admin/system/summary"),
      ]);
      setUsers(userData);
      setAudits(auditData);
      setSummary(summaryData);
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setLoading(false);
    }
  }, [fetchJson, token]);

  const updateRole = useCallback(
    async (userId: number, payload: { is_admin: boolean; admin_notes?: string | null }) => {
      if (!token) return false;
      try {
        const res = await fetch(`/api/admin/users/${userId}/role`, {
          method: "POST",
          headers,
          body: JSON.stringify(payload),
        });
        if (res.status === 401 || res.status === 403) {
          handleUnauthorized();
          return false;
        }
        if (res.status === 429) {
          setError(RATE_LIMIT_MESSAGE);
          return false;
        }
        if (!res.ok) {
          const msg = await res.text().catch(() => res.statusText);
          setError(msg || "Failed to update role");
          return false;
        }
        await refresh();
        return true;
      } catch (err) {
        setError((err as Error).message);
        return false;
      }
    },
    [headers, handleUnauthorized, refresh, token],
  );

  const updateBudget = useCallback(
    async (userId: number, monthlyLimitUsd: number) => {
      if (!token) return false;
      try {
        const res = await fetch(`/api/admin/budgets/${userId}`, {
          method: "POST",
          headers,
          body: JSON.stringify({ monthly_limit_usd: monthlyLimitUsd }),
        });
        if (res.status === 401 || res.status === 403) {
          handleUnauthorized();
          return false;
        }
        if (res.status === 429) {
          setError(RATE_LIMIT_MESSAGE);
          return false;
        }
        if (!res.ok) {
          const msg = await res.text().catch(() => res.statusText);
          setError(msg || "Failed to update budget");
          return false;
        }
        await refresh();
        return true;
      } catch (err) {
        setError((err as Error).message);
        return false;
      }
    },
    [headers, handleUnauthorized, refresh, token],
  );

  const triggerWatchdog = useCallback(
    async (ttlMinutes = 30): Promise<WatchdogResult | null> => {
      if (!token) return null;
      try {
        const res = await fetch("/api/admin/watchdog/reset-stuck", {
          method: "POST",
          headers,
          body: JSON.stringify({ ttl_minutes: ttlMinutes }),
        });
        if (res.status === 401 || res.status === 403) {
          handleUnauthorized();
          return null;
        }
        if (res.status === 429) {
          setError(RATE_LIMIT_MESSAGE);
          return null;
        }
        if (!res.ok) {
          const msg = await res.text().catch(() => res.statusText);
          setError(msg || "Failed to reset watchdog");
          return null;
        }
        return (await res.json()) as WatchdogResult;
      } catch (err) {
        setError((err as Error).message);
        return null;
      }
    },
    [headers, handleUnauthorized, token],
  );

  const adminEmailFor = useCallback(
    (adminId: number | null | undefined) => {
      if (!adminId) return null;
      const found = users.find((u) => u.id === adminId);
      return found?.email ?? null;
    },
    [users],
  );

  useEffect(() => {
    refresh();
  }, [refresh]);

  return {
    users,
    audits,
    summary,
    loading,
    error,
    refresh,
    updateRole,
    updateBudget,
    triggerWatchdog,
    adminEmailFor,
  };
}
