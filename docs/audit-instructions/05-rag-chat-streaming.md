<!-- INSTRUCTION-05-rag-chat-streaming.md -->

# Instruction Set 05 — RAG Querying, Chat Streaming & GeminiRag Audit

## Scope

- `backend/app/routes/chat.py`
- `backend/app/services/gemini_rag.py`
- `backend/app/models.py` (QueryLog, ChatHistory)
- `backend/app/costs.py` (as used in chat)
- Frontend SSE consumer:
  - `frontend/src/useSseRuntime.ts`
  - Relevant parts of `frontend/src/App.tsx`
- Tests: `backend/tests/test_streaming.py`, `backend/tests/test_gemini_rag.py`, `backend/tests/test_sse_smoke.py`
- Context 002 & 003

## Objective

Ensure that the RAG flow:

> user query → store lookup → Gemini RAG → streaming SSE → logging & billing

is:

- Correct and robust to provider failures.
- Budget-aware and tenant-safe.
- Clear in its SSE protocol and error envelopes.
- Implemented without unexplained “vibe” logic.

---

## 1. API Contract & Request Handling

1. Inspect `POST /api/chat` handler:
   - Input schema: single `question` vs Assistant UI-style `messages`.
   - Store selection: `storeIds` or equivalent in payload.
   - Optional metadata filter and its gating (`ALLOW_METADATA_FILTERS`).
2. Verify:
   - Ownership checks for each store ID (tenant isolation).
   - Behavior when a user references a deleted or foreign store.
   - Returned HTTP status codes for:
     - Missing/invalid input.
     - Unauthorized/unauthenticated.
     - Exceeded budget.
     - Internal errors.

---

## 2. Budget & Cost Integration

1. Identify budget checks tied to chat:
   - Pre-query: whether spend already exceeds monthly limit.
   - Post-query: logging token usage and cost.
2. Confirm:
   - 402 is returned when budgets are exceeded.
   - Query logs capture:
     - user id, store id(s), tokens (prompt/completion), model, cost, timestamp.
   - Provider cases where token-count metadata is missing are handled explicitly (e.g., approximate or skip with clear semantics).

---

## 3. GeminiRag Wrapper Behavior

1. Examine `GeminiRag` methods:
   - `create_store`, `upload_document`, `get_operation_status`, `ask`, `ask_stream`.
2. Check:
   - Timeout values and retry counts.
   - Error classes that trigger retry vs immediate failure.
   - Logging for provider errors, timeouts, and unexpected payloads.
3. Ensure:
   - Retries are bounded and metrics capture attempts and latency.
   - No sensitive data (full prompts) is logged at high severity; if logged, ensure redaction policy is followed.

---

## 4. SSE Streaming Implementation (Backend)

1. In `chat.py`:
   - Map the order and types of SSE events emitted:
     - `start`, `text-start`, `text-delta`, `text-end`, `source-document`, `finish`, `[DONE]`, and any error-specific events.
   - Determine:
     - Where connection closed/disconnect is detected.
     - Whether work is cancelled promptly when client disconnects.
2. Error envelopes:
   - Identify how error conditions are encoded for SSE:
     - Event type, `data` structure (status code, message, code field).
   - Check these error events are distinct from normal text streams and documented in code (or can be documented).

---

## 5. SSE Consumer & Client Integration

1. `frontend/src/useSseRuntime.ts` (and SSE logic in `App.tsx`):
   - Confirm:
     - It checks `response.body` and handles null bodies safely.
     - It parses SSE events consistently with backend event types.
     - It logs non-SSE or malformed payloads at warning level without breaking the UI.
2. Check:
   - How error events are surfaced in the UI.
   - Whether any errors are silently swallowed or misclassified as success.

---

## 6. Citations & History Usage

1. Citations:
   - Inspect how `GeminiRag` parses `grounding_metadata` and emits citation events.
   - Confirm `source-document` events carry enough info (doc id/name/ref) to be useful for the UI and benchmark runner.
2. Chat history:
   - Examine how ChatHistory (if used) is integrated:
     - History length limits or token caps.
     - Avoiding unbounded context growth across repeated queries.

---

## 7. Performance & Concurrency

1. Identify any RAG-related capacity controls:
   - `MAX_CONCURRENT_STREAMS` or equivalent.
   - Backpressure strategies for streaming.
2. Evaluate:
   - Whether serving N concurrent SSE streams for 20–50 users is realistic with current worker config.
   - Whether timeouts and retry behavior are suitable for streaming under load.

---

## 8. Error Envelope Consistency

1. HTTP errors:
   - Check shape of JSON error responses across chat-related endpoints (and ideally all endpoints):
     - Do they follow a consistent envelope? (e.g., `{ "detail": "...", "code": "..." }`).
   - Note any divergence that would be confusing to clients.
2. SSE errors:
   - Define a canonical format, even informally:
     - Which fields are always present (`type`, `status`, `message`, optional `code`)?
   - Verify all error paths in streaming code use this format rather than ad-hoc strings.

Record any gaps and propose a minimal, consistent error envelope for both HTTP and SSE.

---

## 9. Vibe Artifact Pass (RAG & Streaming)

Search for:

- Broad `except` around streaming and provider calls with no logging.
- Magic retry/backoff constants without documentation.
- Unused/undocumented SSE event types.

For each:

- Decide: keep as intentional resilience (and document) vs fix.
- Add short comments where behavior is subtle.

---

## 10. Output

Provide:

- A concise description of the end-to-end RAG flow (question → stream → log).
- A list of SSE event types and their semantics.
- Observations on budget enforcement, error envelopes, and performance knobs.
- A prioritized list of fixes/enhancements (especially around error consistency and resilience).
