export type PendingUpload = {
  id: string;
  name: string;
  status: "uploading" | "indexed" | "error";
  message?: string;
};

export type DocumentRow = {
  id: number;
  store_id: number;
  filename: string;
  display_name?: string | null;
  status: string;
  size_bytes: number;
  created_at: string;
  gcs_uri?: string | null;
};

export type StoreSummary = {
  id: number;
  display_name: string;
  fs_name: string;
};
