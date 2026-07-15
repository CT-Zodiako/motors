# file-upload-ui Specification

## Purpose

Defines the Angular frontend behavior for the file-upload wizard: a dedicated
"Cargar archivo" tab that guides the user through source selection, sheet
selection, schema approval, and destination selection before creating a new
BigQuery table, reusing the existing BigQuery destination picker. The wizard is
stateless per request and adds no new npm dependencies.

## Purpose

Frontend wizard (new page `odoo-ui/src/app/pages/file-upload/`, sixth navigation tab) that guides the user through uploading an `.xlsx`/CSV file, choosing one sheet, approving/editing the inferred schema, and loading the data into a new BigQuery table via the stateless `file-upload` backend endpoints. All user-facing copy is in Rioplatense Spanish.

## ADDED Requirements

### Requirement: Sixth Navigation Tab and Route

The application SHALL add a sixth tab to the main navigation whose label is in Spanish and references file upload (e.g., "Subir archivo"), extending the `Tab` union type and nav definition in `app.ts`. Selecting the tab SHALL render the file-upload wizard page implemented under `odoo-ui/src/app/pages/file-upload/`. Existing tabs and their behavior SHALL remain unchanged.

#### Scenario: Tab renders the wizard
- WHEN the user activates the sixth tab
- THEN the file-upload wizard page SHALL be displayed
- AND the tab label SHALL be a non-empty Spanish string containing "archivo"

#### Scenario: Existing tabs unaffected
- WHEN the new tab is added
- THEN the five pre-existing tabs SHALL still navigate to their respective pages

### Requirement: Ordered Multi-Step Wizard

The wizard SHALL present an ordered, multi-step flow mirroring the `query-create` wizard: (1) source selection, (2) sheet selection, (3) schema review/editing, (4) destination selection, (5) result. A step indicator SHALL show the current step. The user SHALL NOT be able to advance past a step until that step's inputs are valid and its backend call (when applicable) has succeeded. Navigating back SHALL preserve all previously entered data and selections.

#### Scenario: Forward guard
- WHEN the source step has no valid file or URL
- THEN the continue control SHALL be disabled
- AND no backend call SHALL be made

#### Scenario: Back navigation preserves state
- GIVEN the user completed the source and sheet steps and edited column names
- WHEN the user navigates back to the sheet step and forward again
- THEN the previously edited column names and type selections SHALL still be present

### Requirement: Source Selection Step

The first step SHALL let the user choose a local file via a file input restricted to `.xlsx` and `.csv`. Client-side validation SHALL reject other extensions — including `.xls` — with inline Spanish error messages before any backend call, and the continue control SHALL remain disabled until a valid file is chosen.

#### Scenario: Invalid extension blocked client-side
- WHEN the user selects a `.xls` file
- THEN an inline error SHALL state that `.xls` is not supported and must be saved as `.xlsx`
- AND the continue control SHALL remain disabled

#### Scenario: Continue disabled without file
- WHEN no file has been chosen
- THEN the continue control SHALL be disabled
- AND no backend call SHALL be made

### Requirement: Conditional Sheet Selection Step

When inspection reports more than one sheet, the wizard SHALL show a sheet-selection step listing the sheet names returned by `/bigquery/upload-file/inspect` and SHALL require exactly one selection. For CSV sources (single pseudo-sheet) the wizard SHALL skip this step automatically.

#### Scenario: CSV skips sheet selection
- WHEN the user uploads a CSV file
- THEN the wizard SHALL proceed from source directly to the schema step
- AND the sheet parameter sent to preview SHALL be the single pseudo-sheet reported by inspect

#### Scenario: Workbook requires one selection
- WHEN the uploaded `.xlsx` has three worksheets
- THEN the sheet step SHALL list all three names
- AND the user SHALL NOT advance until exactly one is selected

### Requirement: Schema Review and Editing Step

The schema step SHALL display every column reported by `/bigquery/upload-file/preview` with: an include toggle (default on), an editable name field prefilled with the sanitized default name, a type selector offering exactly `INT64`, `FLOAT64`, `BOOL`, `DATE`, `TIMESTAMP`, `STRING` prefilled with the inferred type, and the sample rows for context. The column-picker interaction SHALL follow the existing `query-runner` BigQuery dialog precedent. The step SHALL validate names against `^[A-Za-z_][A-Za-z0-9_]{0,1023}$` and SHALL detect duplicate resolved names (case-insensitive) client-side, disabling continuation while any name is invalid or duplicated. At least one column MUST remain included.

#### Scenario: Defaults from preview
- WHEN the schema step opens
- THEN each column SHALL show the sanitized default name and inferred type from the preview response
- AND all include toggles SHALL be on

#### Scenario: Duplicate name blocked before submit
- WHEN the user renames two included columns to the same resolved name
- THEN an inline error SHALL identify the collision
- AND the continue control SHALL be disabled

