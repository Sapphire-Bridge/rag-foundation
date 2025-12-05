RAG Codebase Context 004 — Migrations, Tests, OpenAPI, Deployment (≈1k LOC scope)

Scope (files covered)
- backend/alembic/env.py:1, backend/alembic/versions/*.py — Alembic env + migrations
- backend/tests/*.py — Backend test suite (auth, security, uploads, chat, budgets, settings, admin)
- backend/openapi.yaml:1 — OpenAPI 3.1 contract (exported from live app)
- backend/Dockerfile:1, backend/entrypoint.sh:1 — Backend image + Alembic/perm checks
- docker-compose.yml:1 — Dev/preview stack (db, redis, migrations, backend, worker, frontend)
- .env.example:1 — Config template and defaults
- backend/scripts/export_openapi.py:1, backend/scripts/check_admin_patterns.py:1 — Spec export + admin audit guardrail
- scripts/test-backend.sh, scripts/test-frontend.sh, scripts/security-scan.sh — Local test/security helpers
- docs/pricing.md — Pricing + budget enforcement details

Migrations (Alembic)
- `alembic/env.py` binds to `app.db.engine`/`Base.metadata`; offline/online runners share metadata.
- Schema highlights:
  - 0004 unique `stores.fs_name` to align with Gemini store identity; 0005 soft deletes (`deleted_at` indexes) on stores/documents.
  - 0006 admin RBAC (`is_admin` on users + `admin_audit_logs`); 0007 query_logs add `project_id` + JSON `tags`.
  - 0008 chat history table + `documents.gcs_uri`; 0009 add `store_id` index to chat_history.
  - 0010/0011 app settings key/value table seeded with welcome message + 3 suggested prompts.
  - 0012 `deleted_by` FKs on stores/documents; 0013 `status_updated_at` on documents (default now()).
  - Document status stored as string (non-native enum) for portability.

Backend Tests (selected coverage)
- Security defaults matrix (`test_security_defaults_matrix.py`): default env requires CSRF and hides dev token; prod startup fails if dev login enabled.
- Production settings (`test_production_settings.py`): disallow SQLite in prod, dev JWT secret, blank/default DB passwords; require Redis when configured; validate TRUSTED_PROXY_IPS parsing.
- Security middleware (`test_security_middleware.py`): CSRF header enforcement, rate-limit hits, trusted proxy IP resolution, async middleware behavior.
- Auth flows (`test_auth.py`, `test_auth_flows_real.py`): register/login round trip returns bearer token; dev token helpers.
- Tenant isolation (`test_tenant_isolation.py`): uploads/chat/op-status reject cross-tenant access.
- Upload validation (`test_upload_validation.py`): auth required, MIME allow-list enforced, PDF magic checks, 401/403 bubbles to `onAuthExpired`.
- Upload profiles (`test_upload_profiles.py`): Settings validation for safe/office/all-supported/custom MIME sets (normalizes case, rejects unknown types).
- Streaming (`test_streaming.py`, `test_sse_smoke.py`): chat SSE retries transient errors, emits error frames on persistent/unknown errors, keepalive frames honored; route returns 400/401 without auth/body.
- Gemini client (`test_gemini_rag.py`): ask() retry decorator, citation extraction resilience, UUID stream IDs, warning logs on parse failure.
- Costs/budgets (`test_costs.py`): `/api/costs/summary` aggregates prompt/completion/index tokens + budgets; uploads rejected with 402 when exceeding budget.
- Soft delete (`test_soft_delete.py`): store/document delete/restore flow, upload blocked after delete, admin restore succeeds.
- Admin RBAC (`test_admin_rbac.py`): admin-only endpoints require is_admin and record audit logs; watchdog reset returns counts.
- Settings (`test_settings.py`): GET returns defaults; non-admin update forbidden; admin update persists/appends audit; favicon size limit enforced.
- Chat history limits (`test_chat_history_limits.py`): `_load_chat_history` filters by store_id; rejects oversize chat question length.
- Settings/CSRF defaults (`test_security_middleware.py`, `conftest.py`): tests disable CSRF via env; fixtures prepare DB.

OpenAPI Contract
- `backend/openapi.yaml` generated via `backend/scripts/export_openapi.py` (forces GEMINI_MOCK_MODE for export). CI drift checks regenerate and diff.
- Documents all public routes: auth/register/login/token/logout, stores CRUD + soft delete/restore, documents delete/restore, upload + op-status, chat SSE, costs summary, settings get/save, admin (users/roles/budgets/audit/system/watchdog), health/metrics.

Containers & Orchestration
- Backend Dockerfile: two-stage build, installs `requirements.lock` + gunicorn/arq, sets non-root `appuser`, pre-creates `/tmp/rag_uploads` with perms, healthcheck hits `/health`. Entrypoint ensures upload dir writable then runs `alembic upgrade head`.
- docker-compose.yml: services `db` (Postgres), `redis`, `migrations` (alembic upgrade head), `backend` (gunicorn), `worker` (ARQ ingestion/watchdog), `frontend` (Vite dev server). Secrets pulled from `./secrets/*`; uses `DOCKER_DATABASE_URL` to avoid accidental sqlite. Redis health-gated before backend/worker.
- Frontend Dockerfile builds Vite app; proxied via `VITE_BACKEND_ORIGIN`.

Config Defaults (.env.example)
- Dev defaults: `ENVIRONMENT=development`, `GEMINI_MOCK_MODE=true`, SQLite DB, CSRF required, dev login disabled by default, Redis optional (required in prod via `REQUIRE_REDIS_IN_PRODUCTION=true`).
- Security toggles: `ALLOW_DEV_LOGIN`, `REQUIRE_CSRF_HEADER`, `ALLOW_METADATA_FILTERS`, `METADATA_FILTER_ALLOWED_KEYS`; JWT issuer/audience; `TRUSTED_PROXY_IPS`.
- Upload controls: `UPLOAD_PROFILE` (safe/office/all-supported/custom), `ALLOWED_UPLOAD_MIMES` for custom, `MAX_UPLOAD_MB`, `TMP_DIR=/tmp/rag_uploads`.
- Pricing: `PRICE_PER_MTOK_INPUT/OUTPUT/INDEX` defaults to Gemini 2.5 Flash; `PRICE_CHECK_STRICT` to enforce non-zero even outside prod (see docs/pricing.md).
- Streaming: `GEMINI_HTTP_TIMEOUT_S`, `GEMINI_RETRY_ATTEMPTS`, `GEMINI_STREAM_RETRY_ATTEMPTS`, `STREAM_KEEPALIVE_SECS`, `MAX_CONCURRENT_STREAMS`.
- Frontend: `VITE_BACKEND_ORIGIN` used by Vite proxy; CORS defaults `["http://localhost:5173"]`.

CI Workflows
- `ci-basic.yml`: admin audit pattern check; install backend deps + `alembic upgrade head`; backend tests via `STRICT_MODE=1 FAST_TESTS=0 ./scripts/test-backend.sh`; OpenAPI drift regen/diff; frontend `npm ci` + `STRICT_MODE=1 FAST_TESTS=0 ./scripts/test-frontend.sh` (tests + build).
- `ci-strict.yml`: full backend suite (pytest with coverage, ruff, mypy via script), pip-audit + Bandit, build backend image + Trivy scan, frontend tests/build + `npm audit --production --audit-level=high`, SBOM (spdx-json), OpenAPI drift assertion.
- `security.yml`: gitleaks, semgrep, Trivy (backend+frontend) with SARIF uploads; CodeQL + Dependency Review on public repos.

Local Tooling / Scripts
- `scripts/test-backend.sh`: controls STRICT_MODE/FAST_TESTS/SKIP_STRICT_LINT; forces USE_GOOGLE_GENAI_STUB=1 by default; runs pytest (coverage in strict), then ruff and mypy unless skipped.
- `scripts/test-frontend.sh`: installs deps if missing, runs npm test (skipped when FAST_TESTS=1) and build.
- `scripts/security-scan.sh`: optional local gitleaks/semgrep/pip-audit/npm audit with toggles to skip components.
- `backend/scripts/check_admin_patterns.py`: AST check ensuring admin mutation routes call `record_admin_action` when guarded by `require_admin`; enforced in CI.
- `backend/scripts/export_openapi.py`: regenerate `openapi.yaml` using live FastAPI routes.

Operational Notes
- `entrypoint.sh` aborts if upload dir not writable (volume perms) before running migrations; ensures app never starts on stale schema.
- Budget guardrails: uploads pre-check estimated index cost; chat stops when budget exceeded and emits SSE error frame (tests assert 402 on upload).
- Chat request size limited (`MAX_QUESTION_LENGTH` in routes.chat; tested in `test_chat_history_limits`).
- Trusted proxy parsing normalized to CIDR (`/32` appended to single IPs); rate-limit middleware resolves client IPs using TRUSTED_PROXY_IPS.
