import React from "react";

export type IconId = "sparkles" | "file" | "bot" | "book" | "bolt" | "compass";

type IconOption = { id: IconId; label: string };

const ICONS: IconOption[] = [
  { id: "sparkles", label: "Sparkles" },
  { id: "file", label: "File" },
  { id: "bot", label: "Bot" },
  { id: "book", label: "Book" },
  { id: "bolt", label: "Lightning" },
  { id: "compass", label: "Compass" },
];

type IconGlyphProps = {
  id: IconId;
  className?: string;
};

export function IconGlyph({ id, className }: IconGlyphProps) {
  const stroke = "currentColor";
  const size = 24;
  switch (id) {
    case "sparkles":
      return (
        <svg viewBox="0 0 24 24" className={className} aria-hidden="true">
          <path d="M12 3l1.6 3.8L17 8.4l-3.4 1.3L12 13l-1.6-3.3L7 8.4l3.4-1.6z" fill={stroke} />
          <path d="M6 14l.9 2L9 17l-1.6.6L6 19l-.8-1.4L4 17l1.1-.9z" fill={stroke} />
          <path d="M16 15l.8 1.8L18.6 17 17 17.6 16 19l-.9-1.4L13 17l1.8-.2z" fill={stroke} />
        </svg>
      );
    case "file":
      return (
        <svg viewBox="0 0 24 24" className={className} aria-hidden="true">
          <path d="M7 3h7l5 5v13a1 1 0 0 1-1 1H7a1 1 0 0 1-1-1V4a1 1 0 0 1 1-1z" fill="none" stroke={stroke} strokeWidth="1.6" />
          <path d="M14 3v5h5" fill="none" stroke={stroke} strokeWidth="1.6" />
        </svg>
      );
    case "bot":
      return (
        <svg viewBox="0 0 24 24" className={className} aria-hidden="true">
          <rect x="4" y="8" width="16" height="10" rx="2" ry="2" fill="none" stroke={stroke} strokeWidth="1.6" />
          <circle cx="9" cy="13" r="1" fill={stroke} />
          <circle cx="15" cy="13" r="1" fill={stroke} />
          <path d="M12 4v3" stroke={stroke} strokeWidth="1.6" />
          <circle cx="12" cy="4" r="1" fill={stroke} />
        </svg>
      );
    case "book":
      return (
        <svg viewBox="0 0 24 24" className={className} aria-hidden="true">
          <path d="M5 4h8a3 3 0 0 1 3 3v13H8a3 3 0 0 0-3 3z" fill="none" stroke={stroke} strokeWidth="1.6" />
          <path d="M16 20.5h3.5V7A3 3 0 0 0 16 4H8" fill="none" stroke={stroke} strokeWidth="1.6" />
        </svg>
      );
    case "bolt":
      return (
        <svg viewBox="0 0 24 24" className={className} aria-hidden="true">
          <path d="M13 2L4 14h6l-1 8 9-12h-6z" fill="none" stroke={stroke} strokeWidth="1.6" />
        </svg>
      );
    case "compass":
      return (
        <svg viewBox="0 0 24 24" className={className} aria-hidden="true">
          <circle cx="12" cy="12" r="9" fill="none" stroke={stroke} strokeWidth="1.6" />
          <path d="M10 14l2-6 4 4z" fill="none" stroke={stroke} strokeWidth="1.6" />
        </svg>
      );
    default:
      return <span className={className}>★</span>;
  }
}

type IconPickerProps = {
  value: IconId;
  onChange: (value: IconId) => void;
};

export function IconPicker({ value, onChange }: IconPickerProps) {
  return (
    <div className="grid grid-cols-3 gap-2">
      {ICONS.map((icon) => (
        <button
          key={icon.id}
          type="button"
          onClick={() => onChange(icon.id)}
          className={`flex items-center justify-center gap-1 border rounded-md p-2 text-sm hover:bg-muted ${
            value === icon.id ? "border-primary text-primary" : "border-border"
          }`}
        >
          <IconGlyph id={icon.id} className="w-5 h-5" />
          <span>{icon.label}</span>
        </button>
      ))}
    </div>
  );
}
