import React from "react";
import { themePresets } from "../../themes/presets";
import type { ThemePresetKey } from "../../themes/presets";

type ThemePreviewProps = {
  appName: string;
  themePreset: ThemePresetKey;
  primaryColor: string;
  accentColor: string;
};

export function ThemePreview({ appName, themePreset, primaryColor, accentColor }: ThemePreviewProps) {
  const preset = themePresets[themePreset] ?? themePresets.minimal;
  const primary = primaryColor || "#2563EB";
  const accent = accentColor || primary;
  const bubbleBg =
    themePreset === "gradient"
      ? `linear-gradient(135deg, ${primary} 0%, ${accent} 100%)`
      : primary;

  return (
    <div className="rounded-lg border border-border bg-card p-4 shadow-sm">
      <div className="mb-3">
        <p className="text-xs uppercase text-muted-foreground">Preview</p>
        <p className="text-sm font-semibold">{preset.name}</p>
      </div>
      <div
        className="rounded-lg p-3"
        style={{
          backgroundImage: preset.backgroundImage || "none",
          backgroundColor: "hsl(var(--background))",
        }}
      >
        <div className="rounded-md bg-card border border-border p-3 shadow-sm">
          <p className="text-sm font-semibold mb-2">{appName || "App name"}</p>
          <div className="space-y-2">
            <div className="flex gap-2 items-start">
              <span
                className="inline-flex h-8 w-8 items-center justify-center rounded-full text-white text-xs font-semibold"
                style={{ background: accent }}
              >
                AI
              </span>
              <div
                className="flex-1 rounded-xl text-sm text-white px-3 py-2"
                style={{ background: bubbleBg }}
              >
                I can answer questions about your documents with citations.
              </div>
            </div>
            <div className="flex gap-2 items-start">
              <span className="inline-flex h-8 w-8 items-center justify-center rounded-full bg-muted text-muted-foreground text-xs font-semibold">
                You
              </span>
              <div className="flex-1 rounded-xl bg-muted text-sm text-foreground px-3 py-2 border border-border/70">
                Show me sources and costs.
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
