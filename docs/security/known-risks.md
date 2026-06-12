# Security Risk Register

This document tracks accepted security risks and their justifications.

## Active Accepted Risks

### 1. esbuild Development Server (MODERATE)
**Vulnerability ID**: GHSA-67mh-4wv8-2f99  
**Affected Package**: esbuild <=0.24.2 via Vite  
**Discovery Date**: 2024-11-25  
**Why Accepted**:
- This vulnerability only affects the local development server.
- The build artifact (production code) does not contain the development server.
- Fix requires breaking upgrade to Vite 7.x.
**Exit Criteria**:
- Scheduled upgrade to Vite 7.x in next major release.

## Resolved Risks

### ecdsa Minerva Timing Attack (HIGH)
**Vulnerability ID**: GHSA-wj6h-64fc-37mp
**Previous Package**: ecdsa 0.19.1
**Resolved Date**: 2026-06-12

**Resolution**:
- `backend/requirements.lock` now pins `ecdsa==0.19.2`.
- `pip-audit -r requirements.lock --strict` passes with no ignored vulnerabilities.
- CI and local security scripts no longer suppress this advisory.
