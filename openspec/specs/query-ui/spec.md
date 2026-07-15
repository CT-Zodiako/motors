# query-ui Specification

## Purpose

Defines the Angular frontend behavior for query categories: category selection
and inline creation in the save wizard, category grouping and recategorization
in the query list, category grouping in the runner selector, the default
query limit bugfix, and the query edit mode (wizard prefill, immutable
name/model/method, propagation summary, and removed-field destructive
confirmation). Out of scope: per-category permissions/roles, cascade delete,
custom category ordering, category rename UI, and query rename.

## Requirements

### Requirement: Wizard Category Selection

The wizard Save step MUST present a category selector with "General"
preselected by default. The selector MUST offer inline "Nueva categoría…"
creation that POSTs the new category and preselects it in the wizard. Duplicate
category names MUST be handled gracefully with user-visible feedback and
without losing wizard state.

#### Scenario: General preselected by default

- GIVEN the user reaches the Save step of the wizard
- WHEN the category selector renders
- THEN "General" MUST be the preselected value

#### Scenario: Inline category creation preselects the new category

- GIVEN the Save step category selector
- WHEN the user chooses "Nueva categoría…", enters "Finance", and confirms
- THEN the UI MUST POST the new category to the backend
- AND "Finance" MUST become the selected category in the wizard

#### Scenario: Duplicate category name handled gracefully

- GIVEN a category named "Finance" already exists
- WHEN the user attempts inline creation of "Finance"
- THEN the UI MUST show user-visible feedback about the duplicate name
- AND the wizard MUST retain its current state (query definition and selections)

### Requirement: Query List Grouped by Category

The query list MUST group rows by category using groupRowsBy, with groups
ordered alphabetically by category name. Each row MUST expose a recategorize
action that changes the query's category.

#### Scenario: Groups ordered alphabetically by category name

- GIVEN queries in categories "Finance", "General", and "Audit"
- WHEN the query list renders
- THEN groups MUST appear in alphabetical order: "Audit", "Finance", "General"
- AND each row MUST appear under its query's category group

#### Scenario: Recategorize from the list

- GIVEN a query row under the "General" group and a category "Finance"
- WHEN the user invokes the row's recategorize action and selects "Finance"
- THEN the query MUST move to the "Finance" group in the list
- AND the change MUST persist to the backend

### Requirement: Runner Selector Grouped by Category

The runner's query selector MUST group its options by category.

#### Scenario: Options grouped by category

- GIVEN saved queries in categories "General" and "Finance"
- WHEN the user opens the runner query selector
- THEN options MUST be grouped under their category names
- AND each query MUST appear under its assigned category group

### Requirement: Default Query Limit on Save

Saved queries MUST NOT persist `limit_val: 0`. When the user does not set an
explicit limit, the wizard MUST store the default limit of 100.

#### Scenario: Save without explicit limit stores default

- GIVEN the user completes the wizard without setting a limit
- WHEN the query is saved
- THEN the stored query MUST have `limit_val` 100, not 0

#### Scenario: Explicit limit preserved

- GIVEN the user sets a limit of 250 in the wizard
- WHEN the query is saved
- THEN the stored query MUST have `limit_val` 250

### Requirement: Query Edit Entry and Wizard Edit Mode

The query list SHALL expose an Edit entry point for every saved query. Activating it MUST open the existing query-creation wizard (query-create.ts) in edit mode with the query's current values pre-filled — fields, domain, limit, description, and category. In edit mode the `name`, `model`, and `method` inputs MUST be rendered read-only (D4), while every editable input remains changeable.

#### Scenario: Wizard opens pre-filled in edit mode

- **GIVEN** saved query "sales" with fields [name, amount], a domain filter, limit 50, and category "Finance"
- **WHEN** the user chooses Edit from the query list
- **THEN** the wizard opens in edit mode with all current values pre-filled

#### Scenario: Immutable fields are read-only in edit mode

- **WHEN** the wizard is in edit mode for "sales"
- **THEN** `name`, `model`, and `method` are displayed but not editable
- **AND** all other inputs remain editable

### Requirement: Query Update API Client

The frontend data layer (odoo-queries.ts) SHALL expose `update(name, payload)`, which MUST issue the extended `PATCH /queries/{name}` request with the editable attributes only and resolve with the parsed per-destination propagation results. API validation failures (HTTP 400) MUST be surfaced to the user and MUST NOT clear the wizard's current input state.

#### Scenario: Save issues the extended PATCH

- **WHEN** the user confirms an edit in the wizard
- **THEN** `update(name, payload)` sends PATCH /queries/{name} with the editable attributes
- **AND** resolves with the server's propagation summary

#### Scenario: Validation error surfaced without losing edits

- **WHEN** the API responds 400 to an update
- **THEN** the wizard shows the validation error and stays open with the user's input intact

### Requirement: Propagation Summary After Save

After an edit is saved, the UI MUST render the per-destination propagation summary returned by the API, marking each registered destination as updated or failed. Failed destinations MUST be flagged with copy conveying that the destination "will retry on next run" (D9). The summary MUST also note that destinations created by manual upload before this version are not yet registered and will self-register after their next upload.

#### Scenario: All-ok summary

- **WHEN** an edit propagates successfully to every registered destination
- **THEN** the summary lists each destination as updated

#### Scenario: Partial-failure summary with retry flag

- **WHEN** one destination fails during propagation
- **THEN** the summary shows that destination as failed with its error and the "will retry on next run" note
- **AND** the successful destinations are still shown as updated

#### Scenario: Pre-v1 manual destination note

- **WHEN** the propagation summary is displayed
- **THEN** it includes the note that manually uploaded destinations self-register after their next upload

### Requirement: Removed-Field Destructive Confirmation

When the user saves an edit that removes one or more fields, the UI MUST first require explicit confirmation stating that each removed field's column and its history will be dropped from BigQuery destinations (D2 destructive WRITE_TRUNCATE mirror). The confirmation MUST appear only when the submitted edit actually removes fields; edits that merely add fields or change non-field metadata MUST be saved without it.

#### Scenario: Confirmation shown when a field is removed

- **GIVEN** the user removed field "cost" from "sales" in the wizard
- **WHEN** the user chooses Save
- **THEN** a confirmation warns that the "cost" column and its history will be dropped
- **AND** the PATCH is sent only after explicit confirmation

#### Scenario: No confirmation when no field is removed

- **WHEN** the user saves an edit that only adds a field or changes the category
- **THEN** no destructive confirmation appears and the PATCH is sent directly
