import re
from datetime import date, datetime
from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from psycopg2 import sql
from psycopg2.extras import execute_values
from google.cloud.bigquery import LoadJobConfig, SchemaField, WriteDisposition

MAX_UPLOAD_ROWS = 100_000

import db
from bigquery_client import get_bigquery_client

router = APIRouter(prefix="/bigquery", tags=["bigquery"])

_BQ_TO_PG_TYPE = {
    "STRING": "TEXT",
    "INTEGER": "BIGINT",
    "FLOAT": "DOUBLE PRECISION",
    "BOOLEAN": "BOOLEAN",
    "DATE": "DATE",
    "TIMESTAMP": "TIMESTAMPTZ",
    "DATETIME": "TIMESTAMP",
    "NUMERIC": "NUMERIC",
    "BIGNUMERIC": "NUMERIC",
    "BYTES": "BYTEA",
    "TIME": "TIME",
}

# BigQuery identifiers: letters, digits, underscores; max 1024 chars; must not start with digit.
_IDENTIFIER_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]{0,1023}$")


def _validate_identifier(value: str, label: str) -> None:
    if not value or not _IDENTIFIER_RE.match(value):
        raise HTTPException(
            status_code=400,
            detail=f"Invalid {label} identifier: {value!r}",
        )


def _sanitize_table_name(dataset_id: str, table_id: str) -> str:
    # BigQuery dataset/table ids cannot contain hyphens or spaces, but sanitize defensively.
    return f"{dataset_id}_{table_id}".lower().replace("-", "_").replace(" ", "_")


def _map_field_type(field) -> str:
    return _BQ_TO_PG_TYPE.get(field.field_type, "TEXT")


@router.get("/datasets")
def list_datasets():
    client = get_bigquery_client()
    datasets = list(client.list_datasets())
    return {"datasets": [{"id": d.dataset_id, "project": client.project} for d in datasets]}


@router.get("/tables/{dataset_id}")
def list_tables(dataset_id: str):
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


class SyncResponse(BaseModel):
    synced: str
    rows: int
    message: str


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
    sample = rows[0]
    schema = []
    for key in sample.keys():
        _validate_identifier(key, "column")
        field_type = _infer_column_type(key, rows)
        schema.append(SchemaField(key, field_type))
    return schema


def _infer_column_type(key: str, rows: list[dict[str, Any]]) -> str:
    """Infer a BigQuery type by scanning all non-None values in a column."""
    inferred = "STRING"  # default when all values are None
    for row in rows:
        value = row.get(key)
        if value is None:
            continue
        value_type = _infer_field_type(value)
        inferred = _promote_bq_type(inferred, value_type)
        # STRING is the most permissive; no need to keep scanning.
        if inferred == "STRING":
            break
    return inferred


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


@router.post("/upload/{dataset_id}/{table_id}", response_model=BigQueryUploadResponse)
def upload_to_bigquery(dataset_id: str, table_id: str, payload: BigQueryUploadPayload):
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
    table_ref = f"{client.project}.{dataset_id}.{table_id}"

    schema = _infer_bq_schema(payload.rows)
    if not schema:
        raise HTTPException(status_code=400, detail="Could not infer schema from rows")

    job_config = LoadJobConfig(
        write_disposition=WriteDisposition.WRITE_TRUNCATE,
        schema=schema,
        source_format="NEWLINE_DELIMITED_JSON",
    )

    try:
        job = client.load_table_from_json(payload.rows, table_ref, job_config=job_config)
        job.result()
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to upload rows to BigQuery: {e}")

    table = client.get_table(table_ref)

    return BigQueryUploadResponse(
        dataset_id=dataset_id,
        table_id=table_id,
        rows_loaded=table.num_rows,
    )


@router.post("/sync/{dataset_id}/{table_id}", response_model=SyncResponse)
def sync_table(dataset_id: str, table_id: str):
    _validate_identifier(dataset_id, "dataset")
    _validate_identifier(table_id, "table")

    client = get_bigquery_client()
    table_ref = f"{client.project}.{dataset_id}.{table_id}"

    try:
        table = client.get_table(table_ref)
    except Exception as e:
        raise HTTPException(status_code=404, detail=f"Table not found or not accessible: {e}")

    pg_table = _sanitize_table_name(dataset_id, table_id)

    columns = [(f.name, _map_field_type(f)) for f in table.schema]
    if not columns:
        raise HTTPException(status_code=400, detail="Table has no columns")

    # Read from BigQuery using a validated TableReference (components already validated).
    try:
        rows_iter = client.list_rows(table.reference)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to read table from BigQuery: {e}")

    pg_table_id = sql.Identifier(pg_table)
    col_ids = [sql.Identifier(name) for name, _ in columns]

    drop_sql = sql.SQL("DROP TABLE IF EXISTS {}").format(pg_table_id)
    create_sql = sql.SQL("CREATE TABLE {} ({})").format(
        pg_table_id,
        sql.SQL(", ").join(
            sql.SQL("{} {}").format(sql.Identifier(name), sql.SQL(pg_type))
            for name, pg_type in columns
        ),
    )

    rows_inserted = 0
    with db.get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(drop_sql)
            cur.execute(create_sql)

            insert_sql = sql.SQL("INSERT INTO {} ({}) VALUES %s").format(
                pg_table_id,
                sql.SQL(", ").join(col_ids),
            )
            values = []
            for row in rows_iter:
                values.append(tuple(getattr(row, name) for name, _ in columns))
                if len(values) >= 1000:
                    execute_values(cur, insert_sql, values, page_size=len(values))
                    rows_inserted += len(values)
                    values = []
            if values:
                execute_values(cur, insert_sql, values, page_size=len(values))
                rows_inserted += len(values)
        conn.commit()

    return SyncResponse(
        synced=pg_table,
        rows=rows_inserted,
        message=f"Synced {rows_inserted} rows into {pg_table}",
    )
