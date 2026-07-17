from fastapi import APIRouter, Depends, HTTPException
from auth import require_permission
from config_store import get_store
from odoo_client import execute as odoo_execute

router = APIRouter(prefix="/run", tags=["runner"])


def _fetch_registered(name: str) -> dict | None:
    row = get_store().get_query(name)
    if row is None or not row.get("active", True):
        return None
    return row


def fetch_query_rows(query: dict) -> list[dict]:
    """Execute a stored query against Odoo and return raw rows.

    Honors query['limit_val'] when set to a positive integer.
    None / 0 / negative / empty → no limit (False).
    """
    limit_val = query.get("limit_val")
    limit = False
    if limit_val is not None:
        try:
            n = int(limit_val)
            if n > 0:
                limit = n
        except (ValueError, TypeError):
            pass

    return odoo_execute(
        query["model"],
        query["method"],
        [query["domain"]],
        {"fields": query["fields"], "limit": limit},
    )


@router.get("/{name}")
def run_query(name: str, user: dict = Depends(require_permission("menu.consultar.ejecutar"))):
    registered = _fetch_registered(name)
    if not registered:
        raise HTTPException(status_code=404, detail=f"Query '{name}' not found or inactive")

    result = fetch_query_rows(registered)
    return {"query": name, "total": len(result), "data": result}
