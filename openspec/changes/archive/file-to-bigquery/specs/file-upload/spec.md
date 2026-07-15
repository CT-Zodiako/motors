# file-upload Specification (Delta)

## Purpose

Backend ingestion of user-supplied tabular data — an uploaded Excel `.xlsx`/CSV file — into a **new** BigQuery table under a user-approved schema. Implemented as a new, stateless router `odoo/routers/file_upload.py` exposing three endpoints under `/bigquery/upload-file/`, reusing the BigQuery client, identifier validation, and type-inference helpers from `odoo/routers/bigquery.py`.

## ADDED Requirements

### Requirement: Stateless Three-Endpoint Ingestion API

The system SHALL expose exactly three ingestion endpoints: `POST /bigquery/upload-file/inspect`, `POST /bigquery/upload-file/preview`, and `POST /bigquery/upload-file/load`. Every endpoint SHALL accept the complete source payload as `multipart/form-data` with a `file` binary part on every call, and SHALL NOT retain any server-side state (memory, disk, or session) between calls. The `file` part MUST be present.

#### Scenario: Each request is self-contained
- WHEN a client calls `POST /bigquery/upload-file/load` with a valid complete payload without any prior `inspect` or `preview` call
- THEN the endpoint SHALL process the request successfully
- AND the result SHALL be identical to the same call made after `inspect` and `preview`

#### Scenario: No state survives a restart
- WHEN the backend process restarts between a `preview` call and the corresponding `load` call
- AND the client re-sends the same source with the `load` request
- THEN `load` SHALL succeed

#### Scenario: Missing source rejected
- WHEN a request lacks a `file` part
- THEN the endpoint SHALL return HTTP 400
- AND the error message SHALL state that a file is required

### Requirement: Source Inspection and Sheet Enumeration

`POST /bigquery/upload-file/inspect` SHALL identify the source type (`xlsx` or `csv`) and SHALL return the available sheets/tabs. For CSV uploads the response SHALL contain exactly one pseudo-sheet so no sheet-selection step is needed. The response SHALL include a machine-readable `sourceType` and a `sheets` array containing at least each sheet's `name`.

#### Scenario: Inspect an .xlsx file
- WHEN a client posts a valid `.xlsx` file to `/bigquery/upload-file/inspect`
- THEN the response SHALL be HTTP 200
- AND `sourceType` SHALL be `xlsx`
- AND `sheets` SHALL list every worksheet name in workbook order

#### Scenario: Inspect a CSV file
- WHEN a client posts a valid `.csv` file to `/bigquery/upload-file/inspect`
- THEN the response SHALL be HTTP 200 with `sourceType` `csv`
- AND `sheets` SHALL contain exactly one entry

#### Scenario: Legacy .xls rejected
- WHEN a client uploads a file with the `.xls` extension or legacy OLE2/BIFF content
- THEN the endpoint SHALL return HTTP 415
- AND the message SHALL state that `.xls` is not supported and the file must be saved as `.xlsx`

#### Scenario: Unsupported file type rejected
- WHEN a client uploads content that is neither `.xlsx` nor `.csv` (e.g. `.pdf`, `.json`, `.txt`)
- THEN the endpoint SHALL return HTTP 415
- AND the message SHALL name the accepted formats

### Requirement: In-Memory-Only Extraction

All file bytes SHALL be processed exclusively in memory. The system MUST NOT write uploaded content, extracted rows, or intermediate artifacts to disk, temporary files, or any persistent store at any point during inspect, preview, or load.

#### Scenario: No filesystem writes during processing
- WHEN any of the three endpoints processes an upload of any supported type
- THEN no file SHALL be created on the server filesystem (including OS temp directories) as part of processing
- AND the full file content SHALL be held only in process memory

### Requirement: First-Row Header Semantics

For every source type, the first row of the selected sheet SHALL be interpreted as the header row providing column names, and all subsequent rows SHALL be data rows. This rule SHALL apply identically in preview and load.

#### Scenario: Header separation
- GIVEN a sheet whose first row is `nombre,edad` followed by 3 further rows
- WHEN preview or load extracts the sheet
- THEN the column set SHALL be derived from `nombre,edad`
- AND the data row count SHALL be 3

### Requirement: Column Preview and Type Inference

`POST /bigquery/upload-file/preview` SHALL accept the source plus a selected sheet name and SHALL return, for every column: the source header, the sanitized default BigQuery column name, and the inferred BigQuery type — together with a bounded sample of data rows (at most 100, taken in sheet order from the first data row) and the total data row count. Inferred types SHALL come only from the closed set `INT64`, `FLOAT64`, `BOOL`, `DATE`, `TIMESTAMP`, `STRING`. Inference SHALL be computed over all extracted data rows (not only the sample) using the same inference function load uses, so preview results are consistent with load.

