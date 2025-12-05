
import React, { useCallback, useState } from "react";
import { ThemeProvider, useTheme, AppSettings } from "./contexts/ThemeContext";
import { CustomizationPanel } from "./components/admin/CustomizationPanel";
import { ChatLayout } from "./components/chat/ChatLayout";
import { ChatProvider, ModelOption } from "./contexts/ChatContext";
import { StoreProvider } from "./contexts/StoreContext";
import { Toaster, toast } from "sonner";

const tokenKey = "token";
const readToken = () => sessionStorage.getItem(tokenKey) || "";

const models: ModelOption[] = [
  { id: "gemini-2.5-flash", label: "Gemini 2.5 Flash (fast)" },
  { id: "gemini-2.5-pro", label: "Gemini 2.5 Pro" },
  { id: "gemini-3.0-pro-thinking", label: "Gemini 3.0 Pro Thinking" },
  { id: "gemini-2.0-flash", label: "Gemini 2.0 Flash" },
  { id: "gemini-2.0-pro", label: "Gemini 2.0 Pro" },
  { id: "gemini-1.5-pro", label: "Gemini 1.5 Pro" },
  { id: "gemini-1.5-flash", label: "Gemini 1.5 Flash" },
];

export default function App() {
  return (
    <ThemeProvider>
      <Toaster richColors position="top-center" />
      <AppWithTheme />
    </ThemeProvider>
  );
}

function AppWithTheme() {
  const [token, setToken] = useState<string>(readToken());
  const { settings, saveSettings } = useTheme();
  const [showCustomizer, setShowCustomizer] = useState(false);
  const [savingSettings, setSavingSettings] = useState(false);
  const [settingsError, setSettingsError] = useState<string | null>(null);

  const setAuthToken = useCallback((value: string) => {
    if (value) {
      sessionStorage.setItem(tokenKey, value);
    } else {
      sessionStorage.removeItem(tokenKey);
      setShowCustomizer(false);
    }
    setToken(value);
  }, []);

  const handleAuthExpired = useCallback(() => {
    setAuthToken("");
  }, [setAuthToken]);

  const handleSaveSettings = async (draft: AppSettings) => {
    if (!token) {
      toast.error("Admin login required to save settings.");
      return;
    }
    setSavingSettings(true);
    setSettingsError(null);
    try {
      await saveSettings(draft, token);
      setShowCustomizer(false);
    } catch (err) {
      setSettingsError((err as Error).message);
    } finally {
      setSavingSettings(false);
    }
  };

  return (
    <StoreProvider token={token} onAuthExpired={handleAuthExpired} onSetToken={setAuthToken}>
      <ChatProvider token={token} models={models} onAuthExpired={handleAuthExpired}>
        <ChatLayout settings={settings} onOpenCustomizer={() => setShowCustomizer(true)} />
      </ChatProvider>
      <CustomizationPanel
        open={showCustomizer}
        settings={settings}
        saving={savingSettings}
        error={settingsError}
        onClose={() => setShowCustomizer(false)}
        onSave={handleSaveSettings}
      />
    </StoreProvider>
  );
}
