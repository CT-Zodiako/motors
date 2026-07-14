import json
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from db import query as pg_query, execute as pg_execute
from routers.categories import category_exists, general_category_id

router = APIRouter(prefix="/queries", tags=["catalog"])

# query-categories change: every SELECT embeds the query's category via JOIN.
_SELECT_WITH_CATEGORY = """
    SELECT q.id, q.name, q.description, q.model, q.method, q.limit_val, q.active,
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


@router.patch("/{name}")
def recategorize_query(name: str, body: CategoryPatchIn):
    rows = pg_query(
        "SELECT id FROM odoo_queries WHERE name = %s AND active = TRUE", (name,)
    )
    if not rows:
        raise HTTPException(status_code=404, detail=f"Query '{name}' not found")
    if not category_exists(body.category_id):
        raise HTTPException(
            status_code=422, detail=f"Category {body.category_id} does not exist"
        )
    pg_execute(
        "UPDATE odoo_queries SET category_id = %s WHERE name = %s",
        (body.category_id, name),
    )
    return get_query(name)


@router.delete("/{name}")
def deactivate_query(name: str):
    rows = pg_query("SELECT id FROM odoo_queries WHERE name = %s", (name,))
    if not rows:
        raise HTTPException(status_code=404, detail=f"Query '{name}' not found")
    pg_execute("UPDATE odoo_queries SET active = FALSE WHERE name = %s", (name,))
    return {"deactivated": name}
