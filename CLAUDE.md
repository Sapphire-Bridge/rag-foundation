# CLAUDE.md - AI Assistant Guide for RAG Assistant Codebase

Repo Context Index (agent-discoverable)
- Context 001 — Backend Core, Config, Security: docs/context/CONTEXT-001.md
- Context 002 — Backend Models, Routes, RAG: docs/context/CONTEXT-002.md
- Context 003 — Frontend UI & Integration: docs/context/CONTEXT-003.md
- Context 004 — Migrations, Tests, OpenAPI, Ops: docs/context/CONTEXT-004.md

**Last Updated**: 2025-11-20
**Version**: 0.2.1
**License**: Apache 2.0

This document provides comprehensive guidance for AI assistants working on the RAG Assistant codebase. It covers architecture, conventions, workflows, and critical considerations for making changes safely and effectively.

---

## Table of Contents

1. [Project Overview](#project-overview)
2. [Quick Reference](#quick-reference)
3. [Codebase Architecture](#codebase-architecture)
4. [Technology Stack](#technology-stack)
5. [Development Workflows](#development-workflows)
6. [Code Conventions](#code-conventions)
7. [Security Guidelines](#security-guidelines)
8. [Testing Practices](#testing-practices)
9. [Common Operations](#common-operations)
10. [File Locations Reference](#file-locations-reference)
11. [Troubleshooting](#troubleshooting)

---

## Project Overview

### What is RAG Assistant?

A production-ready RAG (Retrieval-Augmented Generation) web application that enables users to upload documents and chat with them using Google's Gemini AI. Built with security, observability, and cost control as first-class concerns.

### Key Capabilities

- **Multi-tenant document stores** with JWT-based authentication
- **Real-time streaming** chat responses with source citations
- **File upload hardening** (PDF-only, strict validation)
- **Cost tracking** and budget enforcement
- **Production-ready observability** (Prometheus metrics, structured logging, health checks)
- **Rate limiting** (in-memory and Redis-backed)

### Project Statistics

- **Backend**: ~1,434 lines of Python (FastAPI)
- **Frontend**: ~274 lines of TypeScript/React
- **Database Models**: 5 tables (User, Store, Document, QueryLog, Budget)
- **API Endpoints**: 14 endpoints across 5 routers
- **Test Coverage**: ≥80% required

---

## Quick Reference

### Most Important Files

| File | Purpose | Key Notes |
|------|---------|-----------|
| `backend/app/main.py` | FastAPI application factory | Middleware registration order matters |
| `backend/app/config.py` | Configuration with validation | Has field validators that MUST pass |
| `backend/app/auth.py` | JWT authentication | HS256, minimal payload, tenant isolation; router is built via `build_router(settings)` with the default instance exported as `router` |
| `backend/app/services/gemini_rag.py` | Gemini API integration | Has retry logic with exponential backoff |
| `backend/app/routes/uploads.py` | File upload with security | Multi-layer validation (MIME, magic, sanitization) |
| `backend/app/models.py` | SQLAlchemy ORM models | Always filter by user_id for tenant isolation |
| `backend/app/schemas.py` | Pydantic request/response | All validation rules defined here |
| `frontend/src/App.tsx` | Main React component | State management for auth and stores |
| `backend/.env.example` | Environment configuration | Copy to `.env` and customize |

### Critical Environment Variables

```bash
# REQUIRED - Application will not start without these
JWT_SECRET=<64+ random chars>        # NEVER use default value
GEMINI_API_KEY=<your_api_key>        # Get from Google AI Studio

# SECURITY - Disable in production
ALLOW_DEV_LOGIN=false                # NEVER true in production

# Database
DATABASE_URL=sqlite:///./rag.db      # Use PostgreSQL in production

# Redis
REDIS_URL=redis://redis:6379/0       # Required in production when REQUIRE_REDIS_IN_PRODUCTION=true

# Cross-field invariants (enforced at startup in production)
# - ENVIRONMENT must be one of: development, test, staging, production
# - In ENVIRONMENT=production:
#     * ALLOW_DEV_LOGIN must be false
#     * DATABASE_URL must not be SQLite
#     * JWT_SECRET must not equal the known dev default
#     * REDIS_URL must be set when REQUIRE_REDIS_IN_PRODUCTION=true
# Misconfiguration will cause the process to fail fast on startup.

# Optional but recommended
CORS_ORIGINS=["http://localhost:5173"]
RATE_LIMIT_PER_MINUTE=120
MAX_UPLOAD_MB=25

# Advanced toggles
STRICT_MODE=true                   # Fail-fast security gate + strict pytest defaults
ALLOW_METADATA_FILTERS=false         # Enable only if you trust metadataFilter input from clients
FAST_TESTS=0                        # Backend helper script runs only smoke tests when set to 1
SKIP_STRICT_LINT=0                  # Skip ruff/mypy via helper script when 1
```

For the canonical list (including defaults, validation rules, and production invariants), see [`docs/configuration.md`](docs/configuration.md).

### Common Commands

```bash
# Backend development
cd backend
pip install -e .[test]               # Install with test dependencies
alembic upgrade head                 # Run migrations
uvicorn app.main:app --reload        # Start dev server
pytest --cov=app                     # Run tests with coverage
ruff check . && ruff format .        # Lint and format
mypy .                               # Type check
./scripts/test-backend.sh            # Wrapper honoring STRICT_MODE/FAST_TESTS toggles

# Frontend development
cd frontend
npm install                          # Install dependencies
npm run dev                          # Start dev server (port 5173)
npm run build                        # Production build
../scripts/test-frontend.sh          # Wrapper for npm test/build

# Docker
docker-compose up --build            # Start all services
docker-compose down -v               # Stop and remove volumes

# Database operations
alembic revision --autogenerate -m "description"  # Create migration
alembic upgrade head                               # Apply migrations
alembic downgrade -1                               # Rollback one migration
```

### API Endpoints Quick Reference

```
POST   /api/auth/register           - Create new user account
POST   /api/auth/login              - Login with credentials
POST   /api/auth/token              - Dev-only: Get token by email
GET    /api/stores                  - List user's document stores
POST   /api/stores                  - Create new document store
DELETE /api/stores/<id>             - Soft delete store + cascade docs, schedule Gemini cleanup
POST   /api/stores/<id>/restore     - Admin-only restore of soft-deleted store
POST   /api/upload                  - Upload file to store
GET    /api/upload/op-status/<id>  - Check indexing status
DELETE /api/documents/<doc_id>      - Soft delete document (hidden from future operations)
POST   /api/documents/<doc_id>/restore - Admin-only restore of document
POST   /api/chat                    - Stream chat responses (SSE)
GET    /api/costs/summary           - Monthly cost + token + budget summary
GET    /api/admin/users             - List users (admin-only)
POST   /api/admin/users/<id>/role   - Toggle user admin flag
POST   /api/admin/budgets/<id>      - Upsert monthly budgets
GET    /api/admin/audit             - Recent admin audit trail
GET    /api/admin/system/summary    - Lightweight system counts
POST   /api/admin/watchdog/reset-stuck - Admin watchdog for any tenant
GET    /health                      - Health check (200/503)
GET    /metrics                     - Prometheus metrics
GET    /docs                        - OpenAPI documentation
```

---

## Codebase Architecture

### Directory Structure

```
RAG/
├── backend/                        # Python FastAPI application
│   ├── app/
│   │   ├── routes/                # API endpoint handlers
│   │   │   ├── auth.py           # Registration, login, dev token
│   │   │   ├── chat.py           # Streaming chat endpoint
│   │   │   ├── costs.py          # Cost summary endpoint
│   │   │   ├── stores.py         # Store CRUD + delete/restore
│   │   │   ├── documents.py      # Document delete/restore endpoints
│   │   │   ├── uploads.py        # File upload with validation
│   │   │   └── admin.py          # Admin-only routes (users, budgets, watchdog)
│   │   ├── services/              # Business logic layer
│   │   │   ├── gemini_rag.py     # Gemini API wrapper with retries and streaming
│   │   │   ├── cleanup.py        # Remote cleanup helpers for soft deletes
│   │   │   ├── audit.py          # Admin audit logging helper
│   │   ├── main.py               # App factory & middleware setup
│   │   ├── config.py             # Pydantic settings with validators
│   │   ├── models.py             # SQLAlchemy ORM models
│   │   ├── schemas.py            # Pydantic validation schemas
│   │   ├── auth.py               # JWT token operations
│   │   ├── db.py                 # Database session management
│   │   ├── middleware.py         # Correlation ID middleware
│   │   ├── rate_limit.py         # Rate limiting (memory + Redis)
│   │   ├── metrics.py            # Prometheus metrics definitions
│   │   ├── costs.py              # Cost calculation utilities
│   │   └── telemetry.py          # Structured JSON logging
│   ├── alembic/                   # Database migrations
│   │   ├── versions/              # Migration scripts
│   │   │   ├── 0001_init.py
│   │   │   ├── 0002_add_auth_columns.py
│   │   │   ├── 0003_add_indexes.py
│   │   │   ├── 0004_add_unique_fs_name.py
│   │   │   ├── 0005_soft_delete.py
│   │   │   └── 0006_admin_rbac.py
│   │   └── env.py                 # Alembic configuration
│   ├── tests/                     # Unit & integration tests
│   │   ├── conftest.py            # Pytest fixtures
│   │   ├── test_auth.py
│   │   ├── test_gemini_rag.py
│   │   ├── test_streaming.py
│   │   ├── test_upload_validation.py
│   │   ├── test_soft_delete.py    # Store/document delete/restore coverage
│   │   ├── test_costs.py          # Pricing + budgeting logic
│   │   ├── test_admin_rbac.py     # Admin RBAC + watchdog flows
│   │   └── test_sse_smoke.py
│   ├── scripts/
│   │   └── export_openapi.py      # Generate OpenAPI spec
│   ├── pyproject.toml             # Dependencies & tool config
│   ├── requirements.lock          # Locked dependencies
│   ├── Dockerfile                 # Production container
│   ├── alembic.ini                # Alembic config file
│   └── .env.example               # Environment template
├── frontend/                       # React + Vite application
│   ├── src/
│   │   ├── components/
│   │   │   ├── LoginBox.tsx       # Auth UI (register/login/dev)
│   │   │   ├── UploadBox.tsx      # File upload with polling
│   │   │   ├── CostPanel.tsx      # Monthly cost display
│   │   │   └── CitationPanel.tsx  # Source citations
│   │   ├── App.tsx                # Main application
│   │   └── main.tsx               # React entry point
│   ├── index.html                 # HTML template
│   ├── vite.config.ts             # Vite config with proxy
│   ├── package.json               # NPM dependencies
│   └── tsconfig.json              # TypeScript config
├── docs/                          # Extra references
│   ├── context/CONTEXT-*.md       # Deep dives per subsystem
│   └── pricing.md                 # Pricing & budgeting configuration guide
├── .github/
│   ├── workflows/
│   │   └── ci.yml                 # CI pipeline (test, audit, lint)
│   ├── ISSUE_TEMPLATE/
│   ├── PULL_REQUEST_TEMPLATE.md
│   └── dependabot.yml             # Auto dependency updates
├── docker-compose.yml              # Multi-container orchestration
├── .pre-commit-config.yaml         # Git hooks (ruff)
├── README.md                       # Project overview
├── CONTRIBUTING.md                 # Development guidelines
├── SECURITY.md                     # Security policy
├── CODE_OF_CONDUCT.md              # Community guidelines
├── PRIVACY.md                      # Privacy policy
├── RELEASE.md                      # Release process
├── CHANGELOG.md                    # Version history
├── LICENSE                         # Apache 2.0
└── NOTICE                          # License notice
```

### Architectural Pattern

**Modified MVC with Service Layer**:

- **Routes (Controllers)**: Handle HTTP requests, validate input, return responses
- **Services**: Contain business logic, integrate with external APIs (Gemini)
- **Models**: Define database schema and relationships (SQLAlchemy ORM)
- **Schemas**: Define API contracts and validation rules (Pydantic)

**Dependency Flow**:
```
Routes → Services → External APIs (Gemini)
   ↓         ↓
Schemas   Models → Database
```

### Middleware Stack (Order Matters!)

The middleware in `backend/app/main.py` is applied in this order:

1. **CorrelationIdMiddleware** (first) - Adds `X-Correlation-ID` to all requests
2. **rate_limit_middleware** (early) - Rejects requests exceeding limits
3. **CORSMiddleware** - Handles CORS preflight and headers
4. **_http_metrics_middleware** - Records request count and duration
5. **_security_headers** - Adds security headers to responses
6. **_json_body_limit** - Enforces JSON body size limits

**Important**: Middleware is processed in the order registered. Do not change order without careful consideration.

### Database Schema

```sql
-- Users table
CREATE TABLE users (
    id INTEGER PRIMARY KEY,
    email TEXT UNIQUE NOT NULL,
    hashed_password TEXT NOT NULL,
    is_active BOOLEAN DEFAULT TRUE,
    email_verified BOOLEAN DEFAULT FALSE,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Stores table (document collections)
CREATE TABLE stores (
    id INTEGER PRIMARY KEY,
    user_id INTEGER REFERENCES users(id),
    display_name TEXT NOT NULL,
    fs_name TEXT UNIQUE,  -- Gemini store ID
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Documents table
CREATE TABLE documents (
    id INTEGER PRIMARY KEY,
    store_id INTEGER REFERENCES stores(id),
    filename TEXT NOT NULL,
    status TEXT NOT NULL,  -- PENDING, RUNNING, DONE, ERROR
    op_name TEXT,          -- Gemini operation ID
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Query logs (for cost tracking)
CREATE TABLE query_logs (
    id INTEGER PRIMARY KEY,
    user_id INTEGER REFERENCES users(id),
    store_id INTEGER REFERENCES stores(id),
    tokens INTEGER NOT NULL,
    cost_usd REAL NOT NULL,
    model TEXT NOT NULL,
    timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Budget limits
CREATE TABLE budgets (
    id INTEGER PRIMARY KEY,
    user_id INTEGER UNIQUE REFERENCES users(id),
    monthly_limit_usd REAL NOT NULL
);
```

**Indexes** (defined in migration 0003):
- `idx_stores_user_id` on `stores(user_id)`
- `idx_documents_store_id` on `documents(store_id)`
- `idx_query_logs_user_timestamp` on `query_logs(user_id, timestamp)`

---

## Technology Stack

### Backend Stack

| Technology | Version | Purpose |
|------------|---------|---------|
| Python | 3.11+ | Primary language |
| FastAPI | 0.115.0+ | Async web framework |
| Uvicorn | 0.30.0+ | ASGI server |
| Pydantic | 2.8.0+ | Data validation & settings |
| SQLAlchemy | 2.0.32+ | ORM for database access |
| Alembic | 1.13.2+ | Database migrations |
| google-genai | 1.0.0+ | Gemini API SDK |
| python-jose | 3.3.0+ | JWT encoding/decoding |
| passlib | 1.7.4+ | Password hashing (bcrypt) |
| tenacity | 9.0.0+ | Retry logic |
| prometheus-client | 0.20.0+ | Metrics export |
| psycopg2-binary | 2.9.9+ | PostgreSQL driver |
| redis | 5.0.0+ | Rate limiting backend |
| ruff | 0.6.8+ | Linter & formatter |
| mypy | 1.11.0+ | Type checking |
| pytest | 7.4.0+ | Testing framework |

### Frontend Stack

| Technology | Version | Purpose |
|------------|---------|---------|
| React | 18.2.0 | UI library |
| TypeScript | 5.4.0+ | Type safety |
| Vite | 5.3.0 | Build tool & dev server |
| @assistant-ui/react | Latest | Chat UI components |
| @assistant-ui/react-data-stream | Latest | SSE streaming |

### Infrastructure

- **Development DB**: SQLite (file-based)
- **Production DB**: PostgreSQL 16 (recommended)
- **Container**: Docker (multi-stage builds)
- **Orchestration**: Docker Compose
- **Base Image**: `python:3.11-slim` (pinned by SHA256)

### External Services

- **Gemini API** (Google GenAI Platform)
  - File Search with managed vector stores
  - Streaming text generation
  - Citation extraction via grounding metadata
  - Model: `gemini-2.5-flash` (default)

---

## Development Workflows

### Local Development Setup

**First-time setup**:

```bash
# 1. Clone repository
git clone <repo-url>
cd RAG

# 2. Backend setup
cd backend
python -m venv .venv
source .venv/bin/activate  # Windows: .venv\Scripts\activate
pip install -e .[test]
cp .env.example .env
# Edit .env: Set JWT_SECRET (64+ chars) and GEMINI_API_KEY

# 3. Run migrations
alembic upgrade head

# 4. Start backend (terminal 1)
uvicorn app.main:app --reload

# 5. Frontend setup (terminal 2)
cd ../frontend
npm install
npm run dev
```

**Access**:
- Backend: http://localhost:8000
- Frontend: http://localhost:5173
- API Docs: http://localhost:8000/docs
- Metrics: http://localhost:8000/metrics

### Docker Development

```bash
# Set environment
export GEMINI_API_KEY=your_key_here

# Start all services (PostgreSQL, backend, frontend)
docker-compose up --build

# Stop and clean
docker-compose down -v
```

### CI/CD Pipeline

**GitHub Actions** (`.github/workflows/ci.yml`):

Runs on: Push and Pull Request

**Steps**:
1. **Test & Coverage** (Python 3.11)
   - Install from `requirements.lock`
   - Run Alembic migrations
   - Execute `pytest --cov=app --cov-report=term --cov-fail-under=80`
   - **Fails if coverage < 80%**

2. **Security Audits**
   - `pip-audit --strict` (checks backend dependencies)
   - `npm audit --production --audit-level=high` (checks frontend)
   - SBOM generation with Anchore (SPDX JSON format)

3. **Frontend Quality Gates**
   - `npm test -- --coverage` (frontend unit tests, coverage enforced via Jest config)
   - `npm run build` (production build must succeed)

4. **Caching**
   - `actions/cache` for `~/.cache/pip` keyed by `backend/requirements.lock`
   - `actions/cache` for `~/.npm` keyed by `frontend/package-lock.json`
   - Keeps CI fast while remaining reproducible

5. **Code Quality**
   - `ruff check .` (linting)
   - `ruff format --check .` (formatting verification)
   - `mypy .` (type checking in strict mode)

6. **API Contract**
   - Export OpenAPI spec: `python scripts/export_openapi.py`
   - Compare with committed spec
   - **Fails on drift** (schema changes must be intentional)

### Pre-commit Hooks

**Setup** (one-time):
```bash
cd backend
pre-commit install
```

**Hooks** (`.pre-commit-config.yaml`):
- Ruff linting (`ruff check`)
- Ruff formatting (`ruff format`)
- Runs automatically on `git commit`

**Manual execution**:
```bash
pre-commit run --all-files
```

### Database Migrations

**Create new migration**:
```bash
cd backend
alembic revision --autogenerate -m "Add new column to users"
# Review generated migration in alembic/versions/
```

**Apply migrations**:
```bash
alembic upgrade head           # Apply all pending
alembic upgrade +1             # Apply next one
alembic upgrade <revision_id>  # Apply to specific revision
```

**Rollback**:
```bash
alembic downgrade -1           # Rollback one migration
alembic downgrade <revision_id> # Rollback to specific revision
```

**Check current version**:
```bash
alembic current
```

**View migration history**:
```bash
alembic history --verbose
```

### Branch Strategy

From CONTRIBUTING.md:

- **main**: Production-ready code
- **feature/your-feature-name**: New features
- **fix/issue-description**: Bug fixes
- **docs/update-description**: Documentation updates

**Commit Guidelines**:
- Imperative mood: "Add feature" not "Added feature"
- Reference issues: `Fix #123: resolve upload timeout`
- Sign commits if possible: `git commit -S`

---

## Code Conventions

### Naming Conventions

**Backend (Python)**:

| Type | Convention | Example |
|------|------------|---------|
| Files | snake_case | `gemini_rag.py`, `rate_limit.py` |
| Classes | PascalCase | `GeminiRag`, `User`, `StoreCreate` |
| Functions | snake_case | `create_access_token()`, `get_current_user()` |
| Constants | UPPER_SNAKE_CASE | `JWT_SECRET`, `MAX_UPLOAD_MB` |
| Private | _leading_underscore | `_now()`, `_pack()` |
| Protected | _leading_underscore | `_http_metrics_middleware()` |

**Frontend (TypeScript/React)**:

| Type | Convention | Example |
|------|------------|---------|
| Components | PascalCase | `LoginBox.tsx`, `UploadBox` |
| Functions | camelCase | `setAuthToken()`, `refreshStores()` |
| Variables | camelCase | `authToken`, `isLoading` |
| Constants | UPPER_SNAKE_CASE | `API_BASE_URL` |

### Code Style

**Backend**:
- **Line length**: 120 characters (ruff config)
- **Imports**: Organized (stdlib → third-party → local)
- **Type hints**: Required on all functions (mypy strict mode)
- **Docstrings**: Google style for public APIs
- **Async/await**: Use for I/O operations

**Example**:
```python
async def create_store(
    request: StoreCreate,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> Store:
    """Create a new document store for the authenticated user.

    Args:
        request: Store creation parameters
        db: Database session (injected)
        user: Authenticated user (injected)

    Returns:
        Created store object

    Raises:
        HTTPException: If Gemini API call fails
    """
    # Implementation
```

**Frontend**:
- **Functional components**: Prefer over class components
- **Hooks**: Use for state and effects
- **TypeScript**: Strict mode enabled
- **Props**: Define explicit interfaces

### Dependency Injection Pattern

FastAPI uses dependency injection extensively:

```python
# Define dependency
def get_db() -> Generator[Session, None, None]:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

# Use in route
@router.get("/stores")
async def list_stores(
    db: Session = Depends(get_db),           # DB session injected
    user: User = Depends(get_current_user),  # User from JWT injected
) -> list[StoreOut]:
    return db.query(Store).filter(Store.user_id == user.id).all()
```

**Common dependencies**:
- `Depends(get_db)` - Database session
- `Depends(get_current_user)` - Authenticated user (validates JWT)
- `Depends(settings)` - Application settings

### Error Handling Patterns

**Backend**:

```python
# Client errors (4xx)
raise HTTPException(
    status_code=404,
    detail="Store not found"  # Safe for client
)

# Validation errors (automatic via Pydantic)
class StoreCreate(BaseModel):
    display_name: str = Field(..., min_length=1, max_length=100)

# Server errors (5xx) - caught by global handler
try:
    result = await external_api_call()
except Exception as e:
    logger.exception("Gemini API error", correlation_id=request_id)
    # Global handler returns generic "Internal server error"
    raise
```

**Retry logic** (using tenacity):

```python
from tenacity import retry, stop_after_attempt, wait_exponential

@retry(
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=0.5, min=1, max=5),
    retry=retry_if_exception_type((ServerError, TimeoutError)),
)
async def ask_gemini(query: str) -> str:
    # Will retry up to 3 times with exponential backoff
    return await gemini_client.generate(query)
```

### Logging Standards

**Structured logging** (`backend/app/telemetry.py`):

```python
import logging

logger = logging.getLogger(__name__)

# Always include correlation_id
logger.info(
    "User authenticated",
    extra={
        "correlation_id": request.state.correlation_id,
        "user_id": user.id,
        "email": user.email,
    }
)

# Error logging with exception info
logger.exception(
    "Failed to upload file",
    extra={
        "correlation_id": request_id,
        "filename": filename,
    },
    exc_info=True,
)
```

**Output format** (JSON):
```json
{
  "timestamp": "2025-11-17T10:30:45.123Z",
  "level": "INFO",
  "message": "User authenticated",
  "correlation_id": "abc123",
  "user_id": 42,
  "email": "user@example.com"
}
```

---

## Security Guidelines

### CRITICAL Security Rules

**NEVER**:
- Commit secrets (API keys, JWT secrets) to git
- Use default or weak JWT_SECRET in production
- Enable `ALLOW_DEV_LOGIN=true` in production
- Disable tenant isolation checks
- Trust client input without validation
- Return detailed error messages to clients
- Store plaintext passwords

**ALWAYS**:
- Filter database queries by `user_id` for tenant isolation
- Validate file uploads (MIME, magic number, size, filename)
- Use parameterized queries (SQLAlchemy ORM prevents SQL injection)
- Hash passwords with bcrypt
- Set secure CORS origins (not `*`)
- Log security-relevant events with correlation IDs
- Rate limit API endpoints

### Authentication Implementation

**JWT Structure** (`backend/app/auth.py`):

```python
def create_access_token(*, user_id: int, email: str = "") -> str:
    """Create JWT with minimal payload (no PII)."""
    issued_at = int(time.time())
    payload = {
        "sub": str(user_id),          # Subject: user ID only
        "iss": settings.JWT_ISSUER,   # Issuer: rag-assistant
        "aud": settings.JWT_AUDIENCE, # Audience: rag-users
        "iat": issued_at,
        "exp": issued_at + settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60,
        "jti": str(uuid.uuid4()),     # JWT ID for revocation tracking
    }
    return jwt.encode(payload, settings.JWT_SECRET, algorithm="HS256")
```

**Token validation**:
```python
def get_current_user(
    token: str = Depends(oauth2_scheme),
    db: Session = Depends(get_db),
) -> User:
    """Validate JWT and return authenticated user."""
    try:
        payload = jwt.decode(
            token,
            JWT_SECRET,
            algorithms=["HS256"],
            audience=JWT_AUDIENCE,
            issuer=JWT_ISSUER,
        )
        user_id = int(payload["sub"])
    except JWTError:
        raise HTTPException(401, detail="Invalid token")

    user = db.query(User).filter(User.id == user_id).first()
    if not user or not user.is_active:
        raise HTTPException(401, detail="User not found")

    return user
```

**Revocation flow**:
- `/api/auth/logout` decodes the bearer token, extracts `jti`/`exp`, and writes `revoked:{jti}` to Redis with a TTL matching `exp - now`.
- `get_current_user` checks Redis (`revoked:{jti}`) before loading the user; if it exists, the request fails with HTTP 401.
- If Redis is unavailable the logout handler still returns success, but revocation falls back to the short token lifetime.

### Tenant Isolation Pattern

**CRITICAL**: Every query accessing user data MUST filter by `user_id`.

**Correct** (tenant-isolated):
```python
@router.delete("/stores/{store_id}")
async def delete_store(
    store_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    store = db.query(Store).filter(
        Store.id == store_id,
        Store.user_id == user.id,      # ← Tenant filter
        Store.deleted_at.is_(None),    # ← Ignore already deleted rows
    ).first()

    if not store:
        raise HTTPException(404, detail="Store not found")

    deleted_at = store.soft_delete()
    db.query(Document).filter(
        Document.store_id == store_id,
        Document.deleted_at.is_(None),
    ).update({"deleted_at": deleted_at}, synchronize_session=False)
    db.commit()
```

**WRONG** (security vulnerability):
```python
# BAD: Missing user_id filter allows cross-tenant access
store = db.query(Store).filter(Store.id == store_id).first()
```

### File Upload Security

**Multi-layer validation** (`backend/app/routes/uploads.py`):

1. **MIME Type Allowlist**:
   Upload acceptance is governed by `UPLOAD_PROFILE`/`ALLOWED_UPLOAD_MIMES` rather than a hard-coded set.
   - `safe` (default): PDF + plain/markdown/CSV/TSV
   - `office`: `safe` plus Word/Excel/PowerPoint/OpenDocument formats
   - `all-supported`: the entire Gemini-supported text + application MIME set defined in `app/file_types.py`
   - `custom`: use the exact list from `ALLOWED_UPLOAD_MIMES`
   During startup, `Settings.apply_upload_profile` normalizes every entry to lower case and verifies it’s included in `GEMINI_SUPPORTED_MIMES`, preventing configuration drift.

2. **Magic Number Validation** (post-save):
   ```python
   def validate_file_magic(filepath: str, expected_mime: str) -> bool:
       with open(filepath, "rb") as f:
           header = f.read(8)

       if expected_mime == "application/pdf":
           return header.startswith(b"%PDF-")
       elif "wordprocessing" in expected_mime:  # DOCX
           return header.startswith(b"PK\x03\x04")  # ZIP signature
       # ... more checks
   ```

3. **Filename Sanitization**:
   ```python
   def sanitize_filename(filename: str) -> str:
       # Remove path components
       filename = os.path.basename(filename)
       # Replace dangerous chars with underscore
       filename = re.sub(r'[^A-Za-z0-9._-]+', '_', filename)
       # Remove leading dots
       filename = filename.lstrip('.')
       # Truncate
       return filename[:128]
   ```

4. **Size Limit** (streaming check):
   ```python
   MAX_UPLOAD_BYTES = settings.MAX_UPLOAD_MB * 1024 * 1024

   size = 0
   async for chunk in file.stream:
       size += len(chunk)
       if size > MAX_UPLOAD_BYTES:
           raise HTTPException(413, detail="File too large")
       f.write(chunk)
   ```

5. **Secure File Creation**:
   ```python
   # Atomic create with exclusive flag (prevents race conditions)
   fd = os.open(dest_path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
   with os.fdopen(fd, 'wb') as f:
       # Write file
   ```

### Rate Limiting

**Configuration**:
```python
# In-memory (development)
RATE_LIMIT_PER_MINUTE=120

# Redis (production) - set REDIS_URL
REDIS_URL=redis://localhost:6379/0
```

**Implementation** (`backend/app/rate_limit.py`):
- Fixed window algorithm (simple and performant)
- Per-user rate limiting (authenticated)
- Per-IP rate limiting (anonymous)
- Returns `429 Too Many Requests` with `Retry-After` header

**Headers**:
```
X-RateLimit-Limit: 120
X-RateLimit-Remaining: 115
Retry-After: 45
```

### Security Headers

Automatically added by middleware:

```python
X-Content-Type-Options: nosniff
Referrer-Policy: strict-origin-when-cross-origin
X-Frame-Options: DENY
```

### Secrets Management

**Development**:
```bash
# Generate strong JWT secret
python -c "import secrets; print(secrets.token_urlsafe(64))"

# Add to .env (NEVER commit)
JWT_SECRET=<generated_secret>
```

**Production**:
- Use environment variables or secret management service (AWS Secrets Manager, HashiCorp Vault)
- Rotate JWT_SECRET periodically
- Monitor for leaked secrets in git history

---

## Testing Practices

### Test Structure

**Backend tests** (`backend/tests/`):

```
tests/
├── conftest.py              # Pytest fixtures
├── test_auth.py             # Authentication flows
├── test_gemini_rag.py       # Gemini API integration
├── test_streaming.py        # SSE streaming
├── test_upload_validation.py # File upload security
└── test_sse_smoke.py        # Basic SSE connectivity
```

**Coverage requirements**:
- Backend: ≥80% (enforced in CI)
- New features: MUST include tests
- Critical paths: Aim for 100% (auth, uploads, tenant isolation)

### Running Tests

**Full test suite**:
```bash
cd backend
pytest
```

**With coverage**:
```bash
pytest --cov=app --cov-report=html --cov-report=term
# View HTML report: open htmlcov/index.html
```

**Specific test file**:
```bash
pytest tests/test_auth.py -v
```

**Specific test**:
```bash
pytest tests/test_auth.py::test_register_success -v
```

**With logs**:
```bash
pytest -s  # Show print/log output
```

### Writing Tests

**Example test** (`tests/test_auth.py`):

```python
import pytest
from fastapi.testclient import TestClient
from app.main import create_app

@pytest.fixture
def client():
    """Test client with in-memory database."""
    app = create_app()
    return TestClient(app)

def test_register_success(client):
    """Test successful user registration."""
    response = client.post("/api/auth/register", json={
        "email": "test@example.com",
        "password": "SecurePass123!"
    })

    assert response.status_code == 201
    data = response.json()
    assert data["email"] == "test@example.com"
    assert "id" in data
    assert "password" not in data  # Never return password

def test_register_duplicate_email(client):
    """Test registration with duplicate email fails."""
    # First registration
    client.post("/api/auth/register", json={
        "email": "test@example.com",
        "password": "SecurePass123!"
    })

    # Duplicate registration
    response = client.post("/api/auth/register", json={
        "email": "test@example.com",
        "password": "DifferentPass456!"
    })

    assert response.status_code == 400
    assert "already registered" in response.json()["detail"]
```

**Testing tenant isolation**:

```python
def test_cannot_access_other_user_store(client, db):
    """Test that users cannot access other users' stores."""
    # Create two users
    user1 = create_user(db, "user1@example.com")
    user2 = create_user(db, "user2@example.com")

    # User1 creates store
    token1 = create_access_token(user1.id)
    response = client.post(
        "/api/stores",
        headers={"Authorization": f"Bearer {token1}"},
        json={"display_name": "User1 Store"}
    )
    store_id = response.json()["id"]

    # User2 tries to access User1's store
    token2 = create_access_token(user2.id)
    response = client.get(
        f"/api/stores/{store_id}",
        headers={"Authorization": f"Bearer {token2}"}
    )

    assert response.status_code == 404  # Store not found (not accessible)
```

**Mocking external APIs**:

```python
from unittest.mock import patch, MagicMock

@patch('app.services.gemini_rag.GeminiRag.ask')
def test_chat_endpoint(mock_ask, client):
    """Test chat endpoint with mocked Gemini API."""
    mock_ask.return_value = "Mocked response"

    response = client.post("/api/chat", json={
        "store_id": 1,
        "query": "What is this about?"
    })

    assert response.status_code == 200
    assert "Mocked response" in response.text
    mock_ask.assert_called_once()
```

### Test Fixtures

**Common fixtures** (`tests/conftest.py`):

```python
@pytest.fixture
def db():
    """In-memory SQLite database for testing."""
    # Setup
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    SessionLocal = sessionmaker(bind=engine)
    db = SessionLocal()

    yield db

    # Teardown
    db.close()

@pytest.fixture
def auth_headers(db):
    """Create user and return auth headers."""
    user = User(email="test@example.com", hashed_password=hash_password("test123"))
    db.add(user)
    db.commit()

    token = create_access_token(user.id)
    return {"Authorization": f"Bearer {token}"}
```

---

## Common Operations

### Adding a New API Endpoint

**Steps**:

1. **Define Pydantic schemas** (`backend/app/schemas.py`):
   ```python
   class FeatureCreate(BaseModel):
       name: str = Field(..., min_length=1, max_length=100)
       enabled: bool = True

   class FeatureOut(BaseModel):
       id: int
       name: str
       enabled: bool
       created_at: datetime

       class Config:
           from_attributes = True
   ```

2. **Create database model** (`backend/app/models.py`):
   ```python
   class Feature(Base):
       __tablename__ = "features"

       id = Column(Integer, primary_key=True)
       user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
       name = Column(String(100), nullable=False)
       enabled = Column(Boolean, default=True)
       created_at = Column(DateTime, default=datetime.utcnow)

       user = relationship("User", back_populates="features")
   ```

3. **Generate migration**:
   ```bash
   cd backend
   alembic revision --autogenerate -m "Add features table"
   # Review migration in alembic/versions/
   alembic upgrade head
   ```

4. **Create route** (`backend/app/routes/features.py`):
   ```python
   from fastapi import APIRouter, Depends, HTTPException
   from sqlalchemy.orm import Session
   from app.auth import get_current_user
   from app.db import get_db
   from app.models import Feature, User
   from app.schemas import FeatureCreate, FeatureOut

   router = APIRouter(prefix="/api/features", tags=["features"])

   @router.post("", response_model=FeatureOut, status_code=201)
   async def create_feature(
       request: FeatureCreate,
       db: Session = Depends(get_db),
       user: User = Depends(get_current_user),
   ):
       """Create a new feature for the authenticated user."""
       feature = Feature(
           user_id=user.id,
           name=request.name,
           enabled=request.enabled,
       )
       db.add(feature)
       db.commit()
       db.refresh(feature)
       return feature

   @router.get("", response_model=list[FeatureOut])
   async def list_features(
       db: Session = Depends(get_db),
       user: User = Depends(get_current_user),
   ):
       """List all features for the authenticated user."""
       return db.query(Feature).filter(Feature.user_id == user.id).all()
   ```

5. **Register router** (`backend/app/main.py`):
   ```python
   from app.routes import features

   app.include_router(features.router)
   ```

6. **Write tests** (`backend/tests/test_features.py`):
   ```python
   def test_create_feature(client, auth_headers):
       response = client.post(
           "/api/features",
           headers=auth_headers,
           json={"name": "Test Feature", "enabled": True}
       )
       assert response.status_code == 201
       data = response.json()
       assert data["name"] == "Test Feature"
       assert data["enabled"] is True
   ```

7. **Update OpenAPI spec**:
   ```bash
   python scripts/export_openapi.py
   git add backend/openapi.yaml
   ```

### Adding a Database Migration

**Scenario**: Add a new column to existing table

```bash
# 1. Edit model
# backend/app/models.py
class User(Base):
    # ... existing fields ...
    phone = Column(String(20), nullable=True)  # New field

# 2. Generate migration
cd backend
alembic revision --autogenerate -m "Add phone to users"

# 3. Review generated migration
# alembic/versions/XXXX_add_phone_to_users.py

# 4. Test migration (up)
alembic upgrade head

# 5. Test rollback (down)
alembic downgrade -1

# 6. Re-apply if tests pass
alembic upgrade head

# 7. Commit migration file
git add alembic/versions/XXXX_add_phone_to_users.py
git commit -m "Add phone column to users table"
```

**Manual migration** (if autogenerate doesn't work):

```python
# alembic/versions/XXXX_add_phone_to_users.py
from alembic import op
import sqlalchemy as sa

def upgrade():
    op.add_column('users', sa.Column('phone', sa.String(20), nullable=True))
    op.create_index('idx_users_phone', 'users', ['phone'])

def downgrade():
    op.drop_index('idx_users_phone', 'users')
    op.drop_column('users', 'phone')
```

### Adding a New Frontend Component

**Steps**:

1. **Create component file** (`frontend/src/components/NewFeature.tsx`):
   ```tsx
   import React, { useState } from 'react';

   interface NewFeatureProps {
     title: string;
     onSubmit: (data: string) => void;
   }

   export function NewFeature({ title, onSubmit }: NewFeatureProps) {
     const [value, setValue] = useState('');

     const handleSubmit = () => {
       if (value.trim()) {
         onSubmit(value);
         setValue('');
       }
     };

     return (
       <div className="new-feature">
         <h2>{title}</h2>
         <input
           value={value}
           onChange={(e) => setValue(e.target.value)}
           placeholder="Enter value"
         />
         <button onClick={handleSubmit}>Submit</button>
       </div>
     );
   }
   ```

2. **Use in App** (`frontend/src/App.tsx`):
   ```tsx
   import { NewFeature } from './components/NewFeature';

   function App() {
     const handleFeatureSubmit = (data: string) => {
       console.log('Submitted:', data);
       // API call here
     };

     return (
       <div>
         {/* ... existing components ... */}
         <NewFeature title="My Feature" onSubmit={handleFeatureSubmit} />
       </div>
     );
   }
   ```

### Updating Dependencies

**Backend**:

```bash
cd backend

# Update specific package
pip install --upgrade fastapi

# Update all packages (careful!)
pip install --upgrade -r requirements.txt

# Lock dependencies
pip freeze > requirements.lock

# Test
pytest

# Commit if tests pass
git add requirements.lock
git commit -m "Update dependencies"
```

**Frontend**:

```bash
cd frontend

# Update specific package
npm update react

# Update all packages
npm update

# Audit for vulnerabilities
npm audit
npm audit fix

# Test
npm run build

# Commit if build succeeds
git add package.json package-lock.json
git commit -m "Update frontend dependencies"
```

**Dependabot**: Automated updates configured in `.github/dependabot.yml`

---

## File Locations Reference

### Configuration Files

| File | Purpose | Key Settings |
|------|---------|--------------|
| `backend/.env` | Environment variables (DO NOT COMMIT) | JWT_SECRET, GEMINI_API_KEY, DATABASE_URL |
| `backend/.env.example` | Environment template | Copy to .env and customize |
| `backend/pyproject.toml` | Python package config | Dependencies, tool settings (ruff, mypy) |
| `backend/alembic.ini` | Alembic configuration | Database URL, migration settings |
| `frontend/vite.config.ts` | Vite build configuration | Proxy settings for API |
| `frontend/tsconfig.json` | TypeScript configuration | Compiler options |
| `docker-compose.yml` | Multi-container orchestration | Service definitions, ports, volumes |
| `.github/workflows/ci.yml` | CI/CD pipeline | Test, lint, audit steps |
| `.pre-commit-config.yaml` | Git pre-commit hooks | Ruff linting and formatting |

### Key Source Files

**Backend Core**:
- `backend/app/main.py` - FastAPI app factory, middleware setup
- `backend/app/config.py` - Settings with validation
- `backend/app/models.py` - Database models (SQLAlchemy)
- `backend/app/schemas.py` - API schemas (Pydantic)
- `backend/app/auth.py` - JWT operations
- `backend/app/db.py` - Database session management

**Backend Routes**:
- `backend/app/routes/auth.py` - Authentication endpoints
- `backend/app/routes/stores.py` - Document store CRUD
- `backend/app/routes/uploads.py` - File upload with validation
- `backend/app/routes/chat.py` - Streaming chat endpoint
- `backend/app/routes/costs.py` - Cost summary endpoint

**Backend Services**:
- `backend/app/services/gemini_rag.py` - Gemini API integration and streaming helpers

**Backend Utilities**:
- `backend/app/middleware.py` - Correlation ID middleware
- `backend/app/rate_limit.py` - Rate limiting
- `backend/app/metrics.py` - Prometheus metrics
- `backend/app/costs.py` - Cost calculation
- `backend/app/telemetry.py` - Structured logging

**Frontend**:
- `frontend/src/main.tsx` - React entry point
- `frontend/src/App.tsx` - Main application component
- `frontend/src/components/LoginBox.tsx` - Authentication UI
- `frontend/src/components/UploadBox.tsx` - File upload UI
- `frontend/src/components/CostPanel.tsx` - Cost display
- `frontend/src/components/CitationPanel.tsx` - Citation display

---

## Troubleshooting

### Common Issues

#### Backend Won't Start

**Error**: `ValueError: JWT_SECRET validation failed`

**Cause**: JWT_SECRET not set or using default value

**Solution**:
```bash
# Generate strong secret
python -c "import secrets; print(secrets.token_urlsafe(64))"

# Add to backend/.env
JWT_SECRET=<generated_value>
```

---

**Error**: `ValueError: GEMINI_API_KEY validation failed`

**Cause**: GEMINI_API_KEY not set or placeholder value

**Solution**:
```bash
# Get API key from https://aistudio.google.com/app/apikey
# Add to backend/.env
GEMINI_API_KEY=<your_actual_key>
```

---

**Error**: `sqlalchemy.exc.OperationalError: no such table: users`

**Cause**: Database migrations not run

**Solution**:
```bash
cd backend
alembic upgrade head
```

---

**Error**: Cost summary always returns zero

**Cause**: Pricing env vars are unset or zero so cost tracking stays disabled.

**Solution**:
1. Set `PRICE_PER_MTOK_INPUT/OUTPUT/INDEX` in `.env` to non-zero values (see `docs/pricing.md` for defaults).
2. (Optional) enable `PRICE_CHECK_STRICT=true` to enforce the values outside production.
3. Restart the backend so settings reload; the app refuses to start in production when any pricing value is zero.

---

#### Authentication Issues

**Error**: `401 Unauthorized` on all endpoints

**Cause**: Invalid or expired JWT token

**Solution**:
1. Check token in `Authorization: Bearer <token>` header
2. Verify JWT_SECRET matches between token creation and validation
3. Check token expiration (default: 24 hours)
4. Re-login to get fresh token

---

**Error**: `404 Store not found` (but store exists)

**Cause**: Tenant isolation - accessing another user's store

**Solution**:
- Verify token belongs to correct user
- Check `Store.user_id` matches authenticated user
- Review query filters for `user_id`

---

#### File Upload Issues

**Error**: `413 Payload Too Large`

**Cause**: File exceeds `MAX_UPLOAD_MB` limit

**Solution**:
```bash
# Increase limit in backend/.env
MAX_UPLOAD_MB=50
```

---

**Error**: `415 Unsupported Media Type`

**Cause**: File type not in MIME allowlist

**Solution**:
- Check `UPLOAD_PROFILE`/`ALLOWED_UPLOAD_MIMES` in `backend/app/config.py` or `.env`
- Ensure file has correct MIME type
- PDF must start with `%PDF-`
- DOCX must be valid ZIP with `[Content_Types].xml`

---

**Error**: `400 Filename sanitization failed`

**Cause**: Filename contains only invalid characters

**Solution**:
- Use alphanumeric filenames with dots, hyphens, underscores
- Avoid special characters: `!@#$%^&*()[]{}|<>?`

---

#### Database Migration Issues

**Error**: `alembic.util.exc.CommandError: Target database is not up to date`

**Cause**: Database version doesn't match code migrations

**Solution**:
```bash
# Check current version
alembic current

# Apply pending migrations
alembic upgrade head

# If conflicts, may need to resolve manually
alembic history --verbose
```

---

**Error**: `sqlalchemy.exc.IntegrityError: FOREIGN KEY constraint failed`

**Cause**: Attempting to delete record with dependent records

**Solution**:
- Delete dependent records first (e.g., documents before store)
- Or use `CASCADE` in foreign key definition
- Review migration for proper cascading behavior

---

#### Gemini API Issues

**Error**: `ServerError: 503 Service Unavailable`

**Cause**: Gemini API temporary outage or rate limit

**Solution**:
- Retry logic will automatically retry (3 attempts)
- Check Gemini API status page
- Verify API key is valid and has quota

---

**Error**: `TimeoutError: Request timed out`

**Cause**: Gemini request exceeded 60s timeout

**Solution**:
```bash
# Increase timeout in backend/.env
GEMINI_HTTP_TIMEOUT_S=120
```

---

#### Frontend Issues

**Error**: `CORS error` in browser console

**Cause**: Frontend origin not in CORS allowlist

**Solution**:
```bash
# Add frontend origin to backend/.env
CORS_ORIGINS=["http://localhost:5173", "https://yourdomain.com"]
```

---

**Error**: `Failed to fetch` on API calls

**Cause**: Backend not running or incorrect proxy configuration

**Solution**:
1. Check backend is running: `curl http://localhost:8000/health`
2. Verify proxy in `frontend/vite.config.ts`:
   ```ts
   server: {
     proxy: {
       '/api': 'http://localhost:8000'
     }
   }
   ```

---

#### Docker Issues

**Error**: `docker-compose up` fails with `port already in use`

**Cause**: Port 8000 or 5173 already bound

**Solution**:
```bash
# Find process using port
lsof -i :8000
kill <PID>

# Or change port in docker-compose.yml
```

---

**Error**: `Failed to connect to database`

**Cause**: PostgreSQL container not ready when backend starts

**Solution**:
- docker-compose has `depends_on` but no health check wait
- Backend will retry connection
- Or add `wait-for-it.sh` script to backend entrypoint

---

### Debugging Tips

**Enable verbose logging**:
```bash
# Backend
LOG_LEVEL=DEBUG uvicorn app.main:app --reload

# Frontend
VITE_DEBUG=true npm run dev
```

**Check logs with correlation IDs**:
```bash
# All requests have X-Correlation-ID
# Search logs for specific request
grep "abc123" backend.log
```

**Test endpoints with curl**:
```bash
# Health check
curl http://localhost:8000/health

# Register user
curl -X POST http://localhost:8000/api/auth/register \
  -H "Content-Type: application/json" \
  -d '{"email":"test@example.com","password":"SecurePass123!"}'

# Login
curl -X POST http://localhost:8000/api/auth/login \
  -H "Content-Type: application/json" \
  -d '{"email":"test@example.com","password":"SecurePass123!"}'

# List stores (with auth)
curl http://localhost:8000/api/stores \
  -H "Authorization: Bearer <token>"
```

**Inspect database**:
```bash
# SQLite
sqlite3 backend/rag.db
> .tables
> SELECT * FROM users;

# PostgreSQL (Docker)
docker-compose exec db psql -U postgres -d rag
# \dt                 -- List tables
# SELECT * FROM users;
```

**Monitor Prometheus metrics**:
```bash
curl http://localhost:8000/metrics
```

**Profile slow endpoints**:
```python
# Add to route
import time
start = time.time()
# ... operation ...
logger.info(f"Operation took {time.time() - start:.2f}s")
```

---

## Appendix: Common Code Patterns

### Authenticated Endpoint Pattern

```python
@router.get("/resource")
async def get_resource(
    resource_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Get resource for authenticated user."""
    resource = db.query(Resource).filter(
        Resource.id == resource_id,
        Resource.user_id == user.id,  # Tenant isolation
    ).first()

    if not resource:
        raise HTTPException(404, detail="Resource not found")

    return resource
```

### Streaming Response Pattern

```python
from fastapi.responses import StreamingResponse

@router.post("/stream")
async def stream_response(
    request: StreamRequest,
    user: User = Depends(get_current_user),
):
    """Stream response to client."""
    async def generate():
        async for chunk in some_async_generator():
            yield f"data: {chunk}\n\n"

    return StreamingResponse(
        generate(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
        }
    )
```

### Cost Tracking Pattern

```python
from app.costs import estimate_cost

async def query_with_cost_tracking(query: str, user: User, db: Session):
    """Execute query and track cost."""
    # Check budget
    budget = get_user_budget(db, user.id)
    monthly_spent = get_monthly_spent(db, user.id)

    if monthly_spent >= budget.monthly_limit_usd:
        raise HTTPException(402, detail="Budget exceeded")

    # Execute query
    response = await gemini_client.query(query)

    # Log cost
    cost = estimate_cost(response.tokens, model="gemini-2.5-flash")
    log_query(db, user.id, response.tokens, cost)

    return response
```

---

## Conclusion

This guide provides comprehensive information for AI assistants working on the RAG Assistant codebase. Key principles to remember:

1. **Security First**: Always validate, always filter by user_id, never trust input
2. **Type Safety**: Use type hints, run mypy, leverage Pydantic validation
3. **Test Thoroughly**: Maintain ≥80% coverage, test tenant isolation, test edge cases
4. **Document Changes**: Update this file, update OpenAPI spec, write clear commit messages
5. **Follow Conventions**: Naming, code style, error handling patterns
6. **Monitor & Log**: Use correlation IDs, structured logging, Prometheus metrics

For questions or clarifications, refer to:
- `README.md` - Project overview and quick start
- `CONTRIBUTING.md` - Development guidelines
- `SECURITY.md` - Security policy
- `/docs` endpoint - Interactive API documentation

**Version**: This document reflects codebase version 0.2.1 as of 2025-11-20.
