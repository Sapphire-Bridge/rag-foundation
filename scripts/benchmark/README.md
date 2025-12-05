# Benchmark Runner

Run repeatable RAG benchmarks against the existing API:

```bash
pip install httpx pyyaml

# Dev auth (uses /api/auth/token)
python -m scripts.benchmark.run_benchmark --bench sample --email you@example.com

# Or with an existing bearer token
python -m scripts.benchmark.run_benchmark --bench sample --token YOUR_JWT
```

Config lives in `benchmarks.yml`; each entry points to a JSONL questions file and optional docs directory (PDFs). Add your PDFs under `docs_path` (or skip to reuse an existing indexed store).

Outputs land in `artifacts/benchmarks/<bench>/`: `results.jsonl`, `results.csv`, `summary.json`. Metrics include EM/F1, refusal handling for empty golds, citation recall (when gold_docs are provided), and latency.

Args (common):
- `--bench` benchmark key from benchmarks.yml (default: sample)
- `--base-url` API root (default: http://localhost:8000/api)
- `--email` / `--password` for login, or `--token` to skip login
- `--out-dir` override output directory
- `--limit` cap number of questions
- `--timeout` per-request timeout seconds
- `--skip-upload` reuse existing indexed docs (skip uploading docs_path)
- `--max-upload-mb` max file size to upload (default 25)
- `--model` override model for all questions

Config tips:
- `benchmarks.yml` supports `display_name`, optional `store_id` (reuse an existing store), `docs_path` (files to upload; cached with .uploads.<store>.done), `docs_path_per_store` mapping for multi-store runs, `skip_upload`, `concurrency`, `top_k`, `language`, `max_questions`, optional `model`.
- Question JSONL supports `answer`, `aliases`, `unanswerable` (bool), `domain`, `difficulty`, `context_doc`, `expected_behavior`, `gold_docs`/`supporting_docs` (maps doc_id to recall), optional `store` to route a question to a specific store (name or numeric ID), optional `model` per question.
