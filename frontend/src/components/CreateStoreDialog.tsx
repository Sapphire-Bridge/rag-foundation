import React, { useState } from "react";
import * as Dialog from "@radix-ui/react-dialog";
import { toast } from "sonner";
import { createStore } from "../services/stores";

type CreateStoreDialogProps = {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  token: string | null;
  onAuthExpired: () => void;
  onCreated: () => Promise<void> | void;
};

export const CreateStoreDialog: React.FC<CreateStoreDialogProps> = ({
  open,
  onOpenChange,
  token,
  onAuthExpired,
  onCreated,
}) => {
  const [name, setName] = useState("");
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const reset = () => {
    setName("");
    setSaving(false);
    setError(null);
  };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (saving) return;

    if (!token) {
      toast.error("Please log in to create a store.");
      onOpenChange(false);
      reset();
      return;
    }

    const trimmed = name.trim();
    if (!trimmed) {
      setError("Please enter a store name.");
      return;
    }

    setSaving(true);
    setError(null);
    try {
      await createStore({ token, name: trimmed });

      toast.success("Store created.");
      await onCreated?.();
      onOpenChange(false);
      reset();
    } catch (err) {
      console.error(err);
      const status = (err as { status?: number })?.status;
      if (status === 401 || status === 403) {
        onAuthExpired();
        toast.error("Session expired. Please log in again.");
      } else {
        setError((err as Error).message);
        toast.error((err as Error).message || "Failed to create store. Please retry.");
      }
    } finally {
      setSaving(false);
    }
  };

  return (
    <Dialog.Root open={open} onOpenChange={(next) => {
      if (!next) reset();
      onOpenChange(next);
    }}>
      <Dialog.Portal>
        <Dialog.Overlay className="fixed inset-0 bg-black/40 backdrop-blur-sm z-40" />
        <Dialog.Content className="fixed z-50 top-1/2 left-1/2 -translate-x-1/2 -translate-y-1/2 bg-card border border-border rounded-lg shadow-xl w-[420px] max-w-[90vw] p-6">
          <div className="flex items-start justify-between mb-4">
            <div>
              <Dialog.Title className="text-lg font-semibold">Create a new store</Dialog.Title>
              <Dialog.Description className="text-sm text-muted-foreground">
                Stores group documents for chat sessions. Pick a clear, descriptive name.
              </Dialog.Description>
            </div>
            <Dialog.Close className="text-muted-foreground hover:text-foreground text-sm">Close</Dialog.Close>
          </div>

          <form className="space-y-4" onSubmit={handleSubmit}>
            <div className="space-y-1">
              <label className="text-sm font-medium">Store name</label>
              <input
                value={name}
                onChange={(e) => setName(e.target.value)}
                className="w-full px-3 py-2 rounded-md border border-input bg-background"
                placeholder="e.g. Marketing Docs"
                autoFocus
              />
            </div>
            {error ? <p className="text-sm text-destructive">{error}</p> : null}
            <div className="flex justify-end gap-2">
              <Dialog.Close className="px-3 py-2 text-sm rounded-md border border-border hover:bg-muted">
                Cancel
              </Dialog.Close>
              <button
                type="submit"
                disabled={saving || !name.trim()}
                className="px-3 py-2 text-sm rounded-md bg-primary text-primary-foreground hover:bg-primary/90 disabled:opacity-50"
              >
                {saving ? "Creating..." : "Create"}
              </button>
            </div>
          </form>
        </Dialog.Content>
      </Dialog.Portal>
    </Dialog.Root>
  );
};
