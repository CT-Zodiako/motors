"""File-upload ingestion endpoints (change: file-to-bigquery).

Stateless three-step API (spec R1): every call carries the complete file;
the server holds nothing between steps and uploaded bytes never touch disk
(spec R3) — extraction runs fully in memory via bq_schema.

PR2 scope: inspect + preview. The load endpoint lands in PR3.
"""
from datetime import date, datetime, time

from fastapi import APIRouter, File, Form, HTTPException, UploadFile

import bq_schema
from routers.bigquery import MAX_UPLOAD_ROWS

router = APIRouter(prefix="/bigquery/upload-file", tags=["file-upload"])

MAX_UPLOAD_FILE_BYTES = 20 * 1024 * 1024  # 20 MB (design D2)

_SOURCE_TYPES = {"xlsx", "csv"}
_OLE2_MAGIC = b"\xd0\xcf\x11\xe0"  # legacy .xls signature
_PREVIEW_SAMPLE_ROWS = 100  # spec R5


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


def _extract_or_400(content: bytes, source_type: str, sheet: str | None):
    """Map bq_schema.ExtractionError to HTTP 400 (repo convention: string detail)."""
    try:
        if source_type == "csv":
            return bq_schema.extract_csv(content)
        return bq_schema.extract_xlsx(content, sheet)
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


@router.post("/inspect")
async def inspect_file(
    file: UploadFile = File(...),
    source_type: str = Form(..., alias="sourceType"),
):
    content = await _read_source(file, source_type)
    if source_type == "csv":
        # CSV has a single pseudo-sheet; validate it parses and enforce the row
        # cap here so malformed files fail at the first wizard step.
        table = _extract_or_400(content, "csv", None)
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
):
    content = await _read_source(file, source_type)
    if source_type == "xlsx" and sheet is None:
        # Default to the first sheet (design D10).
        sheet_names = _extract_or_400(content, "xlsx", None)
        if not sheet_names:
            raise HTTPException(status_code=400, detail="Workbook has no sheets")
        sheet = sheet_names[0]
    table = _extract_or_400(content, source_type, sheet)
    _check_row_cap(len(table.rows))
    if not table.headers:
        raise HTTPException(status_code=400, detail="Sheet has no header row")

    used: set[str] = set()
    columns = []
    for idx, header in enumerate(table.headers):
        # Headers may arrive as non-strings from xlsx cells; normalize once at
        # the boundary so `source` is stable for the load-step decisions (PR3).
        source = "" if header is None else str(header)
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
