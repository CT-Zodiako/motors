"""File-upload ingestion endpoints (change: file-to-bigquery).

Stateless three-step API (spec R1): every call carries the complete file;
the server holds nothing between steps and uploaded bytes never touch disk
(spec R3) — extraction runs fully in memory via bq_schema.

PR2 scope: inspect + preview. PR3 adds the load endpoint.
"""
import json
from datetime import date, datetime, time

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from google.api_core.exceptions import Conflict, NotFound
from google.cloud.bigquery import LoadJobConfig, SchemaField, Table, WriteDisposition

import bq_schema
from auth import require_permission
from bigquery_client import get_bigquery_client
from routers.bigquery import MAX_UPLOAD_ROWS, _validate_identifier

router = APIRouter(prefix="/bigquery/upload-file", tags=["file-upload"])

MAX_UPLOAD_FILE_BYTES = 20 * 1024 * 1024  # 20 MB (design D2)

_SOURCE_TYPES = {"xlsx", "csv"}
_OLE2_MAGIC = b"\xd0\xcf\x11\xe0"  # legacy .xls signature
_PREVIEW_SAMPLE_ROWS = 100  # spec R5
_BQ_TYPES = {"INT64", "FLOAT64", "BOOL", "DATE", "TIMESTAMP", "STRING"}  # spec R5


async def _read_source(file: UploadFile, source_type: str) -> bytes:
    """Shared upload validation (D11): sourceType, extension, size, OLE2 sniff."""
    if source_type not in _SOURCE_TYPES:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid sourceType {source_type!r}: expected 'xlsx' or 'csv'",
        )
    filename = file.filename or ""
    ext = filename.rsplit(".", 1)[-1].lower() if "." in filename else ""
    if ext == "xls":
        raise HTTPException(
            status_code=415,
            detail="Legacy .xls files are not supported; save the file as .xlsx",
        )
    if ext in _SOURCE_TYPES and ext != source_type:
        raise HTTPException(
            status_code=400,
            detail=f"File extension '.{ext}' does not match sourceType '{source_type}'",
        )
    if ext not in _SOURCE_TYPES:
        raise HTTPException(
            status_code=415,
            detail=f"Unsupported file type '.{ext}'; accepted formats: .xlsx, .csv",
        )
    content = await file.read(MAX_UPLOAD_FILE_BYTES + 1)
    if len(content) > MAX_UPLOAD_FILE_BYTES:
        limit_mb = MAX_UPLOAD_FILE_BYTES // (1024 * 1024)
        raise HTTPException(
            status_code=413,
            detail=f"File exceeds the {limit_mb} MB upload limit",
        )
    if content[:4] == _OLE2_MAGIC:
        raise HTTPException(
            status_code=415,
            detail="Legacy .xls files are not supported; save the file as .xlsx",
        )
    return content


def _extract_or_400(content: bytes, source_type: str, sheet: str | None, skip_rows: int = 0):
    """Map bq_schema.ExtractionError to HTTP 400 (repo convention: string detail)."""
    try:
        if source_type == "csv":
            return bq_schema.extract_csv(content, skip_rows=skip_rows)
        return bq_schema.extract_xlsx(content, sheet, skip_rows=skip_rows)
    except bq_schema.ExtractionError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e


def _check_row_cap(row_count: int) -> None:
    if row_count > MAX_UPLOAD_ROWS:
        raise HTTPException(
            status_code=413,
            detail=f"Sheet has {row_count} data rows; the maximum is {MAX_UPLOAD_ROWS}",
        )


def _jsonable(value):
    """Serialize preview sample values (dates/times as ISO strings)."""
    if isinstance(value, (date, datetime, time)):
        return value.isoformat()
    return value


def _normalize_headers(headers: list) -> list[str]:
    """String-normalize raw extracted headers (xlsx cells may be non-strings).

    Same normalization preview applies to its `source` field, so load-time
    decision sync compares like with like.
    """
    return ["" if h is None else str(h) for h in headers]


