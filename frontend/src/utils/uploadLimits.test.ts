import { afterEach, describe, expect, it, vi } from "vitest";
import { buildAcceptValue, getUploadLimits } from "./uploadLimits";

type UploadLimitsWindow = Window & {
  __UPLOAD_LIMITS__?: {
    maxUploadMb?: number;
    allowedMimes?: string[];
  };
};

const uploadWindow = window as UploadLimitsWindow;

describe("uploadLimits", () => {
  afterEach(() => {
    delete uploadWindow.__UPLOAD_LIMITS__;
    vi.unstubAllEnvs();
  });

  it("falls back to default MIME types when runtime and env lists are empty", () => {
    uploadWindow.__UPLOAD_LIMITS__ = { maxUploadMb: 10, allowedMimes: [] };
    vi.stubEnv("VITE_ALLOWED_UPLOAD_MIMES", "");
    vi.stubEnv("VITE_ALLOWED_UPLOAD_TYPES", "");

    const limits = getUploadLimits();

    expect(limits.maxUploadMb).toBe(10);
    expect(limits.allowedMimes).toContain("application/pdf");
    expect(buildAcceptValue(limits.allowedMimes)).toContain("application/pdf");
  });

  it("prefers a non-empty runtime MIME list over env and defaults", () => {
    uploadWindow.__UPLOAD_LIMITS__ = { maxUploadMb: 25, allowedMimes: [" text/plain ", ""] };
    vi.stubEnv("VITE_ALLOWED_UPLOAD_MIMES", "application/pdf");

    expect(getUploadLimits().allowedMimes).toEqual(["text/plain"]);
  });
});
