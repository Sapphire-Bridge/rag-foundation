<!-- INSTRUCTION-06-costs-budgets.md -->

# Instruction Set 06 — Cost Tracking, Pricing & Budget Enforcement Audit

## Scope

- `backend/app/costs.py`
- Cost-related fields on models: `QueryLog`, `Budget`
- `backend/app/routes/costs.py`
- Cost/budget checks in:
  - `backend/app/routes/chat.py`
  - `backend/app/routes/uploads.py`
- `docs/pricing.md`
- Any configuration in `backend/app/config.py` for prices/rates
- Context 002 & 004

## Objective

Verify that:

- Token → USD pricing logic is correct and interpretable.
- Budget enforcement is consistent and robust.
- No “vibe” pricing defaults or missing invariants allow silent mis-billing.

---

## 1. Pricing Configuration & Invariants

1. Identify pricing-related settings:
   - Input/output/indexing prices per MTOK (from config).
   - Any strict-check flags (`PRICE_CHECK_STRICT`, etc.).
2. Confirm:
   - Production refuses to start if any price is zero or invalid when cost tracking is expected.
   - Non-production behavior is documented (e.g., test/dev may allow relaxed checks with clear notes).

---

## 2. Token Estimation & Cost Calculation

1. Examine token estimation functions:
   - For indexing (bytes → tokens).
   - For queries if relevant.
2. Ensure:
   - Heuristic is conservative enough for budgets.
   - Its limitations are mentioned in `docs/pricing.md`.
3. Cost calculation:
   - Confirm formula: `cost = tokens / 1e6 * PRICE_PER_MTOK_*`.
   - Ensure numeric types (Decimal vs float) are used appropriately for monetary values.

---

## 3. Budget Enforcement Integration

1. Identify where budget checks are called:
   - Upload/indexing path.
   - Chat queries.
2. Verify:
   - All relevant entry points use the same core logic; no duplicate but divergent implementations.
   - Requests that would exceed budgets are rejected with HTTP 402, with clear client-facing detail.
3. Examine month-to-date computations:
   - How “current month” is defined (start-of-month boundary).
   - Whether timezone assumptions are explicit and consistent.

---

## 4. Cost Reporting & API Exposure

1. Inspect `/api/costs/summary`:
   - Input scope: per-user, per-store, time range.
   - Response shape (`CostsSummary` schema).
2. Confirm:
   - It matches documentation and OpenAPI.
   - It accurately aggregates:
     - Prompt/output tokens.
     - Indexing tokens.
     - Costs per category and total.
3. Ensure no PII beyond necessary identifiers is returned (e.g., no raw prompts).

---

## 5. Vibe Artifact Pass (Costs & Budgets)

Search for:

- Hard-coded prices or currency assumptions.
- Places where cost is computed but never logged/stored.
- Branches that skip logging when provider metadata is missing without explanation.

For each:

- Decide:
  - Intentional (documented approximation).
  - Needs tightening (e.g., require explicit config or log a warning).
- Ensure errors around pricing misconfigurations are fail-fast in production.

---

## 6. Output

Summarize:

- How costs are computed, enforced, and surfaced to users.
- Any identified risks (e.g., under-counting, misaligned month boundaries).
- A short list of improvements (if any) to strengthen budget enforcement and transparency.
