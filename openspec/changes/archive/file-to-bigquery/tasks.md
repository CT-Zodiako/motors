# Tasks: file-to-bigquery — Upload .xlsx/.csv files to BigQuery

## Review Workload Forecast

| Field | Value |
|-------|-------|
| Estimated changed lines | ~2,250 total (range 1,900–2,600) |
| 400-line budget risk | High |
| Chained PRs recommended | Yes |
| Suggested split | PR 1 (bq_schema core) → PR 2 (inspect/preview API) → PR 3 (load API) → PR 4 (frontend wizard) → PR 5 (frontend specs) |
| Delivery strategy | direct-to-main (user-approved; PRs skipped) |
| Chain strategy | n/a — single local branch, work-unit commits, user pushes to main |

Decision needed before apply: No (user switched to direct-to-main mid-apply; PR #3 closed unmerged at the end since its commit is included in the direct push)
Chained PRs recommended: No (superseded)
Chain strategy: direct-to-main
400-line budget risk: High (accepted — no PR review per slice; verify phase still runs)

### Per-PR forecast

| PR | Contents | Est. changed lines | Budget risk |
|----|----------|--------------------|-------------|
| 1 | `odoo/bq_schema.py` + `odoo/tests/test_bq_schema.py` | ~460 | Medium (over budget; if actuals grow, split triangulation/property tests into a follow-up) |
| 2 | `odoo/routers/file_upload.py` (inspect/preview) + `odoo/requirements.txt` + `odoo/tests/test_file_upload_inspect_preview.py` | ~450 | Medium |
| 3 | `odoo/routers/file_upload.py` (load endpoint, stacked on PR 2) + `odoo/tests/test_file_upload_load.py` | ~440 | Medium |
| 4 | `odoo-ui/src/app/app.ts` + `odoo-ui/src/app/services/file-upload.service.ts` + `odoo-ui/src/app/file-upload/file-upload.{ts,html,css}` | ~535 | High (split nav+service from wizard if actuals grow) |
| 5 | `odoo-ui` service + wizard specs | ~370 | Low |

Strict TDD (openspec/config.yaml strict_tdd: true): sequence every work unit RED → GREEN → TRIANGULATE → REFACTOR and record command outputs as evidence. Backend runner: `cd odoo && .venv/bin/python -m pytest -q`. Frontend runner: `cd odoo-ui && npm test`. NOTE: config apply/verify test_command covers frontend only — backend pytest MUST also run before every backend PR.

## 0. Verify-at-apply preflight (blocking discovery, do first)

- [ ] Read `odoo/routers/bigquery.py` and record the HTTPException detail convention (plain string vs structured object); all new endpoint error envelopes in D10/D11 MUST match it. <!-- sdd-owner: implementation -->
- [ ] Read `odoo/routers/bigquery.py` (and any datasets router) and record the existing datasets-list endpoint path + response shape used to populate the destination Select. <!-- sdd-owner: implementation -->
- [ ] Read `odoo-ui/src/app/app.ts` and record the exact Tab union members + nav entry shape; read the query-create layout for where the wizard tab anchors. <!-- sdd-owner: implementation -->
- [ ] Confirm `_infer_string_type`, `_infer_field_type`, `_promote_bq_type`, `_BQ_TYPE_RANK` regexes and `MAX_UPLOAD_ROWS` are importable from `odoo/routers/bigquery.py` with ZERO edits to that file, and record the google-exceptions import style used by existing tests (e.g. `from google.api_core.exceptions import NotFound, Conflict`). <!-- sdd-owner: implementation -->
- [ ] Confirm odoo-ui spec placement convention (colocated `*.spec.ts` vs `__tests__/`) and copy the `HttpClientTestingModule` setup pattern from an existing service spec. <!-- sdd-owner: implementation -->

## Work Unit 1 — PR 1: `odoo/bq_schema.py` pure-logic module (D3, D4, D5, D6, D7, D8)

RED
- [x] Create `odoo/tests/test_bq_schema.py` with failing `sanitize_column_name(raw, used)` tests: `[^A-Za-z0-9_]`→`_`, leading-digit/empty → `_` prefix, 1024 truncate, case-insensitive dedupe `_2`/`_3` with base re-truncation, `""`→`"_"`. <!-- sdd-owner: implementation -->
- [x] Add failing CSV extraction tests from byte fixtures: utf-8-sig BOM, cp1252 fallback, delimiter sniffing `, ; \t |`, ragged row → error naming the row number, empty file → error, fully-empty rows dropped, `ExtractedTable(headers, rows)` positional shape, pseudo-sheet name `"CSV"`, all values `str|None`. <!-- sdd-owner: implementation -->
- [x] Add failing xlsx extraction tests using openpyxl in-memory Workbook fixtures: sheet order from `sheetnames`, native cell types, DATE vs TIMESTAMP via `[hs]` tokens in `number_format` after stripping quoted literals/`[...]`, midnight-fallback datetime → DATE, formula cell without cached value → None, short rows padded None, long rows → error unless extras all empty, corrupt file → error, OLE2 magic (.xls) detected, `time` cells → STRING isoformat. <!-- sdd-owner: implementation -->
- [x] Add failing `infer_column_type` matrix tests over ALL non-empty values: all-int→INT64 (bool excluded), int+float→FLOAT64, all-bool→BOOL, all-date→DATE, all-datetime→TIMESTAMP, all-str single-category→matching type, all-empty→STRING, mixed→STRING, plus LOADABILITY GUARD demotion to STRING when any value fails `convert_value(candidate)`. <!-- sdd-owner: implementation -->
- [x] Add failing `convert_value` strict-matrix tests: None→None; bool checked BEFORE int; NaN/Inf never numeric; INT64 from float only when `is_integer()`; str fullmatch int/decimal; BOOL `true|false` case-insensitive; DATE `date.fromisoformat`; TIMESTAMP `datetime.fromisoformat` accepting `Z` and naive-as-UTC; STRING accepts all finite values; first failure raises `ConversionError(column, row, value, target)`. <!-- sdd-owner: implementation -->
- [x] Add failing PROPERTY TEST: for generated columns, every non-empty value passes `convert_value` under the inferred type. <!-- sdd-owner: implementation -->
- [x] Run `cd odoo && .venv/bin/python -m pytest -q tests/test_bq_schema.py` and record the RED failure output as evidence. <!-- sdd-owner: implementation -->

GREEN
- [x] Create `odoo/bq_schema.py` (pure logic, no FastAPI imports) exporting `ExtractedTable`, `ConversionError`, `extract_csv`, `extract_xlsx`, `infer_column_type`, `convert_value`, `sanitize_column_name`; import the private helpers + `MAX_UPLOAD_ROWS` from `routers/bigquery.py` with ZERO edits to `bigquery.py`. <!-- sdd-owner: implementation -->
- [x] Run `cd odoo && .venv/bin/python -m pytest -q tests/test_bq_schema.py` until green; record the GREEN output as evidence. <!-- sdd-owner: implementation -->

TRIANGULATE
- [x] Add edge-case tests: cp1252-only bytes (e.g. `0xE9`), number formats with quoted literals/`[h]:mm` tokens, dedupe re-truncation at exactly 1024 chars, CSV `"nan"`/`"inf"` strings, bool-vs-int precedence in mixed columns. <!-- sdd-owner: implementation -->

REFACTOR
- [x] Verify `odoo/bq_schema.py` has no FastAPI/HTTP imports (grep for `fastapi` is empty) and the full backend suite `cd odoo && .venv/bin/python -m pytest -q` stays green. <!-- sdd-owner: implementation -->

## Work Unit 2 — PR 2: inspect + preview endpoints (D1, D2, D10 partial, D11, D14)

RED
- [x] Create `odoo/tests/test_file_upload_inspect_preview.py` using TestClient multipart (`files=` + `data=`): sourceType/extension mismatch → 400; body >20MB → 413; >100k data rows (excluding header + fully-empty rows) → 413; `.xls` and unknown extensions → 415. <!-- sdd-owner: implementation -->
- [x] Add failing inspect tests: response `{sourceType, fileName, sizeBytes, sheets[], sheetCount}` for a multi-sheet xlsx and for CSV (single `"CSV"` sheet). <!-- sdd-owner: implementation -->
- [x] Add failing preview tests: default first sheet; explicit `sheet` param; response `{sheet, columns:[{source,name,type,included}], sample, totalRows}`; sample ≤100 positional arrays with ISO-serialized dates; sanitized `name` vs raw `source`. <!-- sdd-owner: implementation -->
- [x] Run `cd odoo && .venv/bin/python -m pytest -q tests/test_file_upload_inspect_preview.py` and record RED evidence. <!-- sdd-owner: implementation -->

GREEN
- [x] Add `python-multipart==0.0.20` to `odoo/requirements.txt`. <!-- sdd-owner: implementation -->
- [x] Create `odoo/routers/file_upload.py` with module-scope `get_bigquery_client` import (called inside endpoints, never at import time), `POST /bigquery/upload-file/inspect` and `POST /bigquery/upload-file/preview` enforcing the 20MB/100k caps, delegating extraction to `bq_schema`, and raising HTTPException with the detail convention recorded in task 0.1. <!-- sdd-owner: implementation -->
- [x] Register the new router in the FastAPI app entrypoint (verify exact file, e.g. `odoo/main.py` or app factory) without touching existing routers. <!-- sdd-owner: implementation -->
- [x] Run `cd odoo && .venv/bin/python -m pytest -q` until green; record GREEN evidence. <!-- sdd-owner: implementation -->

TRIANGULATE
- [x] Add tests: empty CSV → 400; ragged CSV → 400 with row number in detail; long xlsx rows with non-empty extras → 400 but all-empty extras accepted; header-only CSV preview returns `totalRows: 0`. <!-- sdd-owner: implementation -->

REFACTOR
- [x] Extract a shared upload-validation helper (size cap, extension, sourceType match) reused by all three endpoints; keep `file_upload.py` free of extraction logic (delegates to `bq_schema`). <!-- sdd-owner: implementation -->

## Work Unit 3 — PR 3: load endpoint (D7, D8 load-side, D9, D10 validation order, D11) — stacked on PR 2

RED
- [x] Create `odoo/tests/test_file_upload_load.py` with a dict-backed `FakeBigQueryClient` (`get_dataset` raises NotFound; `get_table`; `create_table` raises Conflict; `load_table_from_json` honoring WRITE_EMPTY with a `FakeLoadJob` supporting configurable failure; `delete_table` recording calls with configurable raise) monkeypatching `routers.file_upload.get_bigquery_client`. <!-- sdd-owner: implementation -->
- [x] Add failing decision-validation ORDER tests, each asserting ZERO BQ client calls: unparseable decisions JSON → 400; decisions out-of-sync with re-extracted headers (`source[i] == headers[i]`) → 400; type outside the closed 6-type set → 400; zero included columns → 400; invalid included name → 400; case-insensitive duplicate names → 400; identifier-regex violation (`^[A-Za-z_][A-Za-z0-9_]{0,1023}$`) → 400. <!-- sdd-owner: implementation -->
- [x] Add failing BQ-flow tests: missing dataset → 404; existing-table pre-check → 409 with ZERO writes; `create_table` Conflict → 409; header-only file → 400 BEFORE any BQ call. <!-- sdd-owner: implementation -->
- [x] Add failing conversion tests: first bad value → 400 with exact detail `Column 'precio' row 17: value 'abc' is not compatible with INT64`; conversion completes BEFORE any BQ mutation. <!-- sdd-owner: implementation -->
- [x] Add failing job tests: `load_table_from_json` receives row dicts + `LoadJobConfig(schema, write_disposition="WRITE_EMPTY")`; schema is `SchemaField(name, type, "NULLABLE")` per included column; success → `{"table": "project.dataset.table", "rows": job.output_rows}`; job failure → `delete_table(not_found_ok=True)` then 502 containing the job error + cleanup outcome, and a cleanup exception never masks the 502. <!-- sdd-owner: implementation -->
- [x] Run `cd odoo && .venv/bin/python -m pytest -q tests/test_file_upload_load.py` and record RED evidence. <!-- sdd-owner: implementation -->

GREEN
- [x] Implement `POST /bigquery/upload-file/load` in `odoo/routers/file_upload.py` per D9/D10: re-extract the file, validate decisions in the tested order, convert all values, then dataset/table existence checks, `bigquery.Table(ref, schema=...)` + `create_table`, load job, `job.result()`, response shape. <!-- sdd-owner: implementation -->
- [x] Run `cd odoo && .venv/bin/python -m pytest -q` until green; record GREEN evidence. <!-- sdd-owner: implementation -->

TRIANGULATE
- [x] Add tests: 409 pre-check zero-writes assertion (no `create_table`/`load_table_from_json` calls); TIMESTAMP with `Z` suffix and naive-as-UTC through the endpoint; INT64 column accepting `3.0` float and rejecting `3.5` with column/row in the detail. <!-- sdd-owner: implementation -->

REFACTOR
- [x] Keep the endpoint thin: move decision-validation into a small pure function with its own unit tests; full backend suite green. <!-- sdd-owner: implementation -->

## Work Unit 4 — PR 4 + PR 5: frontend wizard (D12, D13)

Strict-TDD note: specs are written FIRST in this work unit (RED) but land in PR 5 (stacked after PR 4) so each PR stays near budget; do not implement before the specs fail.

RED (lands in PR 5)
- [x] Write the service spec for `odoo-ui/src/app/services/file-upload.service.ts` (HttpClientTestingModule): inspect/preview/load POST to the correct paths with a FRESH `FormData` per call; load sends `decisions` via `JSON.stringify`; error propagation. <!-- sdd-owner: implementation -->
- [x] Write the wizard component spec with a stubbed service: client extension rejection for non-`.xlsx/.csv` with a dedicated `.xls` message; CSV skips the sheet step; sheet step shown only when `sheetCount > 1`; schema-step inline validation (identifier regex, case-insensitive dups, ≥1 included column); busy guard blocks double submit; success panel shows table + rows; 409 detail rendered verbatim and resubmit keeps state; "Volver" preserves state; "Cargar otro archivo" resets. <!-- sdd-owner: implementation -->
- [x] Run `cd odoo-ui && npm test` and record RED evidence. <!-- sdd-owner: implementation -->

GREEN (lands in PR 4)
- [x] Extend `odoo-ui/src/app/app.ts` Tab union with `file-upload` and add nav entry `{id: 'file-upload', label: 'Cargar archivo'}` matching the shape recorded in task 0.3. <!-- sdd-owner: implementation -->
- [x] Create `odoo-ui/src/app/services/file-upload.service.ts` with inspect/preview/load methods building fresh `FormData` per call (decisions via `JSON.stringify`). <!-- sdd-owner: implementation -->
- [x] Create `odoo-ui/src/app/file-upload/file-upload.{ts,html,css}`: step signal `source|sheet|schema|destination|result`; signals file/inspect/selectedSheet/preview/columns/datasets/dataset/table/busy/error/result; preview cached per (file,sheet); `accept=".xlsx,.csv"` with client-side extension rejection; schema step as a PrimeNG table with include toggle + name InputText + type Select (6 types) + sample display + inline validation; destination step with dataset Select (endpoint from task 0.2) + table InputText + never-overwrite helper copy; result step with success/error panels + reset/back actions; Rioplatense voseo copy; PrimeNG modules only, NO new npm deps. <!-- sdd-owner: implementation -->
- [x] Add a TS identifier-regex constant mirroring the backend with a comment pointing to `_validate_identifier` in `odoo/routers/bigquery.py` (D13); pin it via the schema-validation spec. <!-- sdd-owner: implementation -->
- [x] Run `cd odoo-ui && npm test` AND `cd odoo && .venv/bin/python -m pytest -q`; record GREEN evidence for both suites. <!-- sdd-owner: implementation -->

TRIANGULATE (lands in PR 5)
- [x] Add specs: preview cache invalidates on sheet change and is reused on back-navigation; destination submit disabled while busy; error panel recovery after a failed load followed by a corrected resubmit. <!-- sdd-owner: implementation -->

REFACTOR
- [x] Verify spec placement matches the convention from task 0.5; confirm `package.json` has no new dependencies; run lint/build if scripts exist. <!-- sdd-owner: implementation -->

## Work Unit 5 — Cross-cutting apply checks (run for every PR)

- [x] Before each backend PR: run `cd odoo && .venv/bin/python -m pytest -q` (MANDATORY even though config verify test_command is frontend-only) and confirm the diff contains ZERO changes to `odoo/routers/bigquery.py`. <!-- sdd-owner: implementation -->
- [x] Before each frontend PR: run `cd odoo-ui && npm test` and confirm no new npm dependencies were added. <!-- sdd-owner: implementation -->
- [x] Paste RED and GREEN command outputs into each PR description as TDD evidence. <!-- sdd-owner: implementation -->

## Post-apply (parent-owned)

- [ ] Start bounded review for PR 1 (`bq_schema`) before PR 2 apply begins. <!-- sdd-owner: parent -->
- [ ] Start bounded review for PR 2/PR 3 (API chain) and PR 4/PR 5 (frontend chain) as each lands; verify the 400-line budget per PR. <!-- sdd-owner: parent -->
- [ ] Run lifecycle-gate / chain-merge handling once the user confirms the chain strategy (currently `pending`; decision required before apply per interactive mode). <!-- sdd-owner: parent -->
