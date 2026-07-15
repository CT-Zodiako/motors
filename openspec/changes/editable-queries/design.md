# SDD Design — editable-queries

## Decisions

**D1 — Module layout.** Choice: two new pure modules, existing routers stay wiring-only. `odoo/query_registry.py` — registry DDL constant + CRUD (`init_query_destinations(conn)`, `seed_from_schedules(conn)`, `upsert_destination(conn,…)`, `list_destinations(conn,name)`, `mark_ok/mark_stale(conn,…)`). `odoo/query_propagation.py` — `propagate_query_edit(conn, query) -> report`. `catalog.py` PATCH is thin wiring. Rationale: mirrors the file-to-bigquery precedent (file_upload.py wiring / bq_schema.py pure) — the D1/D9 loop needs isolated unit tests without TestClient. Tradeoffs: +2 files and an import graph to keep acyclic vs a fat catalog.py; embedding in catalog.py rejected (locked sync-propagation semantics are too complex to test through HTTP only).

**D2 — `query_destinations` schema.** Inline idempotent SQL in `init_db.init()` (repo pattern):
```sql
CREATE TABLE IF NOT EXISTS query_destinations (
  id SERIAL PRIMARY KEY,
  query_name VARCHAR NOT NULL REFERENCES odoo_queries(name) ON DELETE CASCADE,
  dataset_id VARCHAR NOT NULL,
  table_id   VARCHAR NOT NULL,
  origin     VARCHAR NOT NULL DEFAULT 'manual',  -- 'manual' | 'schedule'
  stale      BOOLEAN NOT NULL DEFAULT FALSE,
  last_error TEXT,
  last_sync_at TIMESTAMP,
  last_schema  JSONB,
  created_at TIMESTAMP NOT NULL DEFAULT now(),
  UNIQUE (query_name, dataset_id, table_id)
);
```
Seed: `INSERT … SELECT query_name, dataset_id, table_id, 'schedule' FROM query_schedules ON CONFLICT DO NOTHING`. Stale mechanism: boolean flag + `last_error`; set on failure, cleared (+`last_sync_at`,+`last_schema`) on success; UI reads it for "will retry on next run". `last_schema` caches the last written BQ schema so empty-result reloads and future drift UI know what BQ holds. Tradeoffs: status ENUM (ok/stale/failed) is more expressive but boolean+error satisfies the spec with less code; FK on UNIQUE `name` (harmless — deletes are soft so cascade never fires) vs repo's loose no-FK style (`query_schedules.query_name`); composite PK rejected (surrogate id matches `odoo_queries` style). `origin` distinguishes manual vs scheduled registration; pre-v1 manual uploads are absent by design and self-register on next upload (frontend note).

**D3 — Reuse without duplication; acyclic imports.** Extract three module-level pure helpers: `fetch_query_rows(query) -> list[dict]` in `runner.py` (from :17-28; applies stored domain/fields/limit_val); `load_rows_to_bigquery(dataset, table, rows, schema)` in `bigquery.py` (core of `upload_to_bigquery` :197-235 minus route concerns); reuse the normalization from `schedules.py` :332-340 inside the fetch path. Import graph: `catalog → {query_propagation, query_registry}`; `query_propagation → {runner, bigquery, query_registry}`; `bigquery → query_registry`; `schedules → {bigquery, query_registry}`. No `bigquery ↔ propagation` cycle because registry lives in its own module. Tradeoffs: extracting from the working upload path carries regression risk (mitigated by a characterization test written before extraction) vs copy-paste of the WRITE_TRUNCATE/schema config (rejected — would diverge); a single shared "services.py" rejected — BQ knowledge stays local to bigquery.py.

