RAG Codebase Context 001 — Backend Core, Config, Security (≈1k LOC scope)

Scope (files covered)
- backend/app/main.py:1 — FastAPI app factory, middleware, routes, health/metrics
- backend/app/config.py:1 — Settings validation, prod safety, secret-file support
- backend/app/auth.py:1 — JWT auth, password hashing, optional Redis revocation
- backend/app/rate_limit.py:1 — Per-IP/per-user limiter (Redis or in-memory) + proxy support
- backend/app/middleware.py:1 — Correlation ID + structured request logging
- backend/app/metrics.py:1 — Prometheus counters/histograms, /metrics endpoint
- backend/app/telemetry.py:1 — JSON logging helpers and header-scrubbing utilities
- backend/app/security_gate.py:1 — Startup security checks (STRICT_MODE-gated)
- backend/app/db.py:1 — SQLAlchemy engine/session, health probe
- backend/app/file_types.py:1 — Upload MIME profiles and Gemini-supported types
- backend/app/costs.py:1 — Pricing, budgeting helpers, cost calculations
- backend/app/models.py:1 — Core ORM models (users/stores/documents/query logs/budgets/chat/app_settings)
- backend/app/routes/*:1 — Auth, chat, stores, documents, uploads, costs, settings, admin
- backend/app/services/*:1 — Gemini RAG client, ingestion, cleanup, storage, audit helpers
- backend/app/worker.py:1 — ARQ ingestion worker + watchdog cron

Architecture Overview
- Application: FastAPI app (`create_app`, version 0.2.1) with layered middleware (correlation IDs, rate limit, CSRF, metrics, security headers, JSON body limit) and API routers under `/api`.
- Configuration: Pydantic Settings with strong validators and production fail-fast checks; supports `{SECRET}_FILE` env indirection.
- Authentication: Stateless JWT (HS256) with `iss`/`aud` checks, `jti` for optional Redis-backed revocation, minimal PII (only `sub`).
- Observability: Prometheus metrics, correlation IDs, structured JSON logs with sensitive header scrubbing.
- Rate Limiting: Fixed-window limiter keyed by IP or authenticated user; Redis preferred with in-memory fallback.
- RAG/Ingress: Gemini File Search client with retries, ingestion worker/cron, and optional GCS archiving.

Application Lifecycle & Middleware
- Startup validation: Settings validate; `run_security_gate()` enforces toggles (STRICT_MODE). In prod with `REQUIRE_REDIS_IN_PRODUCTION=true` and `REDIS_URL` set, Redis ping must succeed or startup fails.
- CSRF defense: Mutating methods require `X-Requested-With: XMLHttpRequest`; `/health` and `/metrics` are exempt.
- CORS: Configurable origins/headers; defaults include Assistant UI; exposes streaming and request ID headers.
- Security headers: CSP (inline allowed only in dev/test; `connect-src` always includes `https://generativelanguage.googleapis.com` and dev origins in non-prod), HSTS (https), frame busting, X-Content-Type-Options, Referrer-Policy, Permissions-Policy, X-Download-Options, X-Permitted-Cross-Domain-Policies.
- JSON size limits: `MAX_JSON_MB` enforced for JSON content-types; request body streamed defensively with 413 on exceed.
- Global errors: Logs exception with request id/path/client; returns generic 500.
- Correlation IDs: Accepts `X-Request-ID` `[A-Za-z0-9-]{8,64}` or generates UUID; echoed on responses.

Security Posture
- Security gate: Blocks ALLOW_DEV_LOGIN outside dev/test; blocks GEMINI_MOCK_MODE outside dev/test; requires JWT secret and Gemini key (unless mock); warns if CSRF disabled or metadata filters enabled.
- JWT hardening: `JWT_SECRET` ≥32 chars; production exits if secret contains `dev_secret` or is weak; `iss`/`aud` enforced; short-lived tokens with `jti`.
- Password safety: Bcrypt 72-byte limit enforced; registration requires upper/lower/digit/special-char.
- Trusted proxies: `TRUSTED_PROXY_IPS` (CIDR) used to resolve client IP from `X-Forwarded-For`.

Configuration Model
- Environment: `ENVIRONMENT ∈ {development,test,staging,production}`; `GEMINI_MOCK_MODE` default true for dev/test.
- Secrets: `JWT_SECRET`, `GEMINI_API_KEY`, `{NAME}_FILE` overrides; JWT secret min length validated.
- Database: `DATABASE_URL` (SQLite allowed only outside prod); prod forbids default/blank DB passwords.
- Redis: `REDIS_URL` required in prod when `REQUIRE_REDIS_IN_PRODUCTION=true`; used for rate limit, JWT revocation, ingestion queue.
- CORS: `CORS_ORIGINS` JSON array or comma list; `CORS_ALLOW_CREDENTIALS` forbids `*` origins.
- Uploads: `UPLOAD_PROFILE ∈ {safe, office, all-supported, custom}` derives `ALLOWED_UPLOAD_MIMES`; any MIME outside Gemini-supported set is rejected.
- Pricing: `PRICE_PER_MTOK_INPUT/OUTPUT/INDEX` must be >0 in prod or when `PRICE_CHECK_STRICT=true`.
- Watchdog: `WATCHDOG_TTL_MINUTES`, `WATCHDOG_CRON_MINUTES` for stuck-job resets.
- Other limits: `MAX_STORES_PER_USER`, `MAX_JSON_MB`, rate-limit knobs (global and per-route), `METRICS_ALLOW_ALL`, `GEMINI_RETRY_ATTEMPTS`, `GEMINI_STREAM_RETRY_ATTEMPTS`, `MAX_CONCURRENT_STREAMS`, `GEMINI_INGESTION_TIMEOUT_S`.

Observability
- Prometheus: `http_requests_total{method,endpoint,status}`, `http_request_duration_seconds{method,endpoint}`, Gemini call counters/latency for upload/generate/generate_stream, `llm_tokens_total{model,type}` (query + indexing). `/metrics` restricted to localhost unless `METRICS_ALLOW_ALL=true`.
- Logging: JSON formatter adds timestamp/level/logger/request_id/user_id; request middleware logs request_complete/request_failed with duration and X-Request-ID and scrubs sensitive headers via `scrub_sensitive_headers()`.

Database & Health
- Engine: SQLite default with `check_same_thread=False`; non-SQLite gets pooling (pool_size 10, max_overflow 20, pre-ping, recycle 1800s).
- Models: Users, Stores (soft-delete, unique fs_name), Documents (soft-delete, status/op_name/gcs_uri), QueryLog, Budget, AdminAuditLog, ChatHistory, AppSetting.
- Health: Checks DB (SELECT 1), optional Redis ping when configured, and instantiates Gemini client (mock logs). Returns 503 if any check fails.

Rate Limiting Details
- Middleware keying: Anonymous `ip:<addr>`, authenticated `user:<sub>`; client IP resolved via `TRUSTED_PROXY_IPS`.
- Endpoint throttles: login `login:<email>`, chat `user:<id>:chat`, upload `user:<id>:upload`, admin `admin:<id>:action`, plus global middleware limit.
- Redis path: INCR per 60s bucket with `Retry-After`/`X-RateLimit-*`; degrades to in-memory on Redis errors; response headers always include limit/remaining.

Routes & Behavior
- Auth: Register/Login/Logout; logout revokes JTI in Redis if available; dev token route only when explicitly allowed outside prod.
- Chat: SSE streaming with keepalives and concurrency semaphore; enforces store ownership, model allowlist, rejects metadataFilter unless enabled, budget pre-check and post-cost check, logs token usage/costs, persists chat history.
- Uploads: MIME allow-list + magic checks for PDFs/Office, size cap, budget pre-check, secure temp files, optional GCS archive, enqueues ingestion to Redis/ARQ when available; in prod returns 503 if queue unavailable (inline ingestion only in non-prod).
- Stores/Documents: Create store via Gemini (SDK with REST fallback), soft-delete with background cleanup, restore requires admin.
- Costs: Monthly spend summary (requires pricing configured).
- Settings: Admin-only updates with validation on colors/icons/presets/lengths.
- Admin: User role/budget management, audit log listing, system summary, stuck-doc reset (sets PENDING/clears op_name), deletion audit.
- Metrics/Health: `/metrics` guarded as above; `/health` returns db/gemini/redis status.

Ingestion & Worker
- Ingestion jobs upload to Gemini with retries, poll LRO until done/error/timeout; mark Document status, log index costs (model `INDEX`), cleanup temp files.
- Worker (`backend/app/worker.py`) requires Redis to start; ARQ cron marks long-running RUNNING docs as ERROR and clears op_name.
- Deploy: Docker images for backend/worker/frontend; shared upload volume (`/tmp/rag_uploads`) mounted on backend + worker in compose; production compose (`docker-compose.prod.yml`) adds an nginx proxy and static frontend build; migrations run on backend entrypoint.
- Bootstrap: `backend/scripts/create_first_admin.py` seeds the first admin without enabling dev login.

Risks / Limitations
- Logging: When adding new logs that include headers or request bodies, contributors must call the scrub helpers to avoid leaking secrets.
- No Redis: JWT revocation and distributed rate limits degrade; ingestion queue unavailable (prod returns 503, non-prod runs inline).
- CSP: Allows inline scripts/styles in dev/test; production stricter but still permits data: for images/fonts.
- JSON guard applies to JSON content-types; mislabeled large bodies could bypass until framework limits.
- Metadata filters are rejected unless explicitly enabled; enabling requires careful validation.
