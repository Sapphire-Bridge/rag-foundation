import React, { useState } from "react";

type WatchdogCardProps = {
  onTrigger: () => Promise<number | null>;
};

export const WatchdogCard: React.FC<WatchdogCardProps> = ({ onTrigger }) => {
  const [pending, setPending] = useState(false);
  const [status, setStatus] = useState<string | null>(null);

  const handleClick = async () => {
    if (pending) return;
    const confirmed = window.confirm("Reset stuck RUNNING documents older than 30 minutes?");
    if (!confirmed) return;
    setPending(true);
    setStatus(null);
    const result = await onTrigger();
    if (result === null) {
      setStatus("Failed to trigger watchdog.");
    } else {
      setStatus(`Reset ${result} document(s).`);
    }
    setPending(false);
  };

  return (
    <div className="border border-border rounded-lg p-4 space-y-3 bg-card/60">
      <div className="flex items-center justify-between">
        <div>
          <p className="font-semibold">Watchdog</p>
          <p className="text-xs text-muted-foreground">
            Resets RUNNING documents older than 30 minutes back to PENDING.
          </p>
        </div>
        <button
          onClick={handleClick}
          disabled={pending}
          className="px-3 py-1.5 text-xs rounded-md border border-border hover:bg-muted disabled:opacity-50"
        >
          {pending ? "Resetting…" : "Reset stuck docs"}
        </button>
      </div>
      {status ? <p className="text-xs text-muted-foreground">{status}</p> : null}
    </div>
  );
};
