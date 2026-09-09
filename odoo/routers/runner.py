from fastapi import APIRouter, Depends, HTTPException, Query
from auth import require_permission
from config_store import get_store
from odoo_client import execute as odoo_execute

router = APIRouter(prefix="/run", tags=["runner"])


def _fetch_registered(name: str) -> dict | None:
    row = get_store().get_query(name)
    if row is None or not row.get("active", True):
        return None
    return row


def _stored_limit(query: dict) -> int | bool:
    limit_val = query.get("limit_val")
    if limit_val is not None:
        try:
            n = int(limit_val)
            if n > 0:
                return n
        except (ValueError, TypeError):
            pass
    return False


def fetch_query_rows(query: dict, offset: int = 0, limit: int | None = None) -> list[dict]:
    """Execute a stored query, optionally returning one offset/limit page."""
    stored_limit = _stored_limit(query)
    effective_limit = stored_limit if limit is None else limit
    if stored_limit is not False and effective_limit is not False:
        effective_limit = min(effective_limit, max(stored_limit - offset, 0))
    if effective_limit == 0 and effective_limit is not False:
        return []

    return odoo_execute(
        query["model"],
        query["method"],
        [query["domain"]],
        {"fields": query["fields"], "limit": effective_limit, "offset": offset},
    )


MAX_PAGE_SIZE = 1000


def count_query_rows(query: dict) -> int:
    """Return the exact count for a compatible stored query."""
    if query.get("method") != "search_read":
        raise ValueError("exact count is only supported for search_read")
    return int(odoo_execute(query["model"], "search_count", [query["domain"]], {}))


@router.get("/{name}")
def run_query(
    name: str,
    offset: int = Query(0, ge=0),
    page_size: int = Query(100, ge=1, le=MAX_PAGE_SIZE),
    user: dict = Depends(require_permission("menu.consultar.ejecutar")),
):
    registered = _fetch_registered(name)
    if not registered:
        raise HTTPException(status_code=404, detail=f"Query '{name}' not found or inactive")

    # Count independently so interactive requests never materialize the result set.
    total_source = "unknown"
    total_known = False
    try:
        counted_total = count_query_rows(registered)
        stored_limit = _stored_limit(registered)
        total = min(counted_total, stored_limit) if stored_limit is not False else counted_total
        total_known = True
        total_source = "search_count"
    except ValueError:
        stored_limit = _stored_limit(registered)
        total = stored_limit if stored_limit is not False else offset + page_size + 1
    except Exception:
        stored_limit = _stored_limit(registered)
        total = stored_limit if stored_limit is not False else offset + page_size + 1
        total_source = "count_error"

    # Keep a sentinel fetch for has_more compatibility and final-page behavior.
    result = fetch_query_rows(registered, offset=offset, limit=page_size + 1)
    has_more = len(result) > page_size
    data = result[:page_size]
    if total_known:
        has_more = offset + len(data) < total
        if not has_more:
            total = offset + len(data)
            total_source = "sentinel"
    elif not has_more:
        total = offset + len(data)
        total_known = True
        total_source = "sentinel"
    return {
        "query": name,
        "total": total,
        "data": data,
        "offset": offset,
        "page_size": page_size,
        "returned": len(data),
        "has_more": has_more,
        "total_known": total_known,
        "total_source": total_source,
        "total_error": "No se pudo calcular el total exacto" if total_source == "count_error" else None,
    }
