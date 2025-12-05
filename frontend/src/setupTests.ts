import "@testing-library/jest-dom";
import { vi } from "vitest";

// Mock fetch
const defaultSettings = {
  app_name: "Test App",
  theme_preset: "minimal",
};

const mocker = (globalThis as any).vi ?? vi;

const fetchMock = mocker.fn(async (input: RequestInfo | URL) => {
  const url = typeof input === "string" ? input : input.toString();
  if (url.includes("/api/settings")) {
    return new Response(JSON.stringify(defaultSettings), { status: 200 });
  }
  return new Response("Not Found", { status: 404 });
});

globalThis.fetch = fetchMock as unknown as typeof fetch;

class ResizeObserver {
  observe() {}
  unobserve() {}
  disconnect() {}
}
globalThis.ResizeObserver = ResizeObserver as unknown as typeof globalThis.ResizeObserver;

if (!globalThis.matchMedia) {
  globalThis.matchMedia = mocker.fn().mockImplementation((query: string) => ({
    matches: false,
    media: query,
    onchange: null,
    addListener: mocker.fn(),
    removeListener: mocker.fn(),
    addEventListener: mocker.fn(),
    removeEventListener: mocker.fn(),
    dispatchEvent: mocker.fn(),
  })) as unknown as typeof globalThis.matchMedia;
}
