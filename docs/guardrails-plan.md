# Guardrails Implementation Plan (Repo-Aligned)

Goal: keep this RAG assistant maintainable for ~50 users with predictable dev/CI flows. Patterns below reuse existing scripts (`scripts/test-backend.sh`, `scripts/test-frontend.sh`), the two-tier CI (`ci-basic.yml`, `ci-strict.yml`), and current stack (FastAPI + React/Vite/Tailwind). Each guardrail lists intent, the repo-aware pattern, immediate deliverables, and how to keep it healthy.

## Guardrail Overview

| Guardrail | Primary Pattern | First Deliverables | Owner(s) |
| --- | --- | --- | --- |
| CI Quality Gates | Two-tier GitHub Actions: required `ci-basic`, scheduled/manual `ci-strict`, both calling repo scripts | Align Node 20, pip/npm caches, enforce required checks, add CODEOWNERS | Backend + Frontend leads |
| Deterministic Harness | Script-first runs with pinned locks and `.env.test` using local SQLite; optional nightly compose for Postgres/Redis | `.env.test`, temp DB handling in backend script, ignore `rag.db`, optional `testing.compose.yaml` | DevX |
| Backend Static Analysis | Ruff + mypy (already configured in `pyproject.toml`) shared across pre-commit/CI | Expand pre-commit to ruff check/format + mypy; document single-source flags | Backend |
| Frontend Quality | Vite build + typecheck; add lint once scripts exist | Add `typecheck` script (`vite check` or `tsc --noEmit`), wire into `scripts/test-frontend.sh`, keep Node 20 | Frontend |
| Security & Dependencies | Single `scripts/security-scan.sh` entrypoint; SBOM in strict CI; grouped bot updates | Run scan in `ci-strict`, add waiver template under `/security/findings/`, enable Dependabot/Renovate with groups | Security |
| Ops Playbooks / Docs | Runbooks that mirror current Docker Compose defaults and prod invariants | `docs/ops/production.md`, `docs/ops/disaster-recovery.md`, link from README/PR template | Ops |
| Observability | Prometheus + structured JSON logging already present; add optional OTLP with fake collector test | `observability/README.md`, log schema doc, OTLP toggle + test, starter dashboards later | Platform |

## 1) CI Quality Gates (reuse existing tiers)
- **Intent:** Every PR hits smoke tests; stricter suite runs nightly/manual before releases.
- **Pattern:** Keep `ci-basic.yml` (required) and `ci-strict.yml` (scheduled/manual). Both call `./scripts/test-backend.sh` and `./scripts/test-frontend.sh` only.
- **Deliverables (sprint):**
  1. Set Node to 20 in both workflows (matches `frontend/package.json`).
  2. Use `backend/requirements.lock` even in `ci-basic`; add pip/npm caches keyed on lockfiles.
  3. Make `ci-basic` and signed commits required on `main`; add `CODEOWNERS` to auto-request reviewers for backend/frontend/ops.
  4. Keep runtimes <10 minutes; fail fast, no >2 auto-retries.
- **Maintenance:** Weekly check on cache hit rate; adjust job matrix only in `ci-strict` to avoid PR slowdowns.

## 2) Deterministic Harness
- **Intent:** Local runs match CI without network flakiness.
- **Pattern:** Reuse wrapper scripts; default to SQLite with stubs; optional compose for integration.
- **Deliverables (sprint):**
  1. Add `.env.test` with safe defaults (`DATABASE_URL=sqlite:///./.ci.db`, `USE_GOOGLE_GENAI_STUB=1`, `JWT_SECRET` strong placeholder).
  2. Update `scripts/test-backend.sh` to create/clean the `.ci.db` path and refuse to run if `.env.test` missing.
  3. Add `.gitignore` entry for `backend/rag.db` and any `.ci.db` artifacts.
  4. Optional: `testing.compose.yaml` (Postgres, Redis) used only in a nightly job that calls the same scripts with `DATABASE_URL` override.
- **Maintenance:** Quarterly dry-run of scripts on clean macOS/Ubuntu; record env and versions in workflow summary.

