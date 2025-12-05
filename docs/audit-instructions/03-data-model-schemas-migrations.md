<!-- INSTRUCTION-03-data-model-schemas-migrations.md -->

# Instruction Set 03 — Data Model, Schemas & Migrations Coherence Audit

## Scope

- `backend/app/models.py`
- `backend/app/schemas.py`
- `backend/alembic/env.py`
- `backend/alembic/versions/*.py`
- `backend/openapi.yaml`
- Context 002 & 004

## Objective

Ensure that:

- ORM models, Pydantic schemas, migrations, and OpenAPI definitions are aligned.
- The data model expresses the intended domain logic (stores, docs, logs, budgets, settings, audit).
- No “vibe” fields, dead columns, or schema drift exist.

---

## 1. Entity Inventory & Relationships

1. List all models:
   - User, Store, Document, QueryLog, Budget, ChatHistory, AdminAuditLog, AppSetting, and any others.
2. For each:
   - Identify primary keys, foreign keys, and important indexes.
   - Draw a quick relationship diagram (user ↔ store ↔ document, user ↔ query logs/budgets, admin logs).

---

## 2. Model ↔ Migration Alignment

For each model:

1. Locate corresponding migration(s) that introduce or modify its table.
2. Verify:
   - Columns in models match columns defined in migrations (types, nullability, defaults).
   - Unique constraints (e.g. `stores.fs_name`) are present in migrations.
   - Indexes referenced in code (e.g. for status/lookups) exist in migrations.
3. Check soft delete support:
   - `deleted_at` fields exist in both models and migrations where used (stores/documents).

Flag any mismatch (extra columns, missing migrations, or unused schema parts).

---

## 3. Model ↔ Pydantic Schema Alignment

1. For each model that appears in API responses/requests:
   - Identify its Pydantic schema(s) (e.g. `StoreOut`, `UploadResponse`, `OpStatus`, `CostsSummary`, `AppSettings`).
2. Verify:
   - Field names and types correspond.
   - Optional vs required semantics match (e.g. `deleted_at` optional vs omitted).
   - Redactions: sensitive fields (password hashes, internal IDs) are not exposed in schemas.
3. Pay attention to:
   - Enum-like fields (status strings, theme presets).
   - Validation constraints (lengths, allowed values) in schemas vs DB column limits.

---

## 4. Schema ↔ OpenAPI Alignment

1. For key endpoints (auth, stores, uploads, chat, costs, settings, admin):
   - Compare schema definitions in code vs OpenAPI types.
2. Check:
   - Field names and required properties.
   - Response codes and their bodies.
   - Any differences that would break generated clients or external integrations.

---

## 5. Domain Constraints & Validators

1. Review validators in `schemas.py`:
   - Store display name sanitization (HTML/script filtering).
   - Constraints on lengths, allowed literal values (e.g. `theme_preset`).
   - Any transformations performed (e.g. normalization, escaping).
2. Evaluate:
   - Are these constraints intentional domain rules, or ad-hoc “vibe” safety nets?
   - Are there constraints missing where they should exist (e.g. color formats, email formats)?

---

## 6. Soft Delete & Lifecycle Fields

1. Identify all fields controlling lifecycle:
   - `created_at`, `updated_at`, `deleted_at`, `status` fields (PENDING/RUNNING/DONE/ERROR).
2. Verify:
   - Code consistently uses these fields (e.g., filters out `deleted_at` rows, checks statuses).
   - Migrations and models define default values and types coherently.
3. Note any ambiguous or unused lifecycle states.

---

## 7. Vibe Artifact Pass (Data Layer)

Search for:

- Columns that are never referenced in code.
- “Enum” values used in queries but not documented centrally.
- Migration scripts that add columns with no apparent usage.

For each:

- Decide: future-reserved (document and keep) vs legacy/dead (mark for cleanup).
- If status/state machines are implicit, consider centralizing them as enums or constants.

---

## 8. Output

Produce:

- A concise entity-relationship map.
- A table mapping model fields → schema fields → migration fields → OpenAPI exposure.
- A list of:
  - Inconsistencies and proposed fixes.
  - Potential cleanups (dead columns, unused states).
  - Missing validations that should be added to schemas.
