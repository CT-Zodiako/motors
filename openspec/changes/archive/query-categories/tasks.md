# Tasks — Query Categories (`query-categories`)

Inputs: `proposal.md`, `specs/query-catalog/spec.md`, `specs/query-ui/spec.md`, `design.md`.
Delivery: **2 chained PRs** (user-approved). PR2 stacks on PR1.
Strict TDD: RED → GREEN → TRIANGULATE → REFACTOR, evidence recorded per task group.
Test runners: backend `cd odoo && .venv/bin/python -m pytest -q` (new, introduced by this change); frontend `cd odoo-ui && npm test` (per `openspec/config.yaml`).

---

## PR1 — Backend (`query-catalog`) — forecast ≈410 lines

### 1. Test infrastructure (RED setup)
- [x] 1.1 Add `pytest` + `httpx` to `odoo/requirements.txt`; create `odoo/tests/__init__.py`, `conftest.py` with FastAPI `TestClient` fixture and per-test DB cleanup fixtures (delete rows created by each test from `odoo_queries`/`query_categories`; never touch seed data).
- [x] 1.2 RED — `tests/test_migration.py`: running `init_db()` twice completes without error; `query_categories` exists with expected columns; `odoo_queries.category_id` exists; "General" exists; pre-existing queries are backfilled to General; re-run causes no duplicates.

### 2. Migration + seeds (GREEN)
- [x] 2.1 `odoo/init_db.py`: append the four idempotent steps in order — `CREATE TABLE IF NOT EXISTS query_categories`, `ALTER TABLE ... ADD COLUMN IF NOT EXISTS category_id`, `INSERT 'General' ON CONFLICT DO NOTHING`, backfill `WHERE category_id IS NULL`.
- [x] 2.2 `odoo/seeds.py`: insert categories first; each seeded query carries its `category_id`.
- [x] 2.3 GREEN — run 1.2 tests; TRIANGULATE with a second pre-existing row shape (inactive query) to prove backfill covers all rows.

### 3. Categories API (RED → GREEN)
- [x] 3.1 RED — `tests/test_categories.py`: list (alphabetical), create 201, duplicate create → 409, delete missing → 404, delete "General" → 409, delete referenced → 409 (including a soft-deleted referencing query), delete unreferenced → 204.
- [x] 3.2 `odoo/routers/categories.py`: `CategoryIn`/`CategoryOut`, `GET /categories/` ordered by name, `POST` with `UniqueViolation` → 409, `DELETE` with the three guards.
- [x] 3.3 Register the router in `odoo/main.py`.
- [x] 3.4 GREEN — run 3.1 tests; TRIANGULATE: category names with trailing spaces/case variants (document chosen behavior; keep DB UNIQUE semantics, no normalization beyond what spec says).

### 4. Category-aware catalog (RED → GREEN)
- [x] 4.1 RED — `tests/test_catalog_categories.py`: create without category → General; create with explicit category; update without category preserves; update with category changes; invalid `category_id` → 422 and row untouched; `PATCH /queries/{name}` 404 unknown, 422 invalid, 200 moves category; `GET /queries/` embeds `category {id, name}` for every row.
- [x] 4.2 `odoo/routers/catalog.py`: `QueryIn.category_id: int | None`; INSERT with `COALESCE(%s, General)`; `ON CONFLICT DO UPDATE` with `COALESCE(EXCLUDED.category_id, odoo_queries.category_id)`; `PATCH` endpoint; `QueryOut` with embedded category via `LEFT JOIN`.
- [x] 4.3 GREEN — run 4.1 tests; TRIANGULATE the upsert-preserve path (the design's highest-risk line) with consecutive POSTs toggling provided/omitted.

### 5. Docs + closeout PR1
- [x] 5.1 `odoo/QUERIES.md`: document `category_id` field, embedded category in responses, `/categories/*` endpoints with curl examples, migration note.
- [x] 5.2 REFACTOR — dedupe repeated SQL fragments (category existence check) into a small helper inside `catalog.py`/`categories.py` boundary (choose one home: `query_bridge.py` or a `categories_repo` helper; keep routers thin).
- [x] 5.3 Full backend suite green (`cd odoo && .venv/bin/python -m pytest -q`); record TDD evidence (RED/GREEN/TRIANGULATE/REFACTOR per group) in the apply-progress note.
- [x] 5.4 Manual smoke against local DB: `init_db.py` on a copy of the live DB; verify backfill + re-run idempotency with `psql`.

## PR2 — Frontend (`query-ui`) — forecast ≈360 lines (stacks on PR1)

### 6. Services (RED → GREEN)
- [x] 6.1 RED — specs for `CategoriesService` (list/create/remove HTTP calls) and the `OdooQueriesService` additions (`category` on `OdooQuery`, `categoryId?` on `CreateQueryPayload`, `updateCategory()` PATCH).
- [x] 6.2 GREEN — implement `odoo-ui/src/app/services/categories.ts` and extend `odoo-queries.ts`.

### 7. Wizard (RED → GREEN)
- [x] 7.1 RED — component specs: Save step preselects "General"; inline create success preselects the new category; inline create duplicate (409) shows feedback and preserves wizard state; save without explicit limit sends `limit_val: 100`; save with limit 250 sends 250.
- [x] 7.2 GREEN — `query-create.ts/.html`: category `p-select` (options loaded on init), inline "Nueva categoría…" flow with 409 handling, `p-inputnumber` limit default 100, payload includes `categoryId` and real `limit_val`.

### 8. Query list (RED → GREEN)
- [x] 8.1 RED — specs: rows grouped by category with alphabetical group order; recategorize action calls `updateCategory` and moves the row; service error reverts the select.
- [x] 8.2 GREEN — `query-list.ts/.html`: sorted copy + `groupRowsBy="category.name"` subheader template; per-row category `p-select` + toast feedback.

### 9. Runner (RED → GREEN)
- [x] 9.1 RED — spec: selector options become `[{label: categoryName, items: [...]}]` sorted alphabetically by category.
- [x] 9.2 GREEN — `query-runner.ts/.html`: group transform + `p-select [group]="true"` with group label/children options.

### 10. Closeout PR2
- [x] 10.1 REFACTOR — extract a shared `sortByCategory`/`toCategoryGroups` helper (used by list and runner) into a small util to avoid duplicated logic.
- [x] 10.2 Full frontend suite green (`cd odoo-ui && npm test`); record TDD evidence in the apply-progress note.
- [x] 10.3 Manual smoke: create category inline in wizard → save query → verify grouping in list and runner → recategorize from list → attempt deleting a referenced category (expect 409 surfaced in UI).

---

## Review workload

| PR | Files | Est. lines | Status vs 400 budget |
|---|---|---|---|
| PR1 backend | init_db, seeds, categories router, catalog, main, 2 test files, requirements, QUERIES.md | ≈410 | at budget (user approved chained strategy) |
| PR2 frontend | 2 services, wizard ts/html, list ts/html, runner ts/html, specs, shared util | ≈360 | within budget |

## Notes for apply

- STRICT TDD MODE IS ACTIVE. Backend runner: `cd odoo && .venv/bin/python -m pytest -q`. Frontend runner: `cd odoo-ui && npm test`. Follow RED, GREEN, TRIANGULATE, REFACTOR. Record evidence.
- Verify the installed PrimeNG major in `odoo-ui/package.json` before tasks 8–9 (grouped component API differs across versions).
- PR1 must be merged (or at least its migration applied) before PR2 is exercised against a real backend.
