<!-- INSTRUCTION-07-frontend-app-auth-upload-devmode.md -->

# Instruction Set 07 — Frontend App, Auth, Stores, Uploads, SSE & Dev Mode Audit

## Scope

- `frontend/src/App.tsx`
- `frontend/src/useSseRuntime.ts`
- `frontend/src/components/LoginBox.tsx`
- `frontend/src/components/UploadBox.tsx`
- `frontend/src/components/CostPanel.tsx`
- `frontend/src/components/CitationPanel.tsx`
- `frontend/src/contexts/ThemeContext.tsx`
- `frontend/src/components/admin/*` (IconPicker, ThemePreview, CustomizationPanel, DevModeToggle)
- `frontend/src/index.css`, `frontend/src/themes/presets.ts`
- Context 003

## Objective

Ensure frontend behavior:

- Correctly aligns with backend contracts (auth, stores, uploads, chat, costs, settings).
- Enforces client-side requirements (CSRF header, token usage) reliably.
- Implements Dev Mode branding safely (visual-only, admin-only).
- Handles errors and SSE gracefully, without hidden “vibe” behavior.

---

## 1. Auth Flows & Token Handling

1. Inspect `LoginBox` and relevant parts of `App.tsx`:
   - Registration vs login vs dev-token usage.
   - Where the JWT is stored (`sessionStorage`/`localStorage`).
   - How token changes propagate to the rest of the app.
2. Check:
   - All authenticated API calls set the Authorization header appropriately.
   - All state-changing calls include `X-Requested-With: XMLHttpRequest` to satisfy CSRF requirements.
3. Ensure:
   - On logout/token removal, admin state and Dev Mode toggles are reset.

---

## 2. Store Management & Uploads

1. Stores:
   - On token acquisition, confirm `/api/stores` is fetched and store selection logic is clear.
   - Store creation (modal/dialog → `POST /api/stores` → refresh).
2. Uploads:
   - Confirm `UploadBox`:
     - Submits `multipart/form-data` with `storeId`, `displayName`, `file`.
     - Attaches token and CSRF header.
   - Polling of `/api/upload/op-status/{op_id}`:
     - Poll interval and stop conditions.
     - Error state handling (user-facing messages).

---

## 3. SSE Runtime Integration

1. `useSseRuntime.ts`:
   - Verify:
     - It checks `response.body` and throws or logs clearly when null.
     - It uses `ReadableStream`/`reader` correctly (no unchecked non-null assertions).
   - Inspect handling of:
     - SSE event parsing.
     - Ignored non-SSE payloads (with warnings).
   - Confirm that:
     - Errors during SSE parsing are logged and surfaced, not silently swallowed.
2. In `App.tsx`:
   - Map how runtime events feed the chat UI, streaming state, and citations panel.

---

## 4. Costs & Citations UI

1. `CostPanel`:
   - Ensure it calls the correct endpoint (`/api/costs/summary`).
   - Handles loading and error states.
2. `CitationPanel`:
   - Confirm it accurately represents the latest citations from SSE `source-document` events.
   - Ensure no assumptions are made that conflict with backend event schema.

---

## 5. Theme & Dev Mode (Admin Customization)

1. `ThemeContext`:
   - Inspect `ThemeProvider`:
     - Default settings.
     - `/api/settings` fetch on mount.
     - `saveSettings` behavior (POST `/api/settings` with token & CSRF).
   - Confirm CSS variable application via `applyThemeTokens` is robust:
     - Uses base tokens + preset tokens.
     - Falls back safely when hex colors are invalid (e.g. `hexToHslString` returning null).
2. Dev Mode:
   - How admin status is detected (e.g. `/api/admin/system/summary`).
   - Where Dev Mode toggles are shown:
     - Header “Dev mode” button.
     - Floating `DevModeToggle` (if both, confirm intentional).
   - `CustomizationPanel`:
     - Tracks local draft state, live preview, reset and save actions.
     - Makes no changes without admin token; shows errors when saves fail.
   - Verify Dev Mode is strictly visual:
     - Only branding settings (name/icon/theme/colors) are affected.
     - No data access or backend behavior changes.

---

## 6. Vibe Artifact Pass (Frontend Integration)

Search for:

- Un-typed `any` or heavy `as unknown as` usage around core flows.
- Silent `catch` blocks in fetch logic or SSE runtime.
- Duplicated or conflicting controls (e.g., multiple Dev Mode toggles with no rationale).

For each:

- Decide if the pattern is acceptable (document intent) or should be refactored.
- Ensure user-facing errors are visible and descriptive wherever possible.

---

## 7. Output

Summarize:

- How the frontend binds to backend endpoints (by area: auth, stores, uploads, chat, costs, settings).
- Security guarantees (CSRF header usage, token handling).
- Dev Mode UX and safety.
- A short list of refactors or fixes to improve robustness and clarity.
