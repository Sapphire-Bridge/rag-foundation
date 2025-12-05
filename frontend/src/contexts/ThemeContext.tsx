import React from "react";
import { themePresets, baseTokens, ThemePresetKey, hexToHslString } from "../themes/presets";
import { toast } from "sonner";

// Simple blue default favicon (SVG data URL) to avoid external assets and stale icons
const DEFAULT_FAVICON =
  "data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 64 64'%3E%3Crect width='64' height='64' rx='12' fill='%232563EB'/%3E%3Cpath d='M32 14l3 7 7 3-7 3-3 7-3-7-7-3 7-3 3-7z' fill='%23E0E7FF'/%3E%3C/svg%3E";

export type AppSettings = {
  app_name: string;
  app_icon: string;
  theme_preset: ThemePresetKey;
  primary_color: string;
  accent_color: string;
  app_favicon: string;
  welcome_message: string;
  suggested_prompt_1: string;
  suggested_prompt_2: string;
  suggested_prompt_3: string;
};

type ThemeContextValue = {
  settings: AppSettings;
  isLoading: boolean;
  lastError: string | null;
  refreshSettings: () => Promise<void>;
  saveSettings: (updates: Partial<AppSettings>, token: string) => Promise<AppSettings>;
};

const defaultSettings: AppSettings = {
  app_name: "RAG Assistant",
  app_icon: "sparkles",
  theme_preset: "minimal",
  primary_color: "#2563EB",
  accent_color: "#6366F1",
  app_favicon: "",
  welcome_message: "Hi! I'm your RAG assistant. Ask me anything about your documents.",
  suggested_prompt_1: "Summarize the key findings from my uploads.",
  suggested_prompt_2: "What are the main risks or open questions?",
  suggested_prompt_3: "Create an outline using the latest documents.",
};

const ThemeContext = React.createContext<ThemeContextValue | undefined>(undefined);

function applyFavicon(dataUrl: string | null | undefined) {
  const href = dataUrl && dataUrl.trim().length > 0 ? dataUrl.trim() : DEFAULT_FAVICON;
  let mimeType = "image/png";

  if (href.startsWith("data:")) {
    const match = href.match(/^data:([^;,]+)/);
    if (match) mimeType = match[1];
  } else if (href.toLowerCase().endsWith(".svg")) {
    mimeType = "image/svg+xml";
  } else if (href.toLowerCase().endsWith(".ico")) {
    mimeType = "image/x-icon";
  } else if (href.toLowerCase().endsWith(".jpg") || href.toLowerCase().endsWith(".jpeg")) {
    mimeType = "image/jpeg";
  }

  // Remove existing icons to avoid stale or duplicated entries
  document.querySelectorAll<HTMLLinkElement>("link[rel='icon'], link[rel='shortcut icon']").forEach((el) => el.remove());

  const cacheBustedHref = href.startsWith("data:")
    ? href
    : `${href}${href.includes("?") ? "&" : "?"}v=${Date.now()}`;

  const iconLink = document.createElement("link");
  iconLink.rel = "icon";
  iconLink.type = mimeType;
  iconLink.href = cacheBustedHref;
  document.head.appendChild(iconLink);

  let appleLink = document.querySelector<HTMLLinkElement>("link[rel='apple-touch-icon']");
  if (!appleLink) {
    appleLink = document.createElement("link");
    appleLink.rel = "apple-touch-icon";
    document.head.appendChild(appleLink);
  }
  appleLink.href = cacheBustedHref;
}

function applyThemeTokens(settings: AppSettings) {
  const root = document.documentElement;
  const preset = themePresets[settings.theme_preset] ?? themePresets.minimal;
  const merged = { ...baseTokens, ...preset.tokens };

  const primary = hexToHslString(settings.primary_color) ?? merged.primary;
  const accent = hexToHslString(settings.accent_color) ?? merged.accent;
  merged.primary = primary;
  merged["primary-foreground"] = merged["primary-foreground"] || "210 40% 98%";
  merged.accent = accent;

  Object.entries(merged).forEach(([key, value]) => {
    root.style.setProperty(`--${key}`, value);
  });

  root.style.setProperty("--font-family-app", preset.fontFamily);
  if (preset.backgroundImage) {
    document.body.style.backgroundImage = preset.backgroundImage;
  } else {
    document.body.style.backgroundImage = "none";
  }
  document.body.style.fontFamily = `var(--font-family-app, ui-sans-serif, system-ui, -apple-system, sans-serif)`;
  applyFavicon(settings.app_favicon);
}

export function ThemeProvider({ children }: { children: React.ReactNode }) {
  const [settings, setSettings] = React.useState<AppSettings>(defaultSettings);
  const [isLoading, setIsLoading] = React.useState(true);
  const [lastError, setLastError] = React.useState<string | null>(null);

  const refreshSettings = React.useCallback(async () => {
    setIsLoading(true);
    try {
      const res = await fetch("/api/settings");
      if (!res.ok) {
        throw new Error(`Failed to load settings (${res.status})`);
      }
      const data = await res.json();
      setSettings((prev) => ({ ...prev, ...data }));
      setLastError(null);
    } catch (err) {
      console.error(err);
      setLastError((err as Error).message);
      toast.error("Failed to load branding. Retrying...", { id: "theme-error" });
    } finally {
      setIsLoading(false);
    }
  }, []);

  const saveSettings = React.useCallback(
    async (updates: Partial<AppSettings>, token: string): Promise<AppSettings> => {
      const res = await fetch("/api/settings", {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          Authorization: `Bearer ${token}`,
          "X-Requested-With": "XMLHttpRequest",
        },
        body: JSON.stringify(updates),
      });
      if (!res.ok) {
        const text = await res.text();
        throw new Error(text || "Failed to save settings");
      }
      const data = await res.json();
      setSettings(data);
      return data;
    },
    [],
  );

  React.useEffect(() => {
    applyThemeTokens(settings);
  }, [settings]);

  React.useEffect(() => {
    refreshSettings();
  }, [refreshSettings]);

  const value: ThemeContextValue = {
    settings,
    isLoading,
    lastError,
    refreshSettings,
    saveSettings,
  };

  return <ThemeContext.Provider value={value}>{children}</ThemeContext.Provider>;
}

export function useTheme() {
  const ctx = React.useContext(ThemeContext);
  if (!ctx) {
    throw new Error("useTheme must be used within a ThemeProvider");
  }
  return ctx;
}
