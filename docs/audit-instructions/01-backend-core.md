<!-- INSTRUCTION-01-backend-core-config-security.md -->

# Instruction Set 01 — Backend Core, Config, Security & Performance Shell Audit

## Scope

Files / contexts:

- `backend/app/main.py`
- `backend/app/config.py`
- `backend/app/security_gate.py`
- `backend/app/middleware.py`
- `backend/app/rate_limit.py`
- `backend/app/metrics.py`
- `backend/app/telemetry.py`
- `backend/app/db.py`
- Context 001 — Backend Core, Config, Security

## Objective

Verify that the backend “shell” (app factory, config, middleware, rate limiting, logging, metrics) is:

- Secure by default in production.
- Logically coherent and predictable.
- Observable and debuggable.
- Resource-aware (basic performance/capacity).
- Free of “vibe” patterns that are not consciously justified.

---

## 1. Configuration & Security Gate

1. Map environment variables → `Settings` fields → security gate checks:
   - `ENVIRONMENT`, `JWT_SECRET`, `GEMINI_API_KEY`, `DATABASE_URL`, `REDIS_URL`,
     `ALLOW_DEV_LOGIN`, `REQUIRE_REDIS_IN_PRODUCTION`, CORS/CSP toggles, upload/profile settings, pricing flags.
2. For `ENVIRONMENT=production`, verify that startup fails fast if:
   - `JWT_SECRET` is weak or default.
   - `DATABASE_URL` uses SQLite.
   - `ALLOW_DEV_LOGIN` is true.
   - `REDIS_URL` is missing when required.
3. Identify magic defaults (timeouts, limits, profiles). For each:
   - Is it domain logic (document and keep)?
   - Or an arbitrary “vibe” number that should be configurable or documented?

Record any configuration that can silently degrade security or correctness.

---

## 2. App Factory & Middleware Order

1. Enumerate middleware in the exact order they execute:
   - Correlation ID, rate limiting, CORS, metrics, security headers, JSON size limit, error handlers, etc.
2. Check that:
   - Correlation ID and rate limiting run before business routes.
   - CSRF header checks cover all mutating endpoints, with only intended exceptions (e.g. `/health`, `/metrics`).
   - JSON body size limits cannot be trivially bypassed via Content-Type tricks.
   - Security headers (CSP, HSTS where applicable, X-Frame-Options, X-Content-Type-Options, etc.) are applied consistently.
3. If order needs justification (e.g., metrics vs rate limiting), add a short code comment or doc note.

---

## 3. Rate Limiting & Redis Fallback

1. Review `backend/app/rate_limit.py`:
   - Key strategy: unauthenticated (IP key), authenticated (user key).
   - Algorithm: fixed window or sliding window; how bucket keys are formed.
2. For Redis mode:
   - Confirm per-key increment and expiry; no unbounded key growth.
   - Check how errors (`ConnectionError`, timeouts, decoding failures) are handled.
3. For fallback mode (no Redis):
   - Inspect in-memory structures (maps/deques); ensure they have bounded size.
   - Verify behavior when memory limits are approached (implicit or explicit).
4. For broad `except` blocks:
   - Confirm they are *intentional guardrails* to prevent rate-limit/Redis issues from breaking requests.
   - Add low-severity logging (`debug`/`warning`) where useful for production debugging.

---

## 4. Telemetry & Metrics

1. Logging (`backend/app/telemetry.py`, `middleware.py`):
   - Confirm every request is tagged with a correlation ID in logs.
   - Verify header scrubbing: Authorization, cookies, API keys, and any other sensitive headers are never logged raw.
   - Ensure error logs include stack traces and enough context (endpoint, user id where allowed, correlation ID) without leaking secrets.
2. Metrics (`backend/app/metrics.py`):
   - Verify:
     - HTTP counters & histograms labeled appropriately (method, endpoint, status).
     - Gemini metrics (upload/generate/stream) with attempts and latency.
   - Check for potential cardinality explosions (unbounded labels like arbitrary user ids or filenames).

---

## 5. DB Session Management & Health

1. `backend/app/db.py`:
   - Validate `get_db` pattern: create session → yield → commit/rollback → close. Ensure no uncommitted dangling sessions.
2. `/health` endpoint:
   - Confirm it probes database connectivity and Gemini client initialization (or equivalent), and returns 503 when either is unhealthy.
   - Ensure `/health` does not reveal sensitive implementation details in its body.

---

## 6. Performance & Capacity (Core Shell)

1. Map runtime resource limits:
   - Gunicorn/Uvicorn worker count and worker type.
   - DB connection pool size and overflow.
   - Redis connections (if configured).
2. Check consistency:
   - Worker count vs DB pool size (avoid over-commit that causes thrash).
   - Rate-limit configuration vs expected traffic (e.g., 20–50 users).
3. Identify any “best-effort” performance choices (e.g., conservative timeouts). For each:
   - Note the rationale.
   - Document in `DEPLOYMENT.md` or comments if not already.

This is not a micro-optimization pass; you are checking that obvious capacity knobs are deliberate and coherent.

---

Scan this scope for “vibe coding”:

- Broad, silent `except Exception`.
- Magic constants without comment (timeouts, limits, retry counts).
   - Bug / unclear logic (mark for fix).
2. Where kept as a guardrail, add a one-line comment like:
   - `# INTENTIONAL_GUARDRAIL: do not fail request on metrics/logging errors.`

---
## 8. Output

Produce a short report covering:

- Are core config and security invariants enforced at startup?
- Is middleware order correct and intentional?
- Are rate limiting and Redis fallback deliberate and observable?
- Are logs/metrics safe and useful?
- List of:
  - Confirmed intentional guardrails.
  - Items to fix now.
  - Items to track as future improvements (with suggested locations for documentation).
