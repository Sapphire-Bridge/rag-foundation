import { useCallback, useEffect, useRef, useState } from "react";
import type { PendingUpload } from "../types";

const MAX_PARALLEL_UPLOADS = 3;
const UPLOAD_RETRY_DELAY_MS = 2000;
const UPLOAD_POLL_TIMEOUT_MS = 180_000;

export const useUploads = ({
  storeId,
  token,
  fetchDocuments,
  onAuthExpired,
}: {
  storeId: number | null;
  token: string;
  fetchDocuments: (sid?: number | null) => Promise<void>;
  onAuthExpired?: () => void;
}) => {
  const [pendingUploads, setPendingUploads] = useState<PendingUpload[]>([]);
  const [lastError, setLastError] = useState<string | null>(null);
  const abortRef = useRef<AbortController | null>(null);

  const getSignal = () => {
    if (!abortRef.current || abortRef.current.signal.aborted) {
      abortRef.current = new AbortController();
    }
    return abortRef.current.signal;
  };

  useEffect(() => {
    return () => {
      abortRef.current?.abort();
    };
  }, [storeId]);

  const uploadFile = useCallback(
    async (file: File) => {
      const id = `${Date.now()}-${Math.random().toString(16).slice(2)}`;
      setPendingUploads((prev) => [...prev, { id, name: file.name, status: "uploading" }]);
      if (!storeId || !token) {
        setPendingUploads((prev) =>
          prev.map((u) =>
            u.id === id ? { ...u, status: "error", message: "Login and select a store first" } : u,
          ),
        );
        return;
      }
      try {
        setLastError(null);
        const form = new FormData();
        form.append("storeId", String(storeId));
        form.append("displayName", file.name);
        form.append("file", file);
        let attempt = 0;

        const sendUpload = async (): Promise<{ op_id: string }> => {
          attempt += 1;
          const res = await fetch("/api/upload", {
            method: "POST",
            headers: { Authorization: `Bearer ${token}`, "X-Requested-With": "XMLHttpRequest" },
            body: form,
            signal: getSignal(),
          });
          if (res.status === 401 || res.status === 403) {
            onAuthExpired?.();
            throw new Error("Session expired. Please log in again.");
          }
          if (res.status === 429) {
            if (attempt <= 2) {
              setPendingUploads((prev) =>
                prev.map((u) =>
                  u.id === id
                    ? { ...u, message: "Rate limited, retrying..." }
                    : u,
                ),
              );
              await new Promise((r) => setTimeout(r, UPLOAD_RETRY_DELAY_MS));
              return sendUpload();
            }
            throw new Error("Upload rate limit reached. Please wait and retry.");
          }
          if (!res.ok) {
            const err = await res.json().catch(() => ({}));
            throw new Error(err?.detail || res.statusText);
          }
          return res.json();
        };

        const { op_id } = await sendUpload();
        let done = false;
        const startedAt = Date.now();
        while (!done) {
          await new Promise((r) => setTimeout(r, 1500));
          const statusRes = await fetch(`/api/upload/op-status/${encodeURIComponent(op_id)}`, {
            headers: { Authorization: `Bearer ${token}` },
            signal: getSignal(),
          });
          if (statusRes.status === 401 || statusRes.status === 403) {
            onAuthExpired?.();
            setPendingUploads((prev) =>
              prev.map((u) =>
                u.id === id ? { ...u, status: "error", message: "Session expired during upload" } : u,
              ),
            );
            return;
          }
          if (!statusRes.ok) {
            done = true;
            setPendingUploads((prev) =>
              prev.map((u) =>
                u.id === id
                  ? {
                      ...u,
                      status: "error",
                      message: "Upload status check failed",
                    }
                  : u,
              ),
            );
            setLastError("Upload status check failed");
            break;
          }
          const status = await statusRes.json();
          if (status.status === "DONE") {
            done = true;
            setPendingUploads((prev) =>
              prev.map((u) => (u.id === id ? { ...u, status: "indexed", message: "Ready" } : u)),
            );
            await fetchDocuments(storeId);
          } else if (status.status === "ERROR") {
            done = true;
            setPendingUploads((prev) =>
              prev.map((u) =>
                u.id === id ? { ...u, status: "error", message: status.error || "Indexing failed" } : u,
              ),
            );
          } else if (Date.now() - startedAt > UPLOAD_POLL_TIMEOUT_MS) {
            done = true;
            setPendingUploads((prev) =>
              prev.map((u) =>
                u.id === id
                  ? { ...u, status: "error", message: "Indexing is taking too long. Please retry." }
                  : u,
              ),
            );
          }
        }
      } catch (err) {
        if ((err as Error).name === "AbortError") {
          setPendingUploads((prev) =>
            prev.map((u) => (u.id === id ? { ...u, status: "error", message: "Canceled" } : u)),
          );
          return;
        }
        setPendingUploads((prev) =>
          prev.map((u) =>
            u.id === id ? { ...u, status: "error", message: (err as Error).message } : u,
          ),
        );
        setLastError((err as Error).message);
      }
    },
    [storeId, token, fetchDocuments, onAuthExpired],
  );

  const handleFiles = useCallback(
    (files: FileList | null) => {
      if (!files?.length) return;
      const queue = Array.from(files);
      const run = async () => {
        const active: Promise<void>[] = [];
        while (queue.length > 0 || active.length > 0) {
          while (queue.length && active.length < MAX_PARALLEL_UPLOADS) {
            const next = queue.shift()!;
            const promise = uploadFile(next).finally(() => {
              const idx = active.indexOf(promise);
              if (idx >= 0) active.splice(idx, 1);
            });
            active.push(promise);
          }
          await Promise.race(active).catch(() => {});
        }
      };
      run();
    },
    [uploadFile],
  );

  return { pendingUploads, handleFiles, uploadFile, lastError };
};
