import React from "react";
import type { AuditEntry } from "../../hooks/useAdminConsole";

type AdminAuditListProps = {
  audits: AuditEntry[];
  adminEmailFor: (id: number | null | undefined) => string | null;
};

const formatAdminLabel = (adminId: number | null, lookup: (id: number | null | undefined) => string | null) => {
  const email = lookup(adminId ?? undefined);
  if (email) return email;
  if (!adminId) return "Unknown admin";
  const truncated = String(adminId).slice(0, 8);
  return `User ${truncated}`;
};

export const AdminAuditList: React.FC<AdminAuditListProps> = ({ audits, adminEmailFor }) => {
  return (
    <div className="border border-border rounded-lg p-4 space-y-3">
      <div className="flex items-center justify-between">
        <h4 className="text-sm font-semibold">Recent Admin Actions</h4>
        <span className="text-xs text-muted-foreground">{audits.length} entries</span>
      </div>
      <div className="space-y-2 max-h-64 overflow-y-auto pr-1">
        {audits.length === 0 ? (
          <p className="text-xs text-muted-foreground">No audit entries yet.</p>
        ) : (
          audits.map((entry) => {
            const label = formatAdminLabel(entry.admin_user_id, adminEmailFor);
            const missing = !adminEmailFor(entry.admin_user_id);
            return (
              <div key={entry.id} className="text-xs border border-border/60 rounded-md p-2 bg-card/50">
                <p className="font-medium">{entry.action}</p>
                <p className="text-muted-foreground">
                  {entry.target_type ? `${entry.target_type} ${entry.target_id ?? ""}` : "—"}
                </p>
                <p className="text-muted-foreground">
                  {new Date(entry.created_at).toLocaleString()}
                </p>
                <p
                  className="text-muted-foreground"
                  title={missing ? "User not in current list" : undefined}
                >
                  {label}
                </p>
              </div>
            );
          })
        )}
      </div>
    </div>
  );
};
