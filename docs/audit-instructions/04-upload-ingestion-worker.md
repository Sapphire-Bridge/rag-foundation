<!-- INSTRUCTION-04-upload-ingestion-worker.md -->

# Instruction Set 04 — Upload, Validation, Ingestion & Worker Audit

## Scope

- `backend/app/routes/uploads.py`
- Ingestion / worker code, e.g.:
  - `backend/app/worker.py` (ARQ WorkerSettings or equivalent)
  - `backend/app/services/ingestion.py` (or whichever module performs Gemini indexing)
  - `backend/app/services/cleanup.py` if it participates in ingestion
- Upload-related settings in `backend/app/config.py`:
  - `UPLOAD_PROFILE`, `ALLOWED_UPLOAD_MIMES`, `MAX_UPLOAD_MB`, `TMP_DIR`
- Tests: `backend/tests/test_upload_validation.py`, `backend/tests/test_soft_delete.py`
- Context 002 (and any worker details in Context 001/004)

## Objective

Ensure the entire path:

> client upload → temp file → validation → background ingestion → Gemini → status tracking

is:

- Secure (no path traversal, MIME spoofing, unbounded size).
- Resource-safe (temp files, retries, idempotency).
- Budget-aware.
- Correctly integrated with worker configuration and long-running jobs.
- Free of unexplained “best-effort” hacks.

---

## 1. Upload Endpoint Flow

In `routes/uploads.py`:

1. Trace the control flow for `POST /api/upload`:
   - Auth and store ownership checks.
   - Store status (deleted / not found) handling.
   - Parsing of `multipart/form-data` (`storeId`, `displayName`, `file`).
2. File handling:
   - Confirm sanitized filename:
     - Strips path components.
     - Filters allowed characters.
     - Truncates length.
   - Destination path:
     - Under `TMP_DIR` or a subdirectory.
     - Created with secure permissions (`0o600` or equivalent).
3. Ensure no possibility of:
   - Directory traversal.
   - Overwriting existing files without explicit intention.

---

## 2. Size & MIME Validation

1. Size enforcement:
   - Inspect streaming loop and size counter.
   - Confirm enforced against `MAX_UPLOAD_MB`.
   - Verify behavior on exceeding limit: 413 with clear message; no partial artifact left in inconsistent state.
2. MIME policy:
   - Map `UPLOAD_PROFILE` values and their semantics (`safe`, `office`, `all-supported`, `custom`).
   - Confirm:
     - Declared content type is checked.
     - File signature/magic bytes are validated for PDFs and other binary formats.
   - Ensure unsupported or mismatched MIME results in explicit 4xx, not silent acceptance.

---

## 3. Budget Pre-Check

1. Identify where indexing cost is estimated (bytes → tokens → USD).
2. Confirm:
   - Budget check happens *before* enqueuing heavy ingestion work.
   - Over-budget requests result in 402 with clear client-visible reason.
3. Evaluate the heuristic’s safety margin:
   - Is it conservative enough to avoid “accidental overspend”?

---

## 4. Background Ingestion Worker Implementation

Inspect the worker code (e.g. `backend/app/worker.py`, `backend/app/services/ingestion.py`):

1. Worker configuration:
   - Queue names, concurrency, retry policies.
   - Backoff strategy, max attempts, dead-letter behavior (if any).
2. Task payload & idempotency:
   - How ingestion tasks are identified (document ID, operation ID, store ID).
   - What happens if:
     - The same task is enqueued twice.
     - A worker crashes mid-operation and picks up the job again.
   - Confirm repeated processing does not create duplicate records or corrupt statuses.
3. Integration with DB model:
   - How document status transitions PENDING → RUNNING → DONE/ERROR are performed.
   - How Gemini operation names/IDs are stored and used for subsequent polling.

---

## 5. File Cleanup & Error Handling

1. Temp file cleanup:
   - Identify all code paths where temp files can be created.
   - Verify they are deleted in:
     - Success path (after ingestion).
     - All error paths (exceptions, timeouts, budget failures, validation failures as needed).
2. Error behavior:
   - Confirm ingestion failures:
     - Update document status to ERROR with meaningful metadata (e.g., error message).
     - Log failure with correlation id and document/store identifiers.
   - Check for any broad `except` that silently hides ingestion errors without logging.

---

## 6. Status Polling & Watchdog

1. `GET /api/upload/op-status/{op_id}`:
   - Confirm it:
     - Maps op_id to a document row.
     - Optionally refreshes external operation status from Gemini.
     - Updates local status accordingly.
2. Watchdog (admin-only):
   - Inspect logic resetting “stuck” RUNNING docs to PENDING.
   - Check:
     - Age threshold (e.g., > 30 minutes) and reasoning.
     - Admin-only guard and audit logging.
     - Idempotence and safeguards (no endless flip-flopping).

---

## 7. Performance & Throughput Considerations

1. Identify ingestion-related capacity parameters:
   - Worker concurrency and queue sizes.
   - Any limits on in-flight indexing operations.
2. Evaluate:
   - Whether ingestion concurrency is aligned with expected document size and user count.
   - Whether there is any back-pressure mechanism to avoid overloading Gemini or the DB.

This is a high-level check; you’re not micro-benchmarking, just verifying the design is not obviously unsafe.

---

## 8. Vibe Artifact Pass (Uploads & Worker)

Search for:

- Silent `except` in worker code, temp-file cleanup, or polling.
- Magic retries, backoff intervals, or age thresholds with no comment.
- Commented-out alternative ingestion paths.

For each:

- Decide if it is an intentional resilience mechanism (document it) or a risky hack (mark for fix).
- Add short comments like:
  - `# INTENTIONAL_GUARDRAIL: avoid failing user request if ingestion cleanup logging fails.`

---

## 9. Output

Summarize:

- Upload→ingestion→status flow (one concise diagram).
- Security guarantees (path traversal, MIME spoofing, size limits).
- Worker robustness (retries, idempotency, stuck-job handling).
- List of improvements required (if any) and where to implement them.
