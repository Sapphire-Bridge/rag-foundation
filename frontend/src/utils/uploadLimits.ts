export type UploadLimits = {
  maxUploadMb: number;
  allowedMimes: string[];
};

const DEFAULT_MAX_UPLOAD_MB = 25;
const DEFAULT_ALLOWED_MIMES = [
  "application/pdf",
  "text/plain",
  "text/markdown",
  "text/csv",
  "text/tab-separated-values",
];

const MIME_LABELS: Record<string, string> = {
  "application/pdf": "PDF",
  "text/plain": "Text",
  "text/markdown": "Markdown",
  "text/csv": "CSV",
  "text/tab-separated-values": "TSV",
  "application/msword": "Word",
  "application/vnd.oasis.opendocument.text": "OpenDocument Text",
  "application/vnd.openxmlformats-officedocument.wordprocessingml.document": "Word (DOCX)",
  "application/vnd.openxmlformats-officedocument.presentationml.presentation": "PowerPoint (PPTX)",
  "application/vnd.ms-excel": "Excel",
  "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet": "Excel (XLSX)",
};

const parseNumber = (value: unknown): number | null => {
  if (typeof value === "number" && Number.isFinite(value)) return value;
  if (typeof value === "string") {
    const asNumber = Number(value);
    if (Number.isFinite(asNumber)) return asNumber;
  }
  return null;
};

const parseList = (value: unknown): string[] => {
  if (Array.isArray(value)) {
    return value.map((v) => String(v).trim()).filter(Boolean);
  }
  if (typeof value === "string") {
    return value
      .split(",")
      .map((v) => v.trim())
      .filter(Boolean);
  }
  return [];
};

export function getUploadLimits(): UploadLimits {
  const runtimeLimits =
    typeof window !== "undefined" ? (window as unknown as { __UPLOAD_LIMITS__?: UploadLimits }).__UPLOAD_LIMITS__ : null;

  const maxUploadMb =
    parseNumber(runtimeLimits?.maxUploadMb) ??
    parseNumber(import.meta.env.VITE_MAX_UPLOAD_MB) ??
    DEFAULT_MAX_UPLOAD_MB;

  const allowedMimes =
    parseList(runtimeLimits?.allowedMimes) ||
    parseList(import.meta.env.VITE_ALLOWED_UPLOAD_MIMES || import.meta.env.VITE_ALLOWED_UPLOAD_TYPES) ||
    DEFAULT_ALLOWED_MIMES;

  return { maxUploadMb, allowedMimes };
}

export function formatAllowedTypes(allowedMimes: string[]): string {
  if (!allowedMimes.length) return "See documentation for supported formats";
  const labels = allowedMimes.map((mime) => MIME_LABELS[mime] || mime);
  const unique = Array.from(new Set(labels));
  return unique.join(", ");
}

export function buildAcceptValue(allowedMimes: string[]): string | undefined {
  if (!allowedMimes.length) return undefined;
  return allowedMimes.join(",");
}
