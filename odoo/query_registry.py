"""Query destination registry — pure DB helpers, no FastAPI/HTTP imports.

Covers D1/D2 of the editable-queries design.
"""
import json

from db import execute, query as db_query

QUERY_DESTINATIONS_DDL = """
CREATE TABLE IF NOT EXISTS query_destinations (
    id          SERIAL PRIMARY KEY,
    query_name  VARCHAR(100) NOT NULL REFERENCES odoo_queries(name) ON DELETE CASCADE,
    dataset_id  VARCHAR(100) NOT NULL,
    table_id    VARCHAR(100) NOT NULL,
    origin      VARCHAR(20)  NOT NULL DEFAULT 'manual' CHECK (origin IN ('manual', 'schedule')),
    stale       BOOLEAN      NOT NULL DEFAULT FALSE,
    last_error  TEXT,
    last_sync_at TIMESTAMP,
    last_schema  JSONB,
    created_at  TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
    UNIQUE (query_name, dataset_id, table_id)
)
"""


def init_query_destinations():
    execute(QUERY_DESTINATIONS_DDL)


def seed_from_schedules():
    execute(
        """
        INSERT INTO query_destinations (query_name, dataset_id, table_id, origin)
        SELECT DISTINCT s.query_name, s.dataset_id, s.table_id, 'schedule'
        FROM query_schedules s
        JOIN odoo_queries q ON q.name = s.query_name
        ON CONFLICT (query_name, dataset_id, table_id) DO UPDATE
        SET origin = EXCLUDED.origin
        """
    )


def upsert_destination(query_name, dataset_id, table_id, origin="manual"):
    execute(
        """
        INSERT INTO query_destinations (query_name, dataset_id, table_id, origin)
        VALUES (%s, %s, %s, %s)
        ON CONFLICT (query_name, dataset_id, table_id) DO UPDATE
        SET origin = EXCLUDED.origin
        """,
        (query_name, dataset_id, table_id, origin),
    )


def list_destinations(query_name):
    rows = db_query(
        """
        SELECT id, query_name, dataset_id, table_id, origin, stale,
               last_error, last_sync_at, last_schema, created_at
        FROM query_destinations
        WHERE query_name = %s
        ORDER BY created_at
        """,
        (query_name,),
    )
    return rows


def mark_ok(dest_id, schema):
    execute(
        """
        UPDATE query_destinations
        SET stale = FALSE, last_error = NULL, last_sync_at = NOW(), last_schema = %s
        WHERE id = %s
        """,
        (json.dumps(schema) if schema is not None else None, dest_id),
    )


def mark_stale(dest_id, error):
    execute(
        """
        UPDATE query_destinations
        SET stale = TRUE, last_error = %s
        WHERE id = %s
        """,
        (error, dest_id),
    )
