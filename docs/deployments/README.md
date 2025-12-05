# Deployment Playbooks

This folder collects opinionated deployment guides. Start with the scenario that matches your environment, then customize as needed.

## Common Prerequisites

- `ENVIRONMENT=production`
- `STRICT_MODE=1`
- Updated `.env` file (copy `backend/.env.example` and provide real secrets)
- TLS termination (nginx, Caddy, Traefik, or cloud LB)
- Observability stack (see `../observability/README.md`)

## Docker Compose (single host)

1. Copy `.env.example` to `.env` at the repo root and set production values.
2. Provision Postgres + Redis (the provided `docker-compose.yml` already defines services).
3. Run `docker-compose up --build -d`.
4. Verify:
   - `docker-compose logs backend` shows `Security gate checks passed`.
   - `curl https://your-domain/health` returns 200.
   - `redis-cli keys "revoked:*"` stays empty unless you call `/api/auth/logout`.
5. Configure TLS: terminate HTTPS in a reverse proxy that forwards to the compose stack.

### Production tips

- Store secrets in Docker secrets or your orchestrator, not in `.env`.
- Rotate `JWT_SECRET` periodically.
- Set `ALLOW_DEV_LOGIN=false` and `REQUIRE_CSRF_HEADER=true`.

## Kubernetes (multi-node)

1. Build and push container images (backend + frontend) to your registry.
2. Deploy Postgres (StatefulSet) and Redis (HA pair). Ensure persistent volumes are encrypted.
3. Apply manifests/Helm chart for the backend + frontend. Recommended settings:
   - `STRICT_MODE=1`
   - Resource requests/limits for every pod
   - PodDisruptionBudgets for backend and Redis
4. Configure Ingress with TLS (Let’s Encrypt / cert-manager).
5. Wire Prometheus scraping via ServiceMonitor or annotations (see observability doc).

### Network policies

- Backend pods need egress to the Gemini API.
- Restrict Redis access to backend pods only.
- Expose frontend via CDN or ingress; keep backend API on a private network if possible.

## Post-Deploy Checklist

- Enable backups for Postgres.
- Configure alerting (high error rate, Redis unavailable, out-of-budget notifications).
- Run `./scripts/security-scan.sh` as part of your CI/CD pipeline.
- Document your incident response process and keep SECURITY.md updated with the contact path.
