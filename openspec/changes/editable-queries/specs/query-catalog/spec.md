# Spec Delta — editable-queries

## ADDED Requirements

### Requirement: Query Destination Registry

The system SHALL maintain a `query_destinations` registry recording, for every saved query, each BigQuery destination (`query_name`, `dataset_id`, `table_id`) that receives that query's results. The table MUST be created by an idempotent inline SQL migration executed from `init_db.init()`, following the repository convention of `CREATE TABLE IF NOT EXISTS` / `ALTER ... IF NOT EXISTS`: repeated initialization MUST NOT fail, duplicate rows, or drop data. On first execution the migration MUST seed `query_destinations` from existing `query_schedules` rows, which already persist query name and destination, so every distinct `(query_name, dataset_id, table_id)` in `query_schedules` is present afterwards. Both BigQuery upload paths — manual upload via `upload_to_bigquery` (bigquery.py:197-235) and the schedule executor (schedules.py:314-364) — MUST upsert the registry on every successful upload (D6), so destinations created by manual upload before this version self-register on their next upload.

#### Scenario: Migration is idempotent

- **GIVEN** a database on which `init_db.init()` has already run and `query_destinations` contains rows
- **WHEN** `init_db.init()` runs again
- **THEN** it completes without error
- **AND** the registry contents are unchanged — no duplicates and no dropped rows

#### Scenario: Registry seeded from existing schedules

- **GIVEN** `query_schedules` holds two schedules for query "sales" targeting tables "sales_daily" and "sales_weekly" in dataset "analytics"
- **WHEN** the migration runs for the first time
- **THEN** `query_destinations` contains both (sales, analytics, sales_daily) and (sales, analytics, sales_weekly)

#### Scenario: Manual upload self-registers its destination

- **GIVEN** saved query "sales" has no registered destination for table "ad_hoc_copy"
- **WHEN** a user manually uploads "sales" results to (analytics, ad_hoc_copy)
- **THEN** `query_destinations` gains the row (sales, analytics, ad_hoc_copy)

#### Scenario: Scheduled run upserts its destination

- **GIVEN** an active schedule for query "sales" targeting (analytics, sales_daily)
- **WHEN** the schedule executor completes an upload
- **THEN** the (sales, analytics, sales_daily) row exists in `query_destinations`, inserted if absent

### Requirement: Synchronous Destination Propagation on Edit

When a query edit is saved, the system MUST synchronously — within the PATCH request (D10), with no background queue — re-execute the edited query against Odoo and reload every registered `query_destinations` table using WRITE_TRUNCATE disposition under the union-inferred result schema (D1), so each destination mirrors the edited query exactly. Propagation MUST affect BigQuery destinations only; Postgres sync tables and other artifacts MUST remain untouched (D3). The response MUST report a per-destination result of `ok` or `failed` with an error message, and failed destinations MUST be marked stale so the next manual or scheduled run heals them (D9). The edit itself MUST be persisted regardless of propagation outcome, including total Odoo failure.

#### Scenario: All destinations propagate successfully

- **GIVEN** query "sales" has two registered destinations
- **WHEN** the user saves a valid edit to "sales"
- **THEN** the query re-runs against Odoo and both destination tables are reloaded with WRITE_TRUNCATE before the response is returned
- **AND** the response reports `ok` for both destinations

#### Scenario: Partial propagation failure marks destination stale

- **GIVEN** query "sales" has two registered destinations, one of whose tables was deleted in BigQuery
- **WHEN** the user saves a valid edit
- **THEN** the response reports `ok` for the healthy destination and `failed` plus the error for the missing one
- **AND** the failed destination is marked stale for next-run healing
- **AND** the edit remains saved

#### Scenario: Total Odoo failure still saves the edit

- **GIVEN** Odoo is unreachable
- **WHEN** the user saves a valid edit to "sales"
- **THEN** the edit is persisted and the PATCH succeeds
- **AND** every registered destination is reported `failed` with the Odoo error and marked stale

### Requirement: BigQuery Schema Inference from Query Results

The system MUST infer the BigQuery load schema as the union of the keys across all sampled result rows, never from the first row alone (fixes the latent bug at bigquery.py:134-144, D7; previously the schema was inferred from `rows[0]` only, silently dropping keys absent from the first sampled row). Combined with WRITE_TRUNCATE loads, destination tables MUST mirror the edited query's current field list: a newly added field MUST appear as a populated column after the next load, and a removed field's column — including all historical values — MUST be dropped from the destination (D2 destructive mirror semantics).

#### Scenario: Heterogeneous rows produce a union schema

