# Tasks: editable-queries — Editable stored queries: destination registry, synchronous propagation & edit UI

## Review Workload Forecast

| Field | Value |
|-------|-------|
| Estimated changed lines | ~1,760 total (range 1,400–2,150) |
| 400-line budget risk | High |
| Chained PRs recommended | Yes |
| Suggested split | 7 work-unit commits: WU1 registry (~280) → WU2 BQ union/extract/upsert (~260) → WU3 fetch+limit (~160) → WU4 propagation (~270) → WU5 PATCH (~260) → WU6 FE plumbing (~220) → WU7 FE edit UI (~310). Each commit individually under the 400-line budget. |
| Delivery strategy | direct-to-main per work unit — established pattern: user pushes from own terminal |
| Chain strategy | stacked-to-main |

Decision before apply: **direct-to-main with work-unit commits (user-ratified 2026-07-15)** — 7 commits on branch `actualizacion_querys`, each <400 lines; user pushes to main from own terminal at the end. PRs skipped (same as file-to-bigquery).
Chained PRs recommended: No (superseded by user decision; commit slicing preserves review focus)
Chain strategy: direct-to-main
400-line budget risk: High (accepted — no PR review per slice; verify phase still runs)

Note: the suggested 5 work units were split into 7 (backend WU4 split into propagation module + PATCH endpoint; frontend WU5 split into plumbing + wizard UI) so every work-unit commit stays under the 400-line budget.

Strict TDD is enabled (strict_tdd: true). Every work unit runs RED → GREEN → TRIANGULATE → REFACTOR in order; record each command's output (pytest/npm summaries) as evidence in the apply log or PR body. Backend suite: `cd odoo && .venv/bin/python -m pytest -q`. Frontend suite: `cd odoo-ui && npm test`. Do not start a work unit until the previous unit's full-suite check is green.

## 0. Verify-at-apply preflight (blocking discovery, do first)

- [ ] Read `odoo/routers/catalog.py`: confirm `QueryIn` fields (:22-29), current PATCH handler body (:90), the 400/404 error style, and the response helper used by sibling routes. <!-- sdd-owner: implementation -->
- [ ] Read `odoo/init_db.py` init() (lines 1-82) and `odoo/test_migration.py`: confirm the inline idempotent-migration pattern and how tests obtain a DB connection (conftest fixture, env var, skip-if-unavailable rule). <!-- sdd-owner: implementation -->
- [ ] Confirm test file naming/placement convention (`odoo/test_*.py` flat beside source, per `test_migration.py`) before creating new test files. <!-- sdd-owner: implementation -->
- [ ] Check `google.api_core` exception import style and how the BigQuery client is constructed/faked in `odoo/bigquery.py` and any existing tests (search for `google.api_core`, `bigquery.Client`, mock/fake patterns). <!-- sdd-owner: implementation -->
- [ ] Read `odoo/routers/runner.py` (:17-28) and `odoo/schedules.py` `_execute_schedule` (:314-364): confirm exact call signatures at :26 and :328/:332-346 that `fetch_query_rows` must preserve. <!-- sdd-owner: implementation -->
- [ ] Read frontend `odoo-ui/src/app/query-create.ts` (save :271-294), `query-list.ts`, and `app.html:15-20`: confirm the tab-switch mechanism (no router) and how the wizard could consume an edit-state signal. <!-- sdd-owner: implementation -->
- [ ] Confirm the frontend spec harness: locate an existing spec using `HttpClientTestingModule`/`provideHttpClientTesting` and confirm the Angular signal APIs available in this codebase's Angular version. <!-- sdd-owner: implementation -->

## Work Unit 1 — Query destination registry + init_db migration (D1, D2)

