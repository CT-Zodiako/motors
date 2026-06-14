import json
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from db import query as pg_query, execute as pg_execute

router = APIRouter(prefix="/queries", tags=["catalog"])


class QueryIn(BaseModel):
    name: str
    description: str = ""
    model: str
    method: str = "search_read"
    domain: list = []
    fields: list = []
    limit_val: int = 100


@router.get("/")
def list_queries():
    return pg_query(
        "SELECT id, name, description, model, method, limit_val, active, created_at "
        "FROM odoo_queries ORDER BY id"
    )


@router.get("/{name}")
def get_query(name: str):
    rows = pg_query("SELECT * FROM odoo_queries WHERE name = %s", (name,))
    if not rows:
        raise HTTPException(status_code=404, detail=f"Query '{name}' not found")
    return rows[0]


@router.post("/", status_code=201)
def register_query(body: QueryIn):
    pg_execute(
        """
        INSERT INTO odoo_queries (name, description, model, method, domain, fields, limit_val)
        VALUES (%s, %s, %s, %s, %s::jsonb, %s::jsonb, %s)
        ON CONFLICT (name) DO UPDATE SET
            description = EXCLUDED.description,
            model       = EXCLUDED.model,
            method      = EXCLUDED.method,
            domain      = EXCLUDED.domain,
            fields      = EXCLUDED.fields,
            limit_val   = EXCLUDED.limit_val,
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
        ),
    )
    return {"registered": body.name}


@router.delete("/{name}")
def deactivate_query(name: str):
    rows = pg_query("SELECT id FROM odoo_queries WHERE name = %s", (name,))
    if not rows:
        raise HTTPException(status_code=404, detail=f"Query '{name}' not found")
    pg_execute("UPDATE odoo_queries SET active = FALSE WHERE name = %s", (name,))
    return {"deactivated": name}