def _parse_decisions(raw: str, headers: list[str]) -> list[dict]:
    """Validate the per-column schema decisions against the extracted headers.

    Follows the D10 order: parse -> sync with headers -> closed-set types ->
    >=1 included -> valid names -> no case-insensitive duplicates. Every
    failure is a 400 raised BEFORE any BigQuery interaction.
    Returns normalized decisions (included columns get a concrete name).
    """
    try:
        decisions = json.loads(raw)
    except (json.JSONDecodeError, TypeError) as e:
        raise HTTPException(status_code=400, detail=f"Invalid decisions payload: {e}")
    if not isinstance(decisions, list):
        raise HTTPException(status_code=400, detail="decisions must be a JSON array")
    if len(decisions) != len(headers) or any(
        not isinstance(d, dict) or d.get("source") != headers[i]
        for i, d in enumerate(decisions)
    ):
        raise HTTPException(
            status_code=400,
            detail="decisions out of sync with the file headers; run preview again",
        )

    normalized = []
    for d in decisions:
        col_type = d.get("type")
        if col_type is not None and col_type not in _BQ_TYPES:
            raise HTTPException(
                status_code=400,
                detail=f"Invalid column type {col_type!r}; allowed: {sorted(_BQ_TYPES)}",
            )
        normalized.append({
            "source": d["source"],
            "name": d.get("name"),
            "type": col_type,
            "included": bool(d.get("included", True)),
        })

    included = [d for d in normalized if d["included"]]
    if not included:
        raise HTTPException(status_code=400, detail="At least one column must be included")

    used: set[str] = set()
    for d in included:
        if d["name"] is None:
            d["name"] = bq_schema.sanitize_column_name(d["source"], used)
            continue
        _validate_identifier(d["name"], "column")
        lowered = d["name"].lower()
        if lowered in used:
            raise HTTPException(
                status_code=400,
                detail=f"Duplicate column name after rename: {d['name']!r}",
            )
        used.add(lowered)
    return normalized


def _sheet_or_default(content: bytes, source_type: str, sheet: str | None) -> str | None:
    """Resolve the sheet for extraction; xlsx defaults to the first sheet (D10)."""
    if source_type == "csv" or sheet is not None:
        return sheet
    sheet_names = _extract_or_400(content, "xlsx", None)
    if not sheet_names:
        raise HTTPException(status_code=400, detail="Workbook has no sheets")
    return sheet_names[0]


@router.post("/inspect")
async def inspect_file(
    file: UploadFile = File(...),
    source_type: str = Form(..., alias="sourceType"),
    skip_rows: int = Form(0, alias="skipRows"),
    user: dict = Depends(require_permission("menu.cargar.upload")),
):
    if skip_rows < 0:
        raise HTTPException(status_code=400, detail=f"skipRows must be >= 0, got {skip_rows}")
    content = await _read_source(file, source_type)
    if source_type == "csv":
        # CSV has a single pseudo-sheet; validate it parses and enforce the row
        # cap here so malformed files fail at the first wizard step.
        table = _extract_or_400(content, "csv", None, skip_rows)
        _check_row_cap(len(table.rows))
        sheets = [bq_schema.CSV_SHEET_NAME]
    else:
        # xlsx: sheet names only — no row scan at inspect (design D10).
        sheets = _extract_or_400(content, "xlsx", None)
    return {
        "sourceType": source_type,
        "fileName": file.filename or "",
        "sizeBytes": len(content),
        "sheets": sheets,
        "sheetCount": len(sheets),
    }


@router.post("/preview")
async def preview_file(
    file: UploadFile = File(...),
    source_type: str = Form(..., alias="sourceType"),
    sheet: str | None = Form(None),
    skip_rows: int = Form(0, alias="skipRows"),
    user: dict = Depends(require_permission("menu.cargar.upload")),
):
    if skip_rows < 0:
        raise HTTPException(status_code=400, detail=f"skipRows must be >= 0, got {skip_rows}")
    content = await _read_source(file, source_type)
    sheet = _sheet_or_default(content, source_type, sheet)
    table = _extract_or_400(content, source_type, sheet, skip_rows)
    _check_row_cap(len(table.rows))
    if not table.headers:
        raise HTTPException(status_code=400, detail="Sheet has no header row")

    used: set[str] = set()
    columns = []
    for idx, source in enumerate(_normalize_headers(table.headers)):
        name = bq_schema.sanitize_column_name(source, used)
        values = [row[idx] for row in table.rows]
        col_type = bq_schema.infer_column_type(values)
        columns.append({"source": source, "name": name, "type": col_type, "included": True})

    sample = [[_jsonable(v) for v in row] for row in table.rows[:_PREVIEW_SAMPLE_ROWS]]
    return {
        "sheet": table.sheet_name,
        "columns": columns,
        "sample": sample,
        "totalRows": len(table.rows),
    }


