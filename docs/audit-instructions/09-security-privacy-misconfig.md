<!-- INSTRUCTION-09-security-privacy-misconfig.md -->

# Instruction Set 09 — Cross-Cutting Security, Misconfiguration & Privacy Audit

## Scope

Cross-cutting across:

- `backend/app/config.py`, `backend/app/security_gate.py`
- Auth & admin (`auth.py`, `routes/auth.py`, `routes/admin.py`)
- Uploads (`routes/uploads.py`), chat (`routes/chat.py`), costs (`routes/costs.py`)
- Dev Mode & settings (`routes/settings.py`, `ThemeContext`, admin panels)
- Rate limiting, CSRF, CORS, CSP
- Documentation:
  - `SECURITY.md`
  - `PRIVACY.md`
  - `DEPLOYMENT.md`
  - `docs/configuration.md`
- Contexts 001–004

## Objective

Identify:

- All major security surfaces and misconfiguration risks.
- Privacy & PII flows and data minimization gaps.
- Places where “vibe” defaults could lead to unsafe behavior if misused.

---

## 1. Configuration Flags & Security Surfaces

1. Catalog security-significant settings:
   - `ENVIRONMENT`, `ALLOW_DEV_LOGIN`, `REQUIRE_CSRF_HEADER`, `REQUIRE_REDIS_IN_PRODUCTION`, `ALLOW_METADATA_FILTERS`, pricing strictness, upload profiles, etc.
2. For each:
   - Describe:
     - What it does.
     - What happens if misconfigured (too permissive or too strict).
     - Whether misconfig is prevented by validation (fail-fast) or only documented.
3. Identify any flags that can silently degrade security (e.g. disabling CSRF, enabling risky metadata filters).

---

## 2. CSRF, CORS & CSP

1. CSRF:
   - Confirm the exact rules for `X-Requested-With`.
   - Identify all exemptions (e.g. `/health`, `/metrics`) and confirm they’re safe.
2. CORS:
   - Inspect allowed origins (defaults and configuration).
   - Ensure production guidance discourages `*` and matches security posture.
3. CSP:
   - Check CSP header: allowed script/style/connect sources.
   - Note any allowances like `'unsafe-inline'`; ensure they are justified and documented.

---

## 3. Privacy & PII Handling

1. PII classification:
   - Enumerate where user identifiers and document content appear:
     - Database (tables/columns).
     - Logs (fields in log_json).
     - Metrics (labels and metric names).
     - Frontend storage (token, user email, store names).
2. Cross-check with `PRIVACY.md`:
   - Verify actual behavior matches described data handling:
     - Retention.
     - Access controls.
     - Where PII should or should not be logged.
3. Check specifically for PII in:
   - Logs: email addresses, file names, store names, query text.
   - Metrics: avoid user-specific labels where possible.
   - Error messages: avoid echoing user content in logs unnecessarily.

---

## 4. Data Minimization & Retention

1. Soft delete:
   - Confirm soft-delete behavior and how long deleted data is retained.
   - Ensure `DEPLOYMENT.md` or other docs mention retention policies (or absence thereof).
2. Query logs and audit logs:
   - Determine if they store prompts, content snippets, or only metadata.
   - Evaluate whether this is necessary vs could be minimized or anonymized.

---

## 5. Admin & Debug Surfaces

1. Admin API:
   - Ensure all admin endpoints are clearly documented and require admin auth.
   - Confirm no “hidden” or undocumented debug endpoints.
2. Dev Mode:
   - Verify its settings (branding) cannot be used to exfiltrate or expose sensitive data.
3. Any “debug toggles” or environment flags that can expose internals must be:
   - Clear in the code.
   - Not usable in production or strongly gated.

---

## 6. Misconfiguration Scenarios

Construct and evaluate specific scenarios:

- Scenario A: `ENVIRONMENT=production` but Redis is down or misconfigured.
- Scenario B: `ALLOW_DEV_LOGIN` accidentally left true in staging or prod.
- Scenario C: CORS origins allow more domains than intended.
- Scenario D: Logging level set too verbose in production.

For each, answer:

- What actually happens according to code?
- Is there a fail-fast mechanism, a warning, or silent degradation?
- Is this acceptable given intended deployment patterns?

---

## 7. Vibe Artifact Pass (Security & Privacy)

Search for:

- `TODO`, `FIXME`, `HACK` in security/privacy-related code or docs.
- Broad exception handlers around auth, admin, uploads, or chat that are not clearly documented.
- Privacy gaps:
  - Logging full emails/usernames when not necessary.
  - Logging document titles or content when not explicitly needed.

For each:

- Decide: fix now vs document as known limitation.
- Propose minimal changes where possible (e.g., redact part of email, log user id only).

---

## 8. Output

Summarize:

- Security surfaces and associated configuration flags.
- PII flows and whether they match privacy documentation.
- Top misconfiguration risks and their impact.
- A small, prioritized list of concrete actions to reduce security and privacy risk with minimal code change.
