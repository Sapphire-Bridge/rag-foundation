<!-- INSTRUCTION-08-observability-openapi-ci-ops.md -->

# Instruction Set 08 — Observability, OpenAPI, CI & Deployment Audit

## Scope

- Metrics & health:
  - `backend/app/metrics.py`
  - `backend/app/main.py` (`/metrics`, `/health`)
- Logging:
  - `backend/app/telemetry.py`
  - `backend/app/middleware.py`
- OpenAPI:
  - `backend/scripts/export_openapi.py`
  - `backend/openapi.yaml`
- CI & security:
  - `.github/workflows/*.yml`
  - `scripts/test-backend.sh`, `scripts/test-frontend.sh`, `scripts/security-scan.sh` (if present)
- Deployment:
  - `docker-compose.yml`
  - `backend/Dockerfile`, `frontend/Dockerfile`
  - `.env.example`, `DEPLOYMENT.md`, `docs/pricing.md`, `docs/configuration.md`
- Context 001 & 004

## Objective

Ensure that:

- Observability (logs, metrics, health) is comprehensive and safe.
- The OpenAPI contract is maintained and reliable.
- CI pipelines enforce quality and security.
- Deployment guidance and defaults align with actual runtime behavior.

---

## 1. Health & Metrics

1. `/health`:
   - Confirm which checks it performs (DB, Gemini, other dependencies).
   - Verify:
     - It returns non-200 for meaningful failures (not just “app up”).
     - It does not leak internals in response body.
2. `/metrics`:
   - Inspect metric names and labels:
     - HTTP request metrics, Gemini metrics, any custom business metrics.
   - Check for:
     - Avoidable high-cardinality labels (user ids, document titles, filenames).

---

## 2. Logging & Telemetry

1. Log structure:
   - Confirm logs are structured JSON (or consistent key-value).
   - Ensure presence of:
     - Timestamp, level, message, correlation id, key context fields.
2. Scrubbing:
   - Verify that request headers and body fields that may contain secrets (Authorization, cookies, API keys) are scrubbed or omitted.
3. Error & warning use:
   - Check that severe issues (auth failures, ingestion errors, provider failures) are logged at appropriate levels, with enough, but not excessive, context.

---

## 3. OpenAPI Export & Drift Prevention

1. `export_openapi.py`:
   - Validate how it builds the spec (import app, use FastAPI’s OpenAPI generator, etc.).
   - Note any dependencies (e.g. requiring `GEMINI_API_KEY` to run).
2. OpenAPI file:
   - Spot-check several endpoints against code to confirm correctness.
   - Confirm any strong invariants (e.g. cost response structure, chat request schema) are accurately captured.
3. CI:
   - Check if CI compares generated spec to committed `openapi.yaml` and fails on drift.
   - Ensure the workflow is stable (e.g., doesn’t require external services in CI).

---

## 4. CI Pipelines & Security Gates

1. Inspect workflows:
   - Basic vs strict CI tiers (`ci-basic`, `ci-strict`, etc.).
   - Steps: tests, coverage, lint, type-check, security scans, dependency review.
2. Confirm:
   - Minimum coverage thresholds are enforced.
   - Security tools (Gitleaks, Semgrep, Trivy, pip-audit, npm audit, CodeQL) are configured and actually run.
   - There are no conditional expressions that unintentionally skip checks for certain branches.
3. Check `scripts/test-backend.sh` and `scripts/test-frontend.sh`:
   - How `STRICT_MODE`, `FAST_TESTS`, `SKIP_STRICT_LINT` affect behavior.
   - That CI runs with strict settings.

---

## 5. Deployment & Environment Guidance

1. `DEPLOYMENT.md`, `.env.example`, `docs/configuration.md`:
   - Validate that instructions match the code’s reality:
     - Required env vars.
     - Production-vs-dev differences.
     - Redis, Postgres, TLS, CORS configuration.
2. `docker-compose.yml` & Dockerfiles:
   - Confirm images are built with appropriate base images.
   - Validate that:
     - Migrations are run before serving.
     - Health checks are configured reasonably.
3. Note any gaps where deployment docs recommend something the code doesn’t enforce (or vice versa).

---

## 6. Tests & QA View (High-Level)

Although Instruction Set 11 will go deep on tests, do a high-level check here:

1. Confirm CI executes:
   - `backend/tests/*` with coverage.
   - Frontend tests and/or build.
2. Check for:
   - Hard-coded “skip” markers on critical tests (auth, uploads, budgets, admin).
   - Any patterns that might hide flaky tests (reruns without reporting, ignoring failures).

You will cross-reference this with Instruction Set 11.

---

## 7. Vibe Artifact Pass (Ops & Observability)

Search for:

- Commented-out CI steps or security scans.
- OpenAPI generation workarounds (e.g. dummy keys, artificial imports) that may break in some envs.
- TODO/FIXME notes relating to production hardening or monitoring.

For each:

- Decide if it is acceptable (document as a known limitation) or should be corrected.
- Take special care with anything that might make production health look “better than it is”.

---

## 8. Output

Summarize:

- Observability coverage (what you can see and measure).
- OpenAPI reliability and how it is kept in sync.
- CI and deployment safety guarantees (and gaps).
- A short prioritized list of improvements (e.g., missing metrics, incomplete warnings, doc/code mismatches).
