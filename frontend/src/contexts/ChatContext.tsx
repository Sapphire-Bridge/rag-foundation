import React, { createContext, useCallback, useContext, useEffect, useMemo, useRef, useState } from "react";
import type { TextMessagePart, ThreadMessage, ThreadUserMessagePart, ThreadMessageLike } from "@assistant-ui/react";
import { AssistantRuntimeProvider } from "@assistant-ui/react";
import { ThreadEventsReset } from "../components/chat/ThreadEventsReset";
import type { Citation } from "../components/CitationPanel";
import { useSseRuntime } from "../useSseRuntime";
import { useStoreContext } from "./StoreContext";
import { toast } from "sonner";

export type ModelOption = { id: string; label: string };

type ChatContextValue = {
  runtime: ReturnType<typeof useSseRuntime>;
  model: string;
  setModel: (m: string) => void;
  models: ModelOption[];
  citationByMessage: Record<string, Record<string, Citation[]>>;
  activeCitationMessageId: string | null;
  setActiveCitationMessageId: (id: string | null) => void;
  selectedCitationIndex: number | null;
  setSelectedCitationIndex: (i: number | null) => void;
  showCitations: boolean;
  setShowCitations: (value: boolean) => void;
  getThreadName: (id: string) => string;
  renameThread: (id: string, name: string) => void;
  handleRetryLast: () => void;
  handleLoadLastIntoComposer: () => void;
  composerInputRef: React.RefObject<HTMLTextAreaElement>;
  isAdmin: boolean;
  lastError: string | null;
  sessions: ChatSessionSummary[];
  activeSessionId: string | null;
  loadingSessions: boolean;
  selectSession: (id: string) => Promise<void>;
  createNewSession: () => Promise<void>;
};

export type ChatSessionSummary = {
  id: string;
  store_id: number | null;
  title: string;
  updated_at: string | null;
};

type ChatHistoryMessage = {
  id: number;
  role: "user" | "assistant";
  content: string;
  created_at: string | null;
};

const ChatContext = createContext<ChatContextValue | null>(null);

const isUserTextPart = (part: ThreadUserMessagePart): part is TextMessagePart => part.type === "text";

const extractUserMessageText = (message: ThreadMessage | undefined | null) => {
  if (!message || message.role !== "user") return "";
  return message.content
    .filter(isUserTextPart)
    .map((part) => part.text)
    .join("\n")
    .trim();
};

const generateSessionId = () => {
  if (typeof crypto !== "undefined" && crypto.randomUUID) return crypto.randomUUID();
  return `session-${Math.random().toString(36).slice(2, 10)}-${Date.now()}`;
};

