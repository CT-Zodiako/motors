"""Group 1 — migration tests (query-categories change).

Covers spec `query-catalog` requirements: Query Category Storage, Protected Default Category.
All tests must pass after init_db.init() gains the four idempotent migration steps.
"""
import uuid

from db import execute as pg_execute, query as pg_query
import init_db


def _cols(table: str) -> set[str]:
    rows = pg_query(
        "SELECT column_name FROM information_schema.columns WHERE table_name = %s", (table,)
    )
    return {r["column_name"] for r in rows}


def test_init_is_idempotent():
    init_db.init()
    init_db.init()  # second run MUST NOT raise


def test_query_categories_table_exists():
    init_db.init()
    assert {"id", "name", "description", "created_at"} <= _cols("query_categories")


def test_odoo_queries_has_category_id_fk():
    init_db.init()
    assert "category_id" in _cols("odoo_queries")
    fks = pg_query(
        """
        SELECT ccu.table_name AS ref_table, ccu.column_name AS ref_col
        FROM information_schema.table_constraints tc
        JOIN information_schema.constraint_column_usage ccu
          ON ccu.constraint_name = tc.constraint_name
        JOIN information_schema.key_column_usage kcu
          ON kcu.constraint_name = tc.constraint_name
        WHERE tc.constraint_type = 'FOREIGN KEY'
          AND tc.table_name = 'odoo_queries'
          AND kcu.column_name = 'category_id'
        """
    )
    assert fks and fks[0]["ref_table"] == "query_categories"


def test_general_category_seeded_once():
    init_db.init()
    init_db.init()
    rows = pg_query("SELECT id FROM query_categories WHERE name = 'General'")
    assert len(rows) == 1


def test_backfill_assigns_general_to_null_categories():
    init_db.init()
    name = f"t_orphan_{uuid.uuid4().hex[:8]}"
    pg_execute(
        """
        INSERT INTO odoo_queries (name, description, model, method, domain, fields, limit_val, category_id)
        VALUES (%s, '', 'res.partner', 'search_read', '[]'::jsonb, '[]'::jsonb, 100, NULL)
        """,
        (name,),
    )
    init_db.init()  # migration MUST backfill pre-existing uncategorized rows
    rows = pg_query(
        """
        SELECT c.name AS category
        FROM odoo_queries q JOIN query_categories c ON c.id = q.category_id
        WHERE q.name = %s
        """,
        (name,),
    )
    assert rows and rows[0]["category"] == "General"


def test_backfill_covers_inactive_queries():
    init_db.init()
    name = f"t_inactive_{uuid.uuid4().hex[:8]}"
    pg_execute(
        """
        INSERT INTO odoo_queries (name, description, model, method, domain, fields, limit_val, active, category_id)
        VALUES (%s, '', 'res.partner', 'search_read', '[]'::jsonb, '[]'::jsonb, 100, FALSE, NULL)
        """,
        (name,),
    )
    init_db.init()
    rows = pg_query(
        "SELECT category_id FROM odoo_queries WHERE name = %s", (name,)
    )
    assert rows and rows[0]["category_id"] is not None
