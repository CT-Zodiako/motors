"""Codecs: single source of truth for table schemas and row serialization.

TABLE_SCHEMAS maps each table to its BigQuery-native column definitions,
derived from the original init_db.py DDL (V1) and query_registry.init_query_destinations().
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any

# ---------------------------------------------------------------------------
# Schema definitions — one source of truth for bootstrap, BQ store, memory store
# ---------------------------------------------------------------------------
TABLE_SCHEMAS: dict[str, list[dict[str, Any]]] = {
    "odoo_queries": [
        {"name": "id", "type": "INT64", "mode": "REQUIRED"},
        {"name": "name", "type": "STRING", "mode": "REQUIRED"},
        {"name": "description", "type": "STRING", "mode": "NULLABLE"},
        {"name": "model", "type": "STRING", "mode": "REQUIRED"},
        {"name": "method", "type": "STRING", "mode": "REQUIRED"},
        {"name": "domain", "type": "JSON", "mode": "REQUIRED"},
        {"name": "fields", "type": "JSON", "mode": "REQUIRED"},
        {"name": "limit_val", "type": "INT64", "mode": "REQUIRED"},
        {"name": "active", "type": "BOOL", "mode": "REQUIRED"},
        {"name": "created_at", "type": "TIMESTAMP", "mode": "REQUIRED"},
        {"name": "category_id", "type": "INT64", "mode": "NULLABLE"},
    ],
    "query_schedules": [
        {"name": "id", "type": "INT64", "mode": "REQUIRED"},
        {"name": "name", "type": "STRING", "mode": "REQUIRED"},
        {"name": "query_name", "type": "STRING", "mode": "REQUIRED"},
        {"name": "dataset_id", "type": "STRING", "mode": "REQUIRED"},
        {"name": "table_id", "type": "STRING", "mode": "REQUIRED"},
        {"name": "frequency", "type": "STRING", "mode": "REQUIRED"},
        {"name": "hour", "type": "INT64", "mode": "NULLABLE"},
        {"name": "minute", "type": "INT64", "mode": "NULLABLE"},
        {"name": "day_of_week", "type": "INT64", "mode": "NULLABLE"},
        {"name": "day_of_month", "type": "INT64", "mode": "NULLABLE"},
        {"name": "interval_hours", "type": "INT64", "mode": "NULLABLE"},
        {"name": "active", "type": "BOOL", "mode": "REQUIRED"},
        {"name": "last_run_at", "type": "TIMESTAMP", "mode": "NULLABLE"},
        {"name": "last_run_status", "type": "STRING", "mode": "NULLABLE"},
        {"name": "last_run_message", "type": "STRING", "mode": "NULLABLE"},
        {"name": "created_at", "type": "TIMESTAMP", "mode": "REQUIRED"},
    ],
    "query_schedule_runs": [
        {"name": "id", "type": "INT64", "mode": "REQUIRED"},
        {"name": "schedule_id", "type": "INT64", "mode": "REQUIRED"},
        {"name": "started_at", "type": "TIMESTAMP", "mode": "REQUIRED"},
        {"name": "finished_at", "type": "TIMESTAMP", "mode": "NULLABLE"},
        {"name": "status", "type": "STRING", "mode": "REQUIRED"},
        {"name": "message", "type": "STRING", "mode": "NULLABLE"},
        {"name": "rows_loaded", "type": "INT64", "mode": "NULLABLE"},
    ],
    "query_categories": [
        {"name": "id", "type": "INT64", "mode": "REQUIRED"},
        {"name": "name", "type": "STRING", "mode": "REQUIRED"},
        {"name": "description", "type": "STRING", "mode": "NULLABLE"},
        {"name": "created_at", "type": "TIMESTAMP", "mode": "REQUIRED"},
    ],
    "query_destinations": [
        {"name": "id", "type": "INT64", "mode": "REQUIRED"},
        {"name": "query_name", "type": "STRING", "mode": "REQUIRED"},
        {"name": "dataset_id", "type": "STRING", "mode": "REQUIRED"},
        {"name": "table_id", "type": "STRING", "mode": "REQUIRED"},
        {"name": "origin", "type": "STRING", "mode": "NULLABLE"},
        {"name": "stale", "type": "BOOL", "mode": "NULLABLE"},
        {"name": "last_error", "type": "STRING", "mode": "NULLABLE"},
        {"name": "last_sync_at", "type": "TIMESTAMP", "mode": "NULLABLE"},
        {"name": "last_schema", "type": "JSON", "mode": "NULLABLE"},
        {"name": "created_at", "type": "TIMESTAMP", "mode": "REQUIRED"},
    ],
}

# ---------------------------------------------------------------------------
# Row codecs
# ---------------------------------------------------------------------------

def _to_bq_value(table: str, col_name: str, value: Any) -> Any:
    """Serialize a Python value to the BQ-native representation."""
    if value is None:
        return None
    col = _col_def(table, col_name)
    bq_type = col["type"]
    if bq_type == "JSON":
        return json.dumps(value, separators=(",", ":"), ensure_ascii=False)
    if bq_type == "TIMESTAMP":
        if isinstance(value, datetime):
            # Normalize to UTC, strip tzinfo for BQ load
            if value.tzinfo is not None:
                value = value.astimezone(timezone.utc).replace(tzinfo=None)
            return value.isoformat(sep=" ", timespec="microseconds")
        return value
    if bq_type == "BOOL":
        return bool(value)
    if bq_type == "INT64":
        return int(value)
    return str(value)


def _from_bq_value(table: str, col_name: str, value: Any) -> Any:
    """Deserialize a BQ-native value to Python."""
    if value is None:
        return None
    col = _col_def(table, col_name)
    bq_type = col["type"]
    if bq_type == "JSON":
        if isinstance(value, str):
            return json.loads(value)
        return value
    if bq_type == "TIMESTAMP":
        if isinstance(value, str):
            # Parse ISO-like string, return naive UTC datetime
            return datetime.fromisoformat(value.replace(" ", "T"))
        if isinstance(value, datetime):
            return value.replace(tzinfo=None) if value.tzinfo else value
        return value
    if bq_type == "BOOL":
        return bool(value)
    if bq_type == "INT64":
        return int(value)
    return str(value)


def _col_def(table: str, col_name: str) -> dict:
    for c in TABLE_SCHEMAS[table]:
        if c["name"] == col_name:
            return c
    raise KeyError(f"Column {col_name} not in {table}")


def encode_row(table: str, row: dict[str, Any]) -> dict[str, Any]:
    """Encode a Python dict row to BQ-native values (for NDJSON load or params)."""
    return {k: _to_bq_value(table, k, v) for k, v in row.items()}


def decode_row(table: str, row: dict[str, Any]) -> dict[str, Any]:
    """Decode a BQ-native row (from query result or load) to Python."""
    return {k: _from_bq_value(table, k, v) for k, v in row.items()}
