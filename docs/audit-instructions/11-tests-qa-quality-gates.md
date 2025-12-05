<!-- INSTRUCTION-11-tests-qa-quality-gates.md -->

# Instruction Set 11 — Tests, Fixtures & Quality Gates Audit

## Scope

- Backend tests:
  - `backend/tests/*.py`
  - `backend/tests/conftest.py`
- Frontend tests (if present):
  - `frontend/src/__tests__/*`, `frontend/jest.config.*`, etc.
- Helper scripts:
  - `scripts/test-backend.sh`
  - `scripts/test-frontend.sh`
- CI workflows:
  - `.github/workflows/*.yml` (test-related parts)
- Context 004 (and relevant notes in 001–003)

## Objective

Ensure that:

- Tests meaningfully cover critical features (auth, uploads, RAG, budgets, admin, Dev Mode).
- Fixtures and stubs are clear, stable, and do not encode “vibe” assumptions.
- Quality gates (coverage, strict mode) are correctly wired and effective.

---

## 1. Feature ↔ Test Mapping

1. Build a quick map of major features to test files:
   - Auth & JWT, registration/login/dev login.
   - Admin RBAC & audit.
   - Store CRUD & soft delete/restore.
   - Upload & validation (size, MIME, budget).
   - Chat & streaming (including retries and error handling).
   - Costs & budgets.
   - Settings/Dev Mode (if tested).
2. Note any major feature or endpoint with no obvious corresponding test.

---

## 2. Test Depth (Unit vs Integration vs Smoke)

1. For each feature area:
   - Determine if tests are:
     - Unit-type (small functions/services).
     - Integration (routes + DB + external stubs).
     - End-to-end (via HTTP clients against running app).
2. Check high-risk areas (auth, uploads, budgets, admin, ingestion) have:
   - Positive tests (happy path).
   - Negative/abuse tests (invalid input, unauthorized access, exceeding limits).

---

## 3. Fixtures, Factories & Stubs

1. `backend/tests/conftest.py`:
   - Review how:
     - DB fixtures are created (in-memory SQLite vs real DB).
     - Users, stores, documents are set up.
   - Confirm fixtures don’t accidentally bypass important logic (e.g. skipping auth).
2. Gemini stubs:
   - Inspect how the Gemini client is stubbed:
     - environment toggles (`USE_GENAI_STUB`, etc.)
     - stub behavior (success vs error vs partial).
   - Check that:
     - Stubs are realistic enough for RAG/streaming tests.
     - At least some tests exercise retry and error paths.

---

## 4. Coverage & Quality Gates

1. Check coverage configuration:
   - `pytest --cov=app --cov-fail-under=...` threshold.
   - How coverage is reported in CI.
2. Examine:
   - Areas marked with `# pragma: no cover` (if any).
   - Critical functions excluded from coverage and why.
3. Frontend:
   - Determine whether tests exist and how they’re run.
   - If there are no frontend tests, confirm the build step at least detects type errors and basic runtime issues.

---

## 5. Flakiness & Stability Risks

1. Look for:
   - Tests with sleeps or timing assumptions (particularly for uploads and streaming).
   - Tests that hit real external services (Gemini, Redis) instead of stubs.
2. Determine:
   - Whether retries in tests can hide flakiness.
   - If any tests depend on global/ordered state that could cause nondeterministic failures.

---

## 6. CI Integration with Tests

1. Review `scripts/test-backend.sh` and `scripts/test-frontend.sh`:
   - How `STRICT_MODE`, `FAST_TESTS`, `SKIP_STRICT_LINT` impact which tests and checks run.
   - Confirm CI uses strict settings (full test suite, lint, type-check, coverage).
2. Cross-reference with `.github/workflows`:
   - Ensure there is no path where PRs can be merged without running the relevant tests.

---

## 7. Vibe Artifact Pass (Tests & QA)

Search tests for:

- Overuse of `# type: ignore`, `@pytest.mark.skip` or `xfail` on critical paths.
- very generic assertions (e.g., only checking `status_code == 200` without validating response content).
- Comments like `# TODO: add negative tests` without follow-up.

For each:

- Classify as:
  - Acceptable simplification (for low-risk features).
  - Needs improvement (especially for security/financial features).

---

## 8. Output

Summarize:

- Feature → test coverage map, highlighting gaps.
- Overall coverage posture and notable exclusions.
- Stability risks (flaky or brittle tests).
- A prioritized set of test/QA improvements that would significantly increase confidence per unit effort (e.g., add negative tests for X, add one integration test for Y, etc.).
