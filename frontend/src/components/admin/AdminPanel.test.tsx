import React from "react";
import { describe, it, expect, beforeEach, afterEach, vi } from "vitest";
import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import { AdminPanel } from "../AdminPanel";

const createFakeToken = (id: number) => {
  const header = btoa(JSON.stringify({ alg: "HS256", typ: "JWT" }));
  const payload = btoa(JSON.stringify({ sub: String(id), exp: 9999999999 }));
  return `${header}.${payload}.signature`;
};

const MOCK_ADMIN_ID = 1;
const MOCK_TOKEN = createFakeToken(MOCK_ADMIN_ID);

const MOCK_USERS = [
  {
    id: 1,
    email: "admin@example.com",
    is_admin: true,
    is_active: true,
    admin_notes: null,
    monthly_limit_usd: null,
    created_at: new Date().toISOString(),
  },
  {
    id: 2,
    email: "user@example.com",
    is_admin: false,
    is_active: true,
    admin_notes: null,
    monthly_limit_usd: 50.0,
    created_at: new Date().toISOString(),
  },
];

const MOCK_SUMMARY = { users: 2, stores: 5, documents: 10 };
const MOCK_AUDIT: any[] = [];

const originalFetch = globalThis.fetch;

describe("AdminPanel integration", () => {
  const onAuthExpired = vi.fn();
  let fetchMock: typeof globalThis.fetch;

  beforeEach(() => {
    onAuthExpired.mockReset();
    fetchMock = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      const url = typeof input === "string" ? input : input.toString();
      const method = init?.method ?? "GET";

      if (url.includes("/api/admin/users") && method === "GET") {
        return new Response(JSON.stringify(MOCK_USERS), { status: 200 });
      }
      if (url.includes("/api/admin/audit") && method === "GET") {
        return new Response(JSON.stringify(MOCK_AUDIT), { status: 200 });
      }
      if (url.includes("/api/admin/system/summary") && method === "GET") {
        return new Response(JSON.stringify(MOCK_SUMMARY), { status: 200 });
      }
      if (url.includes("/api/admin/budgets/2") && method === "POST") {
        const rawBody = init?.body ? String(init.body) : "{}";
        const body = JSON.parse(rawBody);
        if (body.monthly_limit_usd === 100) {
          return new Response("OK", { status: 200 });
        }
        return new Response("Bad Request", { status: 400 });
      }

      return new Response("Not Found", { status: 404 });
    }) as typeof globalThis.fetch;
    globalThis.fetch = fetchMock;
  });

  afterEach(() => {
    globalThis.fetch = originalFetch;
    vi.clearAllMocks();
  });

  it("renders users and budgets correctly", async () => {
    render(<AdminPanel token={MOCK_TOKEN} onAuthExpired={onAuthExpired} />);

    await waitFor(() => {
      expect(screen.getByText("admin@example.com")).toBeInTheDocument();
    });

    expect(screen.getByText("Unlimited")).toBeInTheDocument();
    expect(screen.getByText("$50.00")).toBeInTheDocument();
    expect(screen.getByText("Admin")).toBeInTheDocument();
  });

  it("prevents self-demotion for the current admin", async () => {
    render(<AdminPanel token={MOCK_TOKEN} onAuthExpired={onAuthExpired} />);

    await waitFor(() => {
      expect(screen.getByText("admin@example.com")).toBeInTheDocument();
    });

    const editButtons = screen.getAllByText("Edit");
    fireEvent.click(editButtons[0]);

    const adminCheckbox = screen.getByLabelText("Admin") as HTMLInputElement;
    expect(adminCheckbox).toBeDisabled();
    expect(screen.getByText(/cannot remove your own admin access/i)).toBeInTheDocument();
  });

  it("sends the correct payload when updating another user's budget", async () => {
    render(<AdminPanel token={MOCK_TOKEN} onAuthExpired={onAuthExpired} />);

    await waitFor(() => {
      expect(screen.getByText("user@example.com")).toBeInTheDocument();
    });

    const editButtons = screen.getAllByText("Edit");
    fireEvent.click(editButtons[1]);

    const budgetInput = screen.getByPlaceholderText("e.g. 500");
    fireEvent.change(budgetInput, { target: { value: "100" } });

    const updateButton = screen.getByText("Update");
    fireEvent.click(updateButton);

    await waitFor(() => {
      expect(fetchMock).toHaveBeenCalledWith(
        expect.stringContaining("/api/admin/budgets/2"),
        expect.objectContaining({
          method: "POST",
          body: JSON.stringify({ monthly_limit_usd: 100 }),
        }),
      );
    });
  });
});