#### Scenario: Preview returns schema and sample
- WHEN a client posts a valid source and sheet to `/bigquery/upload-file/preview`
- THEN the response SHALL be HTTP 200
- AND each column entry SHALL include source header, sanitized default name, and an inferred type from the closed set
- AND the sample SHALL contain at most 100 rows in source order
- AND the response SHALL include the total data row count

#### Scenario: Inference consistency with load
- GIVEN any supported source
- WHEN the same source is submitted to preview and later to load without type overrides
- THEN the inferred types shown by preview SHALL equal the column types of the created table

#### Scenario: Unknown sheet name
- WHEN the requested sheet name does not exist in the source
- THEN the endpoint SHALL return HTTP 400 naming the available sheets

### Requirement: Deterministic Type Inference Rules

Type inference SHALL ignore empty/NULL cells and apply these rules deterministically: all non-empty values integer-like → `INT64`; all numeric with at least one decimal/exponent → `FLOAT64`; all boolean values (Excel boolean cells, CSV tokens `true`/`false` case-insensitive) → `BOOL`; Excel date-formatted cells without a time component → `DATE`; Excel date+time cells → `TIMESTAMP`; CSV values parseable as ISO 8601 `YYYY-MM-DD` → `DATE`; CSV values parseable as ISO 8601 datetime → `TIMESTAMP`; any mixed or unparsable content → `STRING`; a column with only empty cells → `STRING`.

#### Scenario: Integer column infers INT64
- WHEN a column's non-empty values are `1`, `2`, `300`
- THEN the inferred type SHALL be `INT64`

#### Scenario: Mixed content falls back to STRING
- WHEN a column contains `abc` in one row and `12` in another
- THEN the inferred type SHALL be `STRING`

#### Scenario: All-empty column infers STRING
- WHEN every cell in a column is empty
- THEN the inferred type SHALL be `STRING`

#### Scenario: ISO date strings infer DATE
- WHEN all non-empty values in a column match `YYYY-MM-DD`
- THEN the inferred type SHALL be `DATE`

### Requirement: Malformed and Degenerate Input Handling

The system SHALL reject malformed or degenerate sources with clear, actionable HTTP 400 errors before any BigQuery write. A CSV data row whose field count differs from the header SHALL be reported with the first offending row number. An `.xlsx` file that cannot be parsed SHALL be reported as unreadable. Formula cells SHALL be read using their cached values; a formula cell without a cached value SHALL be treated as NULL. A header-only sheet (zero data rows) SHALL be previewable but MUST be rejected by load with zero writes.

#### Scenario: Ragged CSV row
- WHEN a CSV data row has more or fewer fields than the header
- THEN the endpoint SHALL return HTTP 400
- AND the message SHALL include the row number of the first offending row

#### Scenario: Corrupt xlsx
- WHEN the uploaded `.xlsx` content cannot be parsed as a valid workbook
- THEN the endpoint SHALL return HTTP 400 stating the file could not be read as `.xlsx`

#### Scenario: Formula cells use cached values
- GIVEN an `.xlsx` sheet where a column contains formulas with cached results
- WHEN the sheet is extracted
- THEN the cached values SHALL be used as cell values
- AND a formula cell without a cached value SHALL be treated as NULL

#### Scenario: Header-only sheet rejected at load
- GIVEN a sheet with a header row and zero data rows
- WHEN the client calls load
- THEN the response SHALL be HTTP 400 stating there is no data to load
- AND no BigQuery table SHALL be created or modified

### Requirement: Destination Identifier Validation

The load endpoint SHALL validate the target dataset, the table name, and every final column name against the shared rule `^[A-Za-z_][A-Za-z0-9_]{0,1023}$` (the existing `_validate_identifier` helper) before any BigQuery operation. The referenced dataset MUST already exist; the system SHALL NOT create datasets.

#### Scenario: Invalid table name
- WHEN load is called with a table name containing spaces or leading digits
- THEN the response SHALL be HTTP 400
- AND the message SHALL name the offending identifier and the allowed pattern
- AND no BigQuery write SHALL have occurred

#### Scenario: Non-existent dataset
- WHEN load targets a dataset that does not exist in the project
- THEN the response SHALL be HTTP 404 stating the dataset was not found
- AND no BigQuery write SHALL have occurred

### Requirement: Table Existence Conflict Guard

Before creating anything, load SHALL check whether `dataset.table` already exists. If it exists, the endpoint SHALL return HTTP 409 and MUST perform zero writes: no CREATE, no INSERT, no schema change. The system SHALL never overwrite or append to an existing table.

#### Scenario: Existing table yields 409 with zero writes
- GIVEN dataset `raw` already contains table `ventas`
- WHEN load is called targeting `raw.ventas`
- THEN the response SHALL be HTTP 409 naming `raw.ventas`
- AND the existing table's schema and row count SHALL be unchanged
- AND no new table or rows SHALL be created

