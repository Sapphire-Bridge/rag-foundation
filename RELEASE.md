# Release Management

This document outlines the release process, versioning strategy, and guidelines for RAG Assistant.

## Versioning Strategy

We follow **Semantic Versioning (SemVer)**: `MAJOR.MINOR.PATCH`

- **MAJOR**: Incompatible API changes or breaking changes
- **MINOR**: New features, backward-compatible
- **PATCH**: Bug fixes, security patches, backward-compatible

### Examples
- `0.2.0` → `0.2.1`: Bug fix release
- `0.2.1` → `0.3.0`: New feature release
- `0.3.0` → `1.0.0`: Major release with breaking changes

## Release Process

### 1. Prepare Release Branch
```bash
git checkout main
git pull origin main
git checkout -b release/v0.3.0
```

### 2. Update Version Numbers

Update version in the following files:
- `backend/pyproject.toml` → `version = "0.3.0"`
- `backend/app/main.py` → `FastAPI(version="0.3.0")`
- `frontend/package.json` → `"version": "0.3.0"`

### 3. Update CHANGELOG.md

Follow [Keep a Changelog](https://keepachangelog.com/) format:

```markdown
## [0.3.0] - 2025-11-17

### Added
- New watchdog endpoint to reset stuck documents
- HTTP metrics middleware for observability
- File magic number validation for uploads

### Changed
- Improved rate limiting with X-RateLimit headers
- Enhanced JWT security documentation

### Fixed
- Event-loop blocking in SSE streaming
- Idempotency issues in background indexing

### Security
- Added fail-fast config validation for secrets
- Improved file upload security with restricted permissions
```

### 4. Version Sync Check

Verify versions are consistent across all files:
```bash
# Manual check or create a script
grep -r "version.*0.3.0" backend/pyproject.toml backend/app/main.py frontend/package.json
```

### 5. Run Full Test Suite

```bash
# Backend tests
cd backend && pytest --cov=app --cov-report=term

# Frontend tests
cd frontend && npm test

# Linting
cd backend && ruff check . && mypy .
cd frontend && npm run lint
```

### 6. Generate OpenAPI Spec

```bash
cd backend
python scripts/export_openapi.py
git add openapi.yaml
```

### 7. Create Annotated Git Tag

```bash
git commit -m "Release v0.3.0"
git tag -a v0.3.0 -m "Release version 0.3.0

## Highlights
- Enhanced security with config validation
- Improved file upload handling
- Better observability with HTTP metrics

See CHANGELOG.md for full details."

# Optionally sign the tag
git tag -s v0.3.0 -m "Release version 0.3.0 ..."
```

### 8. Push Release

```bash
git push origin release/v0.3.0
git push origin v0.3.0
```

### 9. Create GitHub Release

1. Go to GitHub → Releases → Draft a new release
2. Select tag `v0.3.0`
3. Title: `v0.3.0 - [Release Name]`
4. Copy changelog content to release notes
5. Attach artifacts:
   - `openapi.yaml`
   - SBOM (Software Bill of Materials) if generated
   - Docker image digest (SHA256)

### 10. Merge to Main

```bash
# Create PR: release/v0.3.0 → main
# After approval, merge and delete branch
```

## CI/CD Automation

Our CI workflow automatically:
- Runs tests on all PRs
- Performs security audits (`pip-audit`, `npm audit`)
- Generates SBOM on releases
- Validates OpenAPI spec drift

### On Tag Push (`v*.*.*`)
- Build and tag Docker image
- Attach SBOM to GitHub release
- Optionally deploy to staging

## Hotfix Process

For urgent security fixes or critical bugs:

```bash
# Create hotfix from main
git checkout main
git checkout -b hotfix/v0.2.2

# Make fix, test, update CHANGELOG
# Increment PATCH version only

git commit -m "Hotfix v0.2.2: Fix critical security issue"
git tag -a v0.2.2 -m "Hotfix: [brief description]"
git push origin hotfix/v0.2.2
git push origin v0.2.2

# Merge back to main immediately
```

## Release Checklist

Before releasing, ensure:

- [ ] All CI checks pass
- [ ] Version bumped in all files
- [ ] CHANGELOG.md updated
- [ ] OpenAPI spec regenerated
- [ ] Tests pass locally
- [ ] Security audit clean (`pip-audit`, `npm audit`)
- [ ] Documentation updated (README, API docs)
- [ ] Migration scripts tested (if DB changes)
- [ ] Backward compatibility verified (or breaking changes documented)
- [ ] Git tag created and signed (optional)
- [ ] GitHub release published with artifacts

## Post-Release

1. Announce release in:
   - GitHub Discussions
   - Project blog/newsletter (if applicable)
   - Community channels

2. Monitor for issues:
   - Check error logs
   - Monitor GitHub issues
   - Watch for security reports

3. Plan next release:
   - Review backlog
   - Prioritize features/fixes for next milestone

## Version Support

- **Latest MINOR**: Full support (features + security)
- **Previous MINOR**: Security fixes only (6 months)
- **Older versions**: No support (upgrade recommended)

## Emergency Release Process

For zero-day vulnerabilities:

1. **Immediate**: Privately patch vulnerability
2. **Coordinate**: Notify security reporter, set disclosure date
3. **Release**: Fast-track patch release with minimal changelog
4. **Disclose**: Publish security advisory after fix is available

---

For questions about releases, contact the maintainers or open a discussion.
