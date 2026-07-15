"""Tests for query_registry module (editable-queries WU1).

Covers spec requirements: Query Destination Registry (R-CAT-4).
"""
import pytest

from db import execute as pg_execute, query as pg_query
import init_db


def _cols(table: str) -> set[str]:
    rows = pg_query(
        "SELECT column_name FROM information_schema.columns WHERE table_name = %s", (table,)
    )
    return {r["column_name"] for r in rows}


def _table_exists(table: str) -> bool:
    rows = pg_query(
        "SELECT 1 AS ok FROM information_schema.tables WHERE table_name = %s", (table,)
    )
    return bool(rows)


def _count(table: str) -> int:
    rows = pg_query(f"SELECT COUNT(*) AS n FROM {table}")
    return rows[0]["n"]


def test_init_creates_query_destinations():
    init_db.init()
    assert _table_exists("query_destinations")
    assert {
        "id",
        "query_name",
        "dataset_id",
        "table_id",
        "origin",
        "stale",
        "last_error",
        "last_sync_at",
        "last_schema",
        "created_at",
    } <= _cols("query_destinations")


def test_init_is_idempotent_for_destinations():
    init_db.init()
    count_before = _count("query_destinations")
    init_db.init()
    count_after = _count("query_destinations")
    assert count_before == count_after


def test_init_seeds_from_query_schedules():
    """Seed inserts distinct (query_name, dataset_id, table_id) from query_schedules."""
    init_db.init()
    # Clean slate: remove any pre-existing destinations for our test query
    pg_execute("DELETE FROM query_destinations WHERE query_name = %s", ("t_seed_query",))
    # Also remove any pre-existing schedule with same PK (name is PK on query_schedules)
    pg_execute("DELETE FROM query_schedules WHERE name = %s", ("t_seed_sched",))
    # Seed a schedule row
    pg_execute(
        """
        INSERT INTO odoo_queries (name, description, model, method, domain, fields, limit_val)
        VALUES (%s, '', 'res.partner', 'search_read', '[]'::jsonb, '[]'::jsonb, 100)
        """,
        ("t_seed_query",),
    )
    pg_execute(
        """
        INSERT INTO query_schedules (name, query_name, dataset_id, table_id, frequency, hour, minute)
        VALUES (%s, %s, %s, %s, 'daily', 0, 0)
        """,
        ("t_seed_sched", "t_seed_query", "t_dataset", "t_table"),
    )
    # Re-init should seed the registry
    init_db.init()
    rows = pg_query(
        "SELECT * FROM query_destinations WHERE query_name = %s",
        ("t_seed_query",),
    )
    assert len(rows) == 1
    assert rows[0]["dataset_id"] == "t_dataset"
    assert rows[0]["table_id"] == "t_table"
    assert rows[0]["origin"] == "schedule"
    assert rows[0]["stale"] is False


def test_seed_is_idempotent():
    init_db.init()
    pg_execute(
        """
        INSERT INTO query_schedules (name, query_name, dataset_id, table_id, frequency, hour, minute)
        VALUES (%s, %s, %s, %s, 'daily', 0, 0)
        """,
        ("t_seed_idem", "t_seed_q2", "t_ds2", "t_t2"),
    )
    init_db.init()
    count1 = _count("query_destinations")
    init_db.init()
    count2 = _count("query_destinations")
    assert count1 == count2


def test_upsert_destination_insert():
    from query_registry import upsert_destination

    init_db.init()
    # Need a query row to satisfy FK
    pg_execute(
        """
        INSERT INTO odoo_queries (name, description, model, method, domain, fields, limit_val)
        VALUES (%s, '', 'res.partner', 'search_read', '[]'::jsonb, '[]'::jsonb, 100)
        """,
        ("t_upsert_q",),
    )
    upsert_destination("t_upsert_q", "ds1", "tbl1", "manual")
    rows = pg_query(
        "SELECT * FROM query_destinations WHERE query_name = %s",
        ("t_upsert_q",),
    )
    assert len(rows) == 1
    assert rows[0]["dataset_id"] == "ds1"
    assert rows[0]["origin"] == "manual"


