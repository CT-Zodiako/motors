from db import query as pg_query
from odoo_client import execute as odoo_execute


def get_registered_query(name: str) -> dict | None:
    rows = pg_query(
        "SELECT * FROM odoo_queries WHERE name = %s AND active = TRUE",
        (name,),
    )
    return rows[0] if rows else None


def run_query(name: str) -> list[dict]:
    registered = get_registered_query(name)
    if not registered:
        return None

    return odoo_execute(
        registered["model"],
        registered["method"],
        [registered["domain"]],
        {"fields": registered["fields"], "limit": registered["limit_val"]},
    )
