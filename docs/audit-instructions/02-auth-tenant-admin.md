<!-- INSTRUCTION-02-auth-tenant-admin.md -->

# Instruction Set 02 — Auth, Admin & Tenant Isolation Audit

## Scope

- `backend/app/auth.py`
- `backend/app/routes/auth.py`
- `backend/app/routes/admin.py`
- Tenant-scoped routes in:
  - `backend/app/routes/stores.py`
  - `backend/app/routes/uploads.py`
  - `backend/app/routes/chat.py`
  - `backend/app/routes/documents.py`
- `backend/app/models.py` (User, is_admin, relationships)
- Tests: `backend/tests/test_auth.py`, `backend/tests/test_admin_rbac.py`, `backend/tests/test_soft_delete.py`
- Context 001 & 002
- Deployment/bootstrapping: production compose with proxy/static frontend (`docker-compose.prod.yml`), shared upload volume (`/tmp/rag_uploads`) on backend/worker, and admin bootstrap script (`backend/scripts/create_first_admin.py`) for first-user creation without dev login.

## Objective

Ensure that:

- Authentication is cryptographically sound and minimal (JWT, bcrypt).
- Admin RBAC is correctly enforced and audited.
- Tenant isolation is strict across all user data operations.
- “Best-effort” guardrails are explicit and safe.

---

## 1. JWT & Password Handling

1. JWT creation:
   - Examine payload: `sub`, `iss`, `aud`, `iat`, `exp`, `jti`.
   - Confirm only minimal, non-PII identifiers are used (e.g. numeric user id).
2. Secret & algorithm:
   - Verify strong `JWT_SECRET` is required.
   - Ensure algorithm is explicit (e.g. HS256) and not derived from token header.
3. Passwords:
   - Check bcrypt usage, including any truncation to 72 bytes and error paths.
   - Ensure there is no path where raw passwords are logged or stored.

---

## 2. Token Validation & Revocation

1. Token validation:
   - Confirm signature, issuer, audience, expiry, and `sub` parsing are enforced.
   - Ensure invalid tokens produce clear 401 (not 500) without leaking details.
2. Revocation:
   - Trace logout flow (e.g. `/api/auth/logout` if present):
     - JTI extraction.
     - Redis storage (key format, TTL).
   - Confirm `get_current_user` checks revocation when Redis is available.
3. Redis failure path:
   - Document exactly what happens when Redis is down:
     - Revocation fallback strategy.
     - Any logging of degraded state.

---

## 3. Dev Login & Environment Separation

1. Dev token endpoint (`/api/auth/token`):
   - Confirm it is gated by a setting (`ALLOW_DEV_LOGIN`) and/or `ENVIRONMENT`.
2. Verify:
   - In production, dev login cannot be enabled accidentally due to security gate checks.
   - Error messages do not leak that dev login exists when disabled.

---

## 4. Admin RBAC & Audit Logging

1. `is_admin` semantics:
   - Locate where and how `is_admin` is set and toggled.
2. Admin enforcement:
   - Check all admin routes use `require_admin` (or equivalent) as a dependency.
   - Ensure there is no header-only or “debug” bypass left.
3. Admin audit logging:
   - For each admin action (budgets, restores, watchdog, settings, etc.):
     - Confirm a row is written to `AdminAuditLog` and a structured log is emitted.
   - Check that audit rows include user id, action, target type/id, and metadata.

---

## 5. Tenant Isolation Across Routes

For each of the main data routes:

- `stores` (list/create/delete/restore)
- `documents` (delete/restore)
- `uploads` (upload, op-status)
- `chat` (query against stores)
- `costs` (user cost summary)

Perform:

1. Query inspection:
   - Ensure all ORM queries filter by `user_id` or equivalent tenant identifier, except where admin override is explicitly intended.
   - Check that soft-deleted entities (`deleted_at` not null) are excluded from normal user flows.
2. Behavior for foreign IDs:
   - Confirm requesting another user’s store/document returns 404 (not 403 or a leak).
3. Soft delete semantics:
   - Verify delete operations mark `deleted_at` instead of hard delete.
   - Confirm restore operations are admin-only and logged.

---

## 6. Vibe Artifact Pass (Auth & Tenant)

1. Look for:
   - Any route using `Store.id == store_id` without `user_id` filter.
   - Any broad `except` around auth or admin code.
   - Any leftover debug endpoints or flags.
2. For each:
   - Decide: hardened pattern vs security risk.
   - Mark risks as “fix now” and guardrails with comments/notes.

---

## 7. Output

Summarize:

- JWT + password safety posture.
- Revocation behavior and its failure modes.
- Admin RBAC model and audit guarantees.
- A table of key routes and their tenant isolation patterns.
- A short list of discovered issues / TODOs with severity (must-fix vs nice-to-have).
