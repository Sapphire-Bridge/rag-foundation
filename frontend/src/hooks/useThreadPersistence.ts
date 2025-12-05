import { useCallback, useEffect, useRef, useState } from "react";
import { get, set } from "idb-keyval";
import type { Citation } from "../components/CitationPanel";
import type { useSseRuntime } from "../useSseRuntime";
import { toast } from "sonner";

type CitationByMessage = Record<string, Record<string, Citation[]>>;

export const useThreadPersistence = ({
  runtime,
  storeId,
  citationByMessage,
  setCitationByMessage,
}: {
  runtime: ReturnType<typeof useSseRuntime>;
  storeId: number | null;
  citationByMessage: CitationByMessage;
  setCitationByMessage: React.Dispatch<React.SetStateAction<CitationByMessage>>;
}) => {
  const [persistDisabled, setPersistDisabled] = useState(false);
  const loadedThreadIdsRef = useRef<Set<string>>(new Set());
  const citationRef = useRef(citationByMessage);

  const makeStorageKey = useCallback(
    (threadId: string) => `chat-thread:${storeId ?? "none"}:${threadId}`,
    [storeId],
  );

  useEffect(() => {
    citationRef.current = citationByMessage;
  }, [citationByMessage]);

  useEffect(() => {
    let lastThreadId: string | null = null;
    const loaded = loadedThreadIdsRef.current;

    const persist = async (threadId: string) => {
      if (persistDisabled) return;
      try {
        const exportRepo = runtime.thread.export();
        const citationsForThread = citationRef.current[threadId] || {};
        await set(makeStorageKey(threadId), JSON.stringify({ messages: exportRepo, citations: citationsForThread }));
      } catch (err) {
        const isQuota =
          err instanceof DOMException &&
          (err.name === "QuotaExceededError" || err.code === 22 || err.code === 1014);
        if (isQuota) {
          console.warn("Storage quota exceeded; disabling thread persistence", err);
          setPersistDisabled(true);
          toast.error("Storage is full. Thread history will stop syncing until you clear storage.");
        } else {
          console.warn("Failed to persist thread", err);
        }
      }
    };

    const unsub = runtime.thread.subscribe(() => {
      const state = runtime.thread.getState();
      const threadId = state.threadId;
      if (!threadId) return;

      if (threadId !== lastThreadId) {
        lastThreadId = threadId;
        if (!loaded.has(threadId)) {
          void get(makeStorageKey(threadId))
            .then((raw) => {
              if (!raw) return;
              try {
                const parsed = JSON.parse(raw as string);
                const messages = parsed?.messages ?? parsed;
                const citations = parsed?.citations ?? {};
                runtime.thread.import(messages);
                setCitationByMessage((prev) => ({ ...prev, [threadId]: citations }));
              } catch (err) {
                console.warn("Failed to restore thread", err);
              }
            })
            .finally(() => loaded.add(threadId));
        }
      }

      void persist(threadId);
    });

    return () => {
      unsub?.();
    };
  }, [runtime, makeStorageKey, persistDisabled, setCitationByMessage]);

  return { persistDisabled };
};
