RAG Codebase Context 002 — Backend Models, Routes, RAG/Costs/Ingestion (≈2k LOC scope)

Scope (files covered)
- backend/app/models.py: SQLAlchemy models with soft-delete helpers, status timestamps, gcs_uri.
- backend/app/schemas.py: Pydantic DTOs for stores, documents, uploads, chat, auth, costs, admin, settings.
- backend/app/config.py, backend/app/file_types.py: settings validation, upload MIME profiles, security gate toggles.
- backend/app/costs.py: pricing helpers, budget checks, token estimates.
- backend/app/routes/auth.py, stores.py, documents.py, uploads.py, chat.py, costs.py, settings.py, admin.py.
- backend/app/services/gemini_rag.py, ingestion.py, cleanup.py, storage.py, audit.py.
- backend/app/security/tenant.py: ownership guards for stores/documents.
- backend/app/worker.py: ARQ ingestion queue wiring and watchdog cron.

Domain Model & Persistence
- DocumentStatus enum (PENDING/RUNNING/DONE/ERROR); helpers set_status/touch_status update status_updated_at; before_insert listener initializes status timestamp.
- SoftDeleteMixin adds deleted_at/deleted_by with soft_delete/restore methods (used by Store and Document).
- User: email unique, hashed_password default "", flags (is_active/email_verified/is_admin), admin_notes, created_at; relations to stores, query_logs, budget (1:1), admin_logs.
- Store: user-owned container with display_name and unique fs_name, deleted_by, created_at; soft-deletable; relations to user/documents/query_logs/deleted_by_user.
- Document: store_id, filename, optional display_name, size_bytes, status/status_updated_at, op_name, gcs_uri (512 chars), deleted_by, created_at; soft-deletable.
- QueryLog: prompt/completion tokens, cost_usd Numeric(10,6), model, project_id, tags JSON, created_at; links to user/store.
- Budget: per-user monthly_limit_usd Numeric(10,2) with created_at.
- AdminAuditLog: admin_user_id optional, action, target_type/id, metadata_json, created_at.
- ChatHistory: session transcripts per user/store/session_id (64 chars) with role and content.
- AppSetting: key/value store with updated_at for branding/theme config.

Config & Security
- Settings enforce strict validation; STRICT_MODE true; GEMINI_MOCK_MODE true by default in dev/test; GEMINI_API_KEY required when not mock; pricing defaults input 0.30/output 2.50/index 0.0015.
- Upload profiles: safe (default) allows {application/pdf, text/plain, text/markdown, text/csv, text/tab-separated-values}; office adds doc/docx/xls/xlsx/pptx/odt; all-supported enables full Gemini list; custom validated against GEMINI_SUPPORTED_MIMES, normalized lowercase/sorted. MAX_UPLOAD_MB=25, TMP_DIR=/tmp/rag_uploads created 0700.
- Security gate at startup blocks unsafe production configs (no dev login, strong JWT secret, Redis required when configured, pricing >0, etc.); CSRF middleware requires X-Requested-With: XMLHttpRequest on mutating requests (except /health,/metrics).
- Rate limiting via middleware (per IP/user) plus endpoint check_rate_limit; specific caps for chat/upload/login and admin actions.
- Auth settings: ALLOW_DEV_LOGIN false by default; REQUIRE_CSRF_HEADER true; ALLOW_METADATA_FILTERS false; CORS settings validated; JWT issuer/audience enforced.

Schemas & Validation
- StoreCreate.display_name sanitized with html.escape, forbids script/iframe/javascript:/on* handlers/eval, strips non-printables, enforces non-empty 1–100 chars.
- DTOs: StoreOut; DocumentOut (includes optional gcs_uri); UploadResponse (op_id/document_id/estimated tokens+cost); OpStatus.
- QueryRequest schema supports storeIds/question/metadataFilter/model/sessionId, but /api/chat uses route-local ChatRequest (messages, tags, metadata_filter dict, assistant UI aliases).
- Auth DTOs: Register/Login/Dev token; RegisterIn.password length 6–72. CostsSummary aggregates tokens/costs/budgets. Admin DTOs (AdminUserOut/RoleUpdate, BudgetUpdate 0–99,999,999.99, AdminAuditEntry).
- AppSettings defaults for branding/theme/welcome prompts; AppSettingsUpdate validates allowed icons/themes, hex colors, length caps (favicon 200k, others 255).