### RED
- [ ] Create `odoo/test_query_registry.py` with failing tests: init creates table with D2 columns/constraints; idempotent double init; `seed_from_schedules` INSERT…SELECT ON CONFLICT DO NOTHING (run twice → same row count); `upsert_destination` insert-then-update on UNIQUE(query_name,dataset_id,table_id); `list_destinations(query_name)`; `mark_ok` sets stale=false, last_error NULL, last_sync_at, last_schema; `mark_stale` sets stale=true + last_error. <!-- sdd-owner: implementation -->
- [ ] Extend `odoo/test_migration.py`: after init(), `query_destinations` exists with D2 shape; re-running init() is a no-op. <!-- sdd-owner: implementation -->
- [ ] Run `cd odoo && .venv/bin/python -m pytest -q test_query_registry.py test_migration.py`; record the failing output (module `query_registry` missing). <!-- sdd-owner: implementation -->

### GREEN
- [ ] Create `odoo/query_registry.py`: `QUERY_DESTINATIONS_DDL` const (id PK; query_name FK→odoo_queries(name) ON DELETE CASCADE; dataset_id; table_id; origin CHECK manual|schedule; stale BOOL; last_error; last_sync_at; last_schema JSONB; created_at; UNIQUE(query_name,dataset_id,table_id)) plus `init_query_destinations`, `seed_from_schedules`, `upsert_destination`, `list_destinations`, `mark_ok`, `mark_stale` per D1. <!-- sdd-owner: implementation -->
- [ ] Wire `odoo/init_db.py` init(): call `init_query_destinations(conn)` then `seed_from_schedules(conn)` after the existing migrations; keep idempotent. <!-- sdd-owner: implementation -->
- [ ] Re-run the two test files; record green output. <!-- sdd-owner: implementation -->

### TRIANGULATE
- [ ] Add edge tests: seed with zero schedules (no-op); upsert flipping origin manual→schedule; `list_destinations` for unknown query → []; FK cascade (delete odoo_queries row → its destinations removed) if the test DB supports it. <!-- sdd-owner: implementation -->
- [ ] Re-run; record green output. <!-- sdd-owner: implementation -->

### REFACTOR
- [ ] Keep `query_registry.py` dependency-free (no imports from bigquery/odoo client/routers — acyclic per D3); extract a row→dict helper only if duplicated. <!-- sdd-owner: implementation -->
- [ ] Full-suite check: `cd odoo && .venv/bin/python -m pytest -q` green; record output. PR 1 stops here. <!-- sdd-owner: implementation -->

## Work Unit 2 — BQ union schema inference + load_rows extraction + registry upsert wiring (D3, D4, D5)

### RED
- [ ] CHARACTERIZATION TEST FIRST (blocking, per D3): create `odoo/test_bigquery_upload.py` pinning current `upload_to_bigquery` (:197-235) behavior with a fake BQ client — WRITE_TRUNCATE disposition, dataset.table target, schema passed to the load job (:216-220). Must pass BEFORE any refactor; record passing output. <!-- sdd-owner: implementation -->
- [ ] Create `odoo/test_union_schema.py` (fails against current `_infer_bq_schema` :134-144): union of keys across ALL rows in first-seen order; conflicting types for a key → STRING; all-None column → STRING. <!-- sdd-owner: implementation -->
- [ ] Add failing tests: `upload_to_bigquery(..., origin='manual')` calls `query_registry.upsert_destination`; an upsert exception is caught+logged and never fails the upload (D4). <!-- sdd-owner: implementation -->

### GREEN
- [ ] Rewrite `_infer_bq_schema` (bigquery.py:134-144) as union inference per D5 (first-seen order, conflict→STRING, all-None→STRING). <!-- sdd-owner: implementation -->
- [ ] Extract `load_rows_to_bigquery(client, dataset_id, table_id, rows, schema)` from `upload_to_bigquery`; behavior identical (characterization test stays green). <!-- sdd-owner: implementation -->
- [ ] Add `origin='manual'` param to `upload_to_bigquery`; call `upsert_destination` inside try/except (log warning, never raise); update the `schedules.py` upload call (:342-346) to pass `origin='schedule'`. <!-- sdd-owner: implementation -->
- [ ] Run backend suite; record green output. <!-- sdd-owner: implementation -->

