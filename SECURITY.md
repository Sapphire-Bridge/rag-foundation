# Security Policy

## Automated Security Checks
- CI workflow `.github/workflows/security.yml` runs on PRs/branches and weekly: Gitleaks (secrets), Semgrep (SAST), Trivy (backend/frontend SCA). Results are uploaded as SARIF to the Security tab.
- Advanced Security (public repos only): CodeQL (deep SAST) and Dependency Review on PRs; skipped automatically on private forks.
- Allowlisted development defaults for secret scanning live in `.gitleaks.toml`; do not add production secrets there.

## Supported Versions

We provide security updates for the following versions:

| Version | Supported          |
| ------- | ------------------ |
| 0.2.x   | :white_check_mark: |
| 0.1.x   | :x:                |

## Reporting a Vulnerability

We take security seriously. If you discover a security vulnerability, please follow responsible disclosure practices:

### Private Reporting (Preferred)
1. **Email**: info@sapphirebridge.de (subject: "Security: [Brief Description]").
2. **GitHub Security Advisories**: Report via the repository Security tab (for example, `https://github.com/Sapphire-Bridge/rag-foundation/security/advisories/new`).
3. **PGP Encryption** (optional): Use our public key if provided.

### What to Include
- **Description**: Clear explanation of the vulnerability
- **Reproduction Steps**: Detailed steps to reproduce the issue
- **Impact Assessment**: Potential security impact and affected components
- **Proof of Concept**: Code snippet or screenshot (if applicable)
- **Suggested Fix**: If you have a proposed solution

### What NOT to Do
- ❌ Do not open public GitHub issues for vulnerabilities
- ❌ Do not share vulnerability details publicly before disclosure
- ❌ Do not exploit vulnerabilities beyond proof-of-concept testing

## Response Timeline

- **Initial Response**: Within 48 hours
- **Status Update**: Within 7 days
- **Fix & Disclosure**: Typically 30-90 days, depending on severity

We will:
1. Acknowledge receipt of your report
2. Confirm the vulnerability and assess severity
3. Develop and test a fix
4. Coordinate disclosure timeline with you
5. Credit you in the security advisory (unless you prefer anonymity)

## Scope

### In Scope
- Authentication and authorization bypass
- SQL injection, XSS, CSRF
- Remote code execution
- Data leakage or exposure
- API security issues
- Dependency vulnerabilities (if exploitable)

### Out of Scope
- Social engineering attacks
- Physical attacks
- DoS/DDoS attacks (rate limiting is best-effort)
- Vulnerabilities in dependencies (report to upstream first)
- Issues in development/test environments

## Security Best Practices for Operators

### Required Configuration
- Set strong `JWT_SECRET` (at least 32 random characters; enforced minimum is 32—use 64+ in production)
- Use valid `GEMINI_API_KEY`
- Enable HTTPS in production
- Set `ALLOW_DEV_LOGIN=false` in production (enforced by security gate)
- Set `ENVIRONMENT=production` in production
- Configure `REDIS_URL` for JWT revocation and atomic rate limiting

### Recommended
- Use PostgreSQL instead of SQLite for production
- Enable Redis for accurate rate limiting
- Set up log monitoring and alerting
- Regularly update dependencies: `pip-audit` and `npm audit`
- See `docs/security/ci.md` for the CI matrix (Gitleaks, Semgrep, Trivy) and local pre-push scan guidance (`scripts/security-scan.sh`).
- Enable database encryption at rest (if supported by your DB)
- Run the ARQ ingestion worker alongside the API for durable uploads; share the configured `UPLOAD_FOLDER` volume
- Use the operational script `scripts/mark_stuck_documents_error.py` if ingestion leaves documents RUNNING after provider outages

### Data Protection
- PII stored: user email addresses
- JWT tokens are stored in browser sessionStorage by default (thread titles in localStorage); operators can swap to cookies if desired.
- Logs retained: operator-controlled (no built-in TTL)
- User data deletion: contact support (future: self-service)

## Bug Bounty

Currently, we do not offer a paid bug bounty program, but we greatly appreciate responsible disclosures and will credit researchers in our security advisories.

---

Thank you for helping keep RAG Assistant secure! 🔒

## Known Acceptable Risks

### Python Dependencies

#### ecdsa 0.19.1 - Minerva Timing Attack (GHSA-wj6h-64fc-37mp)
- **Severity**: HIGH
- **Issue**: Timing side-channel vulnerability in ECDSA signature verification.
- **Status**: No patch available (latest version 0.19.1 is vulnerable).
- **Risk Assessment**:
  - Attack requires precise timing measurements on signature verification.
  - Difficult to exploit remotely in typical web application scenarios.
- **Mitigation**:
  - TLS encryption helps mask timing.
  - Rate limiting reduces observation opportunities.
- **Accepted**: 2024-11-25
- **Will Fix**: When maintainers release patched version.

### Frontend Dependencies

#### esbuild ≤0.24.2 - Development Server Request Handling (GHSA-67mh-4wv8-2f99)
- **Severity**: MODERATE
- **Issue**: Development server accepts arbitrary requests.
- **Status**: Fix available (Vite 7.x upgrade required - breaking change).
- **Risk Assessment**: Development-only tool; not exposed in production.
- **Accepted**: 2024-11-25
