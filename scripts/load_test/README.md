# Load Testing (Locust)

This directory contains a small Locustfile that exercises the upload + chat flows against a running backend.

## Prerequisites

- Backend running locally (e.g., via `docker-compose up` or `uvicorn`).
- A valid JWT token and an existing store id created via the UI or API.
- Locust installed:

```bash
pip install locust
```

## Usage

From the repository root:

```bash
locust -f scripts/load_test/locustfile.py --host http://localhost:8000
```

Environment variables:

- `TOKEN` (required): bearer token for authenticated requests.
- `STORE_ID` (required): numeric store id to target for uploads/chat.
- `CHAT_MODEL` (optional): override model id for chat requests.
- `REQUEST_TIMEOUT` (optional): per-request timeout in seconds (default: 30).

The `RagUser` task set will:

- Send chat requests to `/api/chat` for the configured store.
- Upload small text files to `/api/upload` and poll `/api/upload/op-status/{op_id}` until ingestion finishes.

Use this for short, controlled load tests; for reproducible end-to-end quality evaluations, see `scripts/benchmark/README.md`.