@router.post("/load")
async def load_file(
    file: UploadFile = File(...),
    source_type: str = Form(..., alias="sourceType"),
    sheet: str | None = Form(None),
    decisions: str = Form(...),
    dataset: str = Form(...),
    table: str = Form(...),
    skip_rows: int = Form(0, alias="skipRows"),
    user: dict = Depends(require_permission("menu.cargar.upload")),
):
    if skip_rows < 0:
        raise HTTPException(status_code=400, detail=f"skipRows must be >= 0, got {skip_rows}")
    content = await _read_source(file, source_type)
    sheet = _sheet_or_default(content, source_type, sheet)
    extracted = _extract_or_400(content, source_type, sheet, skip_rows)
    _check_row_cap(len(extracted.rows))
    if not extracted.headers:
        raise HTTPException(status_code=400, detail="Sheet has no header row")
    headers = _normalize_headers(extracted.headers)

    parsed = _parse_decisions(decisions, headers)
    _validate_identifier(dataset, "dataset")
    _validate_identifier(table, "table")

    if not extracted.rows:
        raise HTTPException(status_code=400, detail="No data rows to load")

    included = [d for d in parsed if d["included"]]

    # Convert ALL rows to the approved schema BEFORE any BigQuery call (D7/D9):
    # a conversion failure is a 400 with zero BQ interaction by construction.
    col_index = {d["source"]: i for i, d in enumerate(parsed)}
    for d in included:
        if d["type"] is None:
            idx = col_index[d["source"]]
            d["type"] = bq_schema.infer_column_type([row[idx] for row in extracted.rows])
    converted_rows = []
    for row_idx, row in enumerate(extracted.rows, start=1):
        converted = {}
        for d in included:
            idx = col_index[d["source"]]
            try:
                converted[d["name"]] = bq_schema.convert_value(
                    row[idx], d["type"], column_name=d["name"], row_number=row_idx
                )
            except bq_schema.ConversionError as e:
                raise HTTPException(status_code=400, detail=str(e)) from e
        converted_rows.append(converted)

    client = get_bigquery_client()
    try:
        client.get_dataset(f"{client.project}.{dataset}")
    except NotFound:
        raise HTTPException(status_code=404, detail=f"Dataset not found: {dataset!r}")

    table_ref = f"{client.project}.{dataset}.{table}"
    try:
        client.get_table(table_ref)
    except NotFound:
        pass
    else:
        raise HTTPException(
            status_code=409,
            detail=f"Table already exists: {table_ref}. Choose another name.",
        )

    schema = [SchemaField(d["name"], d["type"], "NULLABLE") for d in included]
    try:
        client.create_table(Table(table_ref, schema=schema))
    except Conflict:
        # TOCTOU race: the table appeared between the pre-check and create.
        raise HTTPException(
            status_code=409,
            detail=f"Table already exists: {table_ref}. Choose another name.",
        )

    job_config = LoadJobConfig(
        schema=schema,
        write_disposition=WriteDisposition.WRITE_EMPTY,
        source_format="NEWLINE_DELIMITED_JSON",
    )
    try:
        job = client.load_table_from_json(converted_rows, table_ref, job_config=job_config)
        job.result()
    except Exception as e:
        # R12: drop the partially created table so a corrected retry does not 409.
        try:
            client.delete_table(table_ref, not_found_ok=True)
            cleanup_msg = "partial table dropped"
        except Exception:
            cleanup_msg = f"cleanup failed; drop {table_ref} manually"
        raise HTTPException(
            status_code=502,
            detail=f"BigQuery load job failed: {e}. {cleanup_msg}",
        ) from e

    rows_loaded = getattr(job, "output_rows", None)
    if rows_loaded is None:
        rows_loaded = len(converted_rows)
    return {"table": table_ref, "rows": rows_loaded}
