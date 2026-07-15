# SDD Technical Design — `file-to-bigquery`

**Change:** `file-to-bigquery` · **Repo:** `/Users/zodiakomac/DEV/motors` · **Phase:** design (SDD)
**Scope (revised):** Upload `.xlsx`/CSV (multipart) → inspect → preview → load to BigQuery. Google Sheets is CUT. Stateless, in-memory only, first row = header, create-only (never overwrite).

## 1. Goals / Non-goals

**Goals**
- Three stateless endpoints under `/bigquery/upload-file/`: `inspect`, `preview`, `load` (R1).
- `.xlsx` via openpyxl, CSV via stdlib `csv`; legacy `.xls` → 415; other types → 415 (R2).
- File never persisted; all processing in memory (R3). First row = header (R4).
- Preview contract: source header + sanitized default name + inferred type (closed set `INT64/FLOAT64/BOOL/DATE/TIMESTAMP/STRING`), ≤100-row sample, total row count, inference over ALL rows (R5/R6).
- Load with user-approved schema (include/rename/retype), `CREATE TABLE` with explicit schema, 409 if table exists with zero writes, load ALL rows (R9–R11).
- Failure cleanup: partial table dropped and cleanup reported (R12).
- Reuse `odoo/routers/bigquery.py` helpers; keep that module stable for `schedules.py` (R13).
- Fully offline pytest suite with faked Google clients (R14); Angular wizard as 6th tab with vitest specs, no new npm deps (frontend R1–R11).

**Non-goals:** persistence/history, append/replace, multi-sheet load, Google Sheets, dataset creation, `.xls` support, locale-aware number parsing (decimal comma).

## 2. Architecture & data flow

```
Angular wizard (6th tab)                FastAPI backend
─────────────────────                   ─────────────────────────────────
FileUploadWizard (signals)              odoo/routers/file_upload.py  (NEW — endpoints only)
   └─ file-upload.service.ts            odoo/bq_schema.py            (NEW — pure domain logic)
        │  FormData per call ───────►        │  imports string regexes/helpers from
        ▼                                    ▼  odoo/routers/bigquery.py (UNTOUCHED)
   inspect → preview → load            extraction → inference → conversion → BigQuery
                                              odoo/bigquery_client.get_bigquery_client()
```

Request lifecycle (all three endpoints share the head of the pipeline):

1. **Read bytes**: `content = await file.read(MAX_UPLOAD_FILE_BYTES + 1)`; `len > cap` → 413.
2. **Validate `sourceType`** ∈ {`xlsx`,`csv`} and consistency with filename extension; `.xls` extension **or OLE2 magic bytes** (`D0 CF 11 E0`) → 415; other extensions → 415.
3. **Extract** (in memory): `extract(content, sourceType, sheet?) -> ExtractedTable(headers: list[str], rows: list[list[NativeValue]])`, enforcing the 100k data-row cap → 413.
4. Endpoint-specific:
   - **inspect**: xlsx → sheet names only (`wb.sheetnames`, no row scan); CSV → pseudo-sheet `["CSV"]`.
   - **preview**: infer per-column type over ALL rows; build sanitized default names; serialize first ≤100 rows.
   - **load**: validate decisions → convert ALL rows to approved types (zero BQ writes before this succeeds) → dataset 404 gate → table-exists 409 gate → create table → `load_table_from_json` (WRITE_EMPTY) → on job failure drop table + report cleanup.

## 3. Decisions

