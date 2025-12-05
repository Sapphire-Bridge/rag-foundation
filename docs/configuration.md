# Configuration & Production Safety

This document is the canonical reference for environment variables and operational guardrails. The source of truth lives in `backend/app/config.py`, where every setting has a default value and validation logic. Whenever you change configuration code or `.env.example`, update this file alongside them.

## Required Environment

| Variable | Default | Purpose | Notes |
|----------|---------|---------|-------|
| `ENVIRONMENT` | `development` | Deployment mode (`development`, `test`, `staging`, `production`) | In production the validator enforces extra safety checks. |
| `JWT_SECRET` | Dev-only sentinel | HS256 signing key for JWTs | Must be 32+ chars and unique per deploy. App refuses to start with the dev default. |
| `GEMINI_API_KEY` | _(none)_ | API key for Google Gemini | Required unless running entirely in mock mode. |
| `DATABASE_URL` | `sqlite:///./rag.db` | SQLAlchemy connection string | Use PostgreSQL in production. The app does **not** read `DB_PASSWORD`; embed credentials in this URL. |
| `REDIS_URL` | _(empty)_ | Redis connection for rate limiting + JWT revocation | Required in production when `REQUIRE_REDIS_IN_PRODUCTION=true`. |

## Security Toggles

- `ALLOW_DEV_LOGIN` (default `false`): Enables the `/api/auth/token` dev shortcut. Opt-in locally; **must** be `false` outside dev/test.
- `REQUIRE_CSRF_HEADER` (default `true`): Enforces `X-Requested-With: XMLHttpRequest` on mutating requests. Tests disable this.
- `ALLOW_METADATA_FILTERS` (default `false`): When `true`, the chat endpoint accepts `metadataFilter` only for keys listed in `METADATA_FILTER_ALLOWED_KEYS`. Complex/nested filters are rejected.
- `METADATA_FILTER_ALLOWED_KEYS` (default empty): Comma-separated or JSON list of metadata keys the chat endpoint will forward when `ALLOW_METADATA_FILTERS=true`.
- `GEMINI_MOCK_MODE` (default `true`): Returns deterministic mock responses when `ENVIRONMENT` is `development` or `test`. Set to `false` to call the real Gemini API.
- `STRICT_MODE` (default `true`): When `false`, the security gate logs warnings instead of failing fast. Only disable during local development/testing.
- `MAX_CONCURRENT_STREAMS` (default `50`): Cap on simultaneous chat streams per process; returns 503 with structured SSE error when exceeded.

## Metadata Filters (advanced)

Metadata filters are **off by default** to avoid user-controlled query scopes in multi-tenant deployments. The chat endpoint will reject any `metadataFilter` payload unless both `ALLOW_METADATA_FILTERS=true` **and** `METADATA_FILTER_ALLOWED_KEYS` is populated. Only simple scalar or list values for allowlisted keys are forwarded; nested objects or complex boolean logic return `400` and are never sent upstream. Prefer server-side store scoping to isolate tenants; opt in to metadata filtering only when you control and validate the allowed keys.

### JWT & Auth

- `ACCESS_TOKEN_EXPIRE_MINUTES` (default `15`): Controls token TTL. Revocation entries in Redis share this TTL.
- `JWT_ISSUER` / `JWT_AUDIENCE`: Claims checked when decoding tokens.

### CORS & HTTP

- `CORS_ORIGINS`: List or JSON array of allowed origins (defaults to `["http://localhost:5173"]`).
- `CORS_ALLOW_CREDENTIALS`, `CORS_ALLOW_METHODS`, `CORS_ALLOW_HEADERS`: Passed directly to FastAPI’s `CORSMiddleware`. Defaults are explicit allowlists (`GET/POST/PUT/DELETE/OPTIONS` and `Authorization, Content-Type, X-Requested-With, X-Request-ID`)—keep these explicit in production instead of `["*"]`.
- `RATE_LIMIT_PER_MINUTE`: Requests per minute per IP/user. Redis keys `ratelimit:<key>:<bucket>` expire after ~120s, where `<key>` is typically `ip:<ip>` or `user:<id>`; feature-specific limits reuse the same mechanism (e.g., `user:<id>:chat`, `user:<id>:upload`, `login:<email>`).
- `TRUSTED_PROXY_IPS`: JSON array or comma-separated CIDR/IP list that is allowed to supply `X-Forwarded-For` for rate limiting. Leave empty to ignore proxy headers.
- `MAX_JSON_MB`: Rejects JSON requests larger than this many megabytes.
- `STREAM_KEEPALIVE_SECS`: Interval between SSE keepalive frames when streaming responses.

