#!/usr/bin/env bash
# ===============================================================
# Codex Repo Audit Runner (macOS-friendly, bounded parallelism)
# - Runs one codex exec per instruction file
# - Uses repo root as working directory for context
# - Forces read-only sandbox
# - Writes Codex output per instruction into FULL_AUDIT_REPORT.md
# ===============================================================

# Note: we intentionally DO NOT use `set -e` so a single failing section
# doesn't abort the whole audit. We handle errors per-section instead.
set -uo pipefail

# -----------------------------
# Configuration (customize here)
# -----------------------------
INSTRUCTION_DIR="${INSTRUCTION_DIR:-docs/audit-instructions}"
OUTPUT_FILE="${OUTPUT_FILE:-FULL_AUDIT_REPORT.md}"
MODEL="${MODEL:-gpt-5.1-codex-max}"
MAX_PARALLEL_JOBS="${MAX_PARALLEL_JOBS:-3}"

# -----------------------------
# Resolve repo root for context
# -----------------------------
REPO_ROOT="$(git rev-parse --show-toplevel 2>/dev/null || true)"
if [[ -z "$REPO_ROOT" ]]; then
  echo "ERROR: This script must be run inside a Git repository." >&2
  exit 1
fi
cd "$REPO_ROOT"

# -----------------------------
# Collect instruction files
# -----------------------------
if command -v bash >/dev/null 2>&1; then
  shopt -s nullglob 2>/dev/null || true
fi
instruction_files=( "$INSTRUCTION_DIR"/*.md )
if (( ${#instruction_files[@]} == 0 )); then
  echo "ERROR: No .md files found in '$INSTRUCTION_DIR'." >&2
  exit 1
fi

# -----------------------------
# Temp directory for per-section outputs
# -----------------------------
TMP_DIR="$(mktemp -d -t codex-audit-XXXXXX)"
trap 'rm -rf "$TMP_DIR"' EXIT

echo "Repo root: $REPO_ROOT"
echo "Instructions dir: $INSTRUCTION_DIR"
echo "Model: $MODEL"
echo "Max parallel jobs: $MAX_PARALLEL_JOBS"
echo

# -----------------------------
# Initialize final report
# -----------------------------
{
  echo "# RAG Assistant System Deep Audit"
  echo
  echo "**Date:** $(date)"
  echo "**Model:** $MODEL"
  echo "**Mode:** codex exec, sandbox=read-only"
  echo
  echo "---"
  echo
} > "$OUTPUT_FILE"

# -----------------------------
# Helper: run one audit section
# -----------------------------
run_section() {
  local instruction_file="$1"
  local base_name
  base_name="$(basename "$instruction_file" .md)"
  local body_file="$TMP_DIR/${base_name}.body"
  local log_file="$TMP_DIR/${base_name}.log"
  local section_out="$TMP_DIR/${base_name}.md"

  echo "  >> Starting audit for: $base_name"

  # Build prompt and run codex exec. Stdout goes to body_file; stderr to log_file.
  {
    cat <<EOF
CRITICAL: READ-ONLY AUDIT.
You are analyzing the Git repository rooted at: $REPO_ROOT

- Do NOT modify files.
- Do NOT run commands that change state.
- Only inspect code and configuration and produce a Markdown report.

EOF
    cat "$instruction_file"
  } | codex exec \
        --model "$MODEL" \
        --sandbox read-only \
        - >"$body_file" 2>"$log_file"

  local status=$?

  {
    echo "## Analysis: $base_name"
    echo

    if [[ $status -ne 0 || ! -s "$body_file" ]]; then
      echo "_Error: codex exec failed or produced no output for section '$base_name'._"
      echo
      echo "_Check the script output or rerun this section manually for debugging._"
    else
      cat "$body_file"
    fi

    echo
  } > "$section_out"
}

# -----------------------------
# Launch audits with bounded parallelism
# -----------------------------
job_count=0
for instruction_file in "${instruction_files[@]}"; do
  run_section "$instruction_file" &
  job_count=$((job_count + 1))
  if (( job_count >= MAX_PARALLEL_JOBS )); then
    wait
    job_count=0
  fi
done
wait

echo
echo "All section audits finished. Assembling final report..."

# -----------------------------
# Assemble final report in the same order
# -----------------------------
for instruction_file in "${instruction_files[@]}"; do
  base_name="$(basename "$instruction_file" .md)"
  section_out="$TMP_DIR/${base_name}.md"
  if [[ -f "$section_out" ]]; then
    cat "$section_out" >> "$OUTPUT_FILE"
    echo >> "$OUTPUT_FILE"
  else
    {
      echo "## Analysis: $base_name"
      echo
      echo "_No output was generated for this section._"
      echo
    } >> "$OUTPUT_FILE"
  fi
done

echo "✅ Audit complete."
echo "Report: $OUTPUT_FILE"