### D1 — Module layout: new router + new pure-logic module; `bigquery.py` untouched
**Decision:** Create `odoo/routers/file_upload.py` (FastAPI wiring only) and `odoo/bq_schema.py` (extraction, sanitization, inference, conversion — pure, unit-testable, no FastAPI imports). `bq_schema.py` imports the existing private string-inference helpers (`_infer_string_type`, `_infer_field_type`, `_promote_bq_type`, `_BQ_TYPE_RANK` regexes) from `odoo.routers.bigquery` and reuses `MAX_UPLOAD_ROWS`. Zero edits to `bigquery.py`. `file_upload.py` does `from odoo.bigquery_client import get_bigquery_client` at module scope but **calls it inside endpoint functions** so tests can monkeypatch and nothing constructs a Google client at import time.
**Rationale:** R13 demands reuse without destabilizing `schedules.py`. Importing same-package privates is the lowest-risk reuse; bigquery.py's behavior and namespace stay byte-identical.
**Rejected:** (a) Extract helpers out of bigquery.py and re-import (larger diff + regression risk for schedules.py); (b) duplicate the regexes (drift risk against spec-pinned R6 rules); (c) put everything in the router (untestable, >400-line file).

### D2 — Concrete in-memory limits
**Decision:** `MAX_UPLOAD_FILE_BYTES = 20 * 1024 * 1024` (20 MB) → **413**; data-row cap reuses `MAX_UPLOAD_ROWS = 100_000` (excluding header and fully-empty rows) → **413** with the limit in the message.
**Rationale:** xlsx is zip-compressed; 20 MB compressed is already a heavy workbook. 100k rows matches the existing JSON-upload cap and bounds `load_table_from_json` payload + Python object graph to a safe size for one request.
**Rejected:** temp-file streaming (violates R3 in-memory-only); no cap (DoS/memory); 1M rows (memory blowup; no precedent).

### D3 — Unified extraction model
**Decision:** One `ExtractedTable(headers, rows)` for both formats. Native value model: xlsx cells arrive as `int | float | bool | datetime.date | datetime.datetime | datetime.time | str | None` (extraction normalizes date-only cells to `date`, see D5); CSV cells arrive as `str | None` (`""` → `None`). Fully-empty rows are dropped everywhere and never counted.
**Rationale:** Single downstream pipeline for inference + conversion regardless of source; satisfies R5 "same function as load".
**Rejected:** per-format inference paths (divergence risk); streaming inference without materialization (needless complexity under the 100k cap).

### D4 — CSV parsing
**Decision:** Decode `utf-8-sig` (handles BOM); on `UnicodeDecodeError` fall back to `cp1252` with `errors="replace"`. Delimiter via `csv.Sniffer().sniff(sample_8k, delimiters=",;\t|")`, fallback comma on `csv.Error`. Default quoting (`QUOTE_MINIMAL` reader semantics, `"` quotechar). Parse with `csv.reader(io.StringIO(text, newline=""))`. Raggedness: any record whose field count ≠ header count (either direction) → **400** `CSV row {n} has {k} fields, expected {m}` (1-based data-row number). Empty file (no records) → 400.
**Rationale:** Rioplatense Excel exports are frequently cp1252 + semicolon-delimited; sniffing + cp1252 fallback avoids the most common real-world failures while staying stdlib-only.
**Rejected:** fixed comma (breaks locale exports); pandas (new dependency, banned); latin-1 fallback (maps control bytes silently; cp1252 is the practical Excel superset); silently padding short CSV rows (spec R7 pins strict 400).

### D5 — xlsx semantics
**Decision:** `load_workbook(io.BytesIO(content), read_only=True, data_only=True)`. Sheets in workbook order via `wb.sheetnames`; sheet selection by exact title, unknown → 400 listing available. CSV pseudo-sheet name constant `CSV_SHEET_NAME = "CSV"`. Iterate `ws.iter_rows()` (cells, not `values_only`) to read both `.value` and `.number_format`.
- **DATE vs TIMESTAMP:** datetime-valued cell whose number format contains time tokens (regex `[hs]` on the format string after stripping quoted literals and `[...]` sections) → keep `datetime` (TIMESTAMP candidate); date-only format → normalize to `datetime.date` (DATE candidate). Fallback when no format is available: midnight (`value.time() == 00:00`) → DATE.
- **Formulas:** `data_only=True` yields cached values; never-calculated formulas → `None` → NULL (R7).
- **Ragged xlsx:** rows shorter than header width are padded with `None`; rows longer than header width → 400 with row number **unless** every extra cell is empty (formatting artifacts), which are dropped.
- **Corrupt xlsx:** catch `openpyxl`/`zipfile` exceptions → 400 "corrupt or unreadable .xlsx". OLE2 magic sniffed up-front → 415 (renamed `.xls`).
- `datetime.time` cells → STRING via `isoformat()` (closed type set has no TIME).
**Rationale:** R6 ties DATE/TIMESTAMP to the cell's date-only vs date+time nature, which in Excel lives in the number format; strict long-row handling mirrors CSV philosophy without punishing used-range artifacts.
**Rejected:** midnight-only heuristic (misclassifies genuine midnight timestamps and 00:00-rendering date-times); treating trailing artifact cells as errors (false positives on real files); header detection beyond literal row 1 (spec R4).

