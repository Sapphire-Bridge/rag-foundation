import { Route } from "@playwright/test";

type Store = { id: number; display_name: string; fs_name: string };

export const mockState = () => {
  let storeIdSeq = 1;
  const stores: Store[] = [{ id: storeIdSeq, display_name: "Default Store", fs_name: "fs-1" }];

  return {
    stores,
    nextStoreId: () => ++storeIdSeq,
  };
};

const sseBody = [
  { type: "start" },
  { type: "text-start" },
  { type: "text-delta", delta: "According to the " },
  { type: "text-delta", delta: "document..." },
  {
    type: "source-document",
    sourceId: "1",
    title: "sample.pdf",
    snippet: "Example snippet from the mocked document.",
  },
  { type: "text-end" },
  { type: "finish" },
]
  .map((obj) => `data: ${JSON.stringify(obj)}\n\n`)
  .join("");

export async function registerApiMocks(route: Route, state: ReturnType<typeof mockState>) {
  const url = route.request().url();

  if (url.endsWith("/api/auth/token")) {
    await route.fulfill({
      contentType: "application/json",
      body: JSON.stringify({ access_token: "mock-token" }),
    });
    return;
  }

  if (url.endsWith("/api/stores")) {
    if (route.request().method() === "GET") {
      await route.fulfill({
        contentType: "application/json",
        body: JSON.stringify(state.stores),
      });
      return;
    }
    if (route.request().method() === "POST") {
      const { display_name } = await route.request().postDataJSON();
      const id = state.nextStoreId();
      const store: Store = { id, display_name, fs_name: `fs-${id}` };
      state.stores.push(store);
      await route.fulfill({
        contentType: "application/json",
        body: JSON.stringify(store),
      });
      return;
    }
  }

  if (url.includes("/api/upload/op-status/")) {
    await route.fulfill({
      contentType: "application/json",
      body: JSON.stringify({ status: "DONE", document_id: 1 }),
    });
    return;
  }

  if (url.endsWith("/api/upload")) {
    await route.fulfill({
      contentType: "application/json",
      body: JSON.stringify({ op_id: "mock-op", document_id: 1 }),
    });
    return;
  }

  if (url.includes("/api/costs/summary")) {
    await route.fulfill({
      contentType: "application/json",
      body: JSON.stringify({
        month: "2025-01",
        query_cost_usd: 0.0002,
        indexing_cost_usd: 0.0001,
        total_usd: 0.0003,
      }),
    });
    return;
  }

  if (url.includes("/api/admin")) {
    await route.fulfill({ status: 403, contentType: "application/json", body: "{}" });
    return;
  }

  if (url.endsWith("/api/chat")) {
    await route.fulfill({
      status: 200,
      headers: {
        "Content-Type": "text/event-stream",
        "Cache-Control": "no-cache",
        Connection: "keep-alive",
      },
      body: sseBody,
    });
    return;
  }

  await route.fallback();
}
