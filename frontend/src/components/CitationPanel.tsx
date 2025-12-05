import React, { useEffect, useRef } from "react";

export type Citation = {
  title?: string | null;
  sourceId?: string | null;
  uri?: string | null;
  filename?: string | null;
  snippet?: string | null;
};

export const CitationPanel: React.FC<{ citations: Citation[]; highlightIndex?: number | null }> = ({
  citations,
  highlightIndex,
}) => {
  const refs = useRef<(HTMLLIElement | null)[]>([]);

  useEffect(() => {
    if (highlightIndex != null && refs.current[highlightIndex]) {
      refs.current[highlightIndex]?.scrollIntoView({ behavior: "smooth", block: "center" });
    }
  }, [highlightIndex]);

  if (!citations.length) return null;
  return (
    <aside>
      <h4 className="text-lg font-semibold mb-4">Sources</h4>
      <ul className="space-y-2">
        {citations.map((c, idx) => {
          const key = c.sourceId || c.uri || c.filename || String(idx);
          const label = c.title || c.filename || c.uri || c.sourceId || `Source ${idx + 1}`;
          const isHighlighted = highlightIndex === idx;
          return (
            <li
              key={key}
              ref={(el) => (refs.current[idx] = el)}
              className={`text-sm p-3 rounded-md border space-y-1 transition-colors ${
                isHighlighted ? "bg-primary/10 border-primary" : "bg-muted border-border"
              }`}
            >
              <p className="font-medium">
                [{idx + 1}] {label}
              </p>
              {c.snippet ? (
                <p className="text-xs text-muted-foreground whitespace-pre-line">{c.snippet}</p>
              ) : null}
            </li>
          );
        })}
      </ul>
    </aside>
  );
};