### Requirement: User-Approved Schema on Load

The load endpoint SHALL accept a per-column schema decision list: which columns to include, an optional name per column, and an optional type per column. The user-approved schema SHALL take precedence over inference: included columns SHALL appear in the created table with exactly the approved (sanitized) names and exactly the approved types. Default column names SHALL be derived by sanitizing source headers — replacing every character outside `[A-Za-z0-9_]` with `_`, prefixing `_` when the first character is not a letter or `_`, truncating to 1024 characters, and appending a deterministic positional suffix (`_2`, `_3`, …) to exact duplicate source headers. If, after applying the user's renames, two included columns resolve to the same BigQuery name (compared case-insensitively), load SHALL return HTTP 400 naming the colliding columns and SHALL perform zero writes.

#### Scenario: Column subset honored
- WHEN the payload includes only 3 of 5 columns
- THEN the created table SHALL contain exactly those 3 columns in the submitted order

#### Scenario: Rename sanitized and honored
- WHEN the user renames a column to `Fecha de Venta`
- THEN the created column SHALL be named exactly `Fecha_de_Venta`
- AND the sanitization SHALL match the sanitized default shown by preview for the same header

#### Scenario: Type override honored exactly
- GIVEN a column inferred as `INT64`
- WHEN the user overrides its type to `STRING`
- THEN the created table SHALL define that column as `STRING`
- AND the loaded values SHALL be converted to the overridden type

#### Scenario: Rename collision rejected with zero writes
- WHEN two included columns are renamed such that both resolve to `fecha`
- THEN the response SHALL be HTTP 400 naming both columns
- AND no table SHALL be created or modified

#### Scenario: Override incompatible with data
- WHEN a column overridden to `INT64` contains the value `abc` in row 17
- THEN the response SHALL be HTTP 400 naming the column and the first offending row
- AND the Load Failure Cleanup requirement SHALL apply

### Requirement: Table Creation and Full Row Load

On a valid load request, the system SHALL first execute CREATE TABLE for the new table with the explicit user-approved schema, and SHALL then load ALL extracted data rows — never only the preview sample — into that table. The successful response SHALL include the fully qualified table name and the number of rows loaded, which SHALL equal the number of data rows extracted from the source.

#### Scenario: All rows loaded
- GIVEN a CSV with a header row and 10000 data rows
- WHEN load succeeds
- THEN the response SHALL report a row count of 10000
- AND `SELECT COUNT(*)` on the created table SHALL return 10000

#### Scenario: Schema comes from approval, not inference
- WHEN load completes
- THEN the created table's column names and types SHALL exactly match the user-approved schema in the request payload

### Requirement: Load Failure Cleanup

If row loading fails after the table has been created, the system SHALL attempt to delete the partially created table so that a corrected retry with the same name does not fail with HTTP 409. The error response SHALL state the failure reason and whether cleanup succeeded.

#### Scenario: Partial load cleans up
- GIVEN a load request that fails during row insertion after table creation
- WHEN the error response is returned
- THEN the system SHALL have attempted to drop the created table
- AND the response SHALL state whether the table was removed

### Requirement: Reuse and Stability of bigquery.py Helpers

`file_upload.py` SHALL obtain its BigQuery client via `get_bigquery_client`, SHALL validate identifiers via `_validate_identifier`, and SHALL reuse the shared type-inference helpers from `odoo/routers/bigquery.py`. Existing behavior of `bigquery.py` SHALL remain stable: no signature or behavior change to symbols imported by `schedules.py`, and no behavioral change to existing `/bigquery/` endpoints.

#### Scenario: Existing consumers unaffected
- WHEN the file-upload router is added
- THEN `schedules.py` SHALL continue importing from `bigquery.py` without modification
- AND all pre-existing backend tests SHALL pass unmodified

### Requirement: Automated Backend Verification

The domain SHALL ship with a pytest suite executable via `cd odoo && .venv/bin/python -m pytest -q` covering, at minimum: each endpoint's happy path, unsupported format (including `.xls`), table-exists 409 with zero writes, rename collision, type override honored exactly, header-only rejection, malformed CSV, formula-cached cells, and preview/load consistency. Tests SHALL run without real BigQuery or Google API access (clients mocked/faked).

#### Scenario: Suite runs green offline
- WHEN `cd odoo && .venv/bin/python -m pytest -q` is executed
- THEN all file-upload tests SHALL pass
- AND no test SHALL require network access to Google services

## Non-Goals

- No persistence of uploaded files or extracted rows (no history, no temp storage).
- No append, replace, or overwrite of existing tables.
- No transformations beyond type conversion to the approved schema.
- No multi-sheet loads (exactly one sheet per load).
- No `.xls` support.
- No Google Sheets URL source in this increment (deferred — requires Google Console Drive/Sheets API activation and service-account sharing).
