#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR/frontend"

STRICT_MODE="${STRICT_MODE:-1}"
FAST_TESTS="${FAST_TESTS:-0}"

echo "[frontend] STRICT_MODE=${STRICT_MODE} FAST_TESTS=${FAST_TESTS}"

# Install deps if node_modules missing (best-effort)
if [[ ! -d node_modules ]]; then
  npm install
fi

if npm run | grep -q "test"; then
  if [[ "${FAST_TESTS}" != "1" && "${STRICT_MODE}" == "1" ]]; then
    npm test -- --coverage
  elif [[ "${FAST_TESTS}" != "1" ]]; then
    npm test || true
  else
    echo "[frontend] FAST_TESTS=1 -> skipping npm test"
  fi
else
  echo "[frontend] No npm test script defined, skipping tests"
fi

npm run build
