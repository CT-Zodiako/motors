"""Synchronous propagation of query edits to registered BigQuery destinations."""
import json
from routers import runner, bigquery
from bigquery_client import get_bigquery_client
import query_registry


def propagate_query_edit(query: dict) -> dict:
    """Re-run `query` against Odoo and reload every registered BQ destination.

    Returns a report dict: {total, ok, failed, destinations:[{dataset_id, table_id, status, error?}]}.
    - status 'ok'    : destination reloaded successfully.
    - status 'failed': load or other error (destination marked stale).
    - status 'empty' : Odoo returned zero rows (no truncate, marked stale).
    The edit itself is the caller's responsibility; this only propagates.
    """
    # Normalize JSONB strings to native Python structures
    domain = query.get("domain", [])
    if isinstance(domain, str):
        domain = json.loads(domain)
    fields = query.get("fields", [])
    if isinstance(fields, str):
        fields = json.loads(fields)

    # Build a normalized query dict for fetch_query_rows
    normalized_query = {
        "name": query.get("name", ""),
        "model": query["model"],
        "method": query["method"],
        "domain": domain,
        "fields": fields,
        "limit_val": query.get("limit_val"),
    }

    destinations = query_registry.list_destinations(normalized_query["name"])

    if not destinations:
        return {"total": 0, "ok": 0, "failed": 0, "destinations": []}

    # Fetch once from Odoo
    try:
        rows = runner.fetch_query_rows(normalized_query)
    except Exception as e:
        error_msg = str(e)
        for dest in destinations:
            query_registry.mark_stale(dest["id"], error_msg)
        return {
            "total": len(destinations),
            "ok": 0,
            "failed": len(destinations),
            "destinations": [
                {
                    "dataset_id": dest["dataset_id"],
                    "table_id": dest["table_id"],
                    "status": "failed",
                    "error": error_msg,
                }
                for dest in destinations
            ],
        }

    if not rows:
        # Empty result → do NOT truncate (user-ratified D9)
        for dest in destinations:
            query_registry.mark_stale(dest["id"], "Empty result set — table not truncated")
        return {
            "total": len(destinations),
            "ok": 0,
            "failed": len(destinations),
            "destinations": [
                {
                    "dataset_id": dest["dataset_id"],
                    "table_id": dest["table_id"],
                    "status": "empty",
                }
                for dest in destinations
            ],
        }

    schema = bigquery._infer_bq_schema(rows)
    client = get_bigquery_client()

    report_destinations = []
    ok_count = 0
    failed_count = 0

    for dest in destinations:
        try:
            bigquery.load_rows_to_bigquery(
                client,
                dest["dataset_id"],
                dest["table_id"],
                rows,
                schema,
            )
            query_registry.mark_ok(dest["id"], [{"name": f.name, "type": f.field_type} for f in schema])
            report_destinations.append(
                {
                    "dataset_id": dest["dataset_id"],
                    "table_id": dest["table_id"],
                    "status": "ok",
                }
            )
            ok_count += 1
        except Exception as e:
            error_msg = str(e)
            query_registry.mark_stale(dest["id"], error_msg)
            report_destinations.append(
                {
                    "dataset_id": dest["dataset_id"],
                    "table_id": dest["table_id"],
                    "status": "failed",
                    "error": error_msg,
                }
            )
            failed_count += 1

    return {
        "total": len(destinations),
        "ok": ok_count,
        "failed": failed_count,
        "destinations": report_destinations,
    }
