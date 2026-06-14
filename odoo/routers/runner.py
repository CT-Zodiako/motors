from fastapi import APIRouter, HTTPException
from db import query as pg_query
from odoo_client import execute as odoo_execute

router = APIRouter(prefix="/run", tags=["runner"])


def _fetch_registered(name: str) -> dict | None:
    rows = pg_query(
        "SELECT * FROM odoo_queries WHERE name = %s AND active = TRUE",
        (name,),
    )
    return rows[0] if rows else None


@router.get("/{name}")
def run_query(name: str):
    registered = _fetch_registered(name)
    if not registered:
        raise HTTPException(status_code=404, detail=f"Query '{name}' not found or inactive")

    result = odoo_execute(
        registered["model"],
        registered["method"],
        [registered["domain"]],
        {"fields": registered["fields"], "limit": False},
    )
    return {"query": name, "total": len(result), "data": result}
