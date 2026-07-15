# Proposal: file-to-bigquery

> Self-service creation of new BigQuery tables from user files (Excel .xlsx, CSV), with an explicit user-approved schema, through a guided wizard — without engineering help and without ever persisting the uploaded file. A Google Sheets URL source was considered and **deferred to a future increment** (see Scope).

## Intent

Give business users of the motorreductores-bi tool a safe, guided way to turn a spreadsheet they already have (an `.xlsx` or a `.csv`) into a **new** BigQuery table they can immediately query with the existing tool — while guaranteeing that:

- the table schema is **explicitly reviewed and approved by the user** before anything is created;
- **no existing table can ever be overwritten or appended to** (create-only semantics);
- the uploaded file is **never persisted** anywhere (in-memory extraction, then discarded).

## Problem

### Business problem

Analysts and commercial/operations staff keep a large share of their working data in spreadsheets: ERP exports, price lists, stock snapshots, campaign trackers maintained in Google Sheets. Today, none of that data can be combined with the data already queryable in the BI tool unless a technical person manually creates a BigQuery table and loads the file. That means:

- **Bottleneck and delay**: every "can we cross this Excel with sales?" question waits on someone with BigQuery access and CLI/console knowledge.
- **Ad-hoc, risky workarounds**: manual loads are done with default/autodetected schemas and destructive write modes, which is how tables get silently truncated or mistyped.
- **Shadow copies**: sensitive files get passed around (mail, Drive, USB) so someone technical can load them, instead of the owner loading the data directly.

### Current-state gap (technical)

- The UI has **no upload path at all**: no file input, no multi-step load flow (greenfield on both frontend and backend).
- The backend's only user-facing load path, `POST /bigquery/upload` in `odoo/routers/bigquery.py`, uses `WRITE_TRUNCATE` and autodetected schema from a JSON payload. It is designed for internal/scheduled loads, and its overwrite semantics are exactly what this flow must never do. **It must not be reused.**
- `odoo/routers/bigquery.py` already provides solid building blocks — `get_bigquery_client` (service account from env or `odoo/bigquery.txt`, project `motorreductores-bi`), `_validate_identifier` (`^[A-Za-z_][A-Za-z0-9_]{0,1023}$`), and type-inference helpers (`_infer_bq_schema`, `_infer_string_type`, `_promote_bq_type`) — but there is **no explicit-schema CREATE TABLE** and **no table-exists check**. Those capabilities are new.
- `odoo/routers/schedules.py` imports `upload_to_bigquery` from `routers.bigquery`, so `bigquery.py` must remain stable; new behavior goes in a **new router** `odoo/routers/file_upload.py`.

### Why now

Every week without this, spreadsheet-based questions either go unanswered, get answered late, or get answered through unsafe manual loads. The tool already authenticates to BigQuery and already infers types; the missing piece is a guarded, user-driven create-table flow.

## Product decisions (approved — settled in the question round)

For reviewers who were not in the question round, these are the agreed product rules and are **not** open for re-litigation in this proposal:

1. **Sources**: upload an Excel (`.xlsx`) or CSV file. A Google Sheets URL source was evaluated and **cut from this increment** (see decision 10 and Scope).
2. The system detects the file type and lists its sheets/tabs; the user picks **one** sheet. CSV is treated as a single pseudo-sheet (no sheet-selection step).
3. The backend extracts data **in memory** and returns a column preview (headers + sample rows + inferred types).
4. The user selects **which columns** to send (may discard columns) and can correct each column's **name** and **BigQuery type** before table creation.
5. First row = header. Types are inferred automatically (`INT64` / `FLOAT64` / `BOOL` / `DATE` / `TIMESTAMP` / `STRING`) and are user-correctable.
6. Column names are **sanitized to BigQuery naming rules**.
7. The user picks an **existing** dataset and types a **new** table name. If the table already exists → error; the user must choose another name. **Never overwrite, never append.**
8. The backend generates the full `CREATE TABLE` with the **explicit user-approved schema** and loads all extracted rows.
9. The file is **never persisted**: in-memory extraction only, then discarded.
10. **Google Sheets URL source is deferred**: the project has no Google Console Drive/Sheets API activation nor service-account sharing flow yet; Sheets support returns as a future increment.
11. Legacy `.xls` is **out of scope**.
12. **Non-goals**: no file persistence, no upload history, no append/replace modes, no data transformations beyond column typing.