### Uploads & Storage

- `MAX_UPLOAD_MB`: Caps upload size (25 MB default).
- `UPLOAD_PROFILE`: Controls which MIME types are allowed. Options:
  - `safe` (default): PDF + plain/markdown/csv/tsv
  - `office`: `safe` plus Word/Excel/PowerPoint/OpenDocument
  - `all-supported`: every Gemini-supported application/text MIME
  - `custom`: supply your own allowlist via `ALLOWED_UPLOAD_MIMES`
- `ALLOWED_UPLOAD_MIMES`: Explicit MIME allowlist only used when `UPLOAD_PROFILE=custom`. The config validator normalizes and verifies this list is a subset of the Gemini-supported set at startup.
- `TMP_DIR`: Directory for staging uploads before sending to Gemini.
- `MAX_STORES_PER_USER`: Limits how many RAG stores each account can create.

### Gemini Settings

- `DEFAULT_MODEL`: Model sent to Gemini (`gemini-2.5-flash`).
- `GEMINI_HTTP_TIMEOUT_S`: Standard HTTP timeout for sync calls.
- `GEMINI_RETRY_ATTEMPTS`: Tenacity retries for non-streaming requests.
- `GEMINI_STREAM_RETRY_ATTEMPTS`: Chat streaming retry attempts inside the SSE handler.

### Cost Tracking

- `PRICE_PER_MTOK_INPUT`, `PRICE_PER_MTOK_OUTPUT`, `PRICE_PER_MTOK_INDEX`: USD per million tokens used when estimating cost in `/api/costs`.

### App Settings & Theming

- App-level branding and theme settings (name, icon, preset, primary/accent colors, favicon, welcome message, suggested prompts) are modeled by `AppSettings`/`AppSettingsUpdate` in `backend/app/schemas.py` and persisted in the `app_settings` table (`backend/app/models.py`).
- The API surface is:
  - `GET /api/settings`: returns merged defaults + overrides from the database.
  - `POST /api/settings` (admin-only): validates and updates individual keys.
- The frontend’s `ThemeContext` (`frontend/src/contexts/ThemeContext.tsx`) calls these endpoints, applies CSS variables according to `theme_preset`, and updates the favicon. When adding new branding knobs, keep these three places in sync.

### Testing & Developer Helpers

- `USE_GOOGLE_GENAI_STUB=1`: Optional override that forces the lightweight stub defined in `app/genai.py`, even when `GEMINI_MOCK_MODE=false`. Useful for CI or machines lacking the Google SDK.
- `PYTEST_DISABLE_PLUGIN_AUTOLOAD=1`: Recommended when running the backend test suite locally to avoid unrelated third-party pytest plugins pulling in heavy dependencies.
- `FAST_TESTS=1`: Limit backend test wrapper to a smoke subset and skip frontend test execution (build still runs).
- `SKIP_STRICT_LINT=1`: Skip `ruff` + `mypy` in the backend wrapper for faster inner loops. CI ignores this toggle.

## Production Invariants

The `Settings` model enforces these rules before the app starts when `ENVIRONMENT=production`:

1. `ALLOW_DEV_LOGIN` must be `false`.
2. `DATABASE_URL` cannot point to SQLite (`sqlite:` prefix).
3. `JWT_SECRET` must not equal the development placeholder.
4. The database password must not be blank or a known default (e.g., `localdev_password_change_in_production`, `postgres`, `password`).
5. When `REQUIRE_REDIS_IN_PRODUCTION=true`, `REDIS_URL` must be non-empty.

The `app/security_gate.py` module reruns these assertions at startup and fails fast with actionable error messages if any invariant is violated.

## Redis Semantics

- **Rate limiting**: Keys `ratelimit:<ip-or-user>:<minute-bucket>` increment via `INCR` and expire after 2× the 60-second window.
- **JWT revocation**: `/api/auth/logout` stores `revoked:{jti}` with a TTL equal to the token’s remaining lifetime. `get_current_user` denies any token whose JTI exists in Redis.

## File Changes Checklist

When modifying configuration-related behavior, update **all** of the following:

1. `backend/app/config.py`
2. `backend/.env.example`
3. `docs/configuration.md` _(this file)_
4. `README.md` (link back here if details are lengthy)
5. `CLAUDE.md` quick reference tables

Keeping these artifacts in sync prevents regressions and makes the security posture reviewable at a glance.
