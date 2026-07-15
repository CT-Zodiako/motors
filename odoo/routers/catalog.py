import json
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from db import query as pg_query, execute as pg_execute
from routers.categories import category_exists, general_category_id

router = APIRouter(prefix="/queries", tags=["catalog"])

# query-categories change: every SELECT embeds the query's category via JOIN.
_SELECT_WITH_CATEGORY = """
    SELECT q.id, q.name, q.description, q.model, q.method, q.domain, q.fields, q.limit_val, q.active,
           q.created_at, q.category_id,
           CASE WHEN c.id IS NULL THEN NULL
                ELSE json_build_object('id', c.id, 'name', c.name)
           END AS category
    FROM odoo_queries q
    LEFT JOIN query_categories c ON c.id = q.category_id
"""


class QueryIn(BaseModel):
    name: str
    description: str = ""
    model: str
    method: str = "search_read"
    domain: list = []
    fields: list = []
    limit_val: int = 100
    category_id: int | None = None


class CategoryPatchIn(BaseModel):
    category_id: int


@router.get("/")
def list_queries():
    return pg_query(_SELECT_WITH_CATEGORY + " ORDER BY q.id")


@router.get("/{name}")
def get_query(name: str):
    rows = pg_query(_SELECT_WITH_CATEGORY + " WHERE q.name = %s", (name,))
    if not rows:
        raise HTTPException(status_code=404, detail=f"Query '{name}' not found")
    return rows[0]


@router.post("/", status_code=201)
def register_query(body: QueryIn):
    # Category validation: provided id must exist; omitted means
    # General on INSERT and preserve-existing on UPDATE.
    if body.category_id is not None and not category_exists(body.category_id):
        raise HTTPException(
            status_code=422, detail=f"Category {body.category_id} does not exist"
        )
    insert_category_id = (
        body.category_id if body.category_id is not None else general_category_id()
    )
    pg_execute(
        """
        INSERT INTO odoo_queries (name, description, model, method, domain, fields, limit_val, category_id)
        VALUES (%s, %s, %s, %s, %s::jsonb, %s::jsonb, %s, %s)
        ON CONFLICT (name) DO UPDATE SET
            description = EXCLUDED.description,
            model       = EXCLUDED.model,
            method      = EXCLUDED.method,
            domain      = EXCLUDED.domain,
            fields      = EXCLUDED.fields,
            limit_val   = EXCLUDED.limit_val,
            category_id = COALESCE(%s, odoo_queries.category_id),
            active      = TRUE
        """,
        (
            body.name,
            body.description,
            body.model,
            body.method,
            json.dumps(body.domain),
            json.dumps(body.fields),
            body.limit_val,
            insert_category_id,
            body.category_id,  # None on update => preserve existing category
        ),
    )
    return {"registered": body.name}


class QueryPatchIn(BaseModel):
    description: str | None = None
    domain: list | None = None
    fields: list | None = None
    limit_val: int | None = None
    category_id: int | None = None
    name: str | None = None
    model: str | None = None
    method: str | None = None


@router.patch("/{name}")
def update_query(name: str, body: QueryPatchIn):
    # Fetch current
    rows = pg_query(
        _SELECT_WITH_CATEGORY + " WHERE q.name = %s AND q.active = TRUE", (name,)
    )
    if not rows:
        raise HTTPException(status_code=404, detail=f"Query '{name}' not found")
    current = rows[0]

    # Immutability check
    for field in ("name", "model", "method"):
        incoming = getattr(body, field)
        if incoming is not None and incoming != current[field]:
            raise HTTPException(
                status_code=400, detail=f"'{field}' is immutable after creation"
            )

    # Validation
    if body.fields is not None and len(body.fields) == 0:
        raise HTTPException(status_code=400, detail="fields must be a non-empty list")
    if body.domain is not None and not isinstance(body.domain, list):
        raise HTTPException(status_code=400, detail="domain must be a list")
    if body.limit_val is not None and body.limit_val < 0:
        raise HTTPException(status_code=400, detail="limit_val must be >= 0")
    if body.category_id is not None and not category_exists(body.category_id):
        raise HTTPException(
            status_code=422, detail=f"Category {body.category_id} does not exist"
        )

    # Build update set (only provided fields)
    updates = {}
    if body.description is not None:
        updates["description"] = body.description
    if body.domain is not None:
        updates["domain"] = json.dumps(body.domain)
    if body.fields is not None:
        updates["fields"] = json.dumps(body.fields)
    if body.limit_val is not None:
        updates["limit_val"] = body.limit_val
    if body.category_id is not None:
        updates["category_id"] = body.category_id

    if updates:
        set_clause = ", ".join(f"{k} = %s" for k in updates.keys())
        pg_execute(
            f"UPDATE odoo_queries SET {set_clause} WHERE name = %s",
            (*updates.values(), name),
        )

    # Propagation (synchronous, best-effort)
    from query_propagation import propagate_query_edit
    updated = get_query(name)
    propagation = propagate_query_edit(updated)
    return {"query": updated, "propagation": propagation}


@router.delete("/{name}")
def deactivate_query(name: str):
    rows = pg_query("SELECT id FROM odoo_queries WHERE name = %s", (name,))
    if not rows:
        raise HTTPException(status_code=404, detail=f"Query '{name}' not found")
    pg_execute("UPDATE odoo_queries SET active = FALSE WHERE name = %s", (name,))
    return {"deactivated": name}