### D6 — Single-source inference with a loadability guarantee
**Decision:** `bq_schema.infer_column_type(values) -> BQType` used by preview; load never re-infers — it converts against the approved schema. Inference rules per column over all non-empty values:

| Value kinds observed (non-empty) | Inferred |
|---|---|
| all `int` (never `bool`) | INT64 |
| `int`+`float`, or all `float` | FLOAT64 |
| all `bool` | BOOL |
| all `datetime.date` | DATE |
| all `datetime.datetime` | TIMESTAMP |
| all `str`: every value matches one string category | INT64 (int regex) / FLOAT64 (int-or-float regex) / BOOL (`true`/`false`, case-insensitive) / DATE (ISO `YYYY-MM-DD`) / TIMESTAMP (ISO datetime) |
| all empty | STRING |
| any other mix (incl. mixed string categories, numbers+dates, date+timestamp) | STRING |

String category detection **reuses the ISO/numeric regexes from bigquery.py** (D1). **Loadability guard:** after picking candidate T, verify every non-empty value passes `convert_value(v, T)`; on any failure demote to STRING (which accepts everything). 
**Rationale:** This makes "preview inference = same function as load" (R5) a provable property: a schema accepted with inferred defaults can never 400 during load.
**Rejected:** separate load-side inference (double source of truth); trusting inference without the converter guard (edge values like `NaN` would 400 on an accepted default).

### D7 — Conversion matrix (approved-type coercion at load)
**Decision:** `convert_value(value, target) -> JSONable`; `None`/empty → `None` for every target. Strict rules:

| target ↓ / source → | bool | int | float | date | datetime | str (CSV) |
|---|---|---|---|---|---|---|
| INT64 | ✗ | ✓ | ✓ only if `v.is_integer()` and finite | ✗ | ✗ | ✓ if fullmatch `[+-]?\d+` |
| FLOAT64 | ✗ | ✓ | ✓ if finite | ✗ | ✗ | ✓ if fullmatch decimal/exponent regex |
| BOOL | ✓ | ✗ | ✗ | ✗ | ✗ | ✓ if `strip().lower()` ∈ {`true`,`false`} |
| DATE | ✗ | ✗ | ✗ | ✓ → ISO str | ✗ (already normalized at extraction) | ✓ if ISO `YYYY-MM-DD` (validate via `date.fromisoformat`) |
| TIMESTAMP | ✗ | ✗ | ✗ | ✗ | ✓ → ISO str (naive treated as UTC, documented) | ✓ if `datetime.fromisoformat` succeeds (accept `Z`) |
| STRING | `str(v)` | `str(v)` | `str(v)` (finite only) | ISO | ISO | ✓ |

Non-finite floats (`NaN`/`Inf`) are incompatible with every numeric target. **Critical implementation note:** check `bool` **before** `int` (`isinstance(True, int)` is `True` in Python). First failure raises `ConversionError(column, row, value_repr_truncated, target, reason)` → 400: `Column 'precio' row 17: value 'abc' is not compatible with INT64` (1-based data-row number, R10). Conversion happens **before any BigQuery mutation**, so conversion 400s are zero-writes by construction.
**Rejected:** lenient coercion (e.g., `"3.0"`→INT64, `1`→BOOL) — silent data corruption; per-column error collection (spec wants first offender with column+row).

