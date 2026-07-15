# Proposal — file-upload-skip-rows

## Why

Real-world Excel sheets (all of the user's main budget sheets) have 1-2
title/parameter rows before the actual table header. The approved rule
"first row = header" makes those sheets unloadable (400), forcing manual
file cleaning. Live E2E confirmed: 4 of 7 sheets in the user's real file
fail for this reason.

## What

Add a user-configurable **start row** (1-based, default 1 = current behavior):

- Backend: `skipRows` form field (int ≥ 0, default 0) on `/preview` and
  `/load`; passed to `extract_csv`/`extract_xlsx` which skip N rows before
  reading the header row. Negative → 400.
- Frontend wizard: "La tabla empieza en la fila" numeric input on the source
  and sheet steps; retry path when preview 400s; load sends the same value.
- `/inspect` unchanged (sheet enumeration does not need row semantics).

## Out of scope

- Auto-detection of the header row (magic, risky — explicit user input only).
- Skipping trailing/footer rows.
- Better error message for empty sheets (noted, not now).

## Impact

- Modifies spec `file-upload` (preview/load contracts) and `file-upload-ui`
  (wizard steps gain the start-row input).
- No new dependencies. `bigquery.py` remains untouched.
