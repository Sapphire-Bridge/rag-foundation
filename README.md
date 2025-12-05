<!-- Repo Context Index: agent-discoverable -->
- Context 001 — Backend Core, Config, Security: docs/context/CONTEXT-001.md
- Context 002 — Backend Models, Routes, RAG: docs/context/CONTEXT-002.md
- Context 003 — Frontend UI & Integration: docs/context/CONTEXT-003.md
- Context 004 — Migrations, Tests, OpenAPI, Ops: docs/context/CONTEXT-004.md
- Context 005 — Benchmark Runner: docs/context/CONTEXT-005.md

# RAG Assistant
[![CI Basic](https://github.com/Sapphire-Bridge/rag-foundation/actions/workflows/ci-basic.yml/badge.svg)](https://github.com/Sapphire-Bridge/rag-foundation/actions/workflows/ci-basic.yml)
[![CI Strict](https://github.com/Sapphire-Bridge/rag-foundation/actions/workflows/ci-strict.yml/badge.svg)](https://github.com/Sapphire-Bridge/rag-foundation/actions/workflows/ci-strict.yml)

A production-ready RAG (Retrieval-Augmented Generation) assistant with JWT authentication, tenant isolation, and comprehensive observability.

## 🚀 Quickstart (Docker)

Prereqs: Docker + Docker Compose v2.

1. Clone the repo: `git clone https://github.com/Sapphire-Bridge/rag-foundation.git && cd rag-foundation`
2. Copy env vars: `cp .env.example .env`, then either keep `GEMINI_MOCK_MODE=true` for the built-in stub or set `GEMINI_API_KEY=<your key>` and `GEMINI_MOCK_MODE=false` to call Gemini.
3. Start the stack: `docker compose up` (add `--build` on first run).
4. Visit http://localhost:5173 and follow the flow: Register → Login → Create store → Upload → Chat.

> Deployers are responsible for production hardening (strong secrets, TLS/proxying, network isolation, auth); the defaults are intentionally development-friendly.

## Components

- Backend: FastAPI served by Gunicorn/Uvicorn with JWT auth, rate limiting, metrics, and SSE chat.
- Ingestion worker: ARQ worker that indexes uploads and runs watchdog resets for stuck documents.
- Database: PostgreSQL via Docker Compose (SQLite supported for lightweight local dev).
- Redis: Handles distributed rate limiting, JWT revocation, and the ingestion queue; required outside mock-mode demos.
- Frontend: React + Vite client on port 5173.

---

## ⚠️ SECURITY WARNING - Development vs Production

The quickstart runs with **development defaults**:

- ❌ **Weak JWT secret** placeholder in `.env`
- ❌ **Gemini mock mode** defaults to on; set a real `GEMINI_API_KEY` and `GEMINI_MOCK_MODE=false` for production
- ❌ **Default database credentials** (`changeme_local_only` in docker compose or SQLite fallback)
- ❌ **Redis without auth** in the sample stack; set `REDIS_URL` with credentials and restrict network access
- ❌ **Dev login endpoint exists**; keep `ALLOW_DEV_LOGIN=false` (the default) outside local testing

**⚠️ NEVER use these defaults in production!**

For production deployment, see **[Production Security Guide](#production-security-guide)** below.

---

## Public Release Notes

- Internal-only docs, reports, and sample database dumps from private environments were intentionally left out of this public release. Use the quickstart flow to generate fresh demo data locally.

---

## Dev vs Prod Flags

**Use only in development**

| Flag | Description | Default |
| --- | --- | --- |
| `GEMINI_MOCK_MODE` | Disable outbound Gemini calls and use the local stub. | `true` |
| `ALLOW_DEV_LOGIN` | Passwordless dev token endpoint. Never enable outside local dev. | `false` |
| `ALLOW_METADATA_FILTERS` | Advanced: stays off unless you also set `METADATA_FILTER_ALLOWED_KEYS` for strict allowlisted filters. | `false` |

**Must be set explicitly in production**

| Flag | Description | Default |
| --- | --- | --- |
| `JWT_SECRET` | 32+ character secret for JWT signing; must not use the dev placeholder. | _none_ |
| `DATABASE_URL` | PostgreSQL connection string (SQLite is for local dev only). | `sqlite:///./rag.db` |
| `REDIS_URL` | Required when `REQUIRE_REDIS_IN_PRODUCTION=true` (default). | _none_ |
| `GEMINI_API_KEY` | Real Gemini API key (unless mock mode explicitly allowed). | _none_ |
| `CORS_ORIGINS` | Allowed frontend origins (JSON array or comma-separated). | `["http://localhost:5173"]` |

## Turnkey usage (single-machine deployment)

For a small team (≈20–50 users) you can run RAG Assistant on a single VM or laptop using Docker Compose:

1. Copy `.env.example` to `.env` and fill in:

   - `JWT_SECRET` – use `python -c "import secrets; print(secrets.token_urlsafe(64))"`
   - Either set `GEMINI_API_KEY` **or** set `GEMINI_MOCK_MODE=true` for local testing
   - `DATABASE_URL` – keep the default SQLite URL for small, low-concurrency setups,
     or point it at a PostgreSQL instance for more durability.
   - `CORS_ORIGINS` – include your frontend URL(s), e.g. `"http://localhost:5173"`
   - (optional) `REDIS_URL` – recommended for production rate limiting.

2. Start everything:

   ```bash
   docker-compose up --build
   ```

3. Open the frontend in a browser:
   - http://localhost:5173

For hosted / multi-user deployments, prefer PostgreSQL + Redis and configure
backups and log retention via your hosting provider.

---

## Features

- **Backend (FastAPI)**
  - Sync FastAPI + SQLAlchemy served via Gunicorn + Uvicorn workers (4 by default in Docker Compose)
  - JWT authentication with tenant isolation
  - SQLAlchemy + Alembic for database migrations
  - Gemini API integration with retries, timeouts, and error handling
  - File upload hardening (PDF by default, with configurable allow-lists and strict validation)
  - Prometheus metrics for monitoring
  - Rate limiting and correlation IDs
  - Cost tracking and logging
  - Health check endpoint
  - SSE streaming for real-time chat responses

- **Frontend (React + Vite)**
  - AssistantUI integration for chat interface
  - Authentication with JWT tokens

## Known Limitations & Roadmap

- Benchmarks: The benchmark harness currently ignores upload failures in its final metrics, and latency stats reflect successful requests only.
- Metadata Filters: Metadata filters are fully functional in the backend, but the benchmark runner does not yet stress-test complex filter combinations.

## API Documentation
- Interactive docs: run the backend and open `http://localhost:8000/docs`.
- Static spec: `backend/openapi.yaml` (generated via `python backend/scripts/export_openapi.py`) for client generation.
  - Document upload and management
  - Monthly cost tracking panel
  - Citation/source document display
  - Real-time streaming responses
  - Lightweight benchmark runner (CLI) to exercise stores, uploads, chat, metrics
  - Admin dev mode for branding (app name/icon/theme presets) stored in the DB via `/api/settings`

## Requirements

- **For Docker setup**: Docker & Docker Compose, Gemini API key
- **For local development**: Python 3.11+, Node.js 20+, Gemini API key

## Alternative: Local Development Setup

If you prefer not to use Docker:

### 1. Backend Setup

```bash
cd backend

# Create virtual environment
python -m venv .venv
source .venv/bin/activate  # On Windows: .venv\Scripts\activate

# Install dependencies
pip install -e .

# Copy environment file and configure
cp .env.example .env
# Edit .env and set your GEMINI_API_KEY and JWT_SECRET

# Run database migrations
alembic upgrade head

# Start the backend server
uvicorn app.main:app --reload

# Background ingestion worker (required for durable uploads)
arq app.worker.WorkerSettings

# Production note: .env is for local development only. In staging/production set
# GEMINI_API_KEY, DATABASE_URL, REDIS_URL, and JWT_SECRET via environment.
```

The backend will be available at http://localhost:8000

> Containers run `alembic upgrade head` on startup via `entrypoint.sh` to prevent serving traffic on stale schemas. Always pair model changes with a migration.

To process queued ingestions outside Docker, run the worker locally:

```bash
cd backend
arq app.worker.WorkerSettings
```

If ingestion ever leaves documents stuck in `RUNNING` (e.g., prolonged provider outage), you can mark them as `ERROR` with:

```bash
cd backend
python -m scripts.mark_stuck_documents_error 60  # minutes threshold (default 60)
```

## Paths and uploads

- `UPLOAD_FOLDER` (or `TMP_DIR`) controls where uploads are stored (default: `/tmp/rag_uploads`). The entrypoint will create/check writability on startup. In Docker Compose, mount a named volume to this path to persist files between restarts.

## Security & compliance

- Security CI runs on PRs/branches: Gitleaks (secrets), Semgrep (SAST), Trivy (SCA), and CodeQL (deep SAST). See `.github/workflows/security.yml`.
- Allowed development-only secrets are documented in `.gitleaks.toml`; do not add real secrets there.
- Dependency review runs on PRs to flag risky package changes.

### 2. Frontend Setup

```bash
cd frontend

# Install dependencies
npm install

# Start the development server
npm run dev
```

The frontend will be available at http://localhost:5173

### Helper Scripts & Dev Toggles

Use the provided wrappers to mirror CI locally:

```bash
./scripts/test-backend.sh    # Pytest + ruff + mypy (respects STRICT_MODE/FAST_TESTS)
./scripts/test-frontend.sh   # npm test/build wrapper
```

Key environment toggles:

| Variable | Default | Effect |
|----------|---------|--------|
| `STRICT_MODE` | `1` | Full pytest with coverage, security gate enforced. Set to `0` to relax local runs (CI ignores this). |
| `FAST_TESTS` | `0` | When `1`, backend wrapper only runs smoke tests and skips frontend tests (still builds). |
| `USE_GENAI_STUB` | `1` during backend tests | Forces the lightweight Gemini stub instead of the real SDK. |
| `SKIP_STRICT_LINT` | `0` | When `1`, backend wrapper skips ruff/mypy for quicker loops. |

Examples:

```bash
# Fast inner loop (smoke tests + build)
FAST_TESTS=1 SKIP_STRICT_LINT=1 ./scripts/test-backend.sh
FAST_TESTS=1 ./scripts/test-frontend.sh

# Full strict run before opening a PR
STRICT_MODE=1 ./scripts/test-backend.sh
STRICT_MODE=1 ./scripts/test-frontend.sh
```

### CI Tiers

- `ci-basic` (required): runs on every push/PR, executes backend smoke tests (coverage disabled) and frontend build via the helper scripts with `FAST_TESTS=1`.
- `ci-strict` (nightly + manual): runs full coverage, lint, type checking, dependency audits, and OpenAPI drift detection. Trigger via the “Run workflow” button or wait for the nightly schedule.

Always run the strict helper scripts locally before requesting review to avoid surprises when the nightly job runs.

### Security & Dependency Scans

- Local: run `./scripts/security-scan.sh` (pip-audit, npm audit, optional Gitleaks if installed).
- CI: see `docs/security/ci.md` for the "what runs when" matrix. The adaptive Security CI workflow runs Gitleaks, Semgrep, and Trivy everywhere, and adds CodeQL + Dependency Review on public repos.
- Strict: `./scripts/security-scan.sh` + `STRICT_MODE=1 ./scripts/test-backend.sh` and `STRICT_MODE=1 ./scripts/test-frontend.sh` before releases.

## Usage

1. **Login**: Enter your email and click "Get Token" (in dev mode, any email works)
2. **Create Store**: Click "+ New Store" to create a document store
3. **Upload Documents**: Select a store and upload PDF files. By default the backend allows PDF uploads only. In more advanced profiles, additional MIME types (text, CSV, Office docs) can be enabled via `ALLOWED_UPLOAD_MIMES` / `UPLOAD_PROFILE`. The upload route enforces the active allow-list and validates file magic numbers for binary formats.
4. **Chat**: Ask questions about your uploaded documents
5. **View Costs**: See monthly usage costs in the right panel

## API Endpoints

- `POST /api/auth/register` - Create new user account
- `POST /api/auth/login` - Login with credentials
- `POST /api/auth/token` - Dev-only: Get token by email
- `GET /api/stores` - List user's document stores
- `POST /api/stores` - Create new document store
- `DELETE /api/stores/{id}` - Soft delete a store (marks `deleted_at` and schedules Gemini cleanup)
- `POST /api/stores/{id}/restore` - Admin-only restore of a soft-deleted store
- `DELETE /api/documents/{id}` - Soft delete a document
- `POST /api/documents/{id}/restore` - Admin-only restore of a document
- `POST /api/upload` - Upload document to store
- `GET /api/upload/op-status/{op_id}` - Check upload/indexing status
- `POST /api/chat` - Stream chat responses (SSE)
- `GET /api/costs/summary` - Get monthly cost summary
- `GET /api/admin/users` - Admin list of users
- `POST /api/admin/users/{id}/role` - Toggle a user's admin flag
- `POST /api/admin/budgets/{id}` - Upsert monthly budget for a user
- `GET /api/admin/audit` - View admin audit log entries
- `GET /api/admin/system/summary` - Lightweight system counts
- `POST /api/admin/watchdog/reset-stuck` - Reset RUNNING documents back to PENDING
- `GET /health` - Health check
- `GET /metrics` - Prometheus metrics
- `GET /docs` - OpenAPI documentation

### Data Lifecycle & Soft Delete

- DELETE routes mark rows with `deleted_at` instead of hard-deleting, keeping query/billing audit trails intact.
- Background tasks trigger best-effort Gemini cleanup for stores/documents. Document-level delete currently does **not** remove the remote Gemini file because the SDK does not expose file IDs here; data is hidden via soft delete until full-store deletion or retention cleanup.
- Soft-deleted stores are hidden from list/create/upload/chat flows; attempts return `404` to avoid leaking tenancy info.
- Admins (superusers) can restore records via `/api/stores/{id}/restore` and `/api/documents/{id}/restore`; restores are global, not per-tenant scoped.
- Purging (hard delete) can be layered on later via a retention job that removes rows where `deleted_at` exceeds your retention policy.

### Cost Tracking & Pricing

- Token rates default to Gemini 2.5 Flash pricing (`0.35` input / `1.05` output / `0.13` index USD per million tokens) and the backend refuses to start in production if any rate is zero.
- `POST /api/upload` responses now return `estimated_tokens` and `estimated_cost_usd` so the UI can warn users before indexing charges accrue.
- `/api/costs/summary` adds token counts plus budget information (`monthly_budget_usd`, `remaining_budget_usd`) alongside query vs indexing cost.
- Upload and chat endpoints share the same budget enforcement helper—requests that would exceed a tenant’s monthly budget return HTTP `402`.
- Known limitation: if the upstream provider does not return usage metadata for a call, that call may be under-reported or missing from cost totals.
- See [`docs/pricing.md`](docs/pricing.md) for step-by-step guidance on overriding rates, enabling strict validation, and verifying spend.

### Admin Operations & Logging

- Promote trusted operators by toggling the `is_admin` flag via `POST /api/admin/users/{id}/role`. Admin access is now tied only to users marked as admins; shared header bypasses have been removed.
- Every admin action writes to the `admin_audit_logs` table and emits structured logs via `log_json`, so you get both persistent records and searchable telemetry.
- Admin APIs help with day-to-day operations: list users, adjust budgets, inspect audit history, fetch quick system counts, and run the watchdog reset for stuck documents—all without touching the database directly.

## Architecture

```
RAG/
├── backend/
│   ├── app/
│   │   ├── routes/          # API endpoints
│   │   ├── services/        # Business logic (Gemini integration)
│   │   ├── models.py        # Database models
│   │   ├── schemas.py       # Pydantic schemas
│   │   ├── auth.py          # JWT authentication
│   │   ├── config.py        # Configuration
│   │   └── main.py          # FastAPI app
│   ├── alembic/             # Database migrations
│   └── pyproject.toml       # Python dependencies
├── frontend/
│   └── src/
│       ├── components/      # React components
│       ├── App.tsx          # Main app
│       └── main.tsx         # Entry point
└── docker-compose.yml       # Docker orchestration
```

## Development

### Running Tests

```bash
cd backend
pytest --cov=app
```

### Database Migrations

```bash
# Create new migration
alembic revision --autogenerate -m "description"

# Apply migrations
alembic upgrade head

# Rollback
alembic downgrade -1

# All schema changes must ship with an Alembic migration. Run
# `alembic upgrade head` as part of every deployment before starting the app.
```

### Code Quality

```bash
# Linting and formatting
cd backend
ruff check .
ruff format .

# Type checking
mypy .
```

---

## Production Security Guide

**🔒 Required changes for production deployment:**

- For a concise small-deployment checklist (env vars, disabling dev login, TLS/proxy notes, migrations, health/metrics), see `DEPLOYMENT.md`.

### 1. Generate Strong Secrets

```bash
# Generate a cryptographically random JWT secret
python -c "import secrets; print(secrets.token_urlsafe(64))"

# Generate a strong database password
python -c "import secrets; print(secrets.token_urlsafe(32))"
```

### 2. Create Production Environment File

Create a `.env` file with your production secrets:

```bash
# REQUIRED - Security
ENVIRONMENT=production
JWT_SECRET=<paste-generated-secret-from-above>
GEMINI_API_KEY=<your-real-gemini-api-key>

# REQUIRED - Database
DATABASE_URL=postgresql+psycopg2://rag:<db-password>@db:5432/rag

# REQUIRED - Redis for rate limiting & JWT revocation
REDIS_URL=redis://redis:6379/0

# CRITICAL - Disable dev login
ALLOW_DEV_LOGIN=false

# Security headers and CORS
CORS_ORIGINS=["https://yourdomain.com"]
REQUIRE_CSRF_HEADER=true

# Rate limiting (adjust based on your needs)
RATE_LIMIT_PER_MINUTE=120

# JWT token expiration (15 minutes default)
ACCESS_TOKEN_EXPIRE_MINUTES=15
```

> The backend reads the database credentials from `DATABASE_URL` only. Infrastructure tooling such as `docker-compose.yml` may still use `DB_PASSWORD` to provision Postgres, but the app itself never consumes that variable directly.

### 3. Add Redis to docker-compose.yml

For production, you need Redis for distributed rate limiting and JWT revocation:

```yaml
services:
  redis:
    image: redis:7-alpine
    ports: ["6379:6379"]
    volumes:
      - redis_data:/data
    command: redis-server --appendonly yes
    healthcheck:
      test: ["CMD", "redis-cli", "ping"]
      interval: 5s
      timeout: 3s
      retries: 5

volumes:
  postgres_data:
  redis_data:
```

Tokens include a random `jti` (JWT ID). The `/api/auth/logout` endpoint writes `revoked:{jti}` keys to Redis with a TTL that matches the token expiry, and `get_current_user` rejects any token whose JTI is present. If Redis is unavailable, logout still returns success but revocation falls back to the short access-token lifetime.

### 4. Deploy with Production Settings

```bash
# Load your .env file
source .env  # or use direnv, docker secrets, etc.

# Deploy (single compose file; configuration driven by ENVIRONMENT and .env)
docker-compose up -d
```

### 5. Additional Production Hardening

- **Use HTTPS/TLS**: Deploy behind a reverse proxy (nginx, Caddy, Traefik) with SSL certificates
- **Implement real authentication**: Replace dev login with proper OAuth2/OIDC provider (Auth0, Keycloak, etc.)
- **Database backups**: Set up automated PostgreSQL backups
- **Monitoring**: Deploy Prometheus + Grafana for metrics and alerting
- **Log aggregation**: Use ELK stack or Loki for centralized logging
- **Resource limits**: Set Docker CPU/memory limits in docker-compose
- **Network isolation**: Use Docker networks to isolate services
- **Secrets management**: Use Docker secrets, AWS Secrets Manager, or HashiCorp Vault
- **Rate limiting**: Consider using a WAF (Cloudflare, AWS WAF) for additional protection
- **Regular updates**: Enable Dependabot and review security advisories

### 6. Production Checklist

Before going live, verify:

- [ ] `ENVIRONMENT=production` is set
- [ ] `JWT_SECRET` is a random 64+ character string (not the dev default)
- [ ] `ALLOW_DEV_LOGIN=false` (dev login disabled)
- [ ] `DATABASE_URL` points to PostgreSQL (not SQLite)
- [ ] `REDIS_URL` is configured and Redis is running
- [ ] `CORS_ORIGINS` only includes your actual domain(s)
- [ ] HTTPS/TLS is configured (not HTTP)
- [ ] Database backups are configured
- [ ] Monitoring and alerting are set up
- [ ] All default passwords have been changed
- [ ] Firewall rules are configured (only expose necessary ports)
- [ ] Security headers are enabled (check /health response)
- [ ] Rate limiting is working (test with curl)
- [ ] Logs are being collected and rotated
- [ ] Resource limits are set on containers
- [ ] Secrets are managed securely (not in git)

### 7. Verify Security

After deployment, test your security:

```bash
# Check health endpoint
curl https://yourdomain.com/health

# Verify security headers are present
curl -I https://yourdomain.com/api/stores

# Test rate limiting (should get 429 after limit)
for i in {1..130}; do curl https://yourdomain.com/health; done

# Verify dev login is disabled (should fail)
curl -X POST https://yourdomain.com/api/auth/token \
  -H "Content-Type: application/json" \
  -d '{"email":"test@test.com"}'
```

## Configuration Reference

The full matrix of environment variables lives in [`docs/configuration.md`](docs/configuration.md). Highlights:

### Required
- `JWT_SECRET`: Secret key for JWT token signing (64+ chars, random)
- `GEMINI_API_KEY`: Your Gemini API key from Google AI Studio
- `DATABASE_URL`: Database connection string
- `REDIS_URL`: Redis connection string (required in production)

### Security
- `ALLOW_DEV_LOGIN`: Enable simple dev login (MUST be false in production)
- `ENVIRONMENT`: Environment name (development/test/staging/production)
- `CORS_ORIGINS`: Allowed CORS origins (JSON array)
- `REQUIRE_CSRF_HEADER`: Require X-Requested-With header (default: true)
- `TRUSTED_PROXY_IPS`: Comma/JSON list of proxy CIDRs allowed to supply `X-Forwarded-For` for rate limiting (default: empty)
- `ALLOW_METADATA_FILTERS`: Off by default; when true the chat endpoint only forwards simple filters for keys in `METADATA_FILTER_ALLOWED_KEYS`.
- `METADATA_FILTER_ALLOWED_KEYS`: Comma/JSON allowlist of metadata keys accepted when metadata filters are enabled.
- `STRICT_MODE`: Fail-fast security gate; default `true` and only disable in local development.
- `MAX_CONCURRENT_STREAMS`: Cap on concurrent chat streams per process (default: 50); over-cap requests return 200 with a structured SSE error payload.

### Application
- `MAX_UPLOAD_MB`: Maximum file upload size (default: 25MB)
- `RATE_LIMIT_PER_MINUTE`: API rate limit (default: 120)
- `ACCESS_TOKEN_EXPIRE_MINUTES`: JWT token lifetime (default: 15 minutes)
- `MAX_STORES_PER_USER`: Maximum stores per user (default: 10)
- `UPLOAD_PROFILE`: Controls which MIME types uploads accept (`safe`, `office`, `all-supported`, `custom`)
- `ALLOWED_UPLOAD_MIMES`: Explicit MIME allowlist (used when `UPLOAD_PROFILE=custom`)
- `PRICE_PER_MTOK_INPUT/OUTPUT/INDEX`: Token pricing for cost tracking

### Gemini API
- `DEFAULT_MODEL`: Gemini model to use (default: gemini-2.5-flash)
- `GEMINI_HTTP_TIMEOUT_S`: Request timeout (default: 60s)
- `GEMINI_RETRY_ATTEMPTS`: Retry attempts (default: 3)
- `USE_GOOGLE_GENAI_STUB`: When `true`, forces the in-process Google GenAI stub implementation even if `GEMINI_MOCK_MODE` is `false`. This is read directly in `backend/app/genai.py` and is useful for offline development or CI.

### Frontend environment variables

The frontend (Vite) uses the following environment variable:

- `VITE_BACKEND_ORIGIN`: Base URL of the backend API used by the dev server
  and proxy. Defaults to `http://localhost:8000` for local development.

Set this in a `.env.local` or in the root `.env` when deploying the frontend
separately from the backend.

> In production the config validator enforces several invariants:
> - `ALLOW_DEV_LOGIN=false`
> - `DATABASE_URL` must not use SQLite
> - `JWT_SECRET` must not be the dev default value
> - `REDIS_URL` must be set when `REQUIRE_REDIS_IN_PRODUCTION=true`

## Security Features

- JWT-based authentication with short expiration (15 minutes)
- Tenant isolation (users can only access their own data)
- File upload validation (MIME type, magic number, size, filename sanitization)
- Rate limiting with Redis backend (120 req/min by default)
- CORS configuration with origin restrictions
- SQL injection prevention (SQLAlchemy ORM with parameterized queries)
- Request correlation IDs for security tracing
- CSRF protection via custom header requirement
- Security headers (X-Content-Type-Options, X-Frame-Options, etc.)
- Password hashing with bcrypt
- JWT revocation backed by Redis (`/api/auth/logout` stores `revoked:{jti}` until expiration and the auth dependency denies revoked tokens)
- Production configuration safety checks (fail-fast if dev login, SQLite, the dev JWT secret, or missing Redis config slip into production)

Authentication tokens are currently stored in browser `sessionStorage` and sent as
`Authorization: Bearer <token>` headers from the frontend. This is a demo-friendly
default; for production deployments, prefer httpOnly, `SameSite=Strict` cookies (or
another storage isolated from the JS runtime) plus a tight Content Security Policy.

## Observability

- **Structured JSON logging** with correlation IDs for request tracing
- **Prometheus metrics**:
  - HTTP request count and duration (by endpoint, status code)
  - Gemini API call metrics (success/failure rates, latency)
  - Active users and document counts
  - Rate limit hit rates
- **Health check endpoint** (`/health`) for load balancers
- **Cost tracking** per query with monthly summaries
- **OpenAPI documentation** at `/docs` (Swagger UI)

Application logs (structured JSON) are written to stdout / the host system.
There is no built-in log rotation or 90-day retention job; operators are
responsible for configuring log retention (e.g. via Docker logging drivers,
cloud log sinks, or cron-based rotation).

## Documentation

- **[CLAUDE.md](CLAUDE.md)**: Comprehensive guide for AI assistants and contributors
- **[CONTRIBUTING.md](CONTRIBUTING.md)**: Guidelines for contributing
- **[SECURITY.md](SECURITY.md)**: Security policy and vulnerability reporting
- **[CODE_OF_CONDUCT.md](CODE_OF_CONDUCT.md)**: Community guidelines
- **[PRIVACY.md](PRIVACY.md)**: Privacy policy and data handling
- **[RELEASE.md](RELEASE.md)**: Release management and versioning
- **[CHANGELOG.md](CHANGELOG.md)**: Version history
- **[DEPLOYMENT.md](DEPLOYMENT.md)**: Small-production deployment checklist (20–50 users)
- **[OpenAPI Spec](backend/openapi.yaml)**: API contract
- **[Deployment playbooks](docs/deployments/README.md)**: Docker Compose + Kubernetes guidance
- **[Observability guide](docs/observability/README.md)**: Metrics, logging, and dashboard ideas

## Contributing

We welcome contributions! Please read [CONTRIBUTING.md](CONTRIBUTING.md) for guidelines.

Quick pointers:
- Follow the Code of Conduct ([CODE_OF_CONDUCT.md](CODE_OF_CONDUCT.md))
- Run `STRICT_MODE=1 ./scripts/test-backend.sh` and `STRICT_MODE=1 ./scripts/test-frontend.sh` before opening a PR
- Avoid committing secrets; run a secret scan locally if you touched credentials (see `DEPLOYMENT.md` for the public-release checklist)

Key areas for contribution:
- Bug fixes and feature enhancements
- Documentation improvements
- Test coverage improvements
- Security hardening
- Performance optimizations
- Frontend UI/UX improvements

### Release & Communication

- Follow [`CHANGELOG.md`](CHANGELOG.md) for release notes and upcoming milestones.
- `ci-basic` badges must be green for every PR; `ci-strict` runs nightly and before releases.
- Major changes (deployment guidance, security updates) are reflected in [`docs/deployments`](docs/deployments/README.md) and announced in the next changelog entry.

## Security

For security vulnerabilities, please see our [Security Policy](SECURITY.md). Do not open public issues for security concerns.

## Troubleshooting

### Common Issues

**Error: GEMINI_API_KEY is required**
- Make sure you've exported the API key: `export GEMINI_API_KEY=your_key`
- Get an API key from https://aistudio.google.com/app/apikey

**Error: Cannot use dev default JWT_SECRET in production**
- Generate a real secret: `python -c "import secrets; print(secrets.token_urlsafe(64))"`
- Set it: `export JWT_SECRET=<generated_secret>`

**Database connection errors**
- Wait for PostgreSQL to be ready (health check runs automatically)
- Check logs: `docker-compose logs db`

**Port already in use**
- Change the port in docker-compose.yml or stop the conflicting service

## License

Apache License 2.0 - see [LICENSE](LICENSE) for details.

SPDX-License-Identifier: Apache-2.0
