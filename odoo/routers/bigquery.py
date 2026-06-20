import re
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from psycopg2 import sql
from psycopg2.extras import execute_values

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
