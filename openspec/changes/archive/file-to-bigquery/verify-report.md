# Verify Report — file-to-bigquery

**Verdict: PASS — 25/25 requirements verified with executable evidence.**

## Executable evidence (fresh at verify time)

| Command | Result |
|---|---|
| `cd odoo && .venv/bin/python -m pytest -q` | **153 passed**, 0 failed |
| `cd odoo-ui && npm test -- --watch=false` | **38 passed** (8 files), 0 failed |
| `cd odoo-ui && npx ng build` | bundle OK |
| `git diff main -- odoo/routers/bigquery.py` | empty (untouched) |
| `git diff main -- odoo-ui/package.json odoo-ui/package-lock.json` | empty (no npm deps) |
| `git diff main -- odoo/requirements.txt` | `+python-multipart==0.0.20` only |

## Spec: file-upload (backend) — 14/14

| Req | Verdict | Evidence |
|---|---|---|
| R1 Stateless three-endpoint API | PASS | `routers/file_upload.py` L18/L46/L127; no disk writes (grep: only error strings + BigQuery enum); router registered `main.py`; request/response shapes covered by all endpoint tests |
| R2 Type identification & sheet enumeration | PASS | `test_inspect_csv/xlsx` (sheets/sheetCount); `.xls`→415 both endpoints |
| R3 Limit and format failures | PASS | `test_inspect_file_too_large` (413 @20MB); rows>100k→413; corrupt→400 (`ExtractionError` mapping) |
| R4 Typed column preview | PASS | `test_preview_*`: columns {source,name,type,included}, sample ≤10, totalRows; inferrer demotion loop `bq_schema.py` |
| R5 Schema approval & decisions | PASS | `test_load_*defaults*` (sanitize/infer on omission); loadability enforced by conversion-before-write |
| R6 Invalid/duplicate names rejected | PASS | `test_load_invalid_name_400`, `test_load_duplicate_case_insensitive_400` — before any BigQuery call |
| R7 Create-only semantics | PASS | `test_load_table_exists_409_zero_bq_writes` + `Conflict`→409 race test; message verbatim |
| R8 Explicit schema creation | PASS | `test_load_creates_table_with_explicit_nullable_schema` (SchemaField types, NULLABLE); closed-set 400 test |
| R9 Full row load | PASS | `load_table_from_json` + `WRITE_EMPTY` asserted in load tests; rows echo |
| R10 Conversion failure safety | PASS | `test_load_conversion_error_400_before_any_bq_call` — exact detail "Column 'precio' row 17: string 'abc' is not an integer", zero BQ calls |
| R11 Job failure cleanup | PASS | `test_load_job_failure_502_table_removed` + cleanup-failure variant (502 detail reports outcome) |
| R12 Load result contract | PASS | `{"table": "project.dataset.table", "rows": n}` asserted |
| R13 Zero external ingestion deps | PASS | requirements diff: only python-multipart (framework); no openpyxl/pandas added |
| R14 Existing sync flow untouched | PASS | `git diff main -- bigquery.py` empty; full suite 153 passed includes pre-existing sync tests |

## Spec: file-upload-ui (frontend) — 11/11

| Req | Verdict | Evidence |
|---|---|---|
| R1 Wizard entry point | PASS | `app.ts` nav "Cargar archivo" + `app.html` `@if (upload)`; build OK |
| R2 Guided wizard flow | PASS | 5 steps; gated advance (`schemaValid`/`destinationValid`, auto-advance only post-backend-success); back preserves state (test); "Cargar otro archivo" resets (test) |
| R3 Source selection | PASS | Extension whitelist pre-backend (tests assert zero stub calls on `.xls`/`.pdf`); `.xls` dedicated message; inspect required to advance |
| R4 Sheet selection | PASS | CSV skips sheet step (test); single-sheet auto-advances; multi-sheet lists from inspect (test) |
| R5 Schema approval | PASS | included default true; name/type editable via `updateColumn`; sample table; `schemaValid` mirrors backend regex + case-insensitive dup + ≥1 included (3 tests) |
| R6 Destination selection | PASS | datasets via `BigQueryService.listDatasets()`; table validated by `BQ_IDENTIFIER_RE` (mirrors backend, D13); never-overwrite helper copy in HTML |
| R7 Stateless & cache behavior | PASS | Fresh `FormData` per call (service); preview cache per (file,sheet) cleared on new file/reset (2 triangulation tests) |
| R8 Busy and error handling | PASS | Busy guard blocks double submit (test); 409 verbatim + state preserved + resubmit (test); generic fallback message |
| R9 Success confirmation | PASS | Result panel {table, rows} (test); QueryList `ngOnInit→load()` + `@if` tab recreation ⇒ refresh on navigation |
| R10 No new npm deps | PASS | package.json/lockfile diff empty |
| R11 Existing flows untouched | PASS | Only `app.ts`/`app.html` modified (additive); 19 pre-existing frontend tests still green |

## Notes

- Conversion-error detail follows PR1's implementation ("string 'abc' is not an integer"); design.md example text was updated to match.
- Google Sheets source is out of scope (deferred, decision recorded).
