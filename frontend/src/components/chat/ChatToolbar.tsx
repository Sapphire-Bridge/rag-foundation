import React from "react";

type ChatToolbarProps = {
  isRunning: boolean;
  onStop: () => void;
  onRetry: () => void;
  onEditLast: () => void;
  model: string;
  setModel: (m: string) => void;
  models: { id: string; label: string }[];
};

export const ChatToolbar: React.FC<ChatToolbarProps> = ({
  isRunning,
  onStop,
  onRetry,
  onEditLast,
  model,
  setModel,
  models,
}) => {
  return (
    <div className="flex items-center justify-between text-xs text-muted-foreground">
      <div className="flex items-center gap-3">
        <div className="flex items-center gap-2">
          <span className="w-2 h-2 rounded-full bg-primary inline-block" aria-hidden />
          {isRunning ? "Generating…" : "Ready"}
        </div>
        <div className="flex items-center gap-2">
          <label className="font-medium text-foreground" htmlFor="model-select">
            Model
          </label>
          <select
            id="model-select"
            value={model}
            onChange={(e) => setModel(e.target.value)}
            className="px-2 py-1 border border-border rounded-md bg-background text-foreground"
          >
            {models.map((m) => (
              <option key={m.id} value={m.id}>
                {m.label}
              </option>
            ))}
          </select>
        </div>
      </div>
      <div className="flex items-center gap-2">
        {isRunning ? (
          <button
            onClick={onStop}
            className="px-3 py-1 rounded-md border border-border hover:bg-muted text-foreground"
          >
            Stop
          </button>
        ) : (
          <>
            <button
              onClick={onRetry}
              className="px-3 py-1 rounded-md border border-border hover:bg-muted text-foreground"
            >
              Retry last
            </button>
            <button
              onClick={onEditLast}
              className="px-3 py-1 rounded-md border border-border hover:bg-muted text-foreground"
            >
              Edit last
            </button>
          </>
        )}
      </div>
    </div>
  );
};
