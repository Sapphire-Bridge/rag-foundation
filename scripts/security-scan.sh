#!/bin/bash
set -euo pipefail

# Configuration
VERBOSE=${VERBOSE:-0}
SKIP_GITLEAKS=${SKIP_GITLEAKS:-0}
SKIP_SEMGREP=${SKIP_SEMGREP:-0}
SKIP_PIP_AUDIT=${SKIP_PIP_AUDIT:-0}
SKIP_NPM_AUDIT=${SKIP_NPM_AUDIT:-0}

# Enable verbose mode if requested
if [ "$VERBOSE" = "1" ]; then
    set -x
fi

# Track failures
SCAN_FAILED=0
START_TIME=$(date +%s)

echo "🛡️  Starting Local Security Scan..."
echo ""

# =============================================================================
# 1. Gitleaks (Secrets)
# =============================================================================
if [ "$SKIP_GITLEAKS" = "1" ]; then
    echo "⏭️  Skipping Gitleaks (SKIP_GITLEAKS=1)"
elif command -v gitleaks &> /dev/null; then
    echo "🔎 Running Gitleaks (secret scanning)..."
    if ! gitleaks detect --source=. --no-banner -v; then
        echo "❌ Gitleaks found secrets in repository"
        SCAN_FAILED=1
    else
        echo "✅ No secrets found"
    fi
else
    echo "⚠️  Gitleaks not installed. Install: brew install gitleaks"
    echo "    Skipping secret scanning..."
fi
echo ""

# =============================================================================
# 2. Semgrep (SAST)
# =============================================================================
if [ "$SKIP_SEMGREP" = "1" ]; then
    echo "⏭️  Skipping Semgrep (SKIP_SEMGREP=1)"
elif command -v semgrep &> /dev/null; then
    echo "🔍 Running Semgrep (static analysis)..."
    if ! semgrep scan \
        --config p/default \
        --config p/security-audit \
        --config p/owasp-top-ten \
        --exclude frontend/node_modules \
        --exclude frontend/dist \
        --exclude frontend/playwright-report \
        --exclude frontend/test-results \
        --exclude backend/rag_assistant_backend.egg-info \
        --exclude genai-test \
        --quiet \
        --error; then
        echo "❌ Semgrep found code issues"
        SCAN_FAILED=1
    else
        echo "✅ No code issues found"
    fi
else
    echo "⚠️  Semgrep not installed. Install: pip install semgrep"
    echo "    Skipping SAST..."
fi
echo ""

# =============================================================================
# 3. pip-audit (Python Dependencies)
# =============================================================================
if [ "$SKIP_PIP_AUDIT" = "1" ]; then
    echo "⏭️  Skipping pip-audit (SKIP_PIP_AUDIT=1)"
elif [ -d "backend" ]; then
    if [ ! -f "backend/requirements.lock" ]; then
        echo "❌ backend/requirements.lock not found"
        SCAN_FAILED=1
    else
        echo "🐍 Running pip-audit (Python dependencies)..."
        # Ignored vulnerabilities (see docs/security/known-risks.md for justification):
        # - GHSA-wj6h-64fc-37mp: ecdsa 0.19.1 Minerva attack (no patch available as of 2024-11-25)
        if ! (cd backend && pip-audit -r requirements.lock \
            --ignore-vuln GHSA-wj6h-64fc-37mp); then
            echo "❌ pip-audit found vulnerabilities"
            SCAN_FAILED=1
        else
            echo "✅ No Python vulnerabilities found"
        fi
    fi
else
    echo "⏭️  No backend/ directory found"
fi
echo ""

# =============================================================================
# 4. npm audit (Node Dependencies)
# =============================================================================
if [ "$SKIP_NPM_AUDIT" = "1" ]; then
    echo "⏭️  Skipping npm audit (SKIP_NPM_AUDIT=1)"
elif [ -d "frontend" ]; then
    if [ ! -f "frontend/package-lock.json" ]; then
        echo "❌ frontend/package-lock.json not found"
        SCAN_FAILED=1
    else
        echo "📦 Running npm audit (Node dependencies)..."
        # Use high level; moderate findings are handled by Trivy in CI
        if ! (cd frontend && npm audit --audit-level=high); then
            echo "❌ npm audit found vulnerabilities"
            SCAN_FAILED=1
        else
            echo "✅ No Node vulnerabilities found"
        fi
    fi
else
    echo "⏭️  No frontend/ directory found"
fi
echo ""

# =============================================================================
# Summary
# =============================================================================
END_TIME=$(date +%s)
ELAPSED=$((END_TIME - START_TIME))

echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
if [ $SCAN_FAILED -eq 1 ]; then
    echo "❌ Security scan FAILED (${ELAPSED}s)"
    echo ""
    echo "Fix the issues above before pushing to the repository."
    echo "See docs/security/ci.md for remediation guidance."
    echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    exit 1
else
    echo "✅ Security scan PASSED (${ELAPSED}s)"
    echo ""
    echo "All checks passed. Safe to push."
    echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    exit 0
fi
