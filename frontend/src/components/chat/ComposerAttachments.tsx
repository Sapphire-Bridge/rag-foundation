import React from "react";
import type { PendingUpload } from "../../types";
import type { UploadLimits } from "../../utils/uploadLimits";
import { formatAllowedTypes, getUploadLimits } from "../../utils/uploadLimits";

type ComposerAttachmentsProps = {
  uploads: PendingUpload[];
  onFileDrop: (files: FileList | null) => void;
  canUpload: boolean;
  uploadLimits?: UploadLimits;
};

export const ComposerAttachments: React.FC<ComposerAttachmentsProps> = ({ uploads, onFileDrop, canUpload, uploadLimits }) => {
  const resolvedUploadLimits = React.useMemo(() => uploadLimits ?? getUploadLimits(), [uploadLimits]);
  const allowedTypesLabel = React.useMemo(
    () => formatAllowedTypes(resolvedUploadLimits.allowedMimes),
    [resolvedUploadLimits.allowedMimes],
  );

  return (
    <div
      className="border border-dashed border-border rounded-md p-2 text-xs text-muted-foreground flex flex-col gap-2"
      onDragOver={(e) => e.preventDefault()}
      onDrop={(e) => {
        e.preventDefault();
        e.stopPropagation();
        onFileDrop(e.dataTransfer.files);
      }}
      title={
        !canUpload
          ? "Please log in and select a store to upload files"
          : `Max ${resolvedUploadLimits.maxUploadMb} MB per file. Allowed types: ${allowedTypesLabel}.`
      }
    >
      <p className="font-medium text-foreground">Attachments</p>
      <p>Drop files here or use the Attach button to upload to the selected store.</p>
      <p className="text-[11px] text-muted-foreground">
        Max {resolvedUploadLimits.maxUploadMb} MB per file. Allowed types: {allowedTypesLabel}.
      </p>
      <div className="space-y-1 max-h-24 overflow-y-auto">
        {uploads.length === 0 ? (
          <p className="text-muted-foreground">No uploads yet.</p>
        ) : (
          uploads.map((u) => (
            <div key={u.id} className="flex items-center justify-between">
              <span className="font-medium text-foreground">{u.name}</span>
              <span className={u.status === "error" ? "text-destructive" : ""}>
                {u.status === "uploading" && "Uploading…"}
                {u.status === "indexed" && "Indexed"}
                {u.status === "error" && (u.message || "Failed")}
              </span>
            </div>
          ))
        )}
      </div>
    </div>
  );
};
