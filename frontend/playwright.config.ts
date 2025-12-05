import { defineConfig, devices } from "@playwright/test";

const isLive = process.env.E2E_MODE === "live";
const baseURL = process.env.E2E_BASE_URL || "http://localhost:5173";

export default defineConfig({
  testDir: "tests/e2e",
  fullyParallel: true,
  timeout: isLive ? 45_000 : 25_000,
  expect: {
    timeout: isLive ? 10_000 : 5_000,
  },
  use: {
    baseURL,
    trace: "on-first-retry",
    video: "retain-on-failure",
    screenshot: "only-on-failure",
    headless: true,
  },
  reporter: [["list"], ["html", { outputFolder: "playwright-report" }]],
  projects: [
    {
      name: "chromium",
      use: { ...devices["Desktop Chrome"] },
    },
  ],
  retries: isLive ? 1 : 0,
  webServer: {
    command: "npm run dev -- --host --port 5173",
    url: baseURL,
    reuseExistingServer: !process.env.CI,
    timeout: 120_000,
  },
});
