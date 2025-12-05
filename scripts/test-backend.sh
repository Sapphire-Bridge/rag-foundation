#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR/backend"

# Always keep pytest deterministic by default
export PYTEST_DISABLE_PLUGIN_AUTOLOAD="${PYTEST_DISABLE_PLUGIN_AUTOLOAD:-1}"

# Align USE_GENAI_STUB helper with the google SDK stub toggle
if [[ -n "${USE_GENAI_STUB:-}" ]]; then
  export USE_GOOGLE_GENAI_STUB="${USE_GENAI_STUB}"
fi
export USE_GOOGLE_GENAI_STUB="${USE_GOOGLE_GENAI_STUB:-1}"

STRICT_MODE="${STRICT_MODE:-1}"
FAST_TESTS="${FAST_TESTS:-0}"

echo "[backend] STRICT_MODE=${STRICT_MODE} FAST_TESTS=${FAST_TESTS} SKIP_STRICT_LINT=${SKIP_STRICT_LINT:-0}"

pytest_cmd=(pytest)
if [[ "${FAST_TESTS}" == "1" ]]; then
  # Fast path: targeted smoke tests
  pytest_cmd+=(tests/test_auth.py tests/test_streaming.py)
elif [[ "${STRICT_MODE}" == "1" ]]; then
  pytest_cmd+=(-p pytest_cov --cov=app --cov-report=term-missing --cov-fail-under=80)
else
  pytest_cmd+=(-q)
fi

"${pytest_cmd[@]}"

if [[ "${SKIP_STRICT_LINT:-0}" == "1" ]]; then
  echo "[backend] Skipping ruff/mypy checks (SKIP_STRICT_LINT=1)"
  exit 0
fi

ruff check .
ruff format --check .
mypy app
