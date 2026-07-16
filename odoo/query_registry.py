"""Query destination registry — config_store backed, no FastAPI/HTTP imports.

Covers D1/D2 of the editable-queries design.
"""
import json

from config_store import get_store

QUERY_DESTINATIONS_SCHEMA = [
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
]


def init_query_destinations():
    """No-op when using config_store; schema is managed by the store implementation."""
    pass


def seed_from_schedules():
    """Seed destinations from active schedules via config_store."""
    return get_store().seed_destinations_from_schedules()


def get_destination(query_name):
    """Return the active destination for a query, or the most recent stale one if no active exists."""
    rows = list_destinations(query_name)
    if not rows:
        return None
    active = [r for r in rows if not r.get("stale")]
    if active:
        return active[0]
    return max(rows, key=lambda r: r.get("created_at") or "")


def mark_other_destinations_stale(query_name, dataset_id, table_id):
    """Mark every destination for query_name except (dataset_id, table_id) as stale."""
    for dest in list_destinations(query_name):
        if dest["dataset_id"] != dataset_id or dest["table_id"] != table_id:
            mark_stale(dest["id"], error="Replaced by schedule destination")


def upsert_destination(query_name, dataset_id, table_id, origin="manual"):
    return get_store().upsert_destination({
        "query_name": query_name,
        "dataset_id": dataset_id,
        "table_id": table_id,
        "origin": origin,
        "stale": False,
        "last_error": None,
        "last_sync_at": None,
        "last_schema": None,
    })


def list_destinations(query_name):
    return get_store().list_destinations(query_name)


def mark_ok(dest_id, schema):
    get_store().mark_destination_ok(dest_id, schema)


def mark_stale(dest_id, error):
    get_store().mark_destination_stale(dest_id, error)