Pricing & Budgets
- calc_query_cost/calc_index_cost clamp negatives to zero, use Decimal quantized to 1e-6 with prices from settings.
- estimate_tokens_from_bytes uses n_bytes//4 heuristic.
- mtd_spend totals QueryLog cost since month start; user_budget returns Decimal or None; would_exceed_budget compares spend+add_cost; acquire_budget_lock best-effort SELECT ... FOR UPDATE on Postgres (no-op on others, swallows errors).
- pricing_configured requires all prices >0; require_pricing_configured raises HTTP 500 when missing.

Auth
- /api/auth/register: enforces password <=72 bytes, requires upper+lower+digit+special char, rejects duplicate emails, hashes with bcrypt, creates active non-admin user.
- /api/auth/login: rate limited by email, validates password and active flag, returns JWT with sub=user_id and jti for revocation.
- /api/auth/token: dev-only (ALLOW_DEV_LOGIN true and not production), creates user if missing, returns JWT. /api/auth/logout revokes token in Redis when available. get_current_user enforces JWT validity + revocation; require_admin raises 403 when is_admin false.

Store & Document APIs
- GET /api/stores: lists owned, non-deleted stores ordered by id desc.
- POST /api/stores: enforces per-user cap (MAX_STORES_PER_USER), creates Gemini File Search store via GeminiRag.create_store; requires fs_name starting with corpora/ or fileSearchStores/; 503 on Gemini errors/timeouts, 409 on duplicate fs_name.
- DELETE /api/stores/{id}: require ownership; soft-deletes store and its documents (sets deleted_at/deleted_by), commits, enqueues remote cleanup, logs.
- POST /api/stores/{id}/restore: admin-only with rate limit; clears deleted flags on store/documents, commits, audit logged.
- GET /api/documents/store/{store_id}: require ownership, excludes soft-deleted, orders by created_at desc, returns DocumentOut (with gcs_uri).
- DELETE /api/documents/{document_id}: require ownership, soft delete, enqueue document cleanup, log.
- POST /api/documents/{document_id}/restore: admin-only with rate limit; restores document; audit + telemetry; 404 if missing.

Upload & Ingestion Flow
- POST /api/upload: depends on require_pricing_configured; returns 401 early if missing bearer header. Requires storeId and file; per-user upload rate limit.
- File validation: allowed_type uses settings.ALLOWED_UPLOAD_MIMES (profile-driven). Magic checks for application/pdf (%PDF- header + %%EOF tail) and ZIP-based office types (PK\x03\x04). Filenames sanitized (basename, spaces->_, invalid chars->_, strip leading dots, max 128).
- Streams to TMP_DIR with unique prefix and 0600 perms; enforces MAX_UPLOAD_MB during stream; cleans temp on errors.
- Budget precheck: estimate tokens from size -> calc_index_cost; if would_exceed_budget, deletes temp and returns 402.
- Inserts Document with status PENDING then commits; optional GCS archive upload when bucket set (URI truncated to 512). Logs telemetry.
- Ingestion enqueue: if Redis queue configured (has_ingestion_queue), enqueue index_document_job; on enqueue failure logs error. If no queue: production marks doc ERROR, removes temp, returns 503; non-prod runs run_ingestion_sync inline fallback.
- Response: op_id format doc-{id}, returns estimated_tokens and estimated_cost_usd. GET /api/upload/op-status/{op_id} validates format/ownership; DONE/ERROR short-circuit with optional error message. If op_name present, fetches rag.op_status to flip DONE/ERROR, commits; PENDING returned as RUNNING for UX.

Ingestion Worker & Cost Logging
- run_ingestion_sync locks document row, skips deleted/mismatched store, skips already running/done with op_name; sets status RUNNING.
- Uploads via rag.upload_file (retry decorator), stores op_name (truncated 255), waits for completion with jitter/backoff up to GEMINI_INGESTION_TIMEOUT_S; sets status DONE or ERROR on timeout/failure; commits.
- On DONE logs index cost (QueryLog with model="INDEX"), increments token_usage_total. Always removes temp file.
- index_document_job wraps for ARQ; has_ingestion_queue true when Redis URL valid; enqueue_ingestion_job submits to ARQ. Cron reset_stuck_documents marks RUNNING docs older than WATCHDOG_TTL_MINUTES as ERROR and clears op_name; scheduled per WATCHDOG_CRON_MINUTES.

