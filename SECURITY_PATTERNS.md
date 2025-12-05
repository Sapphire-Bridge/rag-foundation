# Security Architecture & Coding Patterns

This document captures the **concrete patterns** every contributor should follow to keep the system secure and consistent.

It complements `SECURITY.md` (policy/operations) with **developer-facing rules**.

---

## 1. Authentication & Authorization

- **JWTs**
  - Always use `create_access_token`/`decode_token` from `backend/app/auth.py`.
  - Do not hand-roll JWT parsing or verification.
  - Never log raw JWTs or token fragments.

- **Current user**
  - Use `get_current_user` as a dependency in routes that require authentication.
  - Do not accept `user_id` directly from the client for authorization decisions.

- **Admin access**
  - Any route that performs an **admin-only operation** must:
    - Depend on `require_admin` (`user: User = Depends(require_admin)`).
    - Emit an admin audit record via `record_admin_action` (in `backend/app/services/audit.py`) for mutating actions.
    - Emit a structured telemetry event via `log_json` (e.g., `admin_set_user_role`, `admin_set_budget`, `admin_update_settings` for `/api/settings` POST).

- **Dev login**
  - `/auth/token` is for non-production use only and is controlled by `ALLOW_DEV_LOGIN` and `ENVIRONMENT`.
  - Never enable `ALLOW_DEV_LOGIN` in production; this is enforced by config validation and the security gate.

---

## 2. CSRF, CORS, and Client Headers

- **CSRF protection**
  - CSRF mitigation relies on:
    - Bearer tokens in `Authorization` headers (no auth cookies),
    - `X-Requested-With: XMLHttpRequest` header on mutating requests,
    - Middleware in `backend/app/main.py` that enforces the header for `POST/PUT/PATCH/DELETE`.
  - In **production**, `REQUIRE_CSRF_HEADER` must be `true`. This is enforced by `Settings.validate_production_safety`.

- **Frontend requirements**
  - All `fetch` calls that change state **must** include:
    - `Authorization: Bearer <token>` (when authenticated),
    - `X-Requested-With: "XMLHttpRequest"`.
  - Login, registration, uploads, chat, and admin actions are already wired this way; copy those patterns for new features.

- **CORS**
  - Origins are configured via `CORS_ORIGINS` in `Settings`.
  - Do not add `"*"` in production; enumerate the real frontend origins instead.

---

## 3. Multi‑Tenant Access Control

- **Tenant boundary**
  - The primary tenant boundary is `Store.user_id`.
  - `Document` and `ChatHistory` records are always associated to a `Store` and/or `User`.

- **Helpers (mandatory for sensitive data)**
  - Use these helpers from `backend/app/security/tenant.py`:
    - `require_store_owned_by_user(db, store_id, user_id)`
    - `require_stores_owned_by_user(db, store_ids, user_id)`
    - `require_document_owned_by_user(db, document_id, user_id)`
  - Any route that reads or mutates `Store`, `Document`, or `ChatHistory` data for a non-admin must use one of these.

- **Admin overrides**
  - Admin routes that bypass tenant checks (e.g., restore a store for any user) must:
    - Be protected by `require_admin`.
    - Emit `record_admin_action` and a `log_json` event describing the action.

---

## 4. Rate Limiting & Abuse Protection

- **Global middleware**
  - `rate_limit_middleware` in `backend/app/rate_limit.py` applies per-IP or per-user limits (`RATE_LIMIT_PER_MINUTE`).
  - Do not bypass this middleware when adding new ASGI apps or routers.

- **Per-feature limits**
  - Chat: `CHAT_RATE_LIMIT_PER_MINUTE` via `check_rate_limit(f"user:{user.id}:chat", ...)`.
  - Upload: `UPLOAD_RATE_LIMIT_PER_MINUTE` via `check_rate_limit(f"user:{user.id}:upload", ...)`.
  - Login: `LOGIN_RATE_LIMIT_PER_MINUTE` via `check_rate_limit(f"login:{email}", ...)` in `/auth/login`.
  - When adding new high-risk operations (e.g., password reset, invite flows), add a **feature-specific rate key** with `check_rate_limit`.

