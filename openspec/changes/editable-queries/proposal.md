# SDD Proposal — editable-queries

**Change:** `editable-queries` · **Repo:** `/Users/zodiakomac/DEV/motors` · **Artifact store:** engram · **Mode:** interactive

## Intent

Make saved queries editable end-to-end. When a user edits a saved query — adds or removes a field, changes filters, limit, description, or category — every BigQuery table that query has materialized is eagerly re-materialized, so destinations mirror the new query definition exactly (WRITE_TRUNCATE semantics). A removed field means its column and history are dropped; an added field appears everywhere. v1 targets BigQuery destinations only.

## Problem Statement

Saved queries are effectively immutable in practice. `POST /queries/` is a silent full upsert (`odoo/routers/catalog.py:65-76`) with zero propagation: destinations that already materialized a query keep stale schemas and data. Removing a field leaves orphaned columns in BigQuery; changing filters leaves stale rows. There is no record of which tables a query has ever written, so users must manually re-run uploads to every affected table from memory. Two latent bugs compound the problem: BQ schema inference reads only `rows[0]` keys (`bigquery.py:137`), so sparse fields silently disappear; and stored `limit_val` is ignored by both the runner (`routers/runner.py:26`) and the schedule executor (`schedules.py:328`), which hardcode `limit: False`. The frontend has no update path at all — `odoo-queries.ts` has no update method and `PATCH /queries/{name}` accepts category only (`catalog.py:90`).

## Scope

### In (v1)

- Editable surface: **fields, domain/filters, limit_val, description, category**. Model/method immutable (changing model = new query).
- Backend: extend `PATCH /queries/{name}` from category-only to the full editable surface; server-side immutability enforcement for name/model/method. POST upsert semantics unchanged for create; DELETE stays soft (`catalog.py:108`).
- New destination-registry table `query_destinations` (query ref, dataset_id, table_id, origin `manual|schedule`, last_schema, updated_at), written by **all** BQ upload paths; seeded from `query_schedules` at migration. Manual pre-v1 uploads are not recoverable — they self-register on next upload.
- Eager propagation **with reload** on edit save: re-run the query against Odoo and reload every registered destination table (WRITE_TRUNCATE).
- Best-effort per destination: the edit is saved regardless; per-destination success/failure reported in the response; failed destinations marked stale and healed on next run (scheduled tables already self-heal, `bigquery.py:216-220`).
- **In-scope bugfix #1:** `_infer_bq_schema` (`bigquery.py:134-144`) takes the union of keys across sampled rows instead of `rows[0]` only. Propagation correctness depends on it.
- **In-scope bugfix #2:** apply stored `limit_val` in runner (`routers/runner.py:26`) and schedule executor (`schedules.py:328`) instead of hardcoded `limit: False`. An editable limit must be real.
- Frontend: edit mode in the query wizard (`query-create.ts`), `update` method in `odoo-queries.ts`, propagation result surfaced in query-list/query-runner UI.
- Migration: inline idempotent SQL in `init_db.init()` per repo convention, covered by `odoo/tests/test_migration.py`.

### Out / Non-goals (v1)

- Raw-SQL editing of queries.
- Rename — `name` stays immutable (schedules reference queries by name; `query_schedules.query_name` has no FK).
- Postgres auto-propagation — BQ→PG sync tables untouched (`bigquery.py:238-279`); user re-syncs manually as today.
- Google Sheets as a source or destination.
- Async/queued propagation, locking, or conflict resolution beyond the low-contention assumption.

## Decisions

All decisions below were ratified with the user during the proposal question round (v1 lock).

**D1 — Eager propagation with reload.** On edit save, re-run the query against Odoo and reload every registered destination. *Rationale:* the product promise is "everything it materialized gets updated"; scheduled tables would eventually self-heal, manual tables never would. *Alternatives:* lazy heal-on-next-run (rejected — manual tables never heal); schema-only ALTER without data reload (rejected — filter changes need row-level refresh); mark-stale-only (rejected as primary mechanism, kept as failure fallback).

**D2 — Removed field = DROP column and its history.** Destinations mirror the new query exactly; WRITE_TRUNCATE under the new schema drops removed columns naturally. *Rationale:* mirror semantics are predictable and match existing scheduled-run behavior. *Alternative:* retain history in deprecated columns (rejected — breaks mirror expectation, complicates schema).

**D3 — BigQuery only in v1.** Postgres sync tables untouched; manual re-sync as today. *Rationale:* PG sync is already a manual user-driven step; auto-propagation doubles blast radius for marginal value. *Alternative:* propagate to PG too (deferred).

**D4 — No rename in v1.** `name` immutable; schedules reference queries by name with no FK safety net. *Alternative:* add FK + cascade (rejected — schema churn for little v1 value).

**D5 — Editable surface: fields, domain, limit_val, description, category; model/method immutable.** *Rationale:* changing the model yields a fundamentally different dataset — that is a new query, not an edit. *Alternative:* allow model edits with re-derivation (rejected — conflates create and edit lifecycles).

**D6 — New `query_destinations` registry.** Records every BQ table a query materializes; written by all BQ upload paths; seeded from `query_schedules`. *Rationale:* propagation must know where a query lives; today only scheduled destinations are recorded. *Known gap:* pre-v1 manual uploads are not recoverable and self-register on next upload (documented in UX copy). *Alternative:* infer destinations by scanning BQ datasets (rejected — unreliable, slow).

