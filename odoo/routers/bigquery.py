import re
from datetime import date, datetime
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from google.cloud.bigquery import LoadJobConfig, SchemaField, WriteDisposition

from auth import require_permission

MAX_UPLOAD_ROWS = 100_000
BQ_QUERY_CHUNK_SIZE = 5_000

from bigquery_client import get_bigquery_client

router = APIRouter(prefix="/bigquery", tags=["bigquery"])

# BigQuery identifiers: letters, digits, underscores; max 1024 chars; must not start with digit.
_IDENTIFIER_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]{0,1023}$")


def _validate_identifier(value: str, label: str) -> None:
    if not value or not _IDENTIFIER_RE.match(value):
        raise HTTPException(
            status_code=400,
            detail=f"Invalid {label} identifier: {value!r}",
        )


@router.get("/datasets")
def list_datasets(user: dict = Depends(require_permission("menu.consultar.programar"))):
    client = get_bigquery_client()
    datasets = list(client.list_datasets())
    return {"datasets": [{"id": d.dataset_id, "project": client.project} for d in datasets]}


@router.get("/tables/{dataset_id}")
def list_tables(dataset_id: str, user: dict = Depends(require_permission("menu.consultar.programar"))):
    _validate_identifier(dataset_id, "dataset")
    client = get_bigquery_client()

    try:
        tables = list(client.list_tables(f"{client.project}.{dataset_id}"))
    except Exception as e:
        raise HTTPException(status_code=404, detail=f"Dataset not found or not accessible: {e}")

    result = []
    for table_item in tables:
        table_ref = f"{client.project}.{dataset_id}.{table_item.table_id}"
        try:
            table = client.get_table(table_ref)
        except Exception as e:
            # Surface a partial-failure indicator in the response.
            result.append({
                "id": table_item.table_id,
                "dataset_id": dataset_id,
                "full_id": table_ref,
                "error": str(e),
            })
            continue
        result.append({
            "id": table_item.table_id,
            "dataset_id": dataset_id,
            "full_id": table_ref,
            "rows": table.num_rows,
            "bytes": table.num_bytes,
            "columns": [
                {"name": f.name, "type": f.field_type, "mode": f.mode}
                for f in table.schema
            ],
        })
    return {"dataset_id": dataset_id, "tables": result}


class BigQueryUploadPayload(BaseModel):
    rows: list[dict[str, Any]]


class BigQueryUploadResponse(BaseModel):
    dataset_id: str
    table_id: str
    rows_loaded: int


# BigQuery type ranking for promotion. Higher index = more permissive.
_BQ_TYPE_RANK = {
    "BOOLEAN": 0,
    "INTEGER": 1,
    "FLOAT": 2,
    "NUMERIC": 3,
    "BIGNUMERIC": 4,
    "TIMESTAMP": 5,
    "DATE": 6,
    "TIME": 7,
    "DATETIME": 8,
    "STRING": 9,
}


def _promote_bq_type(a: str, b: str) -> str:
    """Return the more permissive of two BigQuery types."""
    return a if _BQ_TYPE_RANK.get(a, 0) >= _BQ_TYPE_RANK.get(b, 0) else b


def _infer_bq_schema(rows: list[dict[str, Any]]) -> list[SchemaField]:
    if not rows:
        return []
    # Union of keys across ALL rows, first-seen order (row-0 prefix preserved for determinism)
    seen: dict[str, None] = {}
    for row in rows:
        for key in row.keys():
            if key not in seen:
                _validate_identifier(key, "column")
                seen[key] = None
    schema = []
    for key in seen:
        field_type = _infer_column_type(key, rows)
        schema.append(SchemaField(key, field_type))
    return schema


def _infer_column_type(key: str, rows: list[dict[str, Any]]) -> str:
    """Infer a BigQuery type by scanning all non-None values in a column."""
    inferred: str | None = None
    for row in rows:
        value = row.get(key)
        if value is None:
            continue
        value_type = _infer_field_type(value)
        inferred = value_type if inferred is None else _promote_bq_type(inferred, value_type)
        # STRING is the most permissive; no need to keep scanning.
        if inferred == "STRING":
            break
    return inferred or "STRING"


def _validate_chunk_schema(rows: list[dict[str, Any]], schema: list[SchemaField]) -> None:
    """Reject later chunks that would be silently omitted or type-incompatible."""
    schema_names = {field.name for field in schema}
    chunk_names = {key for row in rows for key in row}
    extra = chunk_names - schema_names
    if extra:
        raise ValueError(
            "Query result schema changed: later chunk contains new columns "
            + ", ".join(sorted(extra))
        )
    for field in schema:
        values = [row.get(field.name) for row in rows if row.get(field.name) is not None]
        if not values:
            continue
        chunk_type = _infer_column_type(field.name, rows)
        if chunk_type != field.field_type:
            raise ValueError(
                f"Query result schema changed: column {field.name!r} "
                f"changed from {field.field_type} to {chunk_type}"
            )


def _infer_field_type(value: Any) -> str:
    if value is None:
        return "STRING"
    if isinstance(value, bool):
        return "BOOLEAN"
    if isinstance(value, int):
        return "INTEGER"
    if isinstance(value, float):
        return "FLOAT"
    if isinstance(value, str):
        return _infer_string_type(value)
    if isinstance(value, datetime):
        return "TIMESTAMP"
    if isinstance(value, date):
        return "DATE"
    return "STRING"


