import React from "react";
import { IconPicker, IconGlyph, IconId } from "./IconPicker";
import { ThemePreview } from "./ThemePreview";
import { themePresets } from "../../themes/presets";
import type { AppSettings } from "../../contexts/ThemeContext";
import type { ThemePresetKey } from "../../themes/presets";

const MAX_FAVICON_BYTES = 140 * 1024; // Keep encoded data under backend 200k limit
const MAX_FAVICON_DATA_URL_LENGTH = 200_000;

type CustomizationPanelProps = {
  open: boolean;
  settings: AppSettings;
  saving: boolean;
  error: string | null;
  onClose: () => void;
  onSave: (draft: AppSettings) => void;
};

export function CustomizationPanel({ open, settings, saving, error, onClose, onSave }: CustomizationPanelProps) {
  const [draft, setDraft] = React.useState<AppSettings>(settings);
  const [localError, setLocalError] = React.useState<string | null>(null);
  const fileInputRef = React.useRef<HTMLInputElement | null>(null);

  React.useEffect(() => {
    setDraft(settings);
    setLocalError(null);
  }, [settings, open]);

  const handleChange = <K extends keyof AppSettings>(key: K, value: AppSettings[K]) => {
    setDraft((prev) => ({ ...prev, [key]: value }));
  };

  const handleFaviconSelect = (file: File | null) => {
    if (!file) return;
    if (!file.type.startsWith("image/")) {
      setLocalError("Please upload an image file (PNG, JPG, or SVG).");
      return;
    }
    if (file.size > MAX_FAVICON_BYTES) {
      setLocalError("Icon must be 140KB or smaller to meet the backend limit.");
      return;
    }
    const reader = new FileReader();
    reader.onload = () => {
      const result = reader.result;
      if (typeof result === "string") {
        if (result.length > MAX_FAVICON_DATA_URL_LENGTH) {
          setLocalError("Icon is too large after encoding (limit is 200KB). Try a smaller image (~140KB or less).");
          return;
        }
        setDraft((prev) => ({ ...prev, app_favicon: result }));
        setLocalError(null);
      } else {
        setLocalError("Could not read the image. Try another file.");
      }
    };
    reader.onerror = () => setLocalError("Could not read the image. Try another file.");
    reader.readAsDataURL(file);
  };

  const resetFavicon = () => {
    setDraft((prev) => ({ ...prev, app_favicon: "" }));
    setLocalError(null);
    if (fileInputRef.current) fileInputRef.current.value = "";
  };

  const validateDraft = () => {
    if (localError) return localError;
    if (draft.app_favicon && draft.app_favicon.length > MAX_FAVICON_DATA_URL_LENGTH) {
      return "Icon is too large after encoding (limit is 200KB). Try a smaller image (~140KB or less).";
    }
    const hexColorRe = /^#[0-9A-Fa-f]{6}$/;
    if (!hexColorRe.test(draft.primary_color) || !hexColorRe.test(draft.accent_color)) {
      return "Colors must be 6-digit hex values like #2563EB.";
    }
    return null;
  };

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    const validationError = validateDraft();
    if (validationError) {
      setLocalError(validationError);
      return;
    }
    onSave(draft);
  };

  if (!open) return null;

  return (
    <div className="fixed inset-0 z-40 flex items-center justify-center bg-black/40 px-4">
      <div className="w-full max-w-4xl rounded-xl bg-background border border-border shadow-2xl overflow-hidden">
        <div className="flex justify-between items-center px-6 py-4 border-b border-border/80 bg-card">
          <div>
            <p className="text-xs uppercase text-muted-foreground">Dev mode</p>
            <h2 className="text-xl font-semibold">Customize the assistant</h2>
            <p className="text-sm text-muted-foreground">Admin-only controls for name, icon, and theming.</p>
          </div>
          <button
            type="button"
            onClick={onClose}
            className="text-sm px-3 py-1.5 rounded-md border border-border hover:bg-muted"
          >
            Close
          </button>
        </div>

        <form onSubmit={handleSubmit} className="grid grid-cols-1 md:grid-cols-2 gap-6 p-6">
          <div className="space-y-4">
            <div className="space-y-2">
              <label className="text-sm font-medium">App name</label>
              <input
                type="text"
                value={draft.app_name}
                maxLength={100}
                onChange={(e) => handleChange("app_name", e.target.value)}
                className="w-full px-3 py-2 rounded-md border border-input bg-background"
              />
            </div>

            <div className="space-y-2">
              <label className="text-sm font-medium">Icon</label>
              <IconPicker value={draft.app_icon as IconId} onChange={(val) => handleChange("app_icon", val)} />
            </div>

            <div className="space-y-2">
              <label className="text-sm font-medium">Browser icon (favicon)</label>
              <div className="flex items-center gap-3">
                <div className="h-12 w-12 rounded-md border border-border bg-muted flex items-center justify-center overflow-hidden">
                  {draft.app_favicon ? (
                    <img src={draft.app_favicon} alt="Favicon preview" className="h-full w-full object-cover" />
                  ) : (
                    <span className="text-xs text-muted-foreground">Default</span>
                  )}
                </div>
                <div className="flex flex-col gap-2">
                  <div className="flex gap-2">
                    <button
                      type="button"
                      onClick={() => fileInputRef.current?.click()}
                      className="px-3 py-2 rounded-md border border-border hover:bg-muted text-sm"
                    >
                      Upload icon
                    </button>
                    <button
                      type="button"
                      onClick={resetFavicon}
                      className="px-3 py-2 rounded-md border border-border hover:bg-muted text-sm"
                    >
                      Use default
                    </button>
                  </div>
                  <p className="text-xs text-muted-foreground">
                    PNG/JPG/SVG up to 140KB. Square images look best in browser tabs.
                  </p>
                </div>
              </div>
              <input
                ref={fileInputRef}
                type="file"
                accept="image/png,image/jpeg,image/svg+xml,image/x-icon"
                className="hidden"
                onChange={(e) => handleFaviconSelect(e.target.files?.[0] ?? null)}
              />
            </div>

            <div className="space-y-2">
              <label className="text-sm font-medium">Theme preset</label>
              <select
                value={draft.theme_preset}
                onChange={(e) => handleChange("theme_preset", e.target.value as ThemePresetKey)}
                className="w-full px-3 py-2 rounded-md border border-input bg-background"
              >
                {Object.entries(themePresets).map(([key, preset]) => (
                  <option key={key} value={key}>
                    {preset.name}
                  </option>
                ))}
              </select>
            </div>

            <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
              <div className="space-y-1">
                <label className="text-sm font-medium">Primary color</label>
                <div className="flex items-center gap-2">
                  <input
                    type="color"
                    value={draft.primary_color}
                    onChange={(e) => handleChange("primary_color", e.target.value)}
                    className="h-10 w-12 rounded-md border border-input bg-background"
                  />
                  <input
                    type="text"
                    value={draft.primary_color}
                    onChange={(e) => handleChange("primary_color", e.target.value)}
                    className="flex-1 px-3 py-2 rounded-md border border-input bg-background"
                  />
                </div>
              </div>
              <div className="space-y-1">
                <label className="text-sm font-medium">Accent color</label>
                <div className="flex items-center gap-2">
                  <input
                    type="color"
                    value={draft.accent_color}
                    onChange={(e) => handleChange("accent_color", e.target.value)}
                    className="h-10 w-12 rounded-md border border-input bg-background"
                  />
                  <input
                    type="text"
                    value={draft.accent_color}
                    onChange={(e) => handleChange("accent_color", e.target.value)}
                    className="flex-1 px-3 py-2 rounded-md border border-input bg-background"
                  />
                </div>
              </div>
            </div>

            <div className="space-y-2">
              <label className="text-sm font-medium">Welcome message</label>
              <textarea
                value={draft.welcome_message}
                maxLength={255}
                onChange={(e) => handleChange("welcome_message", e.target.value)}
                className="w-full px-3 py-2 rounded-md border border-input bg-background"
                rows={3}
              />
              <p className="text-xs text-muted-foreground">Shown on the empty thread welcome card.</p>
            </div>

            <div className="space-y-2">
              <label className="text-sm font-medium">Suggested prompts</label>
              <div className="space-y-2">
                {[1, 2, 3].map((idx) => {
                  const key = `suggested_prompt_${idx}` as const;
                  return (
                    <input
                      key={key}
                      type="text"
                      value={draft[key]}
                      maxLength={180}
                      onChange={(e) => handleChange(key, e.target.value)}
                      className="w-full px-3 py-2 rounded-md border border-input bg-background"
                      placeholder={`Suggestion ${idx}`}
                    />
                  );
                })}
              </div>
              <p className="text-xs text-muted-foreground">Admins can leave any empty to hide it.</p>
            </div>

            {error ? <p className="text-sm text-destructive">{error}</p> : null}
            {localError ? <p className="text-sm text-destructive">{localError}</p> : null}

            <div className="flex items-center gap-3">
              <button
                type="submit"
                disabled={saving}
                className="px-4 py-2 rounded-md bg-primary text-primary-foreground hover:bg-primary/90 disabled:opacity-50"
              >
                {saving ? "Saving..." : "Save settings"}
              </button>
              <button
                type="button"
                onClick={() => setDraft(settings)}
                className="px-3 py-2 rounded-md border border-border hover:bg-muted text-sm"
              >
                Reset changes
              </button>
            </div>
            <p className="text-xs text-muted-foreground">
              Changes apply to everyone after saving. Visual-only; does not change auth or data access.
            </p>
          </div>

          <div className="space-y-4">
            <div className="flex items-center gap-3">
              <div className="h-10 w-10 rounded-full border border-border flex items-center justify-center text-primary">
                <IconGlyph id={draft.app_icon as IconId} className="w-6 h-6" />
              </div>
              <div>
                <p className="text-sm text-muted-foreground">Live preview</p>
                <p className="font-semibold">{draft.app_name}</p>
              </div>
            </div>
            <ThemePreview
              appName={draft.app_name}
              themePreset={draft.theme_preset}
              primaryColor={draft.primary_color}
              accentColor={draft.accent_color}
            />
          </div>
        </form>
      </div>
    </div>
  );
}