#### Scenario: Invalid identifier blocked
- WHEN a column name contains characters outside the BigQuery identifier pattern
- THEN an inline validation message SHALL appear
- AND continuation SHALL be disabled

#### Scenario: At least one column required
- WHEN the user excludes every column
- THEN continuation SHALL be disabled with an explanatory message

### Requirement: Destination Selection Step

The destination step SHALL let the user choose an existing BigQuery dataset from a list fetched from the backend and enter a new table name as free text validated against the shared identifier pattern. The step SHALL communicate that existing table names are rejected and that load never overwrites or appends. The UI SHALL NOT offer a way to create new datasets.

#### Scenario: Dataset list from backend
- WHEN the destination step opens
- THEN the dataset selector SHALL be populated from the existing datasets endpoint
- AND free-text dataset entry SHALL NOT be offered

#### Scenario: Invalid table name blocked
- WHEN the table name fails identifier validation
- THEN continuation SHALL be disabled with an inline Spanish message

### Requirement: Stateless Resubmission of the Source

The wizard SHALL retain the selected `File` object — plus every user decision — in component state, and SHALL re-send the source with each backend call using `FormData` over the existing `HttpClient`. The wizard SHALL NOT depend on any server-side session or stored upload between steps.

#### Scenario: File re-sent on each call
- WHEN the wizard calls inspect, then preview, then load
- THEN each request SHALL include the file via `FormData`
- AND no request SHALL assume the backend remembers a previous upload

### Requirement: Load Submission, Progress, and Result Handling

On confirmation, the wizard SHALL call `/bigquery/upload-file/load`, showing a progress indicator and preventing duplicate submissions while in flight. On success, the result step SHALL display the fully qualified table name and the loaded row count. On failure, the wizard SHALL display the backend's actionable message verbatim — including the 409 table-exists case — while preserving all wizard state so the user can correct inputs and resubmit.

#### Scenario: Success summary
- WHEN load succeeds
- THEN the result step SHALL show the full `project.dataset.table` identifier and the row count returned by the backend

#### Scenario: Table-exists error keeps state
- WHEN load returns HTTP 409
- THEN an inline error SHALL show the backend message naming the existing table
- AND the user SHALL be able to return to the destination step, change the table name, and resubmit without re-selecting the file

#### Scenario: Duplicate submission prevented
- WHEN a load request is in flight
- THEN the confirm control SHALL be disabled until the request settles

### Requirement: Rioplatense Spanish UI Copy

All user-facing strings in the wizard — step labels, buttons, validation messages, empty states, and error presentation — SHALL be in Rioplatense Spanish (voseo), consistent with the rest of the application. Backend error detail messages SHALL be shown verbatim when actionable.

#### Scenario: Copy audit
- WHEN the wizard renders any step or error state
- THEN all visible strings SHALL be Spanish
- AND imperative forms SHALL use voseo consistent with existing app copy

### Requirement: No New Frontend Dependencies

The feature SHALL be implemented with the existing stack (`HttpClient`, `FormData`, existing components and patterns). `package.json` and the lockfile SHALL remain unchanged.

#### Scenario: Dependency manifest unchanged
- WHEN the feature is complete
- THEN `odoo-ui/package.json` and its lockfile SHALL have no added or upgraded dependencies

### Requirement: Automated Frontend Verification

The domain SHALL ship with tests executable via `cd odoo-ui && npm test` covering, at minimum: tab registration, wizard step order and guards, CSV sheet-step skip, schema editing validation (duplicates, invalid names, all-excluded), payload assembly for load (subset, renames, overrides), 409 error rendering with state preservation, and double-submit prevention.

#### Scenario: Suite runs green
- WHEN `cd odoo-ui && npm test` is executed
- THEN all file-upload wizard tests SHALL pass

## Non-Goals

- No new npm dependencies.
- No upload history or persistence UI.
- No append/replace flows, no multi-sheet selection, no `.xls` handling beyond the client-side rejection message.
- No Google Sheets URL input in this increment (deferred to a future increment).
- Drag-and-drop file input is optional (MAY); a standard file input satisfies the requirement.

### Requirement: Wizard Start-Row Input

The wizard SHALL expose a numeric "start row" input (default 1, minimum 1) on
the source step and on the sheet step. The wizard SHALL send
`skipRows = startRow - 1` on preview and load. When a preview fails, the
wizard SHALL keep the user on the current step with the backend error visible
and allow adjusting the start row and retrying without re-selecting the file.

#### Scenario: Adjust start row after ragged-sheet error

- **WHEN** a sheet preview responds 400 for ragged rows and the user sets the
  start row to 3 and retries
- **THEN** the wizard re-previews with `skipRows=2` and advances to the
  schema step on success

#### Scenario: Load uses the approved start row

- **WHEN** the user confirms the load after previewing with start row 3
- **THEN** the load request carries `skipRows=2` and the created table
  matches the approved schema and row set
