import React, { useMemo, useState } from "react";
import { useAdminConsole, type AdminUser } from "../hooks/useAdminConsole";
import { AdminUsersTable } from "./admin/AdminUsersTable";
import { AdminUserModal } from "./admin/AdminUserModal";
import { AdminSystemCards } from "./admin/AdminSystemCards";
import { WatchdogCard } from "./admin/WatchdogCard";
import { AdminAuditList } from "./admin/AdminAuditList";

type AdminPanelProps = {
  token: string;
  onAuthExpired: () => void;
};

const parseJwtSub = (token: string): number | null => {
  try {
    const [, payload] = token.split(".");
    if (!payload) return null;
    const decoded = JSON.parse(atob(payload.replace(/-/g, "+").replace(/_/g, "/")));
    const sub = parseInt(decoded.sub, 10);
    return Number.isFinite(sub) ? sub : null;
  } catch (err) {
    console.warn("Failed to parse JWT", err);
    return null;
  }
};

export function AdminPanel({ token, onAuthExpired }: AdminPanelProps) {
  const [activeTab, setActiveTab] = useState<"users" | "system">("users");
  const [selectedUser, setSelectedUser] = useState<AdminUser | null>(null);
  const [savingRole, setSavingRole] = useState(false);
  const [savingBudget, setSavingBudget] = useState(false);
  const [status, setStatus] = useState<string | null>(null);
  const currentAdminId = useMemo(() => parseJwtSub(token), [token]);

  const { users, audits, summary, loading, error, refresh, updateRole, updateBudget, triggerWatchdog, adminEmailFor } =
    useAdminConsole({ token, onAuthExpired });

  const identityEmail = useMemo(() => {
    if (currentAdminId) {
      const found = users.find((u) => u.id === currentAdminId);
      if (found) return found.email;
    }
    const cached = sessionStorage.getItem("lastLoginEmail");
    return cached || null;
  }, [currentAdminId, users]);

  const visibleAdmins = useMemo(() => users.filter((u) => u.is_admin).length, [users]);

  if (!token) return null;

  const handleSaveRole = async (nextAdmin: boolean, notes: string | null) => {
    if (!selectedUser) return;
    setSavingRole(true);
    setStatus(null);
    const ok = await updateRole(selectedUser.id, { is_admin: nextAdmin, admin_notes: notes });
    setSavingRole(false);
    if (ok) {
      setSelectedUser(null);
      setStatus("Role updated.");
    }
  };

  const handleSaveBudget = async (monthlyLimitUsd: number) => {
    if (!selectedUser) return;
    setSavingBudget(true);
    setStatus(null);
    const ok = await updateBudget(selectedUser.id, monthlyLimitUsd);
    setSavingBudget(false);
    if (ok) {
      setSelectedUser(null);
      setStatus("Budget updated.");
    }
  };

  const handleWatchdog = async () => {
    const result = await triggerWatchdog(30);
    return result?.reset_count ?? null;
  };

  const headerIdentity = identityEmail || (currentAdminId ? `User #${currentAdminId}` : "Admin");

  return (
    <div className="mt-6 border border-border rounded-lg p-4 space-y-4">
      <div className="flex items-center justify-between">
        <div>
          <h3 className="text-lg font-semibold">Admin Console</h3>
          <p className="text-xs text-muted-foreground">Signed in as {headerIdentity}</p>
        </div>
        <div className="flex items-center gap-2">
          <button
            onClick={() => setActiveTab("users")}
            className={`text-xs px-3 py-1.5 rounded-md border border-border ${
              activeTab === "users" ? "bg-muted" : "hover:bg-muted/60"
            }`}
          >
            Users & Budgets
          </button>
          <button
            onClick={() => setActiveTab("system")}
            className={`text-xs px-3 py-1.5 rounded-md border border-border ${
              activeTab === "system" ? "bg-muted" : "hover:bg-muted/60"
            }`}
          >
            System & Audit
          </button>
          <button onClick={refresh} className="text-xs px-3 py-1.5 rounded-md border border-border hover:bg-muted">
            Refresh
          </button>
        </div>
      </div>

      {status ? <p className="text-xs text-muted-foreground">{status}</p> : null}
      {error ? (
        <p className="text-xs text-red-600 bg-red-50 dark:bg-red-950/40 border border-red-200 dark:border-red-900 rounded px-3 py-2">
          {error}
        </p>
      ) : null}

      {activeTab === "users" ? (
        <AdminUsersTable users={users} loading={loading} onEdit={setSelectedUser} />
      ) : (
        <div className="space-y-4">
          <AdminSystemCards summary={summary} visibleAdmins={visibleAdmins} />
          <WatchdogCard onTrigger={handleWatchdog} />
          <AdminAuditList audits={audits} adminEmailFor={adminEmailFor} />
        </div>
      )}

      <AdminUserModal
        user={selectedUser}
        onClose={() => setSelectedUser(null)}
        onSaveRole={handleSaveRole}
        onSaveBudget={handleSaveBudget}
        currentAdminId={currentAdminId}
        savingRole={savingRole}
        savingBudget={savingBudget}
      />
    </div>
  );
}
