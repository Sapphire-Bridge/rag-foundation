#!/bin/sh
set -e

UPLOAD_DIR="${UPLOAD_FOLDER:-${TMP_DIR:-/tmp/rag_uploads}}"
mkdir -p "$UPLOAD_DIR"
if [ ! -w "$UPLOAD_DIR" ]; then
  echo "FATAL: upload directory ($UPLOAD_DIR) is not writable by $(id -u):$(id -g)." >&2
  echo "Fix permissions on the mounted volume (e.g. chown appuser:appuser $UPLOAD_DIR)." >&2
  ls -ld "$UPLOAD_DIR" || true
  exit 1
fi

if [ "${RUN_MIGRATIONS:-true}" = "true" ]; then
  alembic upgrade head
fi

exec "$@"
