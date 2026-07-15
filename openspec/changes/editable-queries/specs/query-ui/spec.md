# Spec Delta — editable-queries

## ADDED Requirements

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
