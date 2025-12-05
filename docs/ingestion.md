# Ingestion Pipeline

Uploads now flow through a durable Redis + ARQ queue to survive API restarts and to make retry semantics explicit:

1. **HTTP upload** (`/api/upload`) validates tenant, MIME, and size, persists the document row (`PENDING`), and enqueues the job on the `ingestion` queue. In non-production environments without Redis, the job runs inline as a fallback for tests.
2. **Redis queue** stores the job payload (`store_id`, `document_id`, `local_path`) durably.
3. **Worker** (`arq app.worker.WorkerSettings`) pulls from the queue, marks the document `RUNNING`, calls Gemini upload with retries, polls once for op status, then transitions to `DONE` or `ERROR`.
4. **Gemini** hosts the uploaded content; op_name is persisted on the document for status reads.
5. **Database** is updated for status/op_name; index token usage is logged to `query_logs` when the job finishes.
6. **Cleanup**: temp files are removed by the worker once the job completes (success or failure).

If a job fails (network/API issues), ARQ retries with backoff. Manual re-enqueue of a document is idempotent: if status is `DONE` the job exits early.

## Handling Stuck Documents

In rare cases (e.g., extended provider outage or misconfigured worker), documents can remain `RUNNING` longer than intended. There are two supported recovery paths:

- **Admin watchdog endpoint**  
  - `POST /api/admin/watchdog/reset-stuck` (admin-only) resets `RUNNING` documents older than a configurable TTL back to `PENDING` so they can be retried by the ingestion worker.

- **Operational script**  
  - `backend/scripts/mark_stuck_documents_error.py` can be run out of band to mark long-lived `RUNNING` documents as `ERROR` after a threshold in minutes (see usage in README). This is useful when you want to stop showing “in progress” in the UI while investigating underlying issues.

Prefer the watchdog endpoint for routine operations; reserve the script for operator-driven remediation during incidents.
