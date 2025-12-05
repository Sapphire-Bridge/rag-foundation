import React, { createContext, useContext, useEffect, useMemo, useState } from "react";
import { useAdminAndStores } from "../hooks/useAdminAndStores";
import { useUploads } from "../hooks/useUploads";
import type { DocumentRow, PendingUpload, StoreSummary } from "../types";
import { toast } from "sonner";

type StoreContextValue = {
  token: string;
  setToken: (token: string) => void;
  stores: StoreSummary[];
  storeId: number | null;
  setStoreId: (id: number | null) => void;
  documents: DocumentRow[];
  refreshStores: () => Promise<void>;
  fetchDocuments: (sid?: number | null) => Promise<void>;
  pendingUploads: PendingUpload[];
  handleFiles: (files: FileList | null) => void;
  uploadFile: (file: File) => Promise<void>;
  uploadsError: string | null;
  isAdmin: boolean;
  onAuthExpired: () => void;
};

const StoreContext = createContext<StoreContextValue | null>(null);

export const StoreProvider: React.FC<{
  token: string;
  onAuthExpired: () => void;
  onSetToken: (token: string) => void;
  children: React.ReactNode;
}> = ({ token, onAuthExpired, onSetToken, children }) => {
  const [storeId, setStoreId] = useState<number | null>(null);

  const { stores, documents, isAdmin, refreshStores, fetchDocuments } = useAdminAndStores({
    token,
    onAuthExpired,
    storeId,
  });

  const { pendingUploads, handleFiles, uploadFile, lastError } = useUploads({
    storeId,
    token,
    fetchDocuments,
    onAuthExpired,
  });

  useEffect(() => {
    if (stores.length > 0) {
      const rawId = localStorage.getItem("rag_selected_store_id");
      const persistedId = rawId ? Number(rawId) : null;
      const exists = stores.find((s) => s.id === persistedId);

      if (exists) {
        setStoreId(persistedId);
      } else {
        if (persistedId) toast.info("Previous store no longer exists.");
        setStoreId(null);
      }
    } else {
      setStoreId(null);
    }
  }, [stores]);

  useEffect(() => {
    if (storeId) {
      localStorage.setItem("rag_selected_store_id", String(storeId));
    } else {
      localStorage.removeItem("rag_selected_store_id");
    }
  }, [storeId]);

  const value = useMemo(
    () => ({
      token,
      setToken: onSetToken,
      stores,
      storeId,
      setStoreId,
      documents,
      refreshStores,
      fetchDocuments,
      pendingUploads,
      handleFiles,
      uploadFile,
      uploadsError: lastError,
      isAdmin,
      onAuthExpired,
    }),
    [
      token,
      stores,
      onSetToken,
      storeId,
      documents,
      refreshStores,
      fetchDocuments,
      pendingUploads,
      handleFiles,
      uploadFile,
      isAdmin,
      onAuthExpired,
    ],
  );

  return <StoreContext.Provider value={value}>{children}</StoreContext.Provider>;
};

export const useStoreContext = () => {
  const ctx = useContext(StoreContext);
  if (!ctx) {
    throw new Error("useStoreContext must be used within a StoreProvider");
  }
  return ctx;
};
