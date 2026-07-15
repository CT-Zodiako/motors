# Proposal — Query Categories (`query-categories`)

## Intent
Give the Odoo query catalog a grouping concept: persistent categories that users can create, assign at query-creation time, and change later — with the query list and runner UIs grouped by category. One adjacent in-scope bugfix: the wizard currently hardcodes `limit_val: 0`.

## 1. Problem statement (why)
Every query ends up in one flat, undifferentiated list. Verified evidence:
- `odoo_queries` (`odoo/init_db.py:3-17`) has columns id, name (UNIQUE), description, model, method, domain (jsonb), fields (jsonb), limit_val, active, created_at — **no category column**, and no categories table exists anywhere.
- The "Nuevo Query" wizard (`odoo-ui/src/app/pages/query-create/`, 4-step p-stepper) asks only for a name in its final step (`save()` at `query-create.ts:254-274`); saved queries then appear in the query list (`odoo-ui/src/app/pages/query-list/`) as one flat p-table, and in the runner (`odoo-ui/src/app/pages/query-runner/`) as one flat p-select.
- Seeds (`odoo/seeds.py:4-39`) insert 4 queries with no grouping.

User problem: as the catalog grows, discoverability degrades — the user wants queries grouped by category and the ability to create categories.

## 2. Proposed solution (what changes)
Binding the decisions recorded with the user:

**Backend (FastAPI in `odoo/`, psycopg2 via `odoo/db.py`):**
1. New table `query_categories (id SERIAL PRIMARY KEY, name VARCHAR(100) UNIQUE NOT NULL, description TEXT, created_at TIMESTAMPTZ DEFAULT NOW())`.
2. New column `odoo_queries.category_id INTEGER REFERENCES query_categories(id)`, added via `ALTER TABLE ... ADD COLUMN IF NOT EXISTS` — init_db's `CREATE TABLE IF NOT EXISTS` never migrates an already-initialized live DB.
3. Seed a protected default category **"General"** (never deletable); the migration backfills all existing queries to General.
4. Category API: `GET /categories/`, `POST /categories/`, `DELETE /categories/{id}` — delete returns **409 Conflict** while the category still has queries (recategorize first; no cascade).
5. Recategorization: new partial-update endpoint (PATCH `/queries/{name}`) to change a query's category.

**Frontend (Angular standalone in `odoo-ui/`):**
6. Wizard Save step gains a category p-select plus inline "Nueva categoría…" creation (POST `/categories/`, then preselect the created category).
7. Query list groups rows by category (p-table `groupRowsBy`) and exposes the recategorize action from the list.
8. Runner p-select becomes grouped (`[group]="true"`).
9. Bugfix: wizard hardcodes `limit_val: 0` (`query-create.ts:266`); save must store a sane limit.

## 3. Scope
**In scope:** items 1–9 above.
**Out of scope (recorded non-goals):** category permissions/roles; cascade deletion of queries on category delete; custom category ordering; rename-UI for categories.

## 4. Affected capabilities and systems
- **Postgres schema:** new `query_categories` table; new `odoo_queries.category_id` FK column; "General" seed; backfill of existing rows (`odoo/init_db.py`, `odoo/seeds.py`).
- **FastAPI:** `odoo/routers/catalog.py` — `QueryIn` (lines 8-15) and query responses gain category; POST `/queries/` upsert (lines 31-53) gains category handling; new PATCH `/queries/{name}`; new categories router (prefix `/categories`) registered in `odoo/main.py`; DB access stays on `odoo/db.py` helpers.
- **Angular:** `services/odoo-queries.ts` — interfaces (`OdooQuery` 5-14, `CreateQueryPayload` 22-30) and methods gain category operations; `pages/query-create/` — Save step category select + inline creation + limit fix; `pages/query-list/` — grouped table + recategorize action; `pages/query-runner/` — grouped select. No routing changes (tab navigation, `app.ts`).

## 5. Impact and risks
- **R1 — Live DB migration.** Must be idempotent and non-destructive: create table `IF NOT EXISTS`; `ADD COLUMN IF NOT EXISTS`; insert "General" `ON CONFLICT DO NOTHING`; backfill `WHERE category_id IS NULL`. Ordering matters (General must exist before backfill). Deploy order: migration → backend → frontend.
- **R2 — 409 delete contract.** Frontend must surface the conflict and steer the user to recategorize. Edge: `DELETE /queries/{name}` is a *soft* delete (`catalog.py:56-61`) — decision: any referencing row blocks category deletion, including inactive queries.
- **R3 — Upsert semantics of register_query.** POST `/queries/` upserts by name (`catalog.py:31-53`). Decision: omitted category preserves the existing one; provided category updates it.
- **R4 — Wizard inline creation UX.** Duplicate category names hit the UNIQUE constraint; the inline flow needs graceful duplicate handling and must preselect the created/returned category.
- **R5 — Grouped UI behavior.** `groupRowsBy` only renders groups for categories that have queries (empty categories invisible in the list — acceptable); the runner needs a group field in its payload; grouped p-select changes option shape.
- **R6 — Backward compatibility.** `GET /queries/` responses gain category fields — additive, safe for existing consumers.

## 6. Rollback
The migration is additive, so rollback is safe: backend rollback restores pre-category behavior (extra column/table ignored); frontend rollback restores flat list/select. Full schema rollback (drop column + table) is optional cleanup — prefer leaving the table dormant.

## 7. Success criteria
- After migration on a live DB, all pre-existing queries appear under "General" and re-running the migration causes no errors, duplicates, or data loss.
- A query saved from the wizard with a selected category persists that category and appears under its group in both the list and the runner.
- Inline "Nueva categoría…" in the wizard creates the category and preselects it in the same save flow.
- `DELETE /categories/{id}` on a category with queries returns 409 and the category survives; after recategorizing its queries away, deletion succeeds. "General" is never deletable.
- Recategorizing a query from the query list moves it between groups without re-running the wizard.
- Newly saved queries no longer carry `limit_val: 0`; they store the agreed sane limit.
- Non-goals remain untouched: no permissions model, no cascade delete, no custom ordering, no category rename UI.

## 8. Residual assumptions (defaults applied unless the user objects)
1. **Sane limit mechanism:** fixed default (100) applied at save in this slice; no wizard limit input.
2. **409 scope:** any referencing row blocks category deletion, including inactive (soft-deleted) queries.
3. **Wizard default:** preselect "General" when the user picks nothing.
4. **Group ordering:** alphabetical by category name.
5. **Endpoint shape:** PATCH (partial) for `/queries/{name}`; rejecting "General" deletion reuses the same 409 contract.
