import psycopg2
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from db import query as pg_query, execute as pg_execute

router = APIRouter(prefix="/categories", tags=["categories"])

GENERAL_CATEGORY = "General"


class CategoryIn(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    description: str | None = None


def category_exists(category_id: int) -> bool:
    """Shared helper: does this category id exist? Used by the catalog router too."""
    return bool(
        pg_query("SELECT 1 AS ok FROM query_categories WHERE id = %s", (category_id,))
    )


def general_category_id() -> int:
    rows = pg_query(
        "SELECT id FROM query_categories WHERE name = %s", (GENERAL_CATEGORY,)
    )
    if not rows:
        raise HTTPException(
            status_code=500,
            detail="Default category 'General' is missing; run the DB migration (init_db.py).",
        )
    return rows[0]["id"]


@router.get("/")
def list_categories():
    return pg_query(
        "SELECT id, name, description, created_at FROM query_categories ORDER BY lower(name) ASC"
    )


@router.post("/", status_code=201)
def create_category(body: CategoryIn):
    try:
        pg_execute(
            "INSERT INTO query_categories (name, description) VALUES (%s, %s)",
            (body.name, body.description),
        )
    except psycopg2.IntegrityError:
        raise HTTPException(status_code=409, detail="Category name already exists")
    rows = pg_query(
        "SELECT id, name, description, created_at FROM query_categories WHERE name = %s",
        (body.name,),
    )
    return rows[0]


@router.delete("/{category_id}", status_code=204)
def delete_category(category_id: int):
    rows = pg_query(
        "SELECT id, name FROM query_categories WHERE id = %s", (category_id,)
    )
    if not rows:
        raise HTTPException(status_code=404, detail=f"Category {category_id} not found")
    if rows[0]["name"] == GENERAL_CATEGORY:
        raise HTTPException(
            status_code=409, detail="The default category 'General' cannot be deleted"
        )
    refs = pg_query(
        "SELECT COUNT(*) AS n FROM odoo_queries WHERE category_id = %s", (category_id,)
    )
    if refs[0]["n"] > 0:
        raise HTTPException(
            status_code=409,
            detail="Category still has queries; recategorize them first",
        )
    pg_execute("DELETE FROM query_categories WHERE id = %s", (category_id,))
    return None