export const ChatProvider: React.FC<{
  token: string;
  models: ModelOption[];
  onAuthExpired: () => void;
  children: React.ReactNode;
}> = ({ token, models, onAuthExpired, children }) => {
  const { storeId, isAdmin } = useStoreContext();
  const [model, setModel] = useState<string>(models[0]?.id ?? "");
  const [citationByMessage, setCitationByMessage] = useState<Record<string, Record<string, Citation[]>>>(
    {},
  );
  const [activeCitationMessageId, setActiveCitationMessageId] = useState<string | null>(null);
  const [selectedCitationIndex, setSelectedCitationIndex] = useState<number | null>(null);
  const [showCitations, setShowCitations] = useState(false);
  const [threadNames, setThreadNames] = useState<Record<string, string>>({});
  const [lastError, setLastError] = useState<string | null>(null);
  const currentAssistantMessageId = useRef<string | null>(null);
  const composerInputRef = useRef<HTMLTextAreaElement | null>(null);
  const runtimeRef = useRef<ReturnType<typeof useSseRuntime> | null>(null);
  const sessionsRef = useRef<ChatSessionSummary[]>([]);
  const pendingSessionIdRef = useRef<string | null>(null);
  const [sessions, setSessions] = useState<ChatSessionSummary[]>([]);
  const [activeSessionId, setActiveSessionId] = useState<string | null>(null);
  const [loadingSessions, setLoadingSessions] = useState(false);

  const getCitationKey = useCallback(() => {
    if (activeSessionId) return activeSessionId;
    try {
      return runtimeRef.current?.thread.getState().threadId ?? null;
    } catch {
      return null;
    }
  }, [activeSessionId]);

  const threadNameKey = useCallback(
    (threadId: string) => `thread-name:${storeId ?? "none"}:${threadId}`,
    [storeId],
  );

  const getThreadName = useCallback(
    (threadId: string) => {
      const cached = threadNames[threadId];
      if (cached !== undefined) return cached;
      const fromStorage = localStorage.getItem(threadNameKey(threadId));
      return fromStorage || "";
    },
    [threadNames, threadNameKey],
  );

  const renameThread = useCallback(
    (threadId: string, name: string) => {
      setThreadNames((prev) => ({ ...prev, [threadId]: name }));
      localStorage.setItem(threadNameKey(threadId), name);
    },
    [threadNameKey],
  );

  useEffect(() => {
    setThreadNames({});
  }, [storeId]);

  useEffect(() => {
    setSessions([]);
    setActiveSessionId(null);
    const rt = runtimeRef.current;
    if (rt) {
      rt.thread.cancelRun?.();
      rt.thread.reset?.();
    }
    setSelectedCitationIndex(null);
    setShowCitations(false);
    setActiveCitationMessageId(null);
  }, [storeId]);

  const refreshSessions = useCallback(async () => {
    if (!token) {
      setSessions([]);
      setActiveSessionId(null);
      return;
    }
    setLoadingSessions(true);
    try {
      const params = storeId != null ? `?storeId=${storeId}` : "";
      const res = await fetch(`/api/chat/sessions${params}`, {
        headers: {
          Authorization: `Bearer ${token}`,
          "X-Requested-With": "XMLHttpRequest",
        },
      });
      if (res.status === 401 || res.status === 403) {
        onAuthExpired();
        return;
      }
      if (!res.ok) throw new Error(`Failed to load chats (${res.status})`);
      const data: ChatSessionSummary[] = await res.json();
      setSessions(data);
      sessionsRef.current = data;

      const pending = pendingSessionIdRef.current;
      if (pending) {
        if (data.some((s) => s.id === pending)) {
          // Session was created on backend, clear pending flag
          pendingSessionIdRef.current = null;
        } else if (activeSessionId === pending) {
          // Still waiting for backend, don't touch state
          return;
        }
      }

      if (data.length === 0) {
        setActiveSessionId(null);
        return;
      }

      // Only auto-select when nothing is currently active; otherwise keep the user’s selection.
      if (!activeSessionId) {
        setActiveSessionId(data[0].id);
      }
    } catch (err) {
      console.error(err);
      toast.error("Unable to load chats.");
    } finally {
      setLoadingSessions(false);
    }
  }, [activeSessionId, onAuthExpired, storeId, token]);

  const upsertLocalSession = useCallback(
    (sessionId: string, title?: string | null) => {
      setSessions((prev) => {
        if (prev.find((s) => s.id === sessionId)) return prev;
        const entry: ChatSessionSummary = {
          id: sessionId,
          store_id: storeId ?? null,
          title: title || "New chat",
          updated_at: new Date().toISOString(),
        };
        return [entry, ...prev];
      });
    },
    [storeId],
  );

  const runtime = useSseRuntime({
    api: "/api/chat",
    body: { storeIds: storeId ? [storeId] : [], model, session_id: activeSessionId || undefined },
    headers: token
      ? { Authorization: `Bearer ${token}`, "X-Requested-With": "XMLHttpRequest" }
      : { "X-Requested-With": "XMLHttpRequest" },
    onFinish: () => {
      void refreshSessions();
    },
    onError: (err) => {
      console.error(err);
      const code = (err as { code?: string })?.code || "unexpected_error";
      const status = (err as { status?: number })?.status;

      if (status === 401 || status === 403) {
        onAuthExpired();
        toast.error("Session expired. Please log in again.");
        setLastError("Session expired. Please log in again.");
        runtimeRef.current?.thread.cancelRun?.();
        return;
      }

      if (status === 404 || status === 410) {
        toast.error("The selected store is unavailable or was deleted. Please pick another store and retry.");
        setLastError("The selected store is unavailable or was deleted. Please pick another store and retry.");
        runtimeRef.current?.thread.cancelRun();
        return;
      }

      const map: Record<
        string,
        {
          msg: string;
          type: "error" | "warning";
        }
      > = {
        budget_exceeded: { msg: "Monthly budget exceeded.", type: "error" },
        upstream_unavailable: { msg: "AI Service overloaded.", type: "warning" },
        stream_capacity_exceeded: { msg: "Server busy. Please try again.", type: "warning" },
      };
      const { msg, type } = map[code] || { msg: "Connection failed.", type: "error" };
      toast[type](msg);
      setLastError(msg);
      runtimeRef.current?.thread.cancelRun?.();
    },
    onEvent: ({ data }) => {
      const getActiveThreadId = () => getCitationKey();
      const captureAssistantMessageId = () => {
        try {
          const messages = runtime.thread.getState().messages;
          const lastAssistant = [...messages].reverse().find((m) => m.role === "assistant");
          if (lastAssistant?.id) {
            currentAssistantMessageId.current = lastAssistant.id;
            return lastAssistant.id;
          }
        } catch (err) {
          console.warn("Unable to capture assistant message id", err);
        }
        return currentAssistantMessageId.current;
      };

      if (data.type === "start") {
        const threadId = getActiveThreadId();
        const msgId = captureAssistantMessageId();
        setActiveCitationMessageId(null);
        setLastError(null);
        if (activeSessionId) {
          upsertLocalSession(activeSessionId);
        }
        if (threadId && msgId) {
          setCitationByMessage((prev) => ({
            ...prev,
            [threadId]: { ...(prev[threadId] || {}), [msgId]: [] },
          }));
          setActiveCitationMessageId(msgId);
        }
        setSelectedCitationIndex(null);
        setShowCitations(false);
      }

      if (data.type === "error") {
        runtime.thread.cancelRun?.();
      }

      if (data.type === "source-document") {
        const threadId = getActiveThreadId();
        const msgId = currentAssistantMessageId.current ?? captureAssistantMessageId();
        if (!threadId || !msgId) return;
        const nextCitation: Citation = {
          sourceId: data.sourceId,
          title: data.title ?? null,
          snippet: data.snippet ?? null,
        };
        setCitationByMessage((prev) => {
          const forThread = prev[threadId] || {};
          const existing = forThread[msgId] || [];
          return {
            ...prev,
            [threadId]: {
              ...forThread,
              [msgId]: [...existing, nextCitation],
            },
          };
        });
      }
    },
  });
  useEffect(() => {
    runtimeRef.current = runtime;
  }, [runtime]);

  const loadSessionMessages = useCallback(
    async (sessionId: string) => {
      if (!token) return;
      try {
        if (runtime.thread.getState().isRunning) return;
      } catch {
        // If runtime state is unavailable, allow the fetch to continue.
      }
      try {
        const res = await fetch(`/api/chat/sessions/${encodeURIComponent(sessionId)}/messages`, {
          headers: {
            Authorization: `Bearer ${token}`,
            "X-Requested-With": "XMLHttpRequest",
          },
        });
        if (res.status === 401 || res.status === 403) {
          onAuthExpired();
          return;
        }
        if (res.status === 404) {
          toast.error("Chat not found.");
          return;
        }
        if (!res.ok) throw new Error(`Failed to load chat (${res.status})`);
        const data: ChatHistoryMessage[] = await res.json();
        const threadMessages: ThreadMessageLike[] = data.map((m) => ({
          id: String(m.id),
          role: m.role,
          content: [{ type: "text", text: m.content }],
          metadata: {},
        }));
        runtime.thread.cancelRun();
        runtime.thread.reset(threadMessages);
        currentAssistantMessageId.current = null;
        const key = sessionId || getCitationKey();
        if (key) {
          setCitationByMessage((prev) => (prev[key] ? prev : { ...prev, [key]: {} }));
        }
        setSelectedCitationIndex(null);
        setShowCitations(false);
        setLastError(null);
      } catch (err) {
        console.error(err);
        toast.error("Unable to load chat history.");
      }
    },
    [onAuthExpired, runtime, token],
  );

  const selectSession = useCallback(
    async (sessionId: string) => {
      setActiveSessionId(sessionId);
      runtime.thread.cancelRun();
      runtime.thread.reset();
      setSelectedCitationIndex(null);
      setShowCitations(false);
      setActiveCitationMessageId(null);
      setLastError(null);
    },
    [runtime],
  );

  const createNewSession = useCallback(async () => {
    const newId = generateSessionId();
    pendingSessionIdRef.current = newId;
    setActiveSessionId(newId);
    runtime.thread.cancelRun();
    runtime.thread.reset();
    setSelectedCitationIndex(null);
    setShowCitations(false);
    setActiveCitationMessageId(null);
  }, [runtime]);

  useEffect(() => {
    void refreshSessions();
  }, [refreshSessions]);

  useEffect(() => {
    sessionsRef.current = sessions;
  }, [sessions]);

  useEffect(() => {
    if (!activeSessionId) return;
    try {
      if (runtime.thread.getState().isRunning) return;
    } catch {
      // If runtime state is unavailable, allow reload to proceed.
    }
    if (pendingSessionIdRef.current === activeSessionId) return;
    if (sessionsRef.current.some((s) => s.id === activeSessionId)) {
      void loadSessionMessages(activeSessionId);
    }
  }, [activeSessionId, loadSessionMessages, runtime]);

  const handleRetryLast = useCallback(() => {
    const messages = runtime.thread.getState().messages;
    const lastUser = [...messages].reverse().find((m) => m.role === "user");
    if (!lastUser || lastUser.role !== "user") return;
    const text = extractUserMessageText(lastUser);
    runtime.thread.cancelRun();
    runtime.thread.composer.setText(text);
    runtime.thread.composer.send();
  }, [runtime]);

  const handleLoadLastIntoComposer = useCallback(() => {
    const messages = runtime.thread.getState().messages;
    const lastUser = [...messages].reverse().find((m) => m.role === "user");
    if (!lastUser || lastUser.role !== "user") return;
    const text = extractUserMessageText(lastUser);
    runtime.thread.composer.setText(text);
    composerInputRef.current?.focus();
  }, [runtime]);

  const resetThreadUi = useCallback(() => {
    currentAssistantMessageId.current = null;
    setActiveCitationMessageId(null);
    setSelectedCitationIndex(null);
    setShowCitations(false);
  }, []);

  const value = useMemo(
    () => ({
      runtime,
      model,
      setModel,
      models,
      citationByMessage,
      activeCitationMessageId,
      setActiveCitationMessageId,
      selectedCitationIndex,
      setSelectedCitationIndex,
      showCitations,
      setShowCitations,
      getThreadName,
      renameThread,
      handleRetryLast,
      handleLoadLastIntoComposer,
      composerInputRef,
      isAdmin,
      lastError,
      sessions,
      activeSessionId,
      loadingSessions,
      selectSession,
      createNewSession,
    }),
    [
      runtime,
      model,
      models,
      citationByMessage,
      activeCitationMessageId,
      selectedCitationIndex,
      showCitations,
      getThreadName,
      renameThread,
      handleRetryLast,
      handleLoadLastIntoComposer,
      isAdmin,
      lastError,
      sessions,
      activeSessionId,
      loadingSessions,
      selectSession,
      createNewSession,
    ],
  );

  return (
    <ChatContext.Provider value={value}>
      <AssistantRuntimeProvider runtime={runtime}>
        <ThreadEventsReset onReset={resetThreadUi} />
        {children}
      </AssistantRuntimeProvider>
    </ChatContext.Provider>
  );
};

export const useChatContext = () => {
  const ctx = useContext(ChatContext);
  if (!ctx) {
    throw new Error("useChatContext must be used within a ChatProvider");
  }
  return ctx;
};
