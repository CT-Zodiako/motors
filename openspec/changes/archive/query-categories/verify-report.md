# Verify Report — Query Categories (`query-categories`)

Date: 2026-07-14. Verifier: parent session (inline, subagent tooling incident).
Inputs: `proposal.md`, `design.md`, `tasks.md`, `specs/query-catalog/spec.md`, `specs/query-ui/spec.md`, apply-progress notes 1+2 (Engram).

## Verdict: PASS — all 10 requirements verified with executable evidence.

## Test evidence (fresh runs at verify time)

| Suite | Command | Result |
|---|---|---|
| Backend | `cd odoo && .venv/bin/python -m pytest -q` | **23 passed**, 0 failed |
| Frontend | `cd odoo-ui && npm test` (vitest) | **20 passed** (7 files), 0 failed |
| Build | `cd odoo-ui && npm run build` | compiles (AOT templates OK) |
| E2E smoke | uvicorn + Postgres, curl flow | 8/8 behaviors verified, rows cleaned |

Strict TDD: RED→GREEN→TRIANGULATE→REFACTOR evidence recorded in apply-progress notes (Engram `sdd/query-categories/apply-progress`, `apply-progress-2`).

## Requirement-by-requirement checklist

### query-catalog (backend)

1. **Query Category Storage** — PASS. `query_categories` table + `odoo_queries.category_id` FK via idempotent `ALTER TABLE ... ADD COLUMN IF NOT EXISTS`.
   Evidence: `test_migration.py::test_query_categories_table_exists`, `::test_odoo_queries_has_category_id_fk`, `::test_init_is_idempotent`, `::test_general_category_seeded_once` (unique constraint also exercised by duplicate-create API test).
2. **Protected Default Category** — PASS. "General" seeded once, backfill covers NULL rows including inactive queries; General delete → 409.
   Evidence: `test_backfill_assigns_general_to_null_categories`, `test_backfill_covers_inactive_queries`, `test_categories.py::test_delete_general_409`. Live DB: 5 pre-existing queries backfilled, 0 uncategorized.
3. **Category Management API** — PASS. GET alphabetical, POST 201, duplicate 409, DELETE 404/409-referenced (counts inactive)/204.
   Evidence: `test_categories.py` (8 tests) + smoke steps 1, 2, 4, 5, 7.
4. **Query Upsert Category Assignment** — PASS. Provided changes, omitted preserves (update), omitted → General (create), invalid → 422 with row untouched.
   Evidence: `test_catalog_categories.py::test_create_without_category_defaults_to_general`, `::test_create_with_explicit_category`, `::test_update_without_category_preserves_assignment`, `::test_update_with_category_changes_assignment`, `::test_invalid_category_rejected_422_and_row_untouched` + smoke 3, 8.
5. **Query Recategorization Endpoint** — PASS. `PATCH /queries/{name}` 200/404/422.
   Evidence: `test_patch_recategorizes_query`, `test_patch_unknown_query_404`, `test_patch_invalid_category_422_unchanged` + smoke 6.
6. **Query Listing Includes Category** — PASS. Embedded `{id, name}` object on list and get-by-name; non-null post-migration.
   Evidence: `test_list_embeds_category_object` + smoke 3.

### query-ui (frontend)

7. **Wizard Category Selection** — PASS. General preselected; inline create POSTs + preselects; duplicate shows error, wizard state intact.
   Evidence: `query-create.spec.ts` (preselect, inline create success, inline create 409).
8. **Query List Grouped by Category** — PASS. `groupRowsBy="category.name"`, alphabetical group order, per-row recategorize persisted; error keeps original group.
   Evidence: `query-list.spec.ts` (group order, move, error-no-mutation) + `category-groups.spec.ts` (sort util).
9. **Runner Selector Grouped by Category** — PASS. `[group]="true"` p-select over `[{label, items}]`, alphabetical, active-only.
   Evidence: `query-runner.spec.ts`.
10. **Default Query Limit on Save** — PASS. Wizard stores 100 by default; explicit 250 preserved; no more `limit_val: 0`.
    Evidence: `query-create.spec.ts` (both limit scenarios) + smoke 3 (`limit_val: 100` in stored row).

## Non-goals untouched

No permissions model, no cascade delete, no custom ordering, no category rename UI. Confirmed by diff inspection.

## Contract alignment (recorded deviation)

`CreateQueryPayload` uses `category_id` (snake_case), matching the backend and the existing `limit_val` convention — tasks.md mentioned `categoryId`; implementation follows the backend contract. No functional impact.

## Review workload final count

| PR | Productive lines | Test lines | Total | Budget 400 |
|---|---|---|---|---|
| PR1 backend | ≈225 | ≈360 | ≈585 | total exceeds; productive within (user approved chained split) |
| PR2 frontend | ≈150 | ≈290 | ≈440 | total slightly over; productive well within |

Deviation from design forecast (410/360) driven by test weight (repo had zero test infrastructure; first suites for both systems).

## Repo/config changes made at verify

- `openspec/config.yaml`: backend unit command registered (`cd odoo && .venv/bin/python -m pytest -q`, framework pytest) under `testing.commands.unit`.

## Risks carried forward

- Backend pytest requires the local Postgres (docker-compose) running; documented in tasks.md and verify evidence.
- Frontend tests are the project's first; `ng test` is the canonical command going forward (wired through `npm test`).
- Pre-existing unrelated working-tree changes (`MANUAL_USUARIO.md` deleted, `odoo-ui/angular.json` modified before this change) were left untouched.

## Next recommended

User decision: sync/archive the change (SDD closeout) and/or open the two chained PRs (branch + PR per approved delivery strategy). Nothing was committed — working tree contains both PRs' changes; splitting into PR1/PR2 branches is a commit-time decision for the user.