def _infer_string_type(value: str) -> str:
    stripped = value.strip()
    if not stripped:
        return "STRING"
    # ISO 8601 timestamp with optional timezone, e.g. 2024-01-01T12:00:00 or 2024-01-01T12:00:00Z
    if re.match(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d+)?(?:Z|[+-]\d{2}:\d{2})?$", stripped):
        return "TIMESTAMP"
    # ISO 8601 date, e.g. 2024-01-01
    if re.match(r"^\d{4}-\d{2}-\d{2}$", stripped):
        return "DATE"
    # Numeric strings: prefer INTEGER only if no decimal point or exponent.
    if re.match(r"^-?\d+$", stripped):
        return "INTEGER"
    if re.match(r"^-?\d+\.\d+([eE][+-]?\d+)?$", stripped) or re.match(r"^-?\d+[eE][+-]?\d+$", stripped):
        return "FLOAT"
    return "STRING"


def load_rows_to_bigquery(client, dataset_id, table_id, rows, schema, write_disposition=WriteDisposition.WRITE_TRUNCATE):
    """Load one JSON chunk into BigQuery and return the resulting table count."""
    table_ref = f"{client.project}.{dataset_id}.{table_id}"
    job_config = LoadJobConfig(
        write_disposition=write_disposition,
        schema=schema,
        source_format="NEWLINE_DELIMITED_JSON",
    )
    job = client.load_table_from_json(rows, table_ref, job_config=job_config)
    job.result()
    table = client.get_table(table_ref)
    return table.num_rows


def load_query_to_bigquery(query: dict, dataset_id: str, table_id: str, chunk_size: int = BQ_QUERY_CHUNK_SIZE) -> int:
    """Stream a stored Odoo query into BigQuery in bounded chunks.

    The first successful chunk truncates the destination; later chunks append.
    A failed append raises, deliberately leaving the partial table visible rather
    than reporting success. Empty queries do not truncate an existing table.
    """
    from routers.runner import fetch_query_rows

    client = get_bigquery_client()
    offset = 0
    total = 0
    schema = None
    while True:
        rows = fetch_query_rows(query, offset=offset, limit=chunk_size)
        if not rows:
            if total == 0:
                raise ValueError("Query returned no rows; destination was not truncated")
            return total
        normalized = []
        for row in rows:
            normalized.append({k: _exportable_value(row.get(k)) for k in row} if schema is None else {
                f.name: _exportable_value(row.get(f.name)) for f in schema
            })
        if schema is None:
            schema = _infer_bq_schema(normalized)
            if not schema:
                raise ValueError("Could not infer schema from query rows")
        else:
            _validate_chunk_schema(rows, schema)
        load_rows_to_bigquery(
            client, dataset_id, table_id, normalized, schema,
            WriteDisposition.WRITE_TRUNCATE if total == 0 else WriteDisposition.WRITE_APPEND,
        )
        total += len(rows)
        offset += len(rows)
        if len(rows) < chunk_size:
            return total


def _exportable_value(value: Any) -> Any:
    if isinstance(value, (list, dict)):
        import json
        return json.dumps(value, ensure_ascii=False)
    return value


@router.post("/upload-query/{dataset_id}/{table_id}", response_model=BigQueryUploadResponse)
def upload_query_to_bigquery(
    dataset_id: str,
    table_id: str,
    query_name: str,
    origin: str = "manual",
    user: dict = Depends(require_permission("menu.consultar.programar")),
):
    _validate_identifier(dataset_id, "dataset")
    _validate_identifier(table_id, "table")
    from routers.runner import _fetch_registered
    query = _fetch_registered(query_name)
    if not query:
        raise HTTPException(status_code=404, detail=f"Query '{query_name}' not found or inactive")
    try:
        rows_loaded = load_query_to_bigquery(query, dataset_id, table_id)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to load query to BigQuery: {e}")
    try:
        from query_registry import upsert_destination
        upsert_destination(query_name, dataset_id, table_id, origin)
    except Exception:
        pass
    return BigQueryUploadResponse(dataset_id=dataset_id, table_id=table_id, rows_loaded=rows_loaded)


@router.post("/upload/{dataset_id}/{table_id}", response_model=BigQueryUploadResponse)
def upload_to_bigquery(
    dataset_id: str,
    table_id: str,
    payload: BigQueryUploadPayload,
    query_name: str | None = None,
    origin: str = "manual",
    user: dict = Depends(require_permission("menu.consultar.programar")),
):
    _validate_identifier(dataset_id, "dataset")
    _validate_identifier(table_id, "table")

    if not payload.rows:
        raise HTTPException(status_code=400, detail="No rows provided")
    if len(payload.rows) > MAX_UPLOAD_ROWS:
        raise HTTPException(
            status_code=400,
            detail=f"Payload exceeds maximum of {MAX_UPLOAD_ROWS} rows",
        )

    client = get_bigquery_client()
    schema = _infer_bq_schema(payload.rows)
    if not schema:
        raise HTTPException(status_code=400, detail="Could not infer schema from rows")

    try:
        rows_loaded = load_rows_to_bigquery(client, dataset_id, table_id, payload.rows, schema)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to upload rows to BigQuery: {e}")

    # Registry upsert: never fail an upload because of this
    if query_name:
        try:
            from query_registry import upsert_destination
            upsert_destination(query_name, dataset_id, table_id, origin)
        except Exception as e:
            import logging
            logging.getLogger(__name__).warning(
                "Failed to upsert destination for %s.%s (query %s): %s",
                dataset_id, table_id, query_name, e,
            )

    return BigQueryUploadResponse(
        dataset_id=dataset_id,
        table_id=table_id,
        rows_loaded=rows_loaded,
    )
