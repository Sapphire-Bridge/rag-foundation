# CLAUDE.md — RAG Assistant

Guide for AI agents and engineers working in this repo. Written to be trusted: every
specific claim below was checked against the code at the cited path. When in doubt,
the code and the linked source-of-truth docs win over this file.

- **Stack:** FastAPI (Python 3.11) backend, React 18 + Vite (TypeScript) frontend, Google Gemini for RAG.
- **App version:** `0.2.1` (`backend/app/main.py`, `FastAPI(version=...)`).
- **Size (approx, app code only):** backend `~6.3k` LOC under `backend/app/`, frontend `~4.6k` LOC under `frontend/src/`.
- **License:** Apache-2.0 (SPDX headers on source files).

## Architecture in one paragraph

A multi-tenant "chat with your documents" service. Users register/login (JWT, HS256),
create document **stores**, upload files into them, and chat against one or more stores.
The backend is a layered FastAPI app: routes in `backend/app/routes/` (8 routers:
`auth, stores, documents, uploads, chat, costs, settings, admin`) handle HTTP and
validation; `backend/app/services/` holds business logic, the largest being
`gemini_rag.py` (Gemini SDK wrapper: stores, ingestion, streaming, citation extraction);
`backend/app/models.py` defines SQLAlchemy ORM models; `backend/app/schemas.py` defines
Pydantic request/response contracts. Uploaded files are staged to disk, magic-checked,
sent to Gemini's managed file-search stores, and tracked as `Document` rows with a
status state machine (`PENDING → RUNNING → DONE/ERROR`). Ingestion runs
**asynchronously** on an arq + Redis worker (`backend/app/worker.py`,
`services/ingestion.py`): the upload route enqueues a job and clients poll
`GET /api/upload/op-status/{id}`; with no queue reachable, uploads 503 by design.
Chat is server-sent events:
the model streams text deltas, then citation frames, then a finish frame, while the
server meters tokens and enforces per-user budgets. The frontend is component- and
context-driven (`App.tsx` is a thin ~85-line shell; real work lives in
`contexts/` and `components/`), talking to the API over `fetch` + SSE.

## Non-negotiable invariants

These are load-bearing. Breaking one is a security or correctness regression, not a style choice.

### 1. Tenant isolation — filter by owner, return 404 (not 403)

Every query that touches user-owned data MUST be scoped to the caller. The canonical
helpers are in `backend/app/security/tenant.py`:
`require_store_owned_by_user`, `require_stores_owned_by_user`, `require_document_owned_by_user`.
They filter on `user_id` **and** `deleted_at IS NULL`, and raise **404 "not found"** when
the row is missing or owned by someone else — deliberately not 403, so existence isn't
leaked across tenants. Use these helpers in new routes instead of hand-rolling filters.
Chat resolves stores via `require_stores_owned_by_user` (`routes/chat.py`).

Note one intentional exception to the "always 404" rule: `get_current_user` returns
**403** for an authenticated-but-`is_active=False` user (`backend/app/auth.py`), and
`require_admin` returns 403 for non-admins. Those are identity checks on the caller, not
cross-tenant resource lookups, so the 404 rule doesn't apply.

### 2. Auth / JWT model

`backend/app/auth.py` is the single source. Tokens are HS256, signed with `JWT_SECRET`,
audience/issuer-checked on decode. The payload carries `sub` (user id), `iss`, `aud`,
`iat`, `exp`, `jti` — **no email/PII**. Default access-token lifetime is
`ACCESS_TOKEN_EXPIRE_MINUTES = 15` (`config.py`). Passwords are bcrypt (72-byte safe
truncation) with a policy enforced in `validate_password_policy`. Revocation is
`jti`-based via Redis (`revoke_jti` / the `revoked:{jti}` check in `get_current_user`);
if Redis is down the revocation check fails **closed** with 503, not open.

### 3. Production gates (fail-fast)

Two layers enforce safe production config; both raise at startup:
- `Settings.validate_production_safety` in `backend/app/config.py` (runs during settings
  instantiation): when `ENVIRONMENT=production` it forbids `ALLOW_DEV_LOGIN=true`, SQLite
  `DATABASE_URL`, default/blank DB passwords, the dev `JWT_SECRET`, missing `REDIS_URL`
  (when `REQUIRE_REDIS_IN_PRODUCTION`), and `REQUIRE_CSRF_HEADER=false`.
- `run_security_gate()` in `backend/app/security_gate.py` (called from the app lifespan in
  `main.py`): re-asserts the above plus `STRICT_MODE` on, mock-mode restrictions, and a
  live Redis ping when Redis is required.

Do not weaken these to make something "work locally" — set `ENVIRONMENT=development`
instead. The dev defaults (`GEMINI_MOCK_MODE=true`, `ALLOW_DEV_LOGIN` opt-in) exist for that.

### 4. OpenAPI drift gate — regenerate after any API change

CI fails if the committed spec drifts. The check lives in
`.github/workflows/ci-basic.yml` ("Check OpenAPI drift"): it runs
`python scripts/export_openapi.py` and then `git diff --exit-code openapi.yaml`. So after
changing any route, schema, status code, or response model, regenerate and commit
`backend/openapi.yaml`:

```bash
cd backend
GEMINI_MOCK_MODE=true GEMINI_API_KEY=export-mock-key python scripts/export_openapi.py
git add openapi.yaml
```

`backend/openapi.yaml` is the source of truth for the endpoint surface; don't maintain an
endpoint list here.

## Conventions

