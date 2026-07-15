# Spec Delta — file-upload-skip-rows

## ADDED Requirements

### Requirement: Configurable Start Row

The `/preview` and `/load` endpoints SHALL accept an optional `skipRows` form
field: an integer ≥ 0, default 0. `/inspect` SHALL accept the same optional
field and apply it only for CSV sources (its xlsx branch enumerates sheets
without scanning rows). The extractor SHALL skip that many rows
before reading the header row, for both CSV and XLSX sources. The same
`skipRows` value used at preview time SHALL be accepted by `/load` so the
loaded table matches the approved schema.

#### Scenario: Skip title rows before header

- **WHEN** a file whose first 2 rows are title/parameter rows is previewed
  with `skipRows=2`
- **THEN** the third row is treated as the header and the preview returns
  typed columns, sample, and totalRows for the remaining rows

#### Scenario: Default preserves current behavior

- **WHEN** `skipRows` is omitted
- **THEN** extraction behaves exactly as before (header = first row)

#### Scenario: Negative skip rejected

- **WHEN** `skipRows` is negative
- **THEN** the endpoint responds 400 and performs no extraction

#### Scenario: Skip beyond data

- **WHEN** `skipRows` consumes all rows (no header remains)
- **THEN** the endpoint responds 400 with a clear detail

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