## Solution

### User experience (observable outcomes)

A new 6th tab in the app (working label: **"Cargar archivo"**, final Rioplatense copy in design) opens a guided wizard that mirrors the existing `query-create` multi-step pattern:

1. **Source** — The user drops/selects an `.xlsx` or `.csv` file. Unsupported inputs (including legacy `.xls`) produce an immediate, human-readable error.
2. **Sheet** — The backend inspects the input and returns the file type plus the list of sheets/tabs; the user picks exactly one. For CSV this step is skipped automatically (single pseudo-sheet).
3. **Columns & schema** — The backend extracts the sheet in memory and returns headers, a sample of rows, and inferred BigQuery types. The user can:
   - deselect columns to discard them;
   - rename any column (names are sanitized to BigQuery rules);
   - override any inferred type (`INT64` / `FLOAT64` / `BOOL` / `DATE` / `TIMESTAMP` / `STRING`).
4. **Destination & create** — The user picks an existing dataset and types a new table name. The backend checks existence: if the table exists, the load is rejected (409) with a clear "choose another name" message and **nothing is written**. Otherwise the backend issues a `CREATE TABLE` with the exact user-approved schema and loads **all** extracted rows, then confirms table name, schema, and loaded row count.

The column-picker interaction reuses the UX precedent from the `query-runner` BigQuery dialog. All UI copy in Rioplatense Spanish; code, identifiers, and comments in English.

### Backend (new code, existing building blocks)

New router **`odoo/routers/file_upload.py`** (keeps `bigquery.py` behavior stable for `schedules.py`), with three endpoints:

- `POST /bigquery/upload-file/inspect` — accepts a multipart file; returns file type + sheet list.
- `POST /bigquery/upload-file/preview` — accepts the same input plus the chosen sheet; returns columns (sanitized names), sample rows, and inferred types.
- `POST /bigquery/upload-file/load` — accepts the input, sheet, selected columns with final names+types, dataset, and new table name; validates identifiers with `_validate_identifier`, rejects with **409 if the table exists**, otherwise executes explicit-schema `CREATE TABLE` + load of all rows.

Reused from `odoo/routers/bigquery.py` by import (no duplication): `get_bigquery_client`, `_validate_identifier`, `_infer_bq_schema` / `_infer_string_type` / `_promote_bq_type`. New capabilities added: table-exists check and explicit-schema table creation.

**Dependencies**: add `python-multipart` (mandatory for FastAPI `UploadFile`). `openpyxl` 3.1.5 is already present (`.xlsx`); stdlib `csv` covers CSV. No other new dependencies.

**Statelessness consequence**: because the file is never persisted, the backend holds nothing between steps; the frontend keeps the `File` object (or URL) and **re-sends it at each step**. Extraction cost per step is acceptable for the target file sizes; this is called out so the design phase does not accidentally introduce server-side file storage or session temp files.

### Frontend

New page **`odoo-ui/src/app/pages/file-upload/`**, registered as the 6th entry in the tab-based navigation in `odoo-ui/src/app/app.ts` (`Tab` union + `nav` array — there is no Angular Router). Wizard steps mirror `query-create`; `FormData` + `HttpClient` only, **no new frontend dependencies**.

## Scope

### In scope

- Upload of `.xlsx` and `.csv` (multipart) as sources.
- File-type detection and sheet/tab listing; single-sheet selection; CSV as pseudo-sheet.
- In-memory extraction; column preview with headers, sample rows, inferred types.
- Column selection/deselection, column renaming, and type override by the user.
- Column-name sanitization to BigQuery rules.
- Dataset selection (existing datasets) + new-table-name entry with table-exists rejection (409).
- Explicit-schema `CREATE TABLE` + full row load; load confirmation with schema and row count.
- Clear error paths: unsupported format (incl. `.xls`), existing table name, invalid identifiers.
- Backend pytest suite for the new router and frontend vitest suite for the wizard (first tests in this area — see Testing).

### Out of scope (explicit non-goals)