### D8 — Sanitization & rename validation
**Decision:** `sanitize_column_name(raw, used)` in bq_schema: `re.sub(r"[^A-Za-z0-9_]", "_", raw)` → if empty or first char not `[A-Za-z_]`, prefix `_` → truncate to 1024 → dedupe case-insensitively by appending `_2`, `_3`… re-truncating the base so total ≤ 1024 (`used` tracks `.lower()`ed names). Empty header `""` → `"_"`. Preview defaults run through this; at load, every included user-supplied name must additionally match `_validate_identifier`'s regex `^[A-Za-z_][A-Za-z0-9_]{0,1023}$` (reused from bigquery.py) and case-insensitive duplicates → 400 zero-writes (R10).
**Rationale:** sanitized output matches the identifier regex by construction; case-insensitive dedupe matches BigQuery's case-insensitive column access.
**Rejected:** case-sensitive dedupe (BQ create can fail/confuse); hash suffixes (unreadable).

### D9 — Load mechanics against BigQuery
**Decision:** 
1. `client.get_dataset(f"{project}.{dataset}")` → `NotFound` → **404**; never create datasets (R8).
2. Pre-check `client.get_table(ref)` → exists → **409**, zero writes; `NotFound` → proceed. Also catch `Conflict` from `create_table` (TOCTOU race) → 409.
3. `client.create_table(bigquery.Table(ref, schema=[SchemaField(name, type, "NULLABLE") …]))` (R11 explicit schema).
4. `client.load_table_from_json(rows_as_dicts, ref, job_config=LoadJobConfig(schema=…, write_disposition="WRITE_EMPTY"))`; `job.result()` waits. WRITE_EMPTY = "fail if the table already contains data" — since we just created it, first load succeeds and any pathological retry fails safe instead of duplicating rows.
5. Row count from `job.output_rows`; response `{"table": "project.dataset.table", "rows": N}`.
6. On job failure (`job.result()` raises / `job.errors`): `client.delete_table(ref, not_found_ok=True)`, then **502** with detail describing the job error **plus** cleanup outcome (`"partial table dropped"` or `"cleanup failed, drop {ref} manually"`); a cleanup exception never masks the original error (R12).
7. Header-only (0 data rows): preview fine; load → **400** before any BQ call (R7).
**Rejected:** `WRITE_TRUNCATE`/`WRITE_APPEND` (violates never-overwrite); relying on the pre-check alone without catching `Conflict` (race); skipping create and letting the load job auto-create (schema would not be guaranteed explicit; R11).

### D10 — API contracts (exact)
All endpoints: `POST`, multipart/form-data, prefix `/bigquery/upload-file`. `file` part required on every call (stateless; frontend re-sends, frontend R7). `sourceType` form field required (`xlsx`|`csv`) and must match the filename extension (mismatch → 400).

**`POST /inspect`** — fields: `file`, `sourceType`.
```json
200 { "sourceType": "xlsx", "fileName": "ventas.xlsx", "sizeBytes": 184320,
      "sheets": ["Hoja1", "Datos"], "sheetCount": 2 }
```
CSV: `"sheets": ["CSV"], "sheetCount": 1`.

**`POST /preview`** — fields: `file`, `sourceType`, `sheet?` (xlsx default first sheet; ignored for CSV).
```json
200 { "sheet": "Hoja1",
      "columns": [
        { "source": "Fecha de Venta", "name": "Fecha_de_Venta", "type": "DATE", "included": true },
        { "source": "precio",        "name": "precio",         "type": "FLOAT64", "included": true }
      ],
      "sample": [["2024-01-15", 1299.9], ["2024-01-16", null]],
      "totalRows": 1234 }
```
- `sample` rows are **positional arrays** (never header-keyed objects) to survive duplicate/raw headers; dates/timestamps serialized ISO; ≤100 rows. `totalRows` counts non-empty data rows; inference ran over ALL of them.

