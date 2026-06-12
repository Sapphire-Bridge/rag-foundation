# Bandit Triage Policy

Bandit is a security lint gate, not the only security control. CI fails on
medium/high findings and every accepted low-severity pattern below has a scoped
reason. Do not add broad `# nosec` comments without updating this file.

## Enforced Gate

```bash
cd backend
bandit -c pyproject.toml -r app -ll
```

This reports medium and high severity findings. The current medium finding
(`B108` for the upload temp directory default) is marked inline because the path
is configurable and container startup verifies the mounted directory is writable.

## Accepted Low-Severity Patterns

| Rule | Current disposition | Reason |
| --- | --- | --- |
| `B101` assert usage | Fixed | Startup validation now raises explicit `ValueError` instead of relying on `assert`. |
| `B105` hardcoded password string | Accepted when documented inline | Development placeholders are rejected by production config validators and the startup security gate. |
| `B106` hardcoded password function arg | Accepted for dev-login-only empty hash | The dev token endpoint is disabled in production and guarded by `ALLOW_DEV_LOGIN`. |
| `B110` try/except/pass | Accepted only around best-effort logging/cleanup paths | These blocks must not guard core authorization, tenancy, or billing decisions without an explicit error path. |
| `B311` random | Accepted for retry jitter only | The jitter is non-cryptographic backoff noise, not secret or token generation. |

## Review Rule

New Bandit findings must be handled in one of three ways:

1. Fix the code.
2. Add a narrow `# nosec Bxxx` with a concrete justification.
3. Document the accepted risk here and keep CI policy explicit.
