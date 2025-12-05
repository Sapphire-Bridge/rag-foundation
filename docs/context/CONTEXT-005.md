RAG Codebase Context 005 — Benchmark Runner (scripts/benchmark)

Scope (files covered)
- scripts/benchmark/run_benchmark.py — CLI: auth → ensure/create store → optional uploads → chat SSE → metrics/output
- scripts/benchmark/metrics.py — EM/F1 normalization, refusal detection, citation-hit, mean/p95 helpers
- scripts/benchmark/benchmarks.yml — Benchmark definitions (store display_name/id, questions path, docs path/per-store docs, concurrency/top_k/language/max_questions/model)
- scripts/benchmark/datasets/sample/* — Sample questions JSONL (with gold docs) scaffold
- scripts/benchmark/README.md — Usage/args overview

Behavior & Flow
- Auth: uses `/api/auth/token` (dev) when only email is supplied; `/api/auth/login` when password is provided; or accepts `--token`. All requests include `X-Requested-With`.
- Store: `ensure_store` lists `/api/stores` and matches `display_name`; creates via `POST /api/stores` if missing. Optional `store_id` pins reuse.
- Uploads: Optional doc ingestion from `docs_path` (or per-store via `docs_path_per_store`). MIME guessed (`.pdf` → application/pdf else text/plain). Retries 429/500/502/503 up to 3 times with backoff, enforces `--max-upload-mb`, then polls `/api/upload/op-status/{op_id}` every 2s until DONE/ERROR (timeout 300s). Writes `.uploads.<store>.done` sentinel under docs_path (or out_dir) to skip re-uploads.
- Chat: Streams SSE to `/api/chat` with `{question, storeIds:[id], top_k, model?, language?}`; skips keepalives, concatenates `text-delta` chunks, collects `source-document` events as citations, records latency/status. Per-question `store` override (name or numeric id) and per-question `model` override are honored; per-store doc uploads run lazily on first use.
- Concurrency: ThreadPoolExecutor sized by `concurrency` (default 3). Retries chat on HTTP 429/5xx up to 3 attempts before marking status `http_error_<code>`. Timeouts/connection errors map to `timeout`/`connection_error`.

Metrics & Scoring
- EM/F1: `_normalize` lowercases, strips non-alnum, drops articles; compares against gold + aliases. Empty/None gold yields (0,0).
- Refusal: Regex matches refusal phrases; `refusal_ok` only computed when `unanswerable` or gold empty.
- Citation hit: `gold_docs` or `supporting_docs[].doc_id` compared (case-insensitive) to citations’ `sourceId`/uri/title/filename; returns 1/0/None (None when no gold docs).
- Aggregates: mean/p95 latency, EM/F1, refusal_rate, citation hit rate (recall_at_citation), error_rate. Per-question rows include status, latency_ms, citations, model.

Data Formats
- benchmarks.yml entry: `display_name`, optional `store_id`, `questions` (JSONL), optional `docs_path`, optional `docs_path_per_store` map, `skip_upload`, `concurrency`, `top_k`, `language`, `max_questions`, optional `model`, `description`.
- Questions JSONL fields: `id` (optional), `question` (required), `answer` (gold; empty/None → unanswerable), `aliases` (optional), `gold_docs` or `supporting_docs[{doc_id,span_start,span_end}]` for recall checks, optional `store` override, `unanswerable` (bool), `domain/difficulty/context_doc/expected_behavior` metadata, optional `model`.

Outputs
- `results.jsonl`: per-question row (bench, store_display_name/id, id, question, gold/pred, em/f1, refusal_ok, citation_hit, citations, latency_ms, status, model, metadata).
- `results.csv`: tabular subset for quick review.
- `summary.json`: aggregate metrics (em, f1, refusal_rate, recall_at_citation/citation_hit_rate, avg/p95 latency, error_rate, count).
- Default output dir: `artifacts/benchmarks/<bench>/` unless `--out-dir` set.

CLI Usage
- Install deps: `pip install httpx pyyaml`
- Run: `python -m scripts.benchmark.run_benchmark --bench sample --email you@example.com --base-url http://localhost:8000/api`
- Or: `python -m scripts.benchmark.run_benchmark --bench sample --token $JWT`
- Flags: `--limit` question cap; `--timeout` per-request seconds (default 60); `--skip-upload`; `--max-upload-mb`; `--model` override all questions; `--config` to point at custom benchmarks.yml.

Notes / Caveats
- SSE parser is minimal: ignores keepalives, stops on `data: [DONE]`, sets status `sse_parse_error` on decode failures.
- Upload polling/streaming uses httpx synchronous client; runner does not enforce backend rate limits beyond simple retries.
- Sample benchmark uses context docs as gold doc IDs for citation matching; adjust your own corpora/ids accordingly.