**`POST /load`** — fields: `file`, `sourceType`, `sheet?`, `decisions` (form field containing a JSON **string**), `dataset`, `table`.
```json
decisions = [{ "source": "Fecha de Venta", "name": "fecha_venta", "type": "DATE", "included": true },
             { "source": "precio",        "name": "precio",      "type": "FLOAT64","included": false }]
200 { "table": "my-project.mi_dataset.mi_tabla", "rows": 1234 }
```
Server-side decision validation, in order (all 400, zero writes): `decisions` parses and length equals re-extracted header count with `decisions[i].source == headers[i]` (else re-preview signal); each `type` in the closed set; ≥1 included column; each included `name` passes `_validate_identifier`; no case-insensitive duplicate included names; `dataset`/`table` pass `_validate_identifier`; then 404/409 gates; conversion (D7) before mutation (D9).

**Error envelope:** `HTTPException(status_code, detail="<human-readable string>")` — FastAPI's default `{ "detail": "…" }` shape; frontend renders `detail` verbatim (frontend R8). **Verify at apply:** if `bigquery.py` uses structured `detail` objects, adopt that instead (repo convention wins).

### D11 — Error → HTTP mapping
| Condition | Status |
|---|---|
| missing `file`/`sourceType`, bad `sourceType`, ext↔sourceType mismatch, decisions invalid, identifier invalid, dup rename, incompatible override, ragged CSV, corrupt/empty file, unknown sheet, header-only load, 0 included columns | 400 |
| dataset does not exist | 404 |
| table already exists (pre-check or `Conflict`) | 409 |
| file > 20 MB, rows > 100 000 | 413 |
| `.xls` (extension or OLE2 magic), any other extension | 415 |
| BigQuery load-job failure (after cleanup attempt) | 502 |

### D12 — Frontend architecture
- **Tab:** extend the `Tab` union + nav array in `odoo-ui/src/app/app.ts` with id `file-upload`, Spanish label **"Cargar archivo"** (contains "archivo", R1). No Angular Router, mirroring existing tabs.
- **Component:** single `FileUploadWizard` (`odoo-ui/src/app/file-upload/file-upload.{ts,html,css}`, mirroring `query-create` wizard file layout) with `step = signal<'source'|'sheet'|'schema'|'destination'|'result'>` and a step indicator. Forward navigation guarded per step; **Back never resets signals** (state preserved, R2/R8).
- **State signals:** `file`, `inspect`, `selectedSheet`, `preview`, `columns = signal<ColumnDecision[]>` (seeded from preview defaults), `datasets`, `dataset`, `table`, `busy`, `error`, `result`. Preview is cached per `(file, sheet)`; re-preview only when either changes.
- **Step behavior:**
  - *source:* file input `accept=".xlsx,.csv"`; client-side extension check rejects `.xls` with a dedicated message and everything else; "Continuar" disabled until a valid file passes `inspect` (R3).
  - *sheet:* rendered only when `sheetCount > 1`; CSV and single-sheet xlsx skip straight to schema (R4).
  - *schema:* PrimeNG table — include toggle (query-runner `checkedColumns`/`toggleColumn` precedent, adapted to per-row booleans), editable name (InputText, default = sanitized), type selector (SelectModule, 6 types), first sample rows below (SkeletonModule while loading). Inline validation: identifier regex, case-insensitive duplicates, ≥1 included (R5).
  - *destination:* dataset Select from the existing backend datasets endpoint (**verify exact path at apply** — e.g. `GET /bigquery/datasets`), table InputText with regex validation + helper copy stating the table is created new and **never overwritten** (409 means pick another name) (R6).
  - *result:* success panel with `project.dataset.table` + row count; error panel with backend `detail` verbatim (incl. 409); "Cargar otro archivo" resets, "Volver" keeps state for rename-and-resubmit (R8).
