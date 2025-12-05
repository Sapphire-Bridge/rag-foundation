import { useCallback, useEffect, useState } from "react";
import type { DocumentRow, StoreSummary } from "../types";

type UseAdminAndStoresArgs = {
  token: string;
  storeId: number | null;
  onAuthExpired: () => void;
};

export const useAdminAndStores = ({ token, storeId, onAuthExpired }: UseAdminAndStoresArgs) => {
  const [stores, setStores] = useState<StoreSummary[]>([]);
  const [documents, setDocuments] = useState<DocumentRow[]>([]);
  const [isAdmin, setIsAdmin] = useState(false);

  const refreshStores = useCallback(async () => {
    if (!token) {
      setStores([]);
      return;
    }
    const res = await fetch("/api/stores", { headers: { Authorization: `Bearer ${token}` } });
    if (res.status === 401 || res.status === 403) {
      onAuthExpired();
      return;
    }
    if (res.ok) {
      const data = await res.json();
      setStores(data);
    } else {
      console.error("Failed to fetch stores", res.status, res.statusText);
    }
  }, [token, onAuthExpired]);

  const checkAdmin = useCallback(async () => {
    if (!token) {
      setIsAdmin(false);
      return;
    }
    try {
      const res = await fetch("/api/admin/system/summary", {
        headers: { Authorization: `Bearer ${token}`, "X-Requested-With": "XMLHttpRequest" },
      });
      setIsAdmin(res.ok);
    } catch (err) {
      console.warn("Failed to check admin status", err);
      setIsAdmin(false);
    }
  }, [token]);

  const fetchDocuments = useCallback(
    async (sid?: number | null) => {
      const targetStoreId = sid ?? storeId;
      if (!targetStoreId || !token) {
        setDocuments([]);
        return;
      }
      const res = await fetch(`/api/documents/store/${targetStoreId}`, {
        headers: { Authorization: `Bearer ${token}` },
      });
      if (res.status === 401 || res.status === 403) {
        onAuthExpired();
        return;
      }
      if (res.ok) {
        const data = await res.json();
        setDocuments(data);
      } else {
        setDocuments([]);
      }
    },
    [storeId, token, onAuthExpired],
  );

  useEffect(() => {
    if (token) {
      refreshStores();
    } else {
      setStores([]);
      setDocuments([]);
    }
  }, [token, refreshStores]);

  useEffect(() => {
    if (token) {
      checkAdmin();
    } else {
      setIsAdmin(false);
    }
  }, [token, checkAdmin]);

  useEffect(() => {
    if (token) {
      fetchDocuments();
    } else {
      setDocuments([]);
    }
  }, [storeId, token, fetchDocuments]);

  return {
    stores,
    documents,
    isAdmin,
    refreshStores,
    fetchDocuments,
  };
};
