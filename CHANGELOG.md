# Changelog

All notable changes will be documented here following Keep a Changelog and SemVer.

## [0.2.1] - 2025-11-17
### Added
- Initial production hardening (P0/P1).

## [0.2.x] - 2025-11-17
### Added
- Helper scripts (`scripts/test-backend.sh`, `scripts/test-frontend.sh`, `scripts/security-scan.sh`) plus documented STRICT_MODE/FAST_TESTS toggles.
- Deployment and observability doc skeletons outlining Docker Compose, Kubernetes, and Prometheus guidance.
- Tiered CI workflows (`ci-basic`, `ci-strict`) and security/dependency scan targets.

### Changed
- Config validation, production safety checks, env cleanup, and CI/frontend gates.