- **Layering:** routes validate + authorize + shape responses; services hold logic and
  external calls; models/schemas stay free of HTTP concerns. Keep Gemini specifics inside
  `services/gemini_rag.py`.
- **Config:** all settings flow through `backend/app/config.py` (`pydantic-settings`).
  Add new knobs there with a validator and a sensible default; never read `os.environ`
  ad hoc in routes.
- **Lint/types:** `ruff format` + `ruff check` + `mypy` (line length 120). Run
  `./scripts/test-backend.sh` / `./scripts/test-frontend.sh`, or `make test`.
- **Migrations:** Alembic, sequential `NNNN_description.py` files in
  `backend/alembic/versions/` (count them in the directory — don't trust a number here).
  Autogenerate, review, test up *and* down, commit.
- **Tests:** ~108 backend test functions across ~27 `test_*.py` files in `backend/tests/`.
  New behavior needs tests; always add a tenant-isolation test for new owned resources.
- **Frontend:** functional components + hooks; state lives in `contexts/` (`ChatContext`,
  `StoreContext`, `ThemeContext`); auth token is held in `sessionStorage` under `token`.

### Source-of-truth pointers (don't duplicate these here — they rot)

- Env vars, defaults, validation, production invariants → `docs/configuration.md`
- Endpoint surface, schemas, status codes → `backend/openapi.yaml` (and `/docs` at runtime)
- Pricing / budgeting knobs → `docs/pricing.md`, `backend/app/config.py` (`DEFAULT_MODEL_PRICING`)
- Per-subsystem deep dives → `docs/context/CONTEXT-00*.md`
- Deploy/runbook → `DEPLOYMENT.md`, `docker-compose*.yml`

## Data model (high level)

ORM in `backend/app/models.py`: `User`, `Store`, `Document`, `QueryLog`, `Budget`,
`AdminAuditLog`, `ChatHistory`, `ChatSession`, `AppSetting`. `Store` and `Document` use a
`SoftDeleteMixin` (`deleted_at` / `deleted_by`) — most reads must add `deleted_at IS NULL`.
`Document` carries the status enum and Gemini linkage (`op_name`, `gemini_file_id`,
`gcs_uri`, `last_error`). Cost/usage is recorded per query in `QueryLog`.

## Known limitations & deliberate tradeoffs

Called out so reviewers and agents don't mistake them for bugs or assume guarantees that
aren't there. Each is verified against current code.

- **Citations are streamed but not persisted.** In `backend/app/routes/chat.py` the SSE
  generator emits `source-document` frames from `rag.extract_citations_from_response(...)`
  (~L870–879), but the only thing written to the DB is the assistant's text:
  `_persist_chat_message(...)` stores `role`/`content` (~L954–961), and `ChatHistory`
  (`models.py`) has no citations column. Re-opening a past session shows the text, not its
  sources.
- **Admin audit log is not tamper-evident.** `record_admin_action`
  (`backend/app/services/audit.py`) inserts a plain `AdminAuditLog` row; the model
  (`models.py`) has no hash, previous-hash, or signature field. There is no hash chain, so
  a DB-level actor could edit/delete history undetectably. It's an audit *trail*, not an
  immutable ledger.
- **The chat SSE handler is one very large generator.** `chat.py` is ~1055 lines and the
  inner `async def generator()` inside `chat_stream` spans roughly L605–L1003 (~400 lines),
  interleaving streaming, keepalives, citation emission, token accounting, budget checks,
  and persistence. It works and is the hottest path in the app, but it's the first place to
  tread carefully and the prime candidate for decomposition.
- **Defensive `getattr(obj, "attr", default)` against SDK response shapes.** `chat.py`
  uses ~8 such reads (e.g. `usage_metadata`, `candidates`, `text` around L885–895) because
  Gemini SDK response objects vary. This is intentional resilience, but it means a renamed
  attribute fails silently (falls back to a default / token estimate) rather than loudly.
  When debugging wrong token counts or missing citations, suspect these first.
- **Magic-number validation is selective, not universal.** `validate_file_magic`
  (`backend/app/routes/uploads.py`) only deep-checks types in `MAGIC_CHECKED_MIMES`
  (PDF, Office/ZIP-based); for other allowed MIME types it skips strict magic checks
  (see the comment ~L99) and trusts the declared content type plus the profile allowlist.
  Broadening `UPLOAD_PROFILE` widens what is accepted on declared type alone.
- **Budget enforcement is post-hoc per request, not a hard pre-spend cap.** Cost is
  computed after the model responds and checked against the monthly budget
  (`would_exceed_budget` in `chat.py`); a single in-flight request can push a user slightly
  over their limit before the next one is blocked. `BUDGET_HOLD_USD` softens but doesn't
  eliminate this.
- **CI does not currently gate on coverage.** `.github/workflows/ci.yml` runs `pytest`
  without `--cov-fail-under`; there are multiple CI files (`ci.yml`, `ci-basic.yml`,
  `ci-strict.yml`) and the OpenAPI-drift gate lives only in `ci-basic.yml`. Don't assume a
  red build means a coverage drop — check which workflow failed.

## Quick start

```bash
# Backend
cd backend && pip install -e .[test]
cp .env.example .env        # set JWT_SECRET (32+ chars) and GEMINI_API_KEY
alembic upgrade head
uvicorn app.main:app --reload    # :8000, docs at /docs

# Frontend
cd frontend && npm install && npm run dev   # :5173

# Or everything in Docker
docker-compose up --build
```

For anything not covered here, prefer reading the cited file over guessing — this guide is
intentionally short so it stays true.