## 3) Backend Static Analysis
- **Intent:** Single source of lint/type flags; zero drift between local and CI.
- **Pattern:** Ruff + mypy configured in `backend/pyproject.toml`; avoid introducing Black/isort duplicates.
- **Deliverables (sprint):**
  1. Expand `.pre-commit-config.yaml` to run `ruff check`, `ruff format`, and `mypy app` using the repo settings.
  2. Update `CONTRIBUTING.md` to install/run pre-commit; mention scripts are the only place flags live.
  3. Keep `scripts/test-backend.sh` as the entrypoint; no extra flags in workflow YAML.
- **Maintenance:** Add `warn-unused-ignores` budget to `ci-strict` (already set) and track new `# type: ignore` with justification tags in reviews.

## 4) Frontend Quality
- **Intent:** Prevent regressions even without a test suite today.
- **Pattern:** Keep build gate; add typecheck and lint incrementally.
- **Deliverables (sprint):**
  1. Add `typecheck` npm script (`vite check` or `tsc --noEmit`) and call it from `scripts/test-frontend.sh` when `STRICT_MODE=1`.
  2. Add a simple lint script (e.g., `eslint` once introduced) but do not block until rules exist; document the plan in `CONTRIBUTING.md`.
  3. Ensure `ci-basic` uses Node 20 and still runs the build for `FAST_TESTS=1`.
- **Maintenance:** When tests are added, wire them into `scripts/test-frontend.sh` so CI stays script-driven.

## 5) Security & Dependency Hygiene
- **Intent:** Clear audit path and minimal noise.
- **Pattern:** `scripts/security-scan.sh` runs pip-audit + npm audit; `ci-strict` reuses it and emits SBOM.
- **Deliverables (sprint):**
  1. Call `./scripts/security-scan.sh` from `ci-strict.yml` instead of duplicating commands.
  2. Add `/security/findings/` with a waiver template (expire date + owner) and link from `SECURITY.md`.
  3. Enable Dependabot/Renovate with grouped updates (`backend-runtime`, `frontend-runtime`, `dev-deps`) and require the same CI checks.
  4. Keep SBOM step (SPDX) in strict CI; publish on release artifacts.
- **Maintenance:** Monthly review of open waivers; remove when upstream fixed. Label PRs `security-review` to trigger strict workflow if needed.

## 6) Ops Playbooks / Docs
- **Intent:** Operators can deploy, rotate secrets, and recover using the defaults already shipped.
- **Pattern:** Docs mirror current Compose defaults and backend invariants (`ENVIRONMENT=production` requires strong `JWT_SECRET`, non-sqlite, Redis for rate limits).
- **Deliverables (sprint):**
  1. `docs/ops/production.md`: deployment checklist (Compose → container), required env vars, TLS, backups, log retention.
  2. `docs/ops/disaster-recovery.md`: DB restore, MinIO/S3 restore path, JWT secret rotation steps.
  3. Link the runbooks from README and the PR template so env changes require doc updates.
- **Maintenance:** Quarterly fire drill in staging; file issues for gaps and update docs in the same PR as infra changes.

## 7) Observability
- **Intent:** Keep existing Prometheus/structured JSON reliable; add OTLP only when validated locally.
- **Pattern:** Document current metrics/log schema; add optional OTLP exporter behind env flag and a fake-collector test.
- **Deliverables (sprint):**
  1. `observability/README.md` describing current metrics endpoints, log fields, and how to point to an OTLP collector if enabled.
  2. Add a backend integration test (or harness mode) that boots with OTLP exporter pointed at a fake collector to ensure startup safety.
  3. Add starter Grafana dashboard JSON after OTLP validated; until then, keep Prometheus scraping instructions in README.
- **Maintenance:** Snapshot dashboards/alert configs on releases; ensure log schema changes are reviewed via CODEOWNERS.

## Delivery Cadence (repo-specific)
- **Week 1–2:** CI alignment (Node 20, caches, required checks), `.env.test`, DB handling, pre-commit expansion.
- **Week 3–4:** Frontend typecheck hook, security-scan in strict CI, waiver folder + bot config, ops runbooks drafted.
- **Week 5–6:** Optional integration job with `testing.compose.yaml`, OTLP flag + fake collector test, starter observability docs/dashboards.

Cross-cutting: keep all flags in scripts, not YAML; avoid adding duplicate formatters; prefer small, reviewable PRs that update scripts + docs together.
