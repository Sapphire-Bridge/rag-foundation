# DEPLOYMENT (Small Production Setups)

This project targets small deployments (≈20–50 users) using the existing **sync FastAPI + SQLAlchemy** stack and **Gunicorn + Uvicorn** workers.

## Quick Start (1-hour path)
1. `cp .env.prod.example .env` (or `.env.example` for local) and fill **JWT_SECRET**, **GEMINI_API_KEY**, **POSTGRES_PASSWORD**, **CORS_ORIGINS**.
2. `make up-prod` (uses `docker-compose.prod.yml`, builds images, starts db/redis/backend/worker/frontend/proxy). Default proxy host port is `8888` mapping to nginx `8080`.
3. Create first admin: `docker-compose -f docker-compose.prod.yml exec backend python -m scripts.create_first_admin admin@example.com StrongPass123!`
4. Verify: `docker-compose -f docker-compose.prod.yml exec backend curl http://localhost:8000/health` (200 when db/redis/gemini OK). `/metrics` should be 403 unless allowlisted in the proxy config. If you proxy `/health` through nginx, you can instead hit `http://localhost:8888/health`.
5. Rollback: `make down` (or `docker-compose -f docker-compose.prod.yml down`), optional volume cleanup `docker-compose -f docker-compose.prod.yml down -v`.

## Make targets
- `make up-prod` – start prod stack (proxy on host port 8888 by default; backend/frontend not exposed directly)
- `make up-dev` – start dev stack (existing docker-compose.yml)
- `make down` – stop containers
- `make logs` / `make logs-all` – tail backend/worker or all services
- `make migrate` – run Alembic via migrations service
- `make clean` – stop and remove volumes/orphans
- `make secrets` – generate a JWT secret file under ./secrets (fill others manually)
- `demo` – start a mock-mode demo stack (`docker-compose.demo.yml`, serves frontend on :8080)

## Dev vs Production
- **Disable dev login** in prod: `ALLOW_DEV_LOGIN=false`, `STRICT_MODE=true`, `REQUIRE_CSRF_HEADER=true`.
- **Secrets**: set strong `JWT_SECRET` (32+ chars) and non-default DB password in `DATABASE_URL`.
- **Postgres + Redis**: required for production (SQLite is dev-only; Redis handles rate limiting and JWT revocation).
- **TLS/Proxy**: run behind HTTPS (nginx/Caddy/Traefik); set `CORS_ORIGINS` to your domains.
- ⚠️ Note: `STRICT_MODE` defaults to true. If set to false in a production environment, the application will fail to start to prevent accidental exposure of development routes.
- **TLS setup**:
  - Self-signed (testing only): see `certs/README.md` for `openssl` command to generate `fullchain.pem` and `privkey.pem`.
  - Let's Encrypt: use certbot or terminate TLS at your load balancer and keep the proxy on HTTP internally.
  - Metrics: `/metrics` is allowlisted to private ranges in `proxy/nginx.conf`; tighten or expose internally only.
- **Branding**: admin-only `/api/settings` persists app name/icon/theme in the DB (`app_settings` table); include this table in backups.

## Required Environment Variables
- `ENVIRONMENT=production`
- `JWT_SECRET=<strong-random>` (not the dev default)
- `GEMINI_API_KEY=<real key>`
- `DATABASE_URL=postgresql+psycopg2://rag:<strong-db-pass>@<host>:5432/rag`
- `REDIS_URL=redis://<host>:6379/0` (required when `REQUIRE_REDIS_IN_PRODUCTION=true`)
- Recommended: `ALLOW_DEV_LOGIN=false`, `REQUIRE_CSRF_HEADER=true`, `STRICT_MODE=true`
- Gemini mock vs real:
  - Demo/staging without billing: set `GEMINI_MOCK_MODE=true` and `ALLOW_MOCK_IN_PROD=true` (stub key OK).
  - Real production: set `GEMINI_MOCK_MODE=false`, provide `GEMINI_API_KEY`, and omit `ALLOW_MOCK_IN_PROD`.

## Secrets (Docker Compose)
- Secrets are mounted from files via Docker secrets; the app reads `{NAME}_FILE` before env vars.
- Copy `secrets.example/` to `secrets/` and replace placeholders, or create manually (do not commit the `secrets/` folder):
  ```bash
  mkdir -p secrets
  openssl rand -hex 16 > secrets/postgres_password
  openssl rand -hex 32 > secrets/jwt_secret
  echo "<your-gemini-api-key>" > secrets/gemini_api_key
  echo "postgresql+psycopg2://rag:$(cat secrets/postgres_password)@db:5432/rag" > secrets/database_url
  echo "redis://redis:6379/0" > secrets/redis_url
  ```
- `docker-compose.prod.yml` mounts these at `/run/secrets/*` and sets `*_FILE` envs; restart containers after rotation.

## Running
- Docker Compose (uses Gunicorn): `docker-compose up --build`
- Production Compose with proxy: `make up-prod` (or `docker-compose -f docker-compose.prod.yml --env-file .env up -d --build`; proxy listens on host port 8888 by default)
- Demo Compose: `docker-compose -f docker-compose.demo.yml up` (mock mode, frontend on :8080)
  - If you previously ran a different Postgres password, reset the demo volume first: `docker-compose -f docker-compose.demo.yml down -v`
- Health: `GET /health` (200 when DB + Gemini are OK). From the host, use `docker-compose -f docker-compose.prod.yml exec backend curl http://localhost:8000/health`, or if proxied via nginx, `http://localhost:8888/health`.
- Metrics: `GET /metrics` (Prometheus format, by default only reachable from localhost; expose internally to Prometheus via your proxy/load balancer as needed)

