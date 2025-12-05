# Security CI Strategy

This project uses a layered security approach to keep the pipeline fast while catching issues early.

## The matrix: what runs when?

| Trigger | Workflow / Command | Tools run | Goal |
| :--- | :--- | :--- | :--- |
| Local dev | `scripts/security-scan.sh` | pip-audit, npm audit, Gitleaks (if installed) | Catch issues before pushing. |
| Pull request | `Security CI` | Base (all repos): Gitleaks, Semgrep, Trivy<br>Public only: + CodeQL, Dependency Review | Block secrets and obvious bugs from entering main. |
| Nightly | `Security CI` | Base (all repos): Gitleaks, Semgrep, Trivy<br>Public only: + CodeQL | Detect new CVEs in existing dependencies. |
| Release/tag | `ci-strict` + `Security CI` | All of the above + manual checks (as needed) | Final gate before production. |

Private forks skip the Advanced (CodeQL + Dependency Review) jobs automatically to avoid licensing issues.

## Tool purposes

| Tool | Purpose | Scope |
| :--- | :--- | :--- |
| Gitleaks | Secret scanning | Git history and working tree |
| Semgrep | SAST (code analysis) | Python, TypeScript/React |
| Trivy | Dependency scan (SCA) | `requirements.lock`, `package-lock.json` |
| CodeQL (public only) | Deep data-flow SAST | Python, JavaScript/TypeScript |
| Dependency Review (public PRs) | Dependency diff guard | PR dependency changes |

## Local usage

Run the pre-push security scan:

```bash
./scripts/security-scan.sh
```

If Gitleaks is not installed locally, the script skips it and reports the skip.

## Ignored Vulnerabilities

Some vulnerabilities are intentionally ignored when no patch is available:

| ID | Package | Reason | Review Frequency |
|----|---------|--------|------------------|
| GHSA-wj6h-64fc-37mp | ecdsa 0.19.1 | No patch available | Weekly |
| GHSA-67mh-4wv8-2f99 | esbuild ≤0.24.2 | Dev-only, breaking change | Monthly |

See [`known-risks.md`](known-risks.md) for full risk assessments and monitoring plans.

## Updating Ignored Vulnerabilities

When a patch becomes available:

1. Remove `--ignore-vuln` flag from `scripts/security-scan.sh`
2. Upgrade the package
3. Update lock file
4. Update `docs/security/known-risks.md` to mark as resolved
5. Move entry to a new "Resolved Risks" section

## Monthly Security Review

On the first Monday of each month:

```bash
# Check for ecdsa updates
pip index versions ecdsa

# If new version exists:
cd backend
pip install --upgrade ecdsa
pip freeze > requirements.lock
pip-audit -r requirements.lock  # Should pass now

# Update documentation to remove the ignore
```