**D4 — Registry upsert placement.** Inside `upload_to_bigquery` (bigquery.py:197-235), after a successful load, with new param `origin='manual'`; the schedule executor (:342-346) passes `origin='schedule'`. Single choke point ⇒ all current and future BQ upload paths self-register (D6). Tradeoffs: couples a BQ function to a PG write (needs conn; but bigquery.py already does BQ→PG sync :238-279, so precedent exists) vs call-site upsert (explicit, but every future caller can forget — recreating the invisible-destination problem D6 fixes). Upsert failure must not fail a successful upload: catch + log + continue (destination self-heals on next upload).

**D5 — Union inference (bugfix D7).** Rewrite `_infer_bq_schema(rows)` (bigquery.py:134-144): union keys across ALL rows (already materialized in memory), first-seen key order (row-0 prefix preserved → deterministic tests), per-key type = STRING if observed non-null types differ (existing `_infer_column_type` STRING-promotion precedent), all-None → STRING. Empty rows → `[]` (caller decides, see matrix). Tradeoffs: full-scan union is O(Σ keys) — negligible vs network I/O; a sample bound (e.g., first 100) risks silently dropping late-appearing keys, which under D2 semantics means lost columns on reload — rejected.

**D6 — limit_val plumbing (D8).** `fetch_query_rows` reads `query["limit_val"]` and passes Odoo `limit = int if > 0 else False`. Call-site changes: `runner.py:26` `"limit": False` → use helper; `schedules.py:328` → route through the same fetch path instead of hardcoded `False`; propagation inherits enforcement automatically. Semantics: NULL/None/0 = no limit (Odoo convention); negative rejected at PATCH (400). Tradeoffs: centralizing in one helper changes three paths by deletion (fewer signatures to drift) vs an explicit `limit=` kwarg per path (more visible, but easy to forget on the next path).

**D7 — PATCH /queries/{name}.** Request `QueryPatchIn`: optional `description, domain, fields, limit_val, category_id`; plus optional `name/model/method` which, if present and differing from stored → 400 (explicit immutability, spec req). Validation: `fields` non-empty list[str]; `domain` list; `limit_val` ≥ 0 or null; `category_id` must exist. Unknown/inactive name → 404. Order: fetch current → validate immutables → UPDATE → **COMMIT** (edit durable before propagation, D9) → `propagate_query_edit` synchronous (D1/D10) → 200 `{query, propagation: {total, ok, failed, destinations: [{dataset_id, table_id, status: 'ok'|'failed'|'empty', error?}]}}`. Tradeoffs: sync latency ≈ 1 Odoo fetch + N BQ loads (rows fetched once, reused across destinations) — acceptable for small WRITE_TRUNCATE tables; background task rejected (locked D10, and the stale flag already gives an async retry story). Admitting immutable keys in the schema (vs strict-forbid) costs a comparison but yields the spec'd 400 instead of silently ignoring them.

**D8 — Frontend edit mode (no router).** New `QueryEditState` signal service. `query-list.ts` row action "Edit" → sets signal with the row query → switches shell active tab to 'create' (app.html:15-20 tab shell). `query-create.ts` reads the signal: wizard enters edit mode — pre-fill all steps; name/model/method rendered as read-only text (not disabled inputs, to signal immutability); save becomes "Save changes" → new `odoo-queries.update(name, payload)` (PATCH) → propagation summary panel (per-destination ✓/✗ + error, "failed destinations are marked stale and will retry on next run", pre-v1 note "destinations uploaded before this version re-register automatically on next manual upload") → clear signal → back to list. Destructive confirmation lives in the wizard save handler: diff old vs new `fields`; only when removed ≠ ∅ → confirm dialog naming the dropped columns + "column and history are permanently dropped (WRITE_TRUNCATE)". Tradeoffs: signal service vs localStorage/event bus — typed, testable, in-session only (fine: edit is one click away); embedding an edit form in query-list rejected (duplicates wizard validation); confirmation is frontend-only (backend silently drops per D2) — a confirm-flag round trip rejected as v1 over-engineering; spec assigns req 9 to the UI.

