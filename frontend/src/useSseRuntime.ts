import { toLanguageModelMessages } from "@assistant-ui/react-data-stream";
import {
  AssistantRuntime,
  ChatModelAdapter,
  ChatModelRunOptions,
  INTERNAL,
  LocalRuntimeOptions,
  ThreadMessage,
  Tool,
  useLocalRuntime,
} from "@assistant-ui/react";
import { JSONSchema7 } from "json-schema";
import { z } from "zod";
import { AssistantMessageAccumulator } from "assistant-stream";
import { asAsyncIterableStream } from "assistant-stream/utils";

const { splitLocalRuntimeOptions } = INTERNAL;

type HeadersValue = Record<string, string> | Headers;

type FinishReason =
  | "stop"
  | "length"
  | "content-filter"
  | "tool-calls"
  | "error"
  | "other"
  | "unknown";

type StartEvent = { type: "start"; messageId?: string };
type TextStartEvent = { type: "text-start"; id?: string };
type TextDeltaEvent = { type: "text-delta"; id?: string; delta?: string };
type TextEndEvent = { type: "text-end"; id?: string };
type SourceDocumentEvent = {
  type: "source-document";
  sourceId?: string;
  mediaType?: string;
  title?: string | null;
  snippet?: string | null;
};
type ErrorEvent = { type: "error"; errorText?: string; code?: string; message?: string };
type FinishEvent = {
  type: "finish";
  finishReason?: FinishReason;
  promptTokens?: number;
  completionTokens?: number;
};

type SseEventPayload =
  | StartEvent
  | TextStartEvent
  | TextDeltaEvent
  | TextEndEvent
  | SourceDocumentEvent
  | ErrorEvent
  | FinishEvent;

const isSseEventPayload = (value: unknown): value is SseEventPayload => {
  if (!value || typeof value !== "object") return false;
  const type = (value as { type?: unknown }).type;
  return (
    type === "start" ||
    type === "text-start" ||
    type === "text-delta" ||
    type === "text-end" ||
    type === "source-document" ||
    type === "error" ||
    type === "finish"
  );
};

export type UseSseRuntimeOptions = {
  api: string;
  onResponse?: (response: Response) => void | Promise<void>;
  onFinish?: (message: ThreadMessage) => void;
  onError?: (error: Error) => void;
  onEvent?: (event: { data: SseEventPayload }) => void;
  onCancel?: () => void;
  credentials?: RequestCredentials;
  headers?: HeadersValue | (() => Promise<HeadersValue>);
  body?: object;
  sendExtraMessageFields?: boolean;
} & LocalRuntimeOptions;

const toAISDKTools = (tools: Record<string, Tool>) => {
  return Object.fromEntries(
    Object.entries(tools).map(([name, tool]) => [
      name,
      {
        ...(tool.description ? { description: tool.description } : undefined),
        parameters: (tool.parameters instanceof z.ZodType
          ? z.toJSONSchema(tool.parameters)
          : tool.parameters) as JSONSchema7,
      },
    ]),
  );
};

const getEnabledTools = (tools: Record<string, Tool>) => {
  return Object.fromEntries(
    Object.entries(tools).filter(
      ([, tool]) => !tool.disabled && tool.type !== "backend",
    ),
  );
};

type Usage = { promptTokens: number; completionTokens: number };

class SseStreamError extends Error {
  code?: string;
  status?: number;
}