---

## 5. Database & ORM Usage

- **ORM-first policy**
  - Use SQLAlchemy ORM models from `backend/app/models.py` for queries.
  - Avoid raw SQL unless absolutely necessary; when needed:
    - Use `sqlalchemy.text` with bound parameters (never format user input into SQL strings).

- **Production safety**
  - In production:
    - `DATABASE_URL` must not start with `sqlite:` (enforced).
    - DB password must not be a default/weak value (enforced).
  - SQLite is acceptable only for development and tests.

- **Budget locking**
  - Use `acquire_budget_lock(db, user_id)` before mutating cost/budget calculations that rely on `QueryLog`/`Budget`.

---

## 6. Logging, Telemetry, and Secrets

- **Structured logging**
  - Use `log_json(level, event_name, **fields)` for application events.
  - Do not print or use ad-hoc `logging.info` with unstructured strings for user or tenant actions; prefer structured logs.

- **Context**
  - Request and user IDs are attached via:
    - `CorrelationIdMiddleware` (request ID),
    - `bind_user_context` in `auth.get_current_user`.
  - Do not manually attach `request_id`/`user_id` fields; rely on context vars where possible.

- **PII**
  - Do not log emails, passwords, or raw tokens.
  - If you must log something derived from an email, use `email_hash` from `backend/app/telemetry.py`.

- **Secrets & external calls**
  - Never log:
    - `GEMINI_API_KEY`,
    - Other API keys,
    - Full request URLs that contain secrets as query parameters.
  - In particular:
    - When catching HTTP client errors (`httpx.HTTPError`, `errors.APIError`), log only:
      - `error_type`,
      - Status code / error code,
      - High-level context (store/document IDs),
      - Never `str(exc)` if it might embed URLs with secrets.
  - `GeminiRag.delete_store` already treats REST fallback as **best-effort** and does not re-raise HTTP errors; follow this pattern for future fallbacks.

---

## 7. File Upload & Content Security

- **Allowlist**
  - All uploads must be checked via `allowed_type(file)` against `settings.ALLOWED_UPLOAD_MIMES`, which is validated against `GEMINI_SUPPORTED_MIMES`.
  - Do not accept arbitrary content types for ingestion.

- **Path handling**
  - Always use `sanitize_name` and `TMP_DIR` from config.
  - Never trust client-provided paths or filenames for filesystem operations.

- **Size and magic checks**
  - Enforce maximum size via streaming checks (as in `backend/app/routes/uploads.py`).
  - For binary/document formats, call `validate_file_magic` after writing to disk.

---

## 8. Metrics & Health Endpoints

- **Metrics**
  - `/metrics` is intended for internal Prometheus scraping.
  - The handler in `backend/app/main.py` currently restricts access to localhost; if you relax this, do so only behind network ACLs or auth.

- **Health**
  - `/health` should remain a minimal health indicator and not expose secrets or detailed configuration.
  - If you add new checks, keep responses high level (up/down) rather than dumping diagnostics.

---

## 9. When Adding New Features

Before merging new code, check:

1. **Auth & tenant isolation**
   - Does this route use `get_current_user` or `require_admin` where appropriate?
   - If it touches stores/documents, is a `require_*_owned_by_user` helper used?

2. **Input validation**
   - Are all request bodies modeled with Pydantic in `schemas.py`?
   - Are lengths, formats, and enums constrained?

3. **Rate limiting**
   - For login-like or resource-intensive actions, is `check_rate_limit` used?

4. **Logging**
   - Are important actions logged via `log_json` with non-PII identifiers?
   - Are exceptions logged without leaking secrets?

5. **Production safety**
   - Does the change respect `ENVIRONMENT`, `STRICT_MODE`, and the invariants enforced by `Settings.validate_production_safety` and `run_security_gate()`?

Following these patterns keeps the codebase predictable, auditable, and safe as it grows.
