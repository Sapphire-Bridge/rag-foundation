# Pricing & Budgeting

The backend enforces Gemini pricing so that upload/chat costs are tracked accurately and tenant budgets can stop runaway spend. This document explains how to configure pricing, verify the values, and understand what the API returns.

## Default Rates

The defaults follow Google's public Gemini 2.5 Flash pricing (USD per million tokens):

| Meter                          | Default (`.env`) |
| ------------------------------ | ---------------- |
| `PRICE_PER_MTOK_INPUT`         | `0.30`           |
| `PRICE_PER_MTOK_OUTPUT`        | `2.50`           |
| `PRICE_PER_MTOK_INDEX`         | `0.0015`         |


## Rate Precedence

Effective rates are resolved in this order:
1. Model-specific entry in `MODEL_PRICING` (exact match, then longest-prefix match).
2. `MODEL_PRICING["default"]` when present, unless you explicitly set the corresponding `PRICE_PER_MTOK_*` (or `*_FILE`).
3. `PRICE_PER_MTOK_INPUT/OUTPUT/INDEX` as the final fallback.

Per-field overrides apply independently, so you can override just one meter via env without touching the others.



These values are baked into `app.config.Settings` so the backend refuses to start in production (or whenever `PRICE_CHECK_STRICT=true`) if any rate is missing or zero.

## Customizing

1. Copy `backend/.env.example` to `.env`.
2. Override the `PRICE_PER_MTOK_*` values with the rates from your Gemini account.
3. (Optional) set `PRICE_CHECK_STRICT=true` in staging to force validation even when `ENVIRONMENT!=production`.
4. Restart the backend so the new pricing is loaded.

## Upload Cost Previews

`POST /api/upload` now returns:

```json
{
  "op_id": "doc-42",
  "document_id": 42,
  "file_display_name": "contract.pdf",
  "estimated_tokens": 128000,
  "estimated_cost_usd": 0.01664
}
```

The estimate is based on the configured `PRICE_PER_MTOK_INDEX` and a 4-bytes-per-token heuristic that matches Gemini guidance. This lets clients warn users before indexing starts.

## Cost Summary Response

`GET /api/costs/summary` includes token and budget breakdowns:

```json
{
  "month": "2025-01",
  "query_cost_usd": 1.234567,
  "indexing_cost_usd": 0.045,
  "total_usd": 1.279567,
  "prompt_tokens": 10240,
  "completion_tokens": 2048,
  "index_tokens": 4096,
  "monthly_budget_usd": 50.0,
  "remaining_budget_usd": 48.720433
}
```

- `prompt_tokens` / `completion_tokens` aggregate chat usage.
- `index_tokens` accumulates stored estimated tokens for indexing operations.
- `remaining_budget_usd` clamps at zero if the tenant has spent more than the configured limit.

## Budget Enforcement

- Uploads calculate estimated indexing cost up-front and reject the request with HTTP `402` if it would push the tenant beyond their monthly budget.
- Chats stop immediately after streaming if the actual Gemini usage would exceed the limit and emit a structured SSE error event (`{"type":"error","errorText":"Monthly budget exceeded"}`).

Budgets are stored in the `budgets` table; use `/api/costs/summary` to verify the limit.

## Verification Checklist

1. Set `.env` `PRICE_PER_MTOK_*` and restart backend.
2. Run `alembic upgrade head` so pricing changes land alongside migrations.
3. Upload a small PDF and confirm the response includes `estimated_cost_usd`.
4. Call `/api/costs/summary`; check that tokens/costs increment.
5. Set a low budget via SQL (e.g., `$0.01`), try another upload, and confirm the API returns HTTP `402`.
