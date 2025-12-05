import React from "react";
import type { AppSettings } from "../../contexts/ThemeContext";
import { IconGlyph, IconId } from "../admin/IconPicker";

type WelcomeCardProps = {
  settings: AppSettings;
  onSelectPrompt: (prompt: string) => void;
};

export function WelcomeCard({ settings, onSelectPrompt }: WelcomeCardProps) {
  const prompts = [
    settings.suggested_prompt_1,
    settings.suggested_prompt_2,
    settings.suggested_prompt_3,
  ].filter((p): p is string => Boolean(p?.trim()));

  const iconId = (settings.app_icon as IconId) || "sparkles";

  return (
    <div className="border border-border rounded-xl p-5 bg-card shadow-sm">
      <div className="flex items-start gap-3">
        <div className="h-11 w-11 rounded-full border border-border flex items-center justify-center bg-muted text-primary shrink-0">
          <IconGlyph id={iconId} className="w-6 h-6" />
        </div>
        <div className="space-y-1">
          <p className="text-xs uppercase text-muted-foreground">Welcome</p>
          <h3 className="text-lg font-semibold">{settings.app_name}</h3>
          <p className="text-sm text-muted-foreground">{settings.welcome_message}</p>
        </div>
      </div>

      {prompts.length > 0 ? (
        <div className="mt-4">
          <p className="text-xs font-semibold text-muted-foreground mb-2">Try asking:</p>
          <div className="grid sm:grid-cols-2 gap-2">
            {prompts.map((prompt, idx) => (
              <button
                key={`${idx}-${prompt}`}
                type="button"
                onClick={() => onSelectPrompt(prompt)}
                className="text-left px-3 py-2 border border-border rounded-lg hover:bg-muted transition"
              >
                <span className="text-sm text-foreground">{prompt}</span>
              </button>
            ))}
          </div>
        </div>
      ) : null}
    </div>
  );
}