## Networking & Sizing
- Ports: public 80/443 (proxy/LB termination), private 8000 (backend), 6379 (Redis), 5432 (Postgres). Keep `/metrics` internal.
- Proxy/TLS: terminate TLS at nginx/Traefik or your load balancer, then forward to backend:8000. Configure `TRUSTED_PROXY_IPS` if you need forwarded-for addresses for rate limiting.
- Postgres: minimum 2 vCPU / 4 GB RAM for small prod. Run daily `pg_dump` (and retain encrypted backups). Tune connection limits based on gunicorn worker count and SQLAlchemy pool size (see Capacity & Limits).
- Redis: minimum 512 MB RAM. Enable AOF (`appendonly yes`) so rate-limit/JWT revocation survive restarts. Monitor memory eviction.
- Worker: budget ~1 vCPU per concurrent ingestion job; scale ARQ workers accordingly.
- Data lifecycle: back up DB via `pg_dump`/`pg_restore`. Sync uploads/archive volume (e.g., `rsync` or `gsutil rsync`) to object storage; apply lifecycle rules on the bucket to age out old copies.
- Temp files: use `python -m scripts.cleanup_tmp` (or cron/k8s job) to purge `TMP_DIR` files older than `TMP_MAX_AGE_HOURS`.
- DB retention: consider a nightly cron that prunes `chat_history`/`query_logs` older than N days (example):
  ```sql
  DELETE FROM chat_history WHERE created_at < now() - interval '90 days';
  DELETE FROM query_logs   WHERE created_at < now() - interval '90 days';
  ```
  Tune to your compliance needs.
- Cron example (k8s CronJob):
  ```yaml
  apiVersion: batch/v1
  kind: CronJob
  metadata:
    name: cleanup-tmp
  spec:
    schedule: "0 3 * * *"
    jobTemplate:
      spec:
        template:
          spec:
            restartPolicy: OnFailure
            workingDir: /app/backend
            volumes:
              - name: uploads-tmp
                persistentVolumeClaim:
                  claimName: uploads-tmp-pvc
            containers:
              - name: cleanup
                image: your-backend-image
                command: ["python", "-m", "scripts.cleanup_tmp"]
                volumeMounts:
                  - name: uploads-tmp
                    mountPath: /tmp/rag_uploads
  ```

## Migrations
- Apply once on new environments: `cd backend && alembic upgrade head`
- Downgrades are not supported; use forward-only migrations.

## Operations
- Rotate secrets by updating the environment and restarting containers.
- Logs: stdout/stderr from containers (attach your log shipper as needed).

## Capacity & Limits
- Web workers: docker-compose runs `gunicorn ... --workers 4 ...`. Each worker uses a SQLAlchemy pool sized `pool_size=10` with `max_overflow=20` (up to 120 Postgres connections across 4 workers); tune by editing `docker-compose.yml` if you need fewer/more concurrent DB connections. Align with Postgres `max_connections` to avoid exhaustion.
- Worker queue: ARQ `max_jobs=10` with `job_timeout=300s`; the watchdog cron runs every `WATCHDOG_CRON_MINUTES` (15 by default) to reset documents stuck longer than `WATCHDOG_TTL_MINUTES` (60). The worker requires `REDIS_URL`.
- Rate limiting: `RATE_LIMIT_PER_MINUTE=120` per IP/user over a 60s window. With `REDIS_URL` set, limits are distributed; otherwise an in-memory fallback tracks up to ~5k principals with a 15-minute idle eviction. Set `TRUSTED_PROXY_IPS` to honor `X-Forwarded-For` behind a proxy.
- If Redis is disabled, rate limiting falls back to in-memory storage. This memory is per-worker and resets on restart, so it is unsuitable for heavy production traffic and does not synchronize across processes.
- Request sizing: JSON bodies are capped by `MAX_JSON_MB` (default 10MB, returns 413). Uploads are capped by `MAX_UPLOAD_MB` (default 25MB) and MIME allow-lists controlled via `UPLOAD_PROFILE`/`ALLOWED_UPLOAD_MIMES`.
- Cost/budgets: Per-user monthly budgets are enforced on uploads and chat; admins set them via `POST /api/admin/budgets/{id}`. Pricing comes from `PRICE_PER_MTOK_INPUT/OUTPUT/INDEX`. Requests that would exceed the budget return HTTP 402. A best-effort DB lock (`acquire_budget_lock`) serializes budget checks on Postgres; other DBs fall back to optimistic checks.
- Streaming guardrails: `MAX_CONCURRENT_STREAMS` (default 50) caps concurrent chat streams per process; requests over the cap return an SSE error payload.

## Metrics & Health Endpoints
- `/metrics` exposes Prometheus metrics and only serves localhost clients by default. Set `METRICS_ALLOW_ALL=true` (and add your own IP allow list/proxy ACLs) before exposing it to a collector.
- `/health` returns `{"database": bool, "gemini_api": bool, "redis": bool}` and fails with 503 when any dependency is unhealthy. It pings the DB, pings Redis when `REDIS_URL` is set, and instantiates the Gemini client (skipped when `GEMINI_MOCK_MODE=true`).

## Data Retention
Currently, `chat_history` and `query_logs` are retained indefinitely. Operators should configure an external cron job or SQL script to prune old records based on their compliance requirements.

## Secret Hygiene (before going public)
- Run a history scan (e.g., `trufflehog filesystem --since-commit <last-release>` or `ggshield secret scan repo .`).
- If anything is found: revoke/rotate at the provider; avoid history rewrite unless necessary.

## Frontend container note
The Docker image builds static assets and serves them via Nginx for performance and stability.