const parseSseStream = ({
  response,
  onEvent,
  onError,
  abortSignal,
}: {
  response: Response;
  onEvent?: (event: { data: SseEventPayload }) => void;
  onError?: (error: Error) => void;
  abortSignal: AbortSignal;
}) => {
  const body = response.body;
  if (!body) {
    throw new Error("Response body is null");
  }

  return new ReadableStream({
    start(controller) {
      const reader = body.getReader();
      const decoder = new TextDecoder();
      let buffer = "";
      let finished = false;
      let finishReason: FinishReason = "stop";
      let usage: Usage = { promptTokens: 0, completionTokens: 0 };
      let stopReading = false;
      let nextPartIndex = 0;
      let activePartIndex: number | null = null;

      const emitFinish = () => {
        if (finished) return;
        if (activePartIndex !== null) {
          controller.enqueue({
            type: "part-finish",
            path: [activePartIndex],
          } as const);
          activePartIndex = null;
        }
        finished = true;
        controller.enqueue({
          type: "message-finish",
          path: [],
          finishReason,
          usage,
        } as const);
        controller.close();
      };

      const handleEvent = (payload: SseEventPayload) => {
        onEvent?.({ data: payload });
        switch (payload.type) {
          case "start": {
            nextPartIndex = 0;
            activePartIndex = null;
            if (payload.messageId) {
              controller.enqueue({
                type: "step-start",
                path: [],
                messageId: String(payload.messageId),
              } as const);
            }
            break;
          }
          case "text-start": {
            const idx = nextPartIndex++;
            activePartIndex = idx;
            controller.enqueue({
              type: "part-start",
              path: [idx],
              part: { type: "text" },
            } as const);
            break;
          }
          case "text-delta": {
            if (typeof payload.delta === "string" && payload.delta) {
              if (activePartIndex === null) {
                const idx = nextPartIndex++;
                activePartIndex = idx;
                controller.enqueue({
                  type: "part-start",
                  path: [idx],
                  part: { type: "text" },
                } as const);
              }
              controller.enqueue({
                type: "text-delta",
                path: [activePartIndex],
                textDelta: payload.delta,
              } as const);
            }
            break;
          }
          case "text-end": {
            if (activePartIndex !== null) {
              controller.enqueue({
                type: "part-finish",
                path: [activePartIndex],
              } as const);
              activePartIndex = null;
            }
            break;
          }
          case "source-document": {
            controller.enqueue({
              type: "data",
              path: [],
              data: [payload],
            } as const);
            break;
          }
          case "error": {
            const error = new SseStreamError(
              payload.errorText ??
                payload.message ??
                "An error occurred processing your request.",
            );
            error.code = payload.code;
            finishReason = "error";
            stopReading = true;
            controller.error(error);
            break;
          }
          case "finish": {
            finishReason = payload.finishReason ?? "stop";
            usage = {
              promptTokens: Number(payload.promptTokens ?? 0),
              completionTokens: Number(payload.completionTokens ?? 0),
            };
            stopReading = true;
            emitFinish();
            break;
          }
          default:
            break;
        }
      };

      const processBuffer = () => {
        while (true) {
          const boundary = buffer.indexOf("\n\n");
          if (boundary === -1) break;
          const rawEvent = buffer.slice(0, boundary);
          buffer = buffer.slice(boundary + 2);
          const dataLines = rawEvent
            .split("\n")
            .filter((line) => line.startsWith("data:"))
            .map((line) => line.slice(5));
          if (!dataLines.length) continue;
          const payload = dataLines.join("\n").trim();
          if (!payload) continue;
          if (payload.startsWith(":")) continue; // ignore keepalive/comments
          if (payload === "[DONE]") {
            stopReading = true;
            emitFinish();
            break;
          }
          try {
            const parsed = JSON.parse(payload);
            if (isSseEventPayload(parsed)) {
              handleEvent(parsed);
            } else {
              const err = new Error("Ignored non-SSE payload");
              err.name = "SseParseWarning";
              onError?.(err);
            }
          } catch {
            const err = new Error("Failed to parse SSE event payload");
            err.name = "SseParseWarning";
            onError?.(err);
          }
        }
      };

      const readLoop = async () => {
        try {
          while (!stopReading) {
            const { value, done } = await reader.read();
            if (done) break;
            buffer += decoder.decode(value, { stream: true });
            processBuffer();
          }
          buffer += decoder.decode();
          processBuffer();
        } finally {
          emitFinish();
        }
      };

      abortSignal.addEventListener(
        "abort",
        () => {
          stopReading = true;
          reader.cancel().catch(() => {});
        },
        { once: true },
      );

      readLoop().catch((error) => controller.error(error));
    },
  });
};

class SseRuntimeAdapter implements ChatModelAdapter {
  constructor(
    private options: Omit<UseSseRuntimeOptions, keyof LocalRuntimeOptions>,
  ) {}

  async *run({
    messages,
    runConfig,
    abortSignal,
    context,
    unstable_assistantMessageId,
    unstable_getMessage,
  }: ChatModelRunOptions) {
    const headersValue =
      typeof this.options.headers === "function"
        ? await this.options.headers()
        : this.options.headers;

    abortSignal.addEventListener(
      "abort",
      () => {
        if (!abortSignal.reason?.detach) this.options.onCancel?.();
      },
      { once: true },
    );

    const headers = new Headers(headersValue);
    headers.set("Content-Type", "application/json");

    const response = await fetch(this.options.api, {
      method: "POST",
      headers,
      credentials: this.options.credentials ?? "same-origin",
      body: JSON.stringify({
        system: context.system,
        messages: toLanguageModelMessages(messages, {
          unstable_includeId: this.options.sendExtraMessageFields,
        }),
        tools: toAISDKTools(getEnabledTools(context.tools ?? {})),
        ...(unstable_assistantMessageId ? { unstable_assistantMessageId } : {}),
        runConfig,
        state: unstable_getMessage().metadata.unstable_state || undefined,
        ...context.callSettings,
        ...context.config,
        ...this.options.body,
      }),
      signal: abortSignal,
    });

    await this.options.onResponse?.(response);

    if (!response.ok) {
      const text = await response.text();
      const httpError = new SseStreamError(
        text || `Status ${response.status}: ${response.statusText}`,
      );
      httpError.status = response.status;
      this.options.onError?.(httpError);
      throw httpError;
    }

    try {
      const chunkStream = parseSseStream({
        response,
        onEvent: this.options.onEvent,
        onError: this.options.onError,
        abortSignal,
      });

      const messageStream = chunkStream.pipeThrough(
        new AssistantMessageAccumulator(),
      );

      yield* asAsyncIterableStream(messageStream);

      this.options.onFinish?.(unstable_getMessage());
    } catch (error) {
      this.options.onError?.(error as Error);
      throw error;
    }
  }
}

export const useSseRuntime = (
  options: UseSseRuntimeOptions,
): AssistantRuntime => {
  const { localRuntimeOptions, otherOptions } =
    splitLocalRuntimeOptions(options);

  return useLocalRuntime(
    new SseRuntimeAdapter(otherOptions),
    localRuntimeOptions,
  );
};
