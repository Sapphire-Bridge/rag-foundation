import { test, expect } from "@playwright/test";
import path from "path";
import { fileURLToPath } from "url";
import { mockState, registerApiMocks } from "./mocks";

const isLive = process.env.E2E_MODE === "live";
const fixtureFile = path.resolve(
  path.dirname(fileURLToPath(import.meta.url)),
  "fixtures",
  "sample.txt",
);

test.beforeEach(async ({ page }) => {
  if (!isLive) {
    const state = mockState();
    await page.route("**/api/**", (route) => registerApiMocks(route, state));
  }
});

test("dev user can upload and chat with citations", async ({ page }) => {
  await page.goto("/");

  // Dev login
  await page.getByPlaceholder("you@example.com").fill("dev@example.com");
  await page.getByRole("button", { name: /Dev Token/i }).click();

  // Ensure store select is hydrated
  const storeSelect = page.getByRole("combobox");
  await expect(storeSelect).toBeVisible();

  // Create store via prompt dialog
  const storeName = `E2E Store ${Date.now()}`;
  page.on("dialog", (dialog) => dialog.accept(storeName));
  const storePost = page.waitForResponse(
    (resp) =>
      resp.url().includes("/api/stores") &&
      resp.request().method() === "POST" &&
      resp.ok(),
  );
  const storeGet = page.waitForResponse(
    (resp) =>
      resp.url().includes("/api/stores") &&
      resp.request().method() === "GET" &&
      resp.ok(),
  );
  await Promise.all([
    storePost,
    storeGet,
    page.getByRole("button", { name: /\+ New Store/i }).click(),
  ]);
  await expect(storeSelect).toContainText(storeName);

  // Upload fixture via Attach input
  const fileInput = page.locator('input[type="file"]');
  await fileInput.setInputFiles(fixtureFile);
  await expect(page.getByText("Indexed")).toBeVisible({ timeout: 10_000 });

  // Send a question
  const composer = page.getByPlaceholder(/Ask a question/i);
  await composer.fill("What does the document say?");
  await page.getByRole("button", { name: /^Send$/i }).click();

  // Streaming lifecycle: in mock mode the stream completes instantly.
  // Assert the send cleared the composer and the assistant response rendered.
  await expect(composer).toHaveValue("");
  await expect(page.getByText(/According to the document/i)).toBeVisible({ timeout: 10_000 });

  // Assistant response + citation chips
  await expect(page.getByText(/According to the document/i)).toBeVisible({ timeout: 10_000 });
  await expect(page.getByText(/Source 1/i)).toBeVisible({ timeout: 10_000 });

  // Citations panel
  await page.getByRole("button", { name: /Show Citations/i }).click();
  await expect(page.getByRole("heading", { name: /^Sources$/ })).toBeVisible();
  await expect(page.getByText(/Example snippet/i)).toBeVisible();
});