### TRIANGULATE
- [ ] Add tests: nested dict vs scalar conflict → STRING; first-seen order across 3+ rows; `origin='schedule'` path upserts origin 'schedule'; empty-rows input behavior pinned. <!-- sdd-owner: implementation -->
- [ ] Re-run; record green output. <!-- sdd-owner: implementation -->

### REFACTOR
- [ ] Verify import direction stays acyclic (bigquery.py → query_registry only; registry imports nothing back). <!-- sdd-owner: implementation -->
- [ ] Full-suite check: backend pytest green; record output. PR 2 stops here. <!-- sdd-owner: implementation -->

## Work Unit 3 — fetch_query_rows extraction + stored limit enforcement (D3, D6)

### RED
- [ ] Characterization test for the current runner path (`odoo/routers/runner.py:17-28`): execute → rows returned; record passing output before extraction. <!-- sdd-owner: implementation -->
- [ ] Create `odoo/test_limit_enforcement.py` (failing): stored limit_val=5 → Odoo fetch receives limit 5 in runner AND in the schedule executor; limit_val=None and limit_val=0 → no limit (False). <!-- sdd-owner: implementation -->

### GREEN
- [ ] Extract `fetch_query_rows(query)` into `odoo/routers/runner.py`; compute `limit = int(limit_val) if limit_val and int(limit_val) > 0 else False` (D6). <!-- sdd-owner: implementation -->
- [ ] Route `runner.py:26` and `schedules.py:328` through `fetch_query_rows` (removing the hardcoded `False`). <!-- sdd-owner: implementation -->
- [ ] Run backend suite; record green output. <!-- sdd-owner: implementation -->

### TRIANGULATE
- [ ] Add tests: string "5" coerced via int(); limit_val=0 → False; schedule executor row normalization (:332-340) unchanged. <!-- sdd-owner: implementation -->
- [ ] Re-run; record green output. <!-- sdd-owner: implementation -->

### REFACTOR
- [ ] Single source of limit computation inside `fetch_query_rows`; no duplicated limit logic in runner/schedules. <!-- sdd-owner: implementation -->
- [ ] Full-suite check: backend pytest green; record output. PR 3 stops here. <!-- sdd-owner: implementation -->

## Work Unit 4 — Synchronous propagation module (D1, D9)

### RED
- [ ] Create `odoo/test_propagation.py` (failing): single destination success → status 'ok' + `mark_ok` with the union schema; Odoo fetch raises → all destinations 'failed' + `mark_stale(error)` and the module does not raise; empty result set → NO truncate (`load_rows_to_bigquery` not called), status 'empty', marked stale (D9, user-ratified). <!-- sdd-owner: implementation -->
- [ ] Add failing multi-destination isolation test: destination 1 load raises → dest 1 'failed', dest 2 still processed as 'ok'. <!-- sdd-owner: implementation -->

### GREEN
- [ ] Create `odoo/query_propagation.py`: `propagate_query_edit(conn, query) -> {total, ok, failed, destinations:[{dataset_id, table_id, status, error?}]}`; fetch rows once via `fetch_query_rows`; per destination reload via `load_rows_to_bigquery` unless empty; update registry via `mark_ok`/`mark_stale`. <!-- sdd-owner: implementation -->
- [ ] Run backend suite; record green output. <!-- sdd-owner: implementation -->

### TRIANGULATE
- [ ] Add tests: zero destinations → `{total:0, ok:0, failed:0, destinations:[]}` without fetching from Odoo; `last_schema` stored by `mark_ok` equals the union schema of the fetched rows. <!-- sdd-owner: implementation -->
- [ ] Re-run; record green output. <!-- sdd-owner: implementation -->

