import { describe, it, expect } from "vitest";
import { render, screen } from "@testing-library/react";
import { vi } from "vitest";
import React from "react";

// Ensure heavy dependencies are mocked before App is imported.
vi.mock("@assistant-ui/react", async () => {
  const stub = ({ children }: { children: React.ReactNode }) => <div>{children}</div>;
  const btn: React.FC<React.ButtonHTMLAttributes<HTMLButtonElement>> = ({ children, ...props }) => (
    <button {...props}>{children}</button>
  );
  const input = React.forwardRef<HTMLTextAreaElement, React.TextareaHTMLAttributes<HTMLTextAreaElement>>(
    (props, ref) => <textarea ref={ref} {...props} />,
  );
  const select: React.FC<React.SelectHTMLAttributes<HTMLSelectElement>> = ({ children, ...props }) => (
    <select {...props}>{children}</select>
  );

  const state = { thread: { isRunning: false }, threadListItem: { id: null } };
  const useAssistantState = <T,>(selector?: (s: typeof state) => T) => (selector ? selector(state) : state);

  return {
    AssistantRuntimeProvider: stub,
    ThreadPrimitive: { Root: stub, Viewport: stub, Messages: stub },
    ComposerPrimitive: { Root: stub, Input: input, Cancel: btn, Submit: btn, Send: btn },
    MessagePrimitive: { Root: stub, Content: stub },
    MessagePartPrimitive: { Text: () => <span>text</span>, InProgress: stub },
    ThreadListPrimitive: { Root: stub, New: btn, Items: stub },
    ThreadListItemPrimitive: { Root: stub, Trigger: btn },
    useAssistantApi: () => ({ thread: { messages: [] }, on: () => () => {} }),
    useAssistantState,
  };
});

vi.mock("./useSseRuntime", () => {
  const composer = {
    setText: vi.fn(),
    send: vi.fn(),
    cancelRun: vi.fn(),
  };
  const threadState = { messages: [], threadId: "test-thread" };
  const thread = {
    getState: () => threadState,
    subscribe: () => () => {},
    composer,
    cancelRun: vi.fn(),
    import: vi.fn(),
    reset: vi.fn(),
    export: () => ({ messages: [] }),
  };
  return { useSseRuntime: () => ({ thread }) };
});

import App from "./App";

// Smoke test: verify the shell renders without crashing and shows key UI hooks.
describe("App", () => {
  it("renders the app title and thread list section", () => {
    render(<App />);
    expect(screen.getByRole("heading", { level: 2, name: /RAG Assistant/i })).toBeInTheDocument();
    expect(screen.getByRole("heading", { level: 3, name: /Chats/i })).toBeInTheDocument();
  });

  it("shows the composer send control", () => {
    render(<App />);
    expect(screen.getByRole("button", { name: /Send/i })).toBeInTheDocument();
  });
});