- Legacy `.xls` support (clear unsupported-format error instead).
- Persisting uploaded files, temp storage, or any upload history/audit trail.
- Append, replace, or any write mode other than create-new (existing `/bigquery/upload` with `WRITE_TRUNCATE` remains untouched for its scheduled use and is **not** part of this flow).
- Data transformations beyond column typing (no computed columns, filters, joins, or row editing).
- Editing or altering existing tables; dataset creation.
- Loading multiple sheets in one operation.
- Authentication/permission changes to the app itself (the feature rides on the existing single-tenant setup).
- **Google Sheets URL source — deferred to a future increment**: it requires Google Console Drive/Sheets API activation and service-account sharing, which the project does not have yet.

## Impact

### Affected areas

| Area | Change |
|---|---|
| `odoo/routers/file_upload.py` | **New** router: inspect / preview / load endpoints |
| `odoo/routers/bigquery.py` | Import source only; **must remain behavior-stable** (`schedules.py` depends on it) |
| `odoo/requirements.txt` | Add `python-multipart` |
| `odoo-ui/src/app/app.ts` | Add 6th tab (`Tab` union + `nav` entry, Spanish label) |
| `odoo-ui/src/app/pages/file-upload/` | **New** wizard page (4 steps) |
| `odoo/tests/…`, `odoo-ui/…` | **First** test suites for the BigQuery/upload area |

### Edge cases that matter

- **Table name already exists** → 409, explicit "choose another name" message, zero writes performed.
- **Type correction** → user-approved types win over inference; the created schema must match the approved schema exactly (this is the core safety property of the feature).
- **Large files** → preview shows a sample (e.g., first N rows) while load processes **all** extracted rows; a size/row cap and its error message are set in design (in-memory extraction is the constraint). Inference over the full sheet at load time vs. sample-based inference at preview must not silently disagree — user-approved explicit schema is the mitigant, and un-loadable values under the approved type surface as a clear load error.
- **Sanitization collisions** (two source columns mapping to the same sanitized name) and **files with a header row but zero data rows** must produce explicit errors/prompts rather than silent misbehavior (exact UX in design).
- **Empty/invalid sheet selection**, malformed CSV, and formula-only `.xlsx` cells (cached values via openpyxl) handled with clear messages.

### Risks

| Risk | Severity | Mitigation |
|---|---|---|
| Accidental reuse of `WRITE_TRUNCATE` semantics | High | New router with create-only path; table-exists check before any write; tests assert 409 and zero writes |
| Regression in `bigquery.py` breaking `schedules.py` | Medium | `bigquery.py` untouched except (at most) additive exports; backend pytest run |
| Memory pressure from very large uploads | Medium | Size cap in design; streaming/sampled preview; clear rejection error |
| Inferred vs. actual types diverge on full data | Medium | Explicit user-approved schema at load; type-conflict load errors surfaced clearly |
| First test suites in this area slow the change down | Low | Planned: strict TDD is mandatory (see below) |

### Rollback

Feature is additive and self-contained: remove the tab entry from `app.ts`, unregister `file_upload` router, revert the `python-multipart` dependency. No data migration is needed (nothing is persisted by the feature). Tables already created by users in BigQuery are user data and are intentionally left in place.

### Testing (strict TDD obligation)

`openspec/config.yaml` sets `strict_tdd: true` — tests are written before/with implementation, not after.

- **Backend**: `cd odoo && .venv/bin/python -m pytest -q` — new tests for `file_upload.py`: type inference mapping, column-name sanitization, inspect (file vs. sheets URL), preview contract, load happy path (explicit schema asserted), table-exists → 409 with zero writes, unsupported `.xls`. These are the **first** backend tests for the BigQuery router area.
- **Frontend**: `cd odoo-ui && npm test` (vitest) — wizard step flow, CSV pseudo-sheet skip, column deselect/rename/type-override, 409 and sheets-permission error rendering.
- Note: the config's apply/verify `test_command` covers the **frontend only**; the backend pytest command above must be run **additionally** during apply/verify.

### Success criteria

1. A user loads a multi-sheet `.xlsx`, picks one sheet, discards a column, renames another, changes a type (e.g., `STRING` → `DATE`), chooses a dataset and new table name → the table exists in BigQuery with **exactly** the approved schema and **all** rows from the sheet.
2. CSV flow works end-to-end with no sheet-selection step.
3. An existing table name yields a 409 and a clear UI message, with **verifiably zero writes**.
4. `.xls` upload yields an unsupported-format error.
5. Code review confirms uploaded bytes never touch disk/temp storage at any step.
6. `odoo` pytest and `odoo-ui` vitest suites are both green, with tests committed alongside implementation per strict TDD.