def test_upsert_destination_update_origin():
    from query_registry import upsert_destination

    init_db.init()
    pg_execute(
        """
        INSERT INTO odoo_queries (name, description, model, method, domain, fields, limit_val)
        VALUES (%s, '', 'res.partner', 'search_read', '[]'::jsonb, '[]'::jsonb, 100)
        """,
        ("t_upsert_flip",),
    )
    upsert_destination("t_upsert_flip", "ds1", "tbl1", "manual")
    upsert_destination("t_upsert_flip", "ds1", "tbl1", "schedule")
    rows = pg_query(
        "SELECT * FROM query_destinations WHERE query_name = %s",
        ("t_upsert_flip",),
    )
    assert len(rows) == 1
    assert rows[0]["origin"] == "schedule"


def test_list_destinations():
    from query_registry import list_destinations, upsert_destination

    init_db.init()
    pg_execute(
        """
        INSERT INTO odoo_queries (name, description, model, method, domain, fields, limit_val)
        VALUES (%s, '', 'res.partner', 'search_read', '[]'::jsonb, '[]'::jsonb, 100)
        """,
        ("t_list_q",),
    )
    upsert_destination("t_list_q", "ds1", "tbl1", "manual")
    upsert_destination("t_list_q", "ds2", "tbl2", "schedule")
    rows = list_destinations("t_list_q")
    assert len(rows) == 2
    datasets = {r["dataset_id"] for r in rows}
    assert datasets == {"ds1", "ds2"}


def test_list_destinations_unknown_query():
    from query_registry import list_destinations

    init_db.init()
    rows = list_destinations("t_noexist")
    assert rows == []


def test_mark_ok_and_stale():
    from query_registry import upsert_destination, mark_ok, mark_stale

    init_db.init()
    pg_execute(
        """
        INSERT INTO odoo_queries (name, description, model, method, domain, fields, limit_val)
        VALUES (%s, '', 'res.partner', 'search_read', '[]'::jsonb, '[]'::jsonb, 100)
        """,
        ("t_mark_q",),
    )
    upsert_destination("t_mark_q", "ds1", "tbl1", "manual")
    row = pg_query(
        "SELECT id FROM query_destinations WHERE query_name = %s",
        ("t_mark_q",),
    )[0]
    dest_id = row["id"]

    mark_stale(dest_id, "connection error")
    row = pg_query(
        "SELECT stale, last_error FROM query_destinations WHERE id = %s",
        (dest_id,),
    )[0]
    assert row["stale"] is True
    assert row["last_error"] == "connection error"

    schema = [{"name": "col1", "type": "STRING"}]
    mark_ok(dest_id, schema)
    row = pg_query(
        "SELECT stale, last_error, last_schema FROM query_destinations WHERE id = %s",
        (dest_id,),
    )[0]
    assert row["stale"] is False
    assert row["last_error"] is None
    assert row["last_schema"] == schema


def test_seed_with_zero_schedules():
    """Seeding when query_schedules has no matching rows is a no-op."""
    init_db.init()
    # Ensure no t_* schedules exist
    pg_execute("DELETE FROM query_schedules WHERE name LIKE 't\\_%' ESCAPE '\\'")
    pg_execute("DELETE FROM query_destinations WHERE query_name LIKE 't\\_%' ESCAPE '\\'")
    count_before = _count("query_destinations")
    init_db.init()
    count_after = _count("query_destinations")
    assert count_before == count_after


def test_fk_cascade_on_delete():
    """Deleting an odoo_queries row should cascade to its destinations."""
    from query_registry import upsert_destination

    init_db.init()
    pg_execute(
        """
        INSERT INTO odoo_queries (name, description, model, method, domain, fields, limit_val)
        VALUES (%s, '', 'res.partner', 'search_read', '[]'::jsonb, '[]'::jsonb, 100)
        """,
        ("t_cascade_q",),
    )
    upsert_destination("t_cascade_q", "ds1", "tbl1", "manual")
    pg_execute("DELETE FROM odoo_queries WHERE name = %s", ("t_cascade_q",))
    rows = pg_query(
        "SELECT * FROM query_destinations WHERE query_name = %s",
        ("t_cascade_q",),
    )
    assert rows == []