### REFACTOR
- [ ] Confirm acyclic imports (propagation imports registry + runner.fetch_query_rows + bigquery.load_rows_to_bigquery; only catalog will import propagation). <!-- sdd-owner: implementation -->
- [ ] Full-suite check: backend pytest green; record output. PR 4 stops here. <!-- sdd-owner: implementation -->

## Work Unit 5 — PATCH /queries/{name} full editable surface (D7)

### RED
- [ ] Create `odoo/test_patch_queries.py` (failing): PATCH updates fields/domain/limit_val/description/category_id; name/model/method present-and-differing → 400 (one test each); same-value name → 200; unknown name → 404; negative limit_val → 400; response shape `{query, propagation:{total, ok, failed, destinations[...]}}`. <!-- sdd-owner: implementation -->
- [ ] Add failing tests: Odoo down during propagation → HTTP 200, edit persisted, propagation entries 'failed', destinations marked stale; zero registered destinations → propagation total 0 (edit still saved). <!-- sdd-owner: implementation -->

### GREEN
- [ ] Add `QueryPatchIn` to `odoo/routers/catalog.py` (optional fields/domain/limit_val/description/category_id; optional name/model/method validated equal-or-absent, else 400; negative limit_val → 400). <!-- sdd-owner: implementation -->
- [ ] Rewrite PATCH (catalog.py:90) in D7 order: fetch → validate → UPDATE → COMMIT → `propagate_query_edit` synchronously → 200 `{query, propagation}`. <!-- sdd-owner: implementation -->
- [ ] Run backend suite; record green output. <!-- sdd-owner: implementation -->

### TRIANGULATE
- [ ] Add tests: category-only PATCH (backwards compat with the current frontend call) still 200; empty-body no-op PATCH 200; limit_val=0 clears the limit (stored per the D6 no-limit convention). <!-- sdd-owner: implementation -->
- [ ] Re-run; record green output. <!-- sdd-owner: implementation -->

### REFACTOR
- [ ] Keep the handler thin (D1 wiring only); extract a validation helper if the handler exceeds ~40 lines. <!-- sdd-owner: implementation -->
- [ ] Full-suite check: backend pytest green; record output. PR 5 stops here. <!-- sdd-owner: implementation -->

## Work Unit 6 — Frontend edit plumbing: QueryEditState + update() + list edit entry (D8)

### RED
- [ ] Add failing tests to `odoo-ui/src/app/odoo-queries.spec.ts`: `update(name, payload)` issues PATCH to `/queries/{name}` with the body, returns an Observable, propagates HTTP errors. <!-- sdd-owner: implementation -->
- [ ] Create failing `odoo-ui/src/app/query-edit-state.spec.ts`: signal service `beginEdit(query)`/`clear()` semantics; current edit payload readable as a signal. <!-- sdd-owner: implementation -->
- [ ] Add failing `odoo-ui/src/app/query-list.spec.ts` test: row Edit action → `beginEdit(query)` + tab switch via the app.html:15-20 shell mechanism. <!-- sdd-owner: implementation -->

### GREEN
- [ ] Add `update(name, payload)` to `odoo-ui/src/app/odoo-queries.ts`. <!-- sdd-owner: implementation -->
- [ ] Create `odoo-ui/src/app/query-edit-state.ts` signal service per D8. <!-- sdd-owner: implementation -->
- [ ] Add an Edit entry per row in `query-list.ts` (+ template): sets edit state and switches to the create tab. <!-- sdd-owner: implementation -->
- [ ] Run `cd odoo-ui && npm test`; record green output. <!-- sdd-owner: implementation -->

### TRIANGULATE
- [ ] Add tests: URL-encoding of names with spaces/special chars in update(); `beginEdit` called twice replaces prior state; Edit on a query with domain+fields carries the full prefill payload. <!-- sdd-owner: implementation -->
- [ ] Re-run npm test; record green output. <!-- sdd-owner: implementation -->

