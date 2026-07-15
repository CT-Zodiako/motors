# Verify Report — editable-queries

**Verdict: PASS — 9/9 requirements verified with executable evidence.**

Initial reviewer verdict was PASS WITH GAPS (2 full + 2 partial). All gaps were closed and re-verified before delivery. Fresh evidence on main @ 6912420 + gap-closure commit-pending state:

| Command | Result |
|---|---|
| `cd odoo && .venv/bin/python -m pytest -q` | **213 passed**, 5 warnings (FastAPI deprecations only) |
| `cd odoo-ui && npm test` | **54 passed**, 9 test files |
| `cd odoo-ui && npx ng build` | **Success** |

## Per-requirement verification

### query-catalog delta

| Requirement | Verdict | Scenario evidence |
|---|---|---|
| Query Destination Registry | PASS | Idempotent migration: `test_query_registry.py::test_init_is_idempotent_for_destinations`, `test_seed_is_idempotent`. Seed: `test_init_seeds_from_query_schedules`. Manual self-register: `test_union_schema.py::test_upload_with_query_name_upserts_destination` + FE threading `query-runner.ts:337`→`bigquery.ts`. Scheduled upsert: `test_origin_schedule_passed_from_schedules_executor`. DDL: `query_registry.py:9-24`, wired `init_db.py:71-74`. |
| Synchronous Destination Propagation on Edit | PASS | All-ok: `test_propagation.py::test_propagate_single_destination_ok`. WRITE_TRUNCATE: `test_bigquery_upload.py::test_upload_truncates_and_passes_schema`. Sync-in-PATCH: `catalog.py:144-147`. Partial failure + stale: `test_propagate_partial_failure_isolation`. Total Odoo failure: `test_propagate_odoo_failure_marks_all_stale` (edit persisted, `catalog.py:131-147`). Empty → no truncate (D9, user-ratified): `test_propagate_empty_result_no_truncate`. Zero destinations: `test_propagate_zero_destinations`. BQ-only (D3): `query_propagation.py:91-116`. |
| BigQuery Schema Inference from Query Results | PASS | Union: `test_union_schema.py::test_union_keys_across_all_rows`, `test_first_seen_order_preserved`. Conflict→STRING: `test_type_conflict_across_rows_promotes_to_string`, `test_nested_dict_vs_scalar_conflict`. All-None→STRING: `test_all_none_column_is_string`. Added/removed mirror: composition of union + WRITE_TRUNCATE (`bigquery.py:184-186`); BQ mocked. |
| Stored Query Limit Enforcement | PASS | Manual: `test_limit_enforcement.py::test_fetch_query_rows_with_limit`. Scheduled: `test_schedule_executor_routes_through_fetch_query_rows`. None/0→False: `test_fetch_query_rows_none_limit_is_false`, `..._zero_limit_is_false`. String coercion + negative triangulation. Single source: `runner.py:14-33`. Propagation path shares helper (`query_propagation.py:44`). |
| Query Recategorization Endpoint (MODIFIED) | PASS | Recategorize: `test_catalog_categories.py::test_patch_recategorizes_query`. 404: `test_patch_unknown_query_404`. Invalid category: `test_patch_invalid_category_422_unchanged`. Full edit: `test_patch_queries.py::test_patch_full_edit_success`, `test_patch_propagation_in_response`. 400 invalid payload: `test_patch_empty_fields_400`, `test_patch_invalid_domain_400`. Immutables: `test_patch_immutable_{name,model,method}_rejected`. Backwards-compat: `test_patch_category_only_backwards_compat`. Triangulation (gap-closure): `test_patch_same_name_value_ok`, `test_patch_empty_body_noop`, `test_patch_limit_zero_clears_limit`. |

### query-ui delta

| Requirement | Verdict | Scenario evidence |
|---|---|---|
| Query Edit Entry and Wizard Edit Mode | PASS | Entry: `query-list.html:80-85` + `query-list.spec.ts::editQuery sets edit state and navigates via callback`. Pre-fill: `query-create.spec.ts::edit mode pre-fills name, limit, category, fields, and filters from the query`. Read-only immutables (gap CLOSED): `query-create.spec.ts::in edit mode name input is readonly, model cards are non-interactive, and method is shown read-only` + `::selectModel is a no-op when in edit mode`; impl: edit-summary block + `[disabled]="isEditMode()"` model cards + `selectModel()` early-return (`query-create.ts:263`). |
| Query Update API Client | PASS | `odoo-queries.spec.ts::update() PATCHes /queries/{name}...` + URL-encoding test; impl `odoo-queries.ts:62-64`. update-not-create: `query-create.spec.ts::save in edit mode calls update() not create()`. 400 state retention (gap CLOSED): `query-create.spec.ts::400 error keeps edit mode and input state intact`. |
| Propagation Summary After Save | PASS | Rendering: `query-create.html:296-325` + data-level test. Retry note (gap CLOSED): `query-create.spec.ts::propagation summary shows retry note for failed destinations` (DOM assertion). Pre-v1 self-register note (gap CLOSED): `query-create.spec.ts::propagation summary includes pre-v1 self-register note` (DOM assertion); impl `query-create.html` `.self-register-note`. |
| Removed-Field Destructive Confirmation | PASS | `query-create.spec.ts::removing fields shows destructive confirmation and does NOT send PATCH until confirmed`, `::confirmDestructiveSave proceeds with the update`, `::no removed fields → no confirm, direct save`. Dialog lists removed fields + history-dropped copy: `query-create.html:328-349`; diff logic `query-create.ts:344-353`. |

## Tasks conformance

All 7 work units present; tasks.md forecast ~1,760 lines vs actual ~1,734 (delivery commit: 52 files, +4,906/-178 including openspec/ artifacts). Deviations (none affecting compliance): seed uses ON CONFLICT DO UPDATE (idempotency tests green); WU4 ~351 lines (slightly over band, under 400 commit budget); `mark_ok` schema equality is composition-evident.

## Scope hygiene

- `odoo/routers/explorer.py` unrelated change REVERTED before delivery.
- `query-runner.spec.ts`/`query-runner.html` restored from HEAD after rogue rewrite; mocks updated for `domain`/`fields` interface.
- `query_bridge.py` orphan predates this change (initial commit) — untouched.

## Risks noted (accepted)

- Live Odoo/BigQuery behavior fully mocked in tests (FakeOdoo/FakeBQClient); registry tests run against real Postgres. Live E2E against real services not performed for this change.
- Pre-v1 manual destinations self-register on next upload (documented in UI copy).

**Status: PASS · 9/9 requirements · 29/29 scenarios covered · next: sync → archive**
