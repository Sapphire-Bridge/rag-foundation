RAG Codebase Context 003 — Frontend UI, Chat Runtime, Admin Customization (≈1k LOC scope)

Scope (files covered)
- frontend/src/App.tsx:1 — App shell, provider wiring, auth token persistence, model list
- frontend/src/contexts/*.tsx:1 — ThemeContext (branding fetch/save), StoreContext (stores/docs/uploads), ChatContext (runtime, citations, thread helpers)
- frontend/src/hooks/useAdminAndStores.ts:1, useUploads.ts:1, useThreadPersistence.ts:1 — Data fetching, upload pipeline, IndexedDB thread persistence
- frontend/src/useSseRuntime.ts:1 — Custom SSE adapter for Assistant UI runtime
- frontend/src/components/chat/*:1 — ChatLayout, toolbar, assistant message renderer, attachments, welcome card, thread utilities
- frontend/src/components/AdminPanel.tsx:1, components/admin/*:1 — Admin console + branding customizer
- frontend/src/components/LoginBox.tsx:1, CostPanel.tsx:1, CitationPanel.tsx:1 — Auth box, cost summary, citation drawer
- frontend/src/index.css:1, frontend/src/themes/presets.ts:1 — Tailwind tokens, theme presets, favicon helpers
- frontend/vite.config.ts:1, frontend/tailwind.config.js:1 — Build/test config and API proxy

Architecture & Shell
- Stack: React + Vite + Tailwind. Chat UI uses `@assistant-ui/react` primitives; streaming handled by custom `useSseRuntime` built on `@assistant-ui/react-data-stream` + `assistant-stream`.
- Entry: `App` wraps children with ThemeProvider → StoreProvider → ChatProvider. JWT is read from `sessionStorage` key `token`; `setAuthToken` syncs storage and clears the customizer on logout.
- Models dropdown is static (`gemini-*` IDs). Composer `Send` is disabled without both token and selected store.
- `AppSettings` (branding, welcome prompts, colors, favicon) fetched on load via `/api/settings` and applied as CSS vars + favicon (`applyThemeTokens`); saving requires admin token via POST `/api/settings`.

Auth, Stores, Documents
- `LoginBox` handles register/login/dev-token (`/api/auth/register`, `/api/auth/login`, `/api/auth/token`), posts JSON with CSRF header, and passes back `access_token`. Status text is inline; errors prefer response JSON `detail`.
- `StoreProvider` owns `storeId` and exposes token setter. `useAdminAndStores`:
  - Fetches `/api/stores` with Bearer; on first load selects the first store.
  - Checks admin capability via GET `/api/admin/system/summary` (isAdmin true when OK).
  - Fetches documents for the active store from `/api/documents/store/{id}`; on auth failure triggers `onAuthExpired`.
- Thread names persist per store in `localStorage` (`thread-name:{storeId}:{threadId}`) via ChatContext helpers.

Uploads & Document List
- `useUploads` accepts dropped/attached files, queues up to 3 parallel uploads. Each upload builds `FormData` `{storeId, displayName, file}` and POSTs `/api/upload` with Bearer + CSRF.
- Handles 429 with two retries and backoff; on 401/403 invokes `onAuthExpired`. Polls `/api/upload/op-status/{op_id}` every 1.5s up to 3 minutes to transition `pendingUploads` (uploading → indexed/error). Aborts polling when store changes/unmounts via `AbortController`.
- `ComposerAttachments` shows pending uploads and supports drag/drop; uploads are also triggered from the composer Attach control.
- Documents panel in `ChatLayout` lists fetched documents (status, size KB, date) and offers manual refresh.

Chat Runtime & Persistence
- `useSseRuntime` adapter posts JSON to `/api/chat` with Assistant UI’s message/tool payload, plus `body` overrides from ChatProvider (`{ storeIds: [storeId], model }`). `Content-Type` is forced to JSON; credentials default to same-origin.
- SSE parsing recognizes `start`, `text-start/delta/end`, `source-document`, `error`, `finish`, `[DONE]`. Emits Assistant UI stream events and forwards raw events to ChatProvider’s `onEvent`.
- ChatProvider responsibilities:
  - Builds runtime with headers containing Bearer + `X-Requested-With`. `onResponse` clears auth on 401/403; 404/410 alerts user and cancels the run.
  - `onEvent` resets UI on `start`; stores citations per message/thread on `source-document`; on `error` with `code === budget_exceeded` injects a synthetic assistant warning and cancels the run; other errors surface `lastError`.
  - `onError` (network/runtime) injects system message + sets `lastError`. `handleRetryLast`/`handleLoadLastIntoComposer` reuses the last user message.
  - Persists threads + citations per store in IndexedDB via `useThreadPersistence`; quota errors disable persistence and alert. Uses `useAssistantState`/`useAssistantApi` to reset citations when switching threads.
  - Composer input ref is passed down for focus control; thread imports/exports rely on Assistant UI runtime.

UI Composition (ChatLayout and friends)
- Left rail: app branding tile, LoginBox, store selector (+ new store POST `/api/stores`), model selector, thread list (`ThreadListPrimitive` new/switch), documents list, cost panel, admin console (if isAdmin).
- Main pane: optional inline error banner from ChatProvider, editable thread name, thread viewport with WelcomeCard (uses admin-configured prompts/welcome_message when empty). User messages render right-aligned bubbles; assistant messages render markdown-like content with citation chips (`AssistantMessageContent`).
- Composer: draggable drop zone + Attach input wired to `handleFiles`; `Ctrl/Cmd+Enter` sends, `Esc` cancels when running. Toolbar shows run state + model selection + retry/edit controls. Pending uploads listed below composer.
- Citation UX: `source-document` events accumulate per assistant message; small buttons in the message open snippet popover and set the active message. Toggle button opens side `CitationPanel`; snippet popover floats bottom-right.

Admin, Costs, Settings
- `AdminPanel` (only when token + admin) fetches admin users (`/api/admin/users?limit=25`), audit entries (`/api/admin/audit`), and system summary. Role toggle posts to `/api/admin/users/{id}/role`; budget prompt posts `/api/admin/budgets/{id}`; watchdog reset posts `/api/admin/watchdog/reset-stuck` with default TTL 30m. Admin status is hidden when 403.
- `CostPanel` polls `/api/costs/summary` every 30s with Bearer, shows month/query/index/total; 401/403 clear summary and trigger `onAuthExpired`.
- `CustomizationPanel` (Dev mode button shown only to admins) edits branding/theme presets, colors, favicon (<=200KB image, base64 stored), welcome text, suggested prompts. `ThemePreview` shows live sample; `IconPicker` offers a small glyph set. Saving calls `onSave` prop (App handles POST `/api/settings`).

Styling & Build
- Tailwind tokens live in `index.css` and are overridden by ThemeContext; fonts/background images come from presets in `themes/presets.ts` (minimal/gradient/classic, optional gradient background). `applyThemeTokens` writes CSS variables to `:root` and body and swaps favicon (defaults to `/favicon.png`).
- Vite config proxies `/api`, `/metrics`, `/health` to `VITE_BACKEND_ORIGIN` (default `http://localhost:8000`), dev server on 5173. Vitest configured with jsdom via `vite.config.ts` and `src/setupTests.ts`.
- `App.test.tsx` mocks Assistant UI + runtime to smoke-test rendering of the title, thread list label, and send control.

Operational Notes / Gotchas
- Auth/session: Tokens live in `sessionStorage`; `handleAuthExpired` clears token and hides customizer. Most writes include `X-Requested-With`, but GETs rely on backend CSRF exemption for reads.
- Store switching clears thread name cache and rehydrates thread history per store from IndexedDB/localStorage.
- Upload pipeline aborts when store changes/unmounts; long-running polls are capped at 3 minutes.
- Citations rely on SSE `source-document` events; ensure backend continues emitting `sourceId/title/snippet` to avoid empty panels. Budget errors surfaced via SSE `error` with `code`.
