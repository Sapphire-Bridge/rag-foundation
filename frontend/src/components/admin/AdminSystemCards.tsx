import React from "react";
import type { SystemSummary } from "../../hooks/useAdminConsole";

type AdminSystemCardsProps = {
  summary: SystemSummary | null;
  visibleAdmins: number;
};

const Card: React.FC<{ label: string; value: string | number }> = ({ label, value }) => (
  <div className="flex-1 border border-border rounded-lg p-3 bg-card/60 min-w-[140px]">
    <p className="text-xs text-muted-foreground uppercase tracking-wide">{label}</p>
    <p className="text-xl font-semibold">{value}</p>
  </div>
);

export const AdminSystemCards: React.FC<AdminSystemCardsProps> = ({ summary, visibleAdmins }) => {
  return (
    <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
      <Card label="Users" value={summary?.users ?? "—"} />
      <Card label="Stores" value={summary?.stores ?? "—"} />
      <Card label="Documents" value={summary?.documents ?? "—"} />
      <Card label="Visible Admins" value={visibleAdmins} />
    </div>
  );
};
