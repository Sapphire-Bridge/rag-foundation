export type ThemePresetKey = "minimal" | "gradient" | "classic";

type ThemePreset = {
  name: string;
  fontFamily: string;
  tokens: Record<string, string>;
  backgroundImage?: string;
};

export const baseTokens: Record<string, string> = {
  background: "0 0% 100%",
  foreground: "222.2 84% 4.9%",
  card: "0 0% 100%",
  "card-foreground": "222.2 84% 4.9%",
  popover: "0 0% 100%",
  "popover-foreground": "222.2 84% 4.9%",
  primary: "222.2 47.4% 11.2%",
  "primary-foreground": "210 40% 98%",
  secondary: "210 40% 96.1%",
  "secondary-foreground": "222.2 47.4% 11.2%",
  muted: "210 40% 96.1%",
  "muted-foreground": "215.4 16.3% 46.9%",
  accent: "210 40% 96.1%",
  "accent-foreground": "222.2 47.4% 11.2%",
  destructive: "0 84.2% 60.2%",
  "destructive-foreground": "210 40% 98%",
  border: "214.3 31.8% 91.4%",
  input: "214.3 31.8% 91.4%",
  ring: "222.2 84% 4.9%",
  radius: "0.5rem",
};

export const themePresets: Record<ThemePresetKey, ThemePreset> = {
  minimal: {
    name: "Minimal Modern",
    fontFamily: "Inter, ui-sans-serif, system-ui, -apple-system, sans-serif",
    tokens: {
      background: "0 0% 98%",
      card: "0 0% 100%",
      foreground: "0 0% 10%",
      muted: "210 20% 95%",
      "muted-foreground": "220 10% 46%",
      border: "214 20% 88%",
    },
  },
  gradient: {
    name: "Gradient Modern",
    fontFamily: "Poppins, ui-sans-serif, system-ui, -apple-system, sans-serif",
    tokens: {
      background: "210 33% 98%",
      card: "0 0% 100%",
      foreground: "220 14% 15%",
      muted: "222 35% 96%",
      "muted-foreground": "220 12% 40%",
      border: "220 20% 88%",
      accent: "246 83% 67%",
    },
    backgroundImage: "linear-gradient(135deg, rgba(99,102,241,0.08), rgba(139,92,246,0.08))",
  },
  classic: {
    name: "Classic / Retro",
    fontFamily: "Georgia, ui-serif, serif",
    tokens: {
      background: "0 0% 96%",
      card: "0 0% 100%",
      foreground: "220 15% 15%",
      muted: "210 20% 92%",
      "muted-foreground": "216 10% 35%",
      border: "210 16% 82%",
      primary: "227 69% 41%",
      accent: "227 32% 60%",
    },
  },
};

export function hexToHslString(hex: string | null | undefined): string | null {
  if (!hex || typeof hex !== "string" || !/^#[0-9A-Fa-f]{6}$/.test(hex)) return null;
  const value = hex.replace("#", "");
  const parse = (str: string) =>
    parseInt(str, 16);
  const r = parse(value.slice(0, 2));
  const g = parse(value.slice(2, 4));
  const b = parse(value.slice(4, 6));

  const rPct = r / 255;
  const gPct = g / 255;
  const bPct = b / 255;
  const max = Math.max(rPct, gPct, bPct);
  const min = Math.min(rPct, gPct, bPct);
  let h = 0;
  let s = 0;
  const l = (max + min) / 2;

  if (max !== min) {
    const d = max - min;
    s = l > 0.5 ? d / (2 - max - min) : d / (max + min);
    switch (max) {
      case rPct:
        h = (gPct - bPct) / d + (gPct < bPct ? 6 : 0);
        break;
      case gPct:
        h = (bPct - rPct) / d + 2;
        break;
      default:
        h = (rPct - gPct) / d + 4;
        break;
    }
    h /= 6;
  }

  const hDeg = Math.round(h * 360);
  const sPct = Math.round(s * 100);
  const lPct = Math.round(l * 100);
  return `${hDeg} ${sPct}% ${lPct}%`;
}