- **Service** `odoo-ui/src/app/services/file-upload.service.ts` (`providedIn: 'root'`, base `http://localhost:8000`, existing pattern):
```ts
inspect(file: File, sourceType: SourceType): Observable<InspectResponse>
preview(file: File, sourceType: SourceType, sheet?: string): Observable<PreviewResponse>
load(file: File, sourceType: SourceType, sheet: string | undefined,
     decisions: ColumnDecision[], dataset: string, table: string): Observable<LoadResponse>
```
Each builds a fresh `FormData` (`file` + fields; `decisions` as `JSON.stringify`). No double-submit: `busy` signal disables actions and guards the submit handler (R8).
- **Copy:** Rioplatense voseo throughout (R9), e.g. `Subí tu archivo .xlsx o CSV`, `Elegí la hoja`, `Revisá el esquema`, `Definí el destino`, `Cargando…`, `¡Listo! Se cargaron {n} filas en {tabla}`, `Los archivos .xls (formato viejo) no están soportados; guardalo como .xlsx`.
- **PrimeNG modules:** TableModule, ButtonModule, SelectModule, SkeletonModule, MessageService, InputTextModule, ProgressSpinnerModule — all from the existing PrimeNG dependency (R10, no new npm deps).
**Rejected:** one sub-component per step (state-sharing friction; no precedent); storing the file in a service (component state is the spec'd home, R7).

### D13 — Identifier regex duplication (frontend ↔ backend)
**Decision:** duplicate `^[A-Za-z_][A-Za-z0-9_]{0,1023}$` as a TS constant with a comment pointing at `_validate_identifier` in `odoo/routers/bigquery.py`, plus a backend test pinning the exact regex behavior and a frontend spec pinning the TS one.
**Rationale:** no shared-codegen infra exists; tests on both sides catch drift.
**Rejected:** build-time codegen from Python (disproportionate); frontend-only validation (backend must remain authoritative).

### D14 — `requirements.txt` addition
**Decision:** add `python-multipart==0.0.20` (post-ReDos-CVE line, compatible with FastAPI 0.136.3's `>=0.0.7` requirement). Required for `UploadFile`/Form parsing.

### D15 — Offline test strategy
**Backend (pytest, fully offline):**
- `FakeBigQueryClient`: dict-backed (`datasets: set`, `tables: dict[qualified_name → {schema, rows}]`) implementing `get_dataset` (raises `NotFound`), `get_table`, `create_table` (raises `Conflict`), `load_table_from_json` (enforces WRITE_EMPTY, stores rows, returns `FakeLoadJob` with `result()`/`output_rows`/`errors`, configurable to fail), `delete_table` (records calls; configurable to raise). Monkeypatch `odoo.routers.file_upload.get_bigquery_client`.
- `TestClient` multipart posts via `files=` + `data=`. xlsx fixtures built in-memory with openpyxl `Workbook()` → `BytesIO` (multi-sheet, dates with date-only vs date+time number formats, formula-without-cached-value, fully-empty rows, long/short rows, 100k+1 row cap test via generated CSV for speed). CSV fixtures as byte strings (BOM, semicolon, cp1252 bytes, ragged, empty).
- Test matrix: inspect (xlsx sheets, csv pseudo-sheet, .xls→415, renamed-.xls magic→415, bad ext→415, corrupt→400, 413 oversize); preview (each inferred type, mixed→STRING, all-empty→STRING, totalRows, ≤100 sample, sanitized defaults + `_2` dup, ragged→400 w/ row number, formula→null); load (success rows + qualified name; 409 zero-writes — assert fake saw no `create_table`/`load` after exists; dataset 404; dup rename case-insensitive→400; override-incompatible→400 with column+row in detail; header-only→400 zero writes; job failure→502 + `delete_table` called + cleanup reported; cleanup failure→502 with manual-cleanup note; decisions out-of-sync→400; 0 included→400).
- **Property-style test:** for every fixture column, `convert_value` accepts all values under the inferred type (formalizes D6's guarantee).
**Frontend (vitest):** service specs with `HttpClientTestingModule` (URL, FormData parts incl. `decisions` JSON, error passthrough); component specs with a stubbed service (step guard, back-preserves-state, extension rejection incl. `.xls`, CSV skips sheet step, schema validation incl. case-insensitive dup + ≥1 column, busy-guard no double submit, success panel shows qualified name + rows, 409 verbatim + resubmit keeps state).

## 4. File changes

**Backend**
| File | Change | ~Lines |
|---|---|---|
| `odoo/bq_schema.py` | NEW — extraction (xlsx/csv), sanitize, infer, convert, `ExtractedTable`, `ConversionError` | ~260 |
| `odoo/routers/file_upload.py` | NEW — 3 endpoints, validation, error mapping, load orchestration | ~420 |
| `requirements.txt` | +`python-multipart==0.0.20` | 1 |
| `tests/test_bq_schema.py` | NEW — unit tests incl. property test | ~200 |
| `tests/test_file_upload.py` | NEW — API tests + `FakeBigQueryClient` | ~470 |
| `odoo/routers/bigquery.py`, `odoo/bigquery_client.py`, `schedules.py` | **untouched** | 0 |

**Frontend**
| File | Change | ~Lines |
|---|---|---|
| `odoo-ui/src/app/app.ts` | +Tab union member, +nav entry, +tab content branch | ~15 |
| `odoo-ui/src/app/services/file-upload.service.ts` | NEW | ~90 |
| `odoo-ui/src/app/file-upload/file-upload.{ts,html,css}` | NEW wizard | ~430 |
| `odoo-ui/src/app/services/file-upload.service.spec.ts` | NEW | ~120 |
| `odoo-ui/src/app/file-upload/file-upload.spec.ts` | NEW | ~250 |

**Total ≈ 2 250 changed lines → chained PRs** (respecting the 400-line review budget, same backend/frontend chaining style as `query-categories`):
1. **PR1 (backend):** `bq_schema.py` + `test_bq_schema.py` (~460 — trim or split tests if strict).
2. **PR2 (backend):** `file_upload.py` + `requirements.txt` + `test_file_upload.py` (~890 → likely split into router (~420) then tests (~470)).
3. **PR3 (frontend):** `app.ts` + service + wizard (~535).
4. **PR4 (frontend):** vitest specs (~370).
Final split/forecast to be refined at `sdd-apply`; if the forecast conflicts with session preferences, pause and ask per the interactive-mode contract.

## 5. Risks

- **Number-format heuristic (D5):** exotic/custom formats may misclassify DATE vs TIMESTAMP; midnight fallback covers missing styles. *Severity: medium.* Mitigation: fixtures with real-world formats in tests.
- **openpyxl read_only quirks:** stale sheet dimensions may need `ws.reset_dimensions()`; verify with real files during apply. *Severity: medium.*
- **cp1252 `errors="replace"`:** silent mojibake possible for truly non-cp1252 files. Accepted, documented. *Severity: low.*
- **Memory peak:** 20 MB bytes + ≤100k-row object graph per request; no concurrency limit added. *Severity: low* (matches existing upload pattern).
- **Naive datetime → UTC** assumption may surprise users; documented in design + code comment. *Severity: low.*
- **Coupling to bigquery.py privates (D1):** refactors there break bq_schema; pinned by existing + new tests. *Severity: low.*
- **Frontend/backend regex drift:** pinned by tests both sides (D13). *Severity: low.*

## 6. Verify-at-apply checklist (design agent had no read tools in this runtime)
1. Error-envelope convention in `odoo/routers/bigquery.py` (string vs object `detail`) — D10 defers to it.
2. Existing datasets-listing endpoint path/shape for the destination-step Select.
3. Exact `Tab` union/nav-array shape in `app.ts` and `query-create` file layout to mirror.
4. `MAX_UPLOAD_ROWS` import location and current google-exceptions import style in tests.
5. Whether spec files live beside components or under a `tests/` dir in `odoo-ui`.
