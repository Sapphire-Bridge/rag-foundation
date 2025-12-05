import React from "react";
import type { AdminUser } from "../../hooks/useAdminConsole";

type AdminUsersTableProps = {
  users: AdminUser[];
  loading: boolean;
  onEdit: (user: AdminUser) => void;
};

const formatBudget = (value: number | null | undefined) => {
  if (value === null) return "Unlimited";
  if (typeof value === "number" && Number.isFinite(value)) return `$${value.toFixed(2)}`;
  return "—";
};

const Badge: React.FC<{ label: string; tone: "success" | "muted" | "primary" | "info" }> = ({ label, tone }) => {
  const toneClass =
    tone === "success"
      ? "bg-emerald-100 text-emerald-800 dark:bg-emerald-900/40 dark:text-emerald-100"
      : tone === "primary"
        ? "bg-primary/10 text-primary"
        : tone === "info"
          ? "bg-blue-100 text-blue-800 dark:bg-blue-900/40 dark:text-blue-100"
          : "bg-muted text-muted-foreground";
  return <span className={`px-2 py-1 rounded-full text-xs font-medium ${toneClass}`}>{label}</span>;
};

export const AdminUsersTable: React.FC<AdminUsersTableProps> = ({ users, loading, onEdit }) => {
  return (
    <div className="border border-border rounded-lg overflow-hidden">
      <div className="overflow-x-auto">
        <table className="min-w-full text-sm">
          <thead className="bg-muted/50">
            <tr>
              <th className="text-left px-4 py-2 font-semibold text-xs uppercase tracking-wide">User</th>
              <th className="text-left px-4 py-2 font-semibold text-xs uppercase tracking-wide">Status</th>
              <th className="text-left px-4 py-2 font-semibold text-xs uppercase tracking-wide">Role</th>
              <th className="text-left px-4 py-2 font-semibold text-xs uppercase tracking-wide">Budget</th>
              <th className="text-left px-4 py-2 font-semibold text-xs uppercase tracking-wide">Joined</th>
              <th className="text-left px-4 py-2 font-semibold text-xs uppercase tracking-wide">Actions</th>
            </tr>
          </thead>
          <tbody>
            {loading ? (
              <tr>
                <td colSpan={6} className="px-4 py-6 text-center text-muted-foreground">
                  Loading users…
                </td>
              </tr>
            ) : users.length === 0 ? (
              <tr>
                <td colSpan={6} className="px-4 py-6 text-center text-muted-foreground">
                  No users found.
                </td>
              </tr>
            ) : (
              users.map((user) => (
                <tr key={user.id} className="border-t border-border/60">
                  <td className="px-4 py-3">
                    <div className="font-medium">{user.email}</div>
                    <div className="text-xs text-muted-foreground">ID: {user.id}</div>
                  </td>
                  <td className="px-4 py-3">
                    <Badge label={user.is_active ? "Active" : "Inactive"} tone={user.is_active ? "success" : "muted"} />
                  </td>
                  <td className="px-4 py-3">
                    <Badge label={user.is_admin ? "Admin" : "User"} tone={user.is_admin ? "primary" : "info"} />
                  </td>
                  <td className="px-4 py-3 text-muted-foreground">{formatBudget(user.monthly_limit_usd)}</td>
                  <td className="px-4 py-3 text-muted-foreground">
                    {new Date(user.created_at).toLocaleDateString()}
                  </td>
                  <td className="px-4 py-3">
                    <button
                      onClick={() => onEdit(user)}
                      className="px-3 py-1.5 text-xs rounded-md border border-border hover:bg-muted"
                    >
                      Edit
                    </button>
                  </td>
                </tr>
              ))
            )}
          </tbody>
        </table>
      </div>
    </div>
  );
};