**D7 — Fix `rows[0]`-only schema inference (in-scope bugfix).** Union of keys across sampled rows in `_infer_bq_schema`. *Rationale:* if inference drops sparse keys, an added-but-sparse field silently vanishes on reload — the core promise breaks.

**D8 — Apply stored `limit_val` (in-scope bugfix).** Replace hardcoded `limit: False` at `routers/runner.py:26` and `schedules.py:328`. *Rationale:* an editable limit that is ignored is a lie in the UI; propagation must re-run with the same semantics users see.

**D9 — Best-effort per-destination propagation with stale marking.** Edit is saved regardless of outcome; per-destination success/failure reported; failures marked stale, healed on next run. *Rationale:* a transient BQ/Odoo failure must not block a legitimate edit. *Alternative:* all-or-nothing across destinations (rejected — cross-system atomicity is impossible with BQ).

**D10 — Synchronous propagation on save; low contention assumed.** *Rationale:* simple, observable, matches current scale. *Alternative:* background job queue (deferred until contention or latency proves it necessary).

## Requirements outline

### query-catalog (backend delta spec)

- R-CAT-1: `PATCH /queries/{name}` accepts fields, domain, limit_val, description, category_id; validates payload; rejects name/model/method changes.
- R-CAT-2: On successful edit, run synchronous propagation: re-run the query against Odoo; reload each `query_destinations` table with WRITE_TRUNCATE under the union-inferred schema.
- R-CAT-3: Response reports per-destination result (ok | failed + error); failed destinations marked stale for next-run healing.
- R-CAT-4: Migration adds `query_destinations` via inline idempotent SQL in `init_db.init()`; seed from `query_schedules`; extend `odoo/tests/test_migration.py`.
- R-CAT-5: All BQ upload paths (manual `upload_to_bigquery` :197-235, schedule executor :314-364) upsert `query_destinations`.
- R-CAT-6 (bugfix): `_infer_bq_schema` builds union of keys across sampled rows.
- R-CAT-7 (bugfix): runner and schedule executor honor stored `limit_val`.

### query-ui (frontend delta spec)

- R-UI-1: Edit entry point from query list; wizard (`query-create.ts`) opens in edit mode pre-filled; name/model/method read-only.
- R-UI-2: `odoo-queries.ts` gains `update(name, payload)` calling the extended PATCH.
- R-UI-3: After save, show per-destination propagation summary; failures flagged with "will retry on next run" copy; note that pre-v1 manual destinations appear after their next upload.
- R-UI-4: Confirmation copy when fields are removed: "column and its history will be dropped."

## Impact

- `odoo/init_db.py` — `query_destinations` migration; seed from `query_schedules`.
- `odoo/routers/catalog.py` — PATCH extended beyond category-only (:90); immutability validation; propagation trigger on save.
- `odoo/routers/bigquery.py` — `_infer_bq_schema` union fix (:134-144); registry writes in `upload_to_bigquery` (:197-235); propagation reload reusing the WRITE_TRUNCATE path (:216-220).
- `odoo/routers/schedules.py` — executor applies `limit_val` (:328); registry writes on scheduled uploads (:314-364).
- `odoo/routers/runner.py` — apply stored `limit_val` (:26).
- `odoo/tests/test_migration.py` + new tests — migration, registry seeding, propagation, union inference, limit application.
- Frontend — `query-create.ts` (edit mode, save :271-294), `query-list.ts`, `query-runner.ts`, `odoo-queries.ts` (`update` method).
- Specs — delta specs per `openspec/specs/query-catalog/spec.md` and `openspec/specs/query-ui/spec.md` conventions.

## Risks

- **R1 — Propagation latency on save.** Synchronous reload of many destinations can make edits slow. *Mitigation:* per-destination best-effort with reporting; stale marking heals failures (D9); async deferred (D10).
- **R2 — Destructive column drops.** Removed fields drop column + history irreversibly. *Mitigation:* explicit UI confirmation (R-UI-4); user-ratified (D2).
- **R3 — Incomplete destination coverage.** Pre-v1 manual uploads are not in the registry. *Mitigation:* documented self-registration on next upload; UX copy (R-UI-3).
- **R4 — Union-inference edge cases.** Heterogeneous records may widen schemas. *Mitigation:* bounded sample consistent with current inference; test coverage.
- **R5 — Silent behavior change from limit fix.** Existing runs that ignored `limit_val` will now honor it. *Mitigation:* called out in change notes; matches stored user intent.
- **R6 — Name-based schedule references.** `query_schedules.query_name` has no FK. *Mitigation:* rename immutable (D4); registry stores an explicit query ref.

## Rollback

Migration is additive (new table). Rollback = drop `query_destinations`, revert PATCH to category-only, revert the two bugfix changes. BQ tables already reloaded keep their new schemas (forward-only data effect; a re-edit/re-upload restores prior shape if needed).

## Success Criteria

- Editing fields/domain/limit and saving reloads every registered BQ destination: removed columns gone, added columns present with data.
- A field absent from `rows[0]` but present in later rows appears in the BQ schema (union inference).
- Stored `limit_val` is honored by manual run, schedule run, and propagation reload.
- Per-destination propagation report returned and displayed; failed destinations marked stale and healed on next run.
- `query_destinations` seeded from `query_schedules`; all BQ upload paths register destinations.
- Migration test and new propagation/inference/limit tests pass.