Chat Streaming (RAG)
- POST /api/chat streams SSE. Accepts ChatRequest (question/messages/session_id/thread_id/store_ids/project_id/tags/metadata_filter/model with aliases). store_ids required and ownership enforced.
- Builds history: loads up to 50 ChatHistory rows per user/session/store, reverses to chronological; builds transcript (last 24 turns, max 6000 chars) and last user text. Derives question from payload/latest message/history; coerces to str; rejects empty or >32k chars.
- Rate limited per user (CHAT_RATE_LIMIT_PER_MINUTE). project_id must be int if provided. Tags sanitized to <=5 entries (stringified scalar values, keys trimmed). metadata_filter only allowed when ALLOW_METADATA_FILTERS true **and** key is allowlisted in settings.METADATA_FILTER_ALLOWED_KEYS with a scalar/list value; otherwise 400. Model defaults to settings.DEFAULT_MODEL and must be in allowed set {gemini-2.5-flash, gemini-2.5-pro, gemini-3.0-pro-thinking, gemini-2.0-flash, gemini-2.0-pro, gemini-1.5-pro, gemini-1.5-flash}.
- Budget precheck: if mtd_spend >= budget -> 402. Persists user message to ChatHistory before streaming.
- Streaming: semaphore limits concurrent streams (timeout 2s -> start + text-start + error + DONE). Runs rag.ask_stream in background thread pushing chunks into queue; yields SSE events start, text-start, text-delta for chunks, text-end, source-document (citations), finish, [DONE]; keepalives based on STREAM_KEEPALIVE_SECS.
- Retry handling: wraps stream loop with retries on RETRYABLE_EXCEPTIONS up to GEMINI_STREAM_RETRY_ATTEMPTS (exponential backoff). On exhaustion yields upstream_unavailable error; unexpected errors yield sanitized unexpected_error; disconnects stop stream.
- Usage logging: extracts usage_metadata prompt/candidates token counts when present; otherwise approximates tokens (len//4) and logs warning. calc_query_cost used; Prom metrics incremented. acquire_budget_lock before would_exceed_budget; logs QueryLog (store_id first requested, project_id, tags). If over budget post-cost, sends finish then budget_exceeded error then DONE. Persists assistant message when text exists.

Cost Reporting
- GET /api/costs/summary: requires pricing configured; aggregates monthly query costs (excluding model="INDEX") and indexing costs separately; returns totals, token counts, budget, remaining (non-negative), month as YYYY-MM.

Settings & Branding
- GET /api/settings merges defaults with AppSetting rows.
- POST /api/settings: admin-only with rate limit; validates keys, hex colors, allowed icons/themes, length caps (default 255, favicon 200k); trims/normalizes values; upserts AppSetting rows; audit logged.

Admin & Watchdog
- Admin routes require require_admin + rate limiting; record_admin_action writes AdminAuditLog and structured telemetry.
- /api/admin/users lists recent users (limit 1–500). /api/admin/users/{id}/role updates is_admin/admin_notes; prevents self-demotion of admins.
- /api/admin/budgets/{user_id} upserts Budget monthly_limit_usd (Decimal). /api/admin/audit lists latest AdminAuditLog entries (limit 1–200).
- /api/admin/system/summary returns counts for users/stores/documents.
- /api/admin/watchdog/reset-stuck resets RUNNING docs older than ttl_minutes (default 30) optionally filtered by user_id; clears op_name; returns reset_count.
- /api/admin/audit/deletions lists soft-deleted stores with deletion actor info.

GeminiRag Service
- Client wrapper over genai.Client with retry decorator (_gemini_retry) for non-streaming calls; rate-limit-aware backoff logging.
- create_store uses SDK; on timeout with API key falls back to REST fileSearchStores; validates returned name via caller.
- upload_file wraps file_search_stores.upload_to_file_search_store with optional display_name/custom_metadata/chunking_config; records Prom metrics; logs errors.
- delete_store treats 404 as success, falls back to REST delete when SDK delete missing; delete_document_from_store logs and raises NotImplemented.
- op_status accepts name or dict, retries with dict on TypeError, normalizes to {name, done, metadata, error}.
- ask builds FileSearch tool from store names + metadata_filter and calls generate_content with retry; ask_stream streams without retries (caller handles).
- extract_citations_from_response parses grounding_metadata.grounding_chunks for retrieved_context/web entries; robust to missing fields; new_stream_ids returns pair of UUID strings.
- MockGeminiRag used when GEMINI_MOCK_MODE and environment in {development,test} via get_rag_client; returns mock store/op/status and canned streamed text.

Cleanup & Tenant Enforcement
- Tenant guards (security/tenant.py) enforce store/document ownership and soft-delete state; 404 with telemetry on mismatch.
- Cleanup service schedules background deletion of Gemini stores/documents after soft delete; logs failures. cleanup_stale_stores janitor removes soft-deleted stores older than grace_hours when no active documents.
- storage.upload_to_gcs_archive uploads temp file to configured GCS bucket (requires google-cloud-storage), returns gs:// URI.
