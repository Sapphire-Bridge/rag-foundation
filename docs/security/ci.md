# Security CI Strategy

This project uses a layered security approach to keep the pipeline fast while catching issues early.

## The matrix: what runs when?

| Trigger | Workflow / Command | Tools run | Goal |
| :--- | :--- | :--- | :--- |
| Local dev | `scripts/security-scan.sh` | Bandit, pip-audit, npm audit, Gitleaks (if installed) | Catch issues before pushing. |
| Pull request | `Security CI` | Base (all repos): Gitleaks, Semgrep, Trivy<br>Public only: + CodeQL, Dependency Review | Block secrets and obvious bugs from entering main. |
| Nightly | `Security CI` | Base (all repos): Gitleaks, Semgrep, Trivy<br>Public only: + CodeQL | Detect new CVEs in existing dependencies. |
| Release/tag | `ci-strict` + `Security CI` | All of the above + manual checks (as needed) | Final gate before production. |

Private forks skip the Advanced (CodeQL + Dependency Review) jobs automatically to avoid licensing issues.

## Tool purposes

| Tool | Purpose | Scope |
| :--- | :--- | :--- |
| Gitleaks | Secret scanning | Git history and working tree |
| Bandit | Python security lint | Medium/high severity backend findings |
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
If Bandit is not installed locally, install the pinned version with
`pip install bandit==1.9.1` or rely on `ci-strict`.

Bandit triage policy lives in [`bandit-triage.md`](bandit-triage.md).

## Ignored Vulnerabilities

No `pip-audit` vulnerabilities are ignored in local or CI commands. The frontend
audit uses `npm audit --production --audit-level=high`; dev-only risk is tracked
separately when it does not ship in the production bundle.

| ID | Package | Reason | Review Frequency |
|----|---------|--------|------------------|
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
cd backend
pip-audit -r requirements.lock --strict
cd ../frontend
npm audit --production --audit-level=high
```
