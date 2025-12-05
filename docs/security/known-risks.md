# Security Risk Register

This document tracks accepted security risks and their justifications.

## Active Accepted Risks

### 1. ecdsa Minerva Timing Attack (HIGH)
**Vulnerability ID**: GHSA-wj6h-64fc-37mp  
**Affected Package**: ecdsa 0.19.1  
**Discovery Date**: 2024-11-25  
**Accepted By**: Security Team  
**Next Review**: 2024-12-25  

**Technical Details**:
- Timing side-channel in ECDSA signature verification
- Allows potential private key recovery through timing analysis
- Requires attacker to observe many signature verification operations

**Why Accepted**:
1. No patch available from upstream maintainers
2. Exploitation requires precise timing measurements (difficult remotely)
3. Risk is mitigated by TLS encryption and rate limiting

**Monitoring**:
- Weekly check: `pip index versions ecdsa`
- Upstream: https://github.com/tlsfuzzer/python-ecdsa
- Advisory: https://github.com/advisories/GHSA-wj6h-64fc-37mp

**Exit Criteria**:
- ecdsa releases version > 0.19.1 with fix
- Alternative: Migrate to `cryptography` library

---

### 2. esbuild Development Server (MODERATE)
**Vulnerability ID**: GHSA-67mh-4wv8-2f99  
**Affected Package**: esbuild <=0.24.2 via Vite  
**Discovery Date**: 2024-11-25  
**Why Accepted**:
- This vulnerability only affects the local development server.
- The build artifact (production code) does not contain the development server.
- Fix requires breaking upgrade to Vite 7.x.
**Exit Criteria**:
- Scheduled upgrade to Vite 7.x in next major release.