- **GIVEN** an Odoo result set in which the key "discount" appears only in the third sampled row
- **WHEN** the load schema is inferred
- **THEN** the schema contains "discount" together with every key from every sampled row

#### Scenario: Added field appears with data after reload

- **GIVEN** the user adds field "margin" to query "sales" and saves
- **WHEN** propagation reloads the destination table
- **THEN** the table has a "margin" column populated for every returned row

#### Scenario: Removed field drops column and history

- **GIVEN** the user removes field "cost" from query "sales" and saves
- **WHEN** propagation reloads the destination table with WRITE_TRUNCATE
- **THEN** the "cost" column and all of its historical values are absent from the destination

### Requirement: Stored Query Limit Enforcement

The system MUST apply each query's stored `limit_val` on every execution path — the manual runner (routers/runner.py:26), the schedule executor (schedules.py:328), and the edit-propagation reload (D8). When `limit_val` is unset the system MUST execute with no limit and return the full result set. (Previously: the manual runner and the schedule executor hardcoded `limit: False`, ignoring the stored limit.)

#### Scenario: Manual run honors the stored limit

- **GIVEN** query "sales" has `limit_val = 50`
- **WHEN** a user runs "sales" manually
- **THEN** the Odoo call applies limit 50 and at most 50 rows are returned and uploaded

#### Scenario: Scheduled run honors the stored limit

- **GIVEN** query "sales" has `limit_val = 50` and an active schedule
- **WHEN** the schedule executor runs
- **THEN** the Odoo call is made with limit 50, not `limit: False`

#### Scenario: Propagation reload honors the stored limit

- **GIVEN** the user sets `limit_val = 10` on "sales" and saves
- **WHEN** propagation re-executes the query to reload the destinations
- **THEN** each destination table is reloaded with at most 10 rows

#### Scenario: No stored limit returns the full result

- **GIVEN** query "sales" has no `limit_val`
- **WHEN** any execution path runs it
- **THEN** the query executes with no limit and the full Odoo result set is returned

## MODIFIED Requirements

### Requirement: Query Recategorization Endpoint

The system MUST expose `PATCH /queries/{name}` to update a saved query. The endpoint MUST accept any subset of the editable attributes `fields`, `domain`, `limit_val`, `description`, and `category_id`; it MUST validate the payload (`fields` is a non-empty list, `domain` is a valid Odoo domain, `limit_val` is a positive integer or null, `category_id` references an existing category) and persist valid edits. The system MUST reject with HTTP 400 any payload that fails validation and any attempt to change `name`, `model`, or `method`, which are immutable after creation (D4/D5). An unknown query name MUST be rejected with 404 Not Found. An invalid `category_id` MUST be rejected with 400 Bad Request or 422 Unprocessable Entity. On successful save the response MUST include the per-destination propagation results defined in "Synchronous Destination Propagation on Edit".
(Previously: `PATCH /queries/{name}` accepted only category changes.)

#### Scenario: Recategorize existing query

- **GIVEN** a query named "daily_sales" assigned to "General" and a category "Finance"
- **WHEN** a client sends `PATCH /queries/daily_sales` with `category_id` set to Finance's id
- **THEN** the query's category MUST become "Finance"
- **AND** the response MUST reflect the updated category

#### Scenario: Unknown query name

- **GIVEN** no query named "missing_query" exists
- **WHEN** a client sends `PATCH /queries/missing_query`
- **THEN** the API MUST respond 404 Not Found

#### Scenario: Invalid category rejected

- **GIVEN** a query named "daily_sales" and no category with id 99999
- **WHEN** a client sends `PATCH /queries/daily_sales` with `category_id` 99999
- **THEN** the API MUST respond 400 Bad Request or 422 Unprocessable Entity
- **AND** the query's category MUST remain unchanged

#### Scenario: Full edit succeeds and reports propagation

- **WHEN** a client PATCHes /queries/sales with new `fields`, `domain`, `limit_val`, `description`, and `category_id`
- **THEN** all provided attributes are validated and persisted
- **AND** the response includes the per-destination propagation results

#### Scenario: Invalid payload rejected with 400

- **WHEN** a client PATCHes /queries/sales with a malformed `domain` or a non-list `fields` value
- **THEN** the API responds 400 with a validation error
- **AND** neither the stored query nor any destination table is modified

#### Scenario: Immutable attribute change rejected with 400

- **WHEN** a client PATCHes /queries/sales attempting to change `name`, `model`, or `method`
- **THEN** the API responds 400 identifying the immutable attribute
- **AND** the stored query remains unchanged