### REFACTOR
- [ ] Share the Query type between list/state/api modules; remove duplicated interfaces. <!-- sdd-owner: implementation -->
- [ ] Full-suite checks: `npm test` green AND `cd odoo && .venv/bin/python -m pytest -q` still green; record both. PR 6 stops here. <!-- sdd-owner: implementation -->

## Work Unit 7 — Frontend wizard edit mode + propagation summary + destructive confirm (D8; consumes D7 response)

### RED
- [ ] Add failing `odoo-ui/src/app/query-create.spec.ts` tests: edit mode pre-fills fields/domain/limit/description/category; name/model/method rendered read-only (disabled); save in edit mode calls `update()` not `create()`. <!-- sdd-owner: implementation -->
- [ ] Add failing tests: propagation summary panel renders ok/failed/empty entries plus "will retry on next run" copy and the pre-v1 self-register note (req 8); removing a field then saving triggers the destructive confirmation listing the removed fields (req 9); no removed fields → no confirmation. <!-- sdd-owner: implementation -->

### GREEN
- [ ] Implement edit mode in `query-create.ts` (consume the QueryEditState signal; read-only name/model/method; pre-fill; save → `odoo-queries.update`). <!-- sdd-owner: implementation -->
- [ ] Render the propagation summary panel from the PATCH response (template + styles, following existing panel/modal patterns). <!-- sdd-owner: implementation -->
- [ ] Implement removed-field destructive confirmation (diff old vs new fields; confirm only when removed ≠ ∅). <!-- sdd-owner: implementation -->
- [ ] Run `cd odoo-ui && npm test`; record green output. <!-- sdd-owner: implementation -->

### TRIANGULATE
- [ ] Add tests: domain-only change → no destructive confirm; removing all fields → confirm lists all removed; PATCH response with zero destinations → panel shows the self-register note. <!-- sdd-owner: implementation -->
- [ ] Re-run npm test; record green output. <!-- sdd-owner: implementation -->

### REFACTOR
- [ ] Extract the propagation summary into a small presentational component if the create template grows unwieldy; dedupe confirmation copy. <!-- sdd-owner: implementation -->
- [ ] Full-suite checks: `npm test` green AND backend pytest still green; record both. PR 7 stops here. <!-- sdd-owner: implementation -->

## Post-apply bounded review & lifecycle gates (parent-owned)

- [ ] Track changed lines per work-unit commit against this tasks.md (scope, D-refs, 400-line budget) before the user pushes. <!-- sdd-owner: parent -->
- [ ] Verify the cumulative diff stays within forecast (~1,760 lines); escalate if any single PR exceeds 400 changed lines. <!-- sdd-owner: parent -->
- [ ] After WU7 lands and verify passes, run the SDD sync + archive phases for `editable-queries`. <!-- sdd-owner: parent -->

## Phase result

- Status: tasks written (awaiting parent persistence + user gate before sdd-apply).
- Executive summary: 7 strictly-TDD work units covering all 9 spec requirements and D1–D9; each unit leaves the repo green and maps 1:1 to a chained stacked-to-main PR under the 400-line budget.
- Artifacts: tasks.md returned inline (this phase has no file/memory tools); parent persists to engram topic `sdd/editable-queries/tasks`. Persistence NOT performed by this phase.
- Per-WU line estimates: WU1 ~280 (220–330); WU2 ~260 (210–310); WU3 ~160 (120–200); WU4 ~270 (220–330); WU5 ~260 (210–320); WU6 ~220 (170–280); WU7 ~310 (250–380).
- Total forecast: ~1,760 changed lines (range 1,400–2,150); High 400-line risk → 7 chained PRs, stacked-to-main, each under budget.
- Next recommended: user reviews tasks.md → sdd-apply starting at Section 0 preflight, WU1 first.
- Risks: line estimates are forecasts (re-verify at Section 0); registry/propagation tests need a Postgres test DB (preflight item 2); frontend spec harness patterns to confirm (preflight item 7); WU6/WU7 depend on the PATCH response shape from WU5 — keep the D7 contract stable.
- skill_resolution: none