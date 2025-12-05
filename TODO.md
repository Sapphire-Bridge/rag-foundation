## Verify ingestion rollback cleanup

- Introduce a controlled failure in `run_ingestion_sync` after the upload step to force the exception path.
- Run an ingestion attempt and confirm logs include `ingest_upload_rollback_deleted_remote`.
- Verify the Gemini file is deleted (or logs a warning if delete fails).
- Check the document ends in `ERROR` status and the temp file is removed.
