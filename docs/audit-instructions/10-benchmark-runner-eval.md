<!-- INSTRUCTION-10-benchmark-runner-eval.md -->

# Instruction Set 10 — Benchmark Runner & Evaluation Harness Audit

## Scope

- `scripts/benchmark/run_benchmark.py`
- `scripts/benchmark/metrics.py`
- `scripts/benchmark/benchmarks.yml`
- `scripts/benchmark/datasets/sample/*`
- Context 005

## Objective

Ensure that the benchmark harness:

- Interacts with the RAG Assistant correctly and safely.
- Produces meaningful, interpretable metrics (EM/F1, refusal, citation hit, latency).
- Has clear error and status taxonomy; does not hide failures under “vibe” categories.

---

## 1. API Integration

1. Auth:
   - Check how it obtains tokens:
     - `/api/auth/token` vs `/api/auth/login` vs manual `--token`.
   - Confirm CSRF header and Authorization header are set correctly on all calls.
2. Store handling:
   - Inspect logic that:
     - Finds or creates stores based on `benchmarks.yml` definitions.
     - Honors `store_id` overrides when provided.
   - Ensure store creation is compatible with backend store limits and validation.

---

## 2. Upload & Indexing Behavior

1. Upload path:
   - Confirm PDFs/docs are read, MIME is set appropriately, and posted to `/api/upload`.
2. Op-status polling:
   - Analyze the backoff strategy and number of polls.
   - Determine how upload failure is recorded:
     - Are errors surfaced in result records with specific status codes/messages?
3. Upload caching:
   - Examine `.uploads.<store>.done` or equivalent sentinel mechanism.
   - Ensure skipping uploads is safe and does not accidentally test against an unintended store state.

---

## 3. Chat & SSE Consumption

1. Request building:
   - Confirm bench runner constructs `/api/chat` requests consistent with the backend contract (store ids, question, model overrides).
2. SSE parsing:
   - Review how it:
     - Reads the SSE stream.
     - Accumulates `text-delta` into final answer.
     - Collects `source-document` events as citation metadata.
   - Confirm `[DONE]` or equivalent termination is recognized reliably.

---

## 4. Metrics Computation

1. EM/F1:
   - Inspect exact string normalization and comparison logic.
   - Check alias handling: `aliases` vs main answer.
2. Refusal & unanswerable:
   - Confirm behavior when `answer` is empty or `unanswerable=true`:
     - How refusals are detected and scored.
3. Citation metrics:
   - How `gold_docs` / `supporting_docs` are matched against citations from SSE.
   - What counts as a “hit” or recall success.
4. Latency:
   - Verify start and end timestamps for measuring latency per query.
   - Check aggregated metrics (mean, p95).

---

## 5. Error/Status Taxonomy

1. Identify all possible status values in results:
   - HTTP errors (e.g. `http_error_503`), timeouts, parse errors, provider failures, success.
2. Ensure:
   - Each failure mode is captured with a distinct status where possible.
   - There is not an overused generic bucket like `unknown_error` without additional logging.
3. Confirm errors are logged or printed in a way that allows debugging of failing benchmark runs.

---

## 6. Vibe Artifact Pass (Benchmarking)

Search for:

- Broad `except` blocks that ignore or heavily compress errors.
- Magic thresholds for timeouts/concurrency without documentation.
- Places where failures default to “success” or partial scoring.

For each:

- Decide if simplification is acceptable or whether it hides important quality signals.
- Suggest minimal improvements (e.g., add a new status code or log more context).

---

## 7. Output

Summarize:

- How benchmarks drive the system and what metrics they produce.
- The strengths and limitations of the current evaluation approach.
- Concrete suggestions (if any) to:
  - Improve error/status taxonomy.
  - Better align benchmarks with production-like conditions.
  - Avoid false confidence due to “vibe” metric handling.
