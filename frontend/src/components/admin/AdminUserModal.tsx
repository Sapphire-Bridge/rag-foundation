import React, { useEffect, useState } from "react";
import type { AdminUser } from "../../hooks/useAdminConsole";
import { toast } from "sonner";

type AdminUserModalProps = {
  user: AdminUser | null;
  onClose: () => void;
  onSaveRole: (nextAdmin: boolean, notes: string | null) => Promise<void>;
  onSaveBudget: (monthlyLimitUsd: number) => Promise<void>;
  currentAdminId: number | null;
  savingRole: boolean;
  savingBudget: boolean;
};

export const AdminUserModal: React.FC<AdminUserModalProps> = ({
  user,
  onClose,
  onSaveRole,
  onSaveBudget,
  currentAdminId,
  savingRole,
  savingBudget,
}) => {
  const [isAdmin, setIsAdmin] = useState(false);
  const [notes, setNotes] = useState("");
  const [budgetInput, setBudgetInput] = useState("");
  const isSelf = user && currentAdminId === user.id;

  useEffect(() => {
    if (user) {
      setIsAdmin(user.is_admin);
      setNotes(user.admin_notes || "");
      setBudgetInput(
        typeof user.monthly_limit_usd === "number" && Number.isFinite(user.monthly_limit_usd)
          ? String(user.monthly_limit_usd)
          : "",
      );
    }
  }, [user]);

  if (!user) return null;

  const saveRole = async () => {
    await onSaveRole(isAdmin, notes.trim() || null);
  };

  const saveBudget = async () => {
    const parsed = parseFloat(budgetInput);
    if (Number.isNaN(parsed) || parsed < 0) {
      toast.error("Enter a valid non-negative number for the monthly budget.");
      return;
    }
    await onSaveBudget(parsed);
  };

  return (
    <div className="fixed inset-0 bg-black/40 backdrop-blur-sm flex items-center justify-center z-50 px-4">
      <div className="bg-card border border-border rounded-lg shadow-xl max-w-lg w-full p-6 space-y-6">
        <div className="flex items-center justify-between">
          <div>
            <h3 className="text-lg font-semibold">Manage User</h3>
            <p className="text-sm text-muted-foreground">{user.email}</p>
          </div>
          <button onClick={onClose} className="text-sm text-muted-foreground hover:text-foreground">
            Close
          </button>
        </div>

        <div className="space-y-4">
          <div className="border border-border rounded-md p-4 space-y-3">
            <div className="flex items-center justify-between">
              <div>
                <p className="font-medium">Role</p>
                <p className="text-xs text-muted-foreground">Grant or revoke admin privileges.</p>
              </div>
              <label className="flex items-center gap-2 text-sm">
                <input
                  type="checkbox"
                  checked={isAdmin}
                  disabled={Boolean(isSelf)}
                  onChange={(e) => setIsAdmin(e.target.checked)}
                />
                <span>{isAdmin ? "Admin" : "User"}</span>
              </label>
            </div>
            {isSelf ? (
              <p className="text-xs text-amber-600 dark:text-amber-300">
                You cannot remove your own admin access.
              </p>
            ) : null}
            <div>
              <label className="text-xs text-muted-foreground">Admin Notes</label>
              <textarea
                value={notes}
                onChange={(e) => setNotes(e.target.value)}
                className="w-full mt-1 px-3 py-2 text-sm border border-input rounded-md bg-background"
                rows={3}
                placeholder="Optional notes about this user"
              />
            </div>
            <button
              onClick={saveRole}
              disabled={savingRole}
              className="px-3 py-2 text-sm rounded-md border border-border hover:bg-muted disabled:opacity-50"
            >
              {savingRole ? "Saving…" : "Save Role"}
            </button>
          </div>

          <div className="border border-border rounded-md p-4 space-y-3">
            <div className="flex items-center justify-between">
              <div>
                <p className="font-medium">Budget</p>
                <p className="text-xs text-muted-foreground">Monthly limit in USD.</p>
              </div>
            </div>
            <div className="flex items-center gap-2">
              <input
                type="number"
                min="0"
                step="0.01"
                value={budgetInput}
                onChange={(e) => setBudgetInput(e.target.value)}
                className="flex-1 px-3 py-2 text-sm border border-input rounded-md bg-background"
                placeholder="e.g. 500"
              />
              <button
                onClick={saveBudget}
                disabled={savingBudget}
                className="px-3 py-2 text-sm rounded-md border border-border hover:bg-muted disabled:opacity-50"
              >
                {savingBudget ? "Updating…" : "Update"}
              </button>
            </div>
            <p className="text-xs text-muted-foreground">
              Enter a non-negative amount to set or update the monthly limit. Budget cannot be cleared to unlimited via this form.
            </p>
          </div>
        </div>
      </div>
    </div>
  );
};