**D9 — Error semantics.** Locked: edit saved regardless (200 + report even on total Odoo failure); per-destination isolation; failure → `stale=TRUE`+`last_error`, success clears; **empty result → do NOT truncate**: mark stale, status `empty`, keep existing data. Tradeoff: a legitimately emptied query keeps old rows until investigated — accepted (WRITE_TRUNCATE-to-empty is irreversible; stale UI surfaces it; next scheduled run retries). **User-ratified at design gate (2026-07-15).**

## Data Flow
1. User clicks Edit in `query-list` → `QueryEditState` set → tab switch → wizard pre-filled, name/model/method read-only.
2. Save → frontend confirm iff fields were removed → `PATCH /queries/{name}`.
3. Backend: SELECT current (404 if missing) → validate (400s) → UPDATE odoo_queries → COMMIT (edit durable).
4. Load registry destinations for `name` (none → report `total: 0`, skip to 7).
5. `fetch_query_rows` once (new domain/fields/limit_val). On Odoo failure → mark ALL destinations stale + `last_error` → respond 200 all-failed report.
6. Per destination: union schema → `load_rows_to_bigquery` WRITE_TRUNCATE → ok: `mark_ok` (stale=FALSE, last_sync_at, last_schema); fail: `mark_stale` + error. Exceptions isolated per destination.
7. Respond `{query, propagation}` → UI renders summary + stale notes.
Registration paths (parallel): `init_db` seeds from `query_schedules`; manual upload + schedule executor upsert via D4.

## Error Handling Matrix
| Case | Behavior | Flag/Report | User-visible |
|---|---|---|---|
| Odoo down at propagation | No destination reloaded; edit kept | all stale, `last_error` | 200 + all-failed report |
| BQ table deleted externally | WRITE_TRUNCATE load recreates table | ok, stale cleared | ✓ |
| BQ dataset missing/permission | Load fails for that destination | stale + error | ✗ per destination |
| Partial failure | Others still reloaded | per-row status | mixed summary |
| Empty result set | No truncate; data kept | stale, status `empty` | warning row |
| Fields removed | New schema replaces old | column+history dropped (D2) | frontend confirm pre-save |
| Registry upsert fails on manual upload | Upload still succeeds | logged | none (self-heals) |
| Unknown name / immutable change / bad payload | — | — | 404 / 400 / 400 |
| Pre-v1 manual destination | Not in registry → not reloaded | — | self-register note |

## Testing Strategy
Backend, STRICT TDD (`cd odoo && .venv/bin/python -m pytest -q`):
- `tests/test_query_registry.py` — migration idempotent (init ×2, extends test_migration.py pattern); seed from query_schedules (conflict no-op); upsert insert vs update; mark_stale/mark_ok round-trip.
- `tests/test_union_schema.py` — disjoint keys union; first-seen order; mixed types → STRING; all-None → STRING; single-row parity.
- `tests/test_propagation.py` — all-ok; partial-failure isolation; total Odoo failure → all stale + edit committed; success clears stale; empty → stale/no-truncate; WRITE_TRUNCATE asserted; limit applied on reload.
- `tests/test_patch_queries.py` — 200 full edit; 400 model/method/name change; 400 empty fields/negative limit/bad domain; 404 unknown; propagation report in response; category validation.
- `tests/test_limit_enforcement.py` — runner/schedule/helper pass limit_val; None/0 → False.
Frontend (`cd odoo-ui && npm test`): `query-create.spec.ts` (pre-fill, read-only trio, update-not-create, destructive confirm only when fields removed, summary incl. stale note); `odoo-queries.spec.ts` (update → PATCH shape); `query-list.spec.ts` (edit sets state + tab switch).

---
- **status**: designed — ready for review gate before sdd-apply
- **risks**: (a) empty-result keeps stale rows — conservative choice, USER-RATIFIED at design gate 2026-07-15; (b) uniqueness excludes `project_id` — v1 single-project assumption; (c) sync PATCH latency grows with destination count; (d) extraction touches the working upload path — characterization test first
- **skill_resolution**: none
