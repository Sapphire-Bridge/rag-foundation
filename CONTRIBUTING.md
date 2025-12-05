# Contributing to RAG Assistant

Thank you for your interest in contributing! This document provides guidelines and instructions for contributing to this project.

We track all work transparently through public GitHub Issues and Pull Requests in this repository. If you want to propose a feature or report a bug, please open an Issue first (unless it is a security vulnerability, in which case follow SECURITY.md). Submit changes via PRs that reference the relevant Issue; we do not use internal ticketing systems.

## Getting Started

### Local Development Setup

1. **Clone the repository**
   ```bash
   git clone https://github.com/Sapphire-Bridge/rag-foundation.git
   cd rag-foundation
   ```

2. **Backend setup (Python 3.11+)**
   ```bash
   cd backend
   pip install -e .[test]
   cp .env.example .env
   # Edit .env with your API keys and secrets
   ```

3. **Frontend setup (Node 20+)**
   ```bash
   cd frontend
   npm install
   cp .env.example .env.local
   ```

4. **Run database migrations**
   ```bash
   cd backend
   alembic upgrade head
   ```

5. **Start development servers**
   ```bash
   # Terminal 1 (backend)
   cd backend && uvicorn app.main:app --reload

   # Terminal 2 (frontend)
   cd frontend && npm run dev
   ```

## Development Workflow

### Branching Strategy
- **main**: Production-ready code
- **feature/your-feature-name**: New features
- **fix/issue-description**: Bug fixes
- **docs/update-description**: Documentation updates

### Commit Guidelines
- Write clear, concise commit messages in imperative mood (e.g., "Add user authentication", not "Added...")
- Reference issue numbers when applicable: `Fix #123: resolve upload timeout`
- Sign commits if possible: `git commit -S -m "..."`

### Pull Request Process
1. Create a feature branch from `main`
2. Make your changes with tests
3. Ensure all checks pass (linting, type checking, tests)
4. Update documentation if needed
5. Submit PR with clear description
6. Address review feedback
7. Squash commits if requested

### Helper Scripts & Env Toggles
- `./scripts/test-backend.sh` — runs pytest + coverage and (unless `SKIP_STRICT_LINT=1`) `ruff` + `mypy`. Honors:
  - `STRICT_MODE=0` to run pytest quietly without coverage.
  - `FAST_TESTS=1` to execute only smoke tests.
  - `SKIP_STRICT_LINT=1` to skip lint/type checks.
  - `USE_GENAI_STUB=0` to exercise the real Gemini SDK (default uses stub).
- `./scripts/test-frontend.sh` — runs `npm test` (when defined) and `npm run build`. Honors `STRICT_MODE` and `FAST_TESTS` the same way.

Run with `STRICT_MODE=1` before requesting review. During local iteration, feel free to set `FAST_TESTS=1` / `SKIP_STRICT_LINT=1` for quicker loops. Difference:
- `SKIP_STRICT_LINT=0` (preferred end state): runs ruff lint/format checks and mypy. Catches type/annotation drift and interface breakage early; best safety and maintainability.
- `SKIP_STRICT_LINT=1` (current default): runs pytest+coverage only. Faster and unblocks local/CI while we pay down type debt, but lets type mistakes slip through.

**Type-check backlog (mypy):** We currently have outstanding mypy errors. Default to `SKIP_STRICT_LINT=1` during local/dev runs to keep feedback fast. When you touch a module, prefer to fix its type errors and expand strict runs over time. Please link PRs to an issue tracking the work to re-enable `SKIP_STRICT_LINT=0` by default.

### CI
- `.github/workflows/ci.yml` runs on every push/PR and enforces linting, typing, tests, audits, license inventories, and security scans (gitleaks + semgrep). Use `GEMINI_MOCK_MODE=true USE_GOOGLE_GENAI_STUB=1` locally to match CI behavior.
- A PR is merge-ready once CI is green and you have run the helper scripts locally for confidence.

### Dependency Policy
- New dependencies must use permissive licenses (MIT, Apache-2.0, BSD). GPL/AGPL (and similar copyleft) are prohibited.
- CI generates license inventories (`backend/licenses.json`, `frontend/licenses.json`); new deps must not cause the license job to fail. Document exceptions with maintainers before merging.

## Code Quality Standards

### Backend (Python)
- **Linting**: Run `ruff check .` before committing
- **Type checking**: Run `mypy .` to ensure type safety
- **Testing**: Run `pytest` with minimum 80% coverage
- **Formatting**: Use `ruff format .`

### Frontend (TypeScript/React)
- **Linting**: Run `npm run lint`
- **Type checking**: Run `npm run type-check`
- **Testing**: Run `npm test`
- **Formatting**: Run `npm run format`

### Coverage Requirements
- Backend: Maintain ≥80% code coverage
- Frontend: Maintain ≥70% code coverage
- All new features must include tests

## Testing

### Running Tests
```bash
# Backend (strict defaults)
STRICT_MODE=1 ./scripts/test-backend.sh

# Frontend
STRICT_MODE=1 ./scripts/test-frontend.sh
```

### Security Scans
```bash
./scripts/security-scan.sh   # pip-audit + npm audit --production
```

### Secret Hygiene
- Before pushing, run a secret scan if you touched credentials/config:
  - `trufflehog filesystem --since-commit <last-clean-commit> .` (or comparable tool like `ggshield secret scan repo .`)
  - For a quick check of staged changes: `trufflehog git --since-commit HEAD~5`
- If you ever find a secret in history: revoke/rotate it at the provider; avoid history rewrites unless absolutely necessary.

### Writing Tests
- Place backend tests in `backend/tests/`
- Place frontend tests alongside components as `*.test.tsx`
- Use fixtures from `backend/tests/conftest.py`
- Mock external API calls (Gemini, etc.)
- Auth routes are built via `build_router(settings)` and exported as `router`; use `build_router` if you need a router with custom settings in tests.

## Pull Request Checklist

Before submitting your PR, ensure:
- [ ] Code follows project style guidelines
- [ ] All tests pass locally
- [ ] New tests added for new functionality
- [ ] Documentation updated (README, API docs, etc.)
- [ ] Commit messages are clear and descriptive
- [ ] No secrets or credentials committed
- [ ] CHANGELOG.md updated (for significant changes)
- [ ] Code coverage maintained or improved

## Security Contributions

For security-related contributions:
- **DO NOT** open public issues for vulnerabilities
- Follow responsible disclosure in SECURITY.md
- Security fixes may be fast-tracked for release

## Code Review Process

- Maintainers will review PRs within 48-72 hours
- Address feedback promptly
- Be open to suggestions and improvements
- Discussions should be constructive and respectful

## Questions or Help?

- Open a GitHub Issue for bugs or feature requests; use Discussions for general questions
- Check existing Issues before opening new ones
- Tag maintainers only if urgent

Thank you for contributing! 🎉
