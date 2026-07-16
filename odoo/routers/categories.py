from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from config_store import get_store, ConflictError, NotFoundError

router = APIRouter(prefix="/categories", tags=["categories"])

GENERAL_CATEGORY = "General"


class CategoryIn(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    description: str | None = None


def category_exists(category_id: int) -> bool:
    """Shared helper: does this category id exist? Used by the catalog router too."""
    return any(c["id"] == category_id for c in get_store().list_categories())


def general_category_id() -> int:
    for c in get_store().list_categories():
        if c["name"] == GENERAL_CATEGORY:
            return c["id"]
    raise HTTPException(
        status_code=500,
        detail="Default category 'General' is missing; run the DB migration (init_db.py).",
    )


@router.get("/")
def list_categories():
    return get_store().list_categories()


@router.post("/", status_code=201)
def create_category(body: CategoryIn):
    try:
        return get_store().create_category(body.name, body.description)
    except ConflictError:
        raise HTTPException(status_code=409, detail="Category name already exists")


@router.delete("/{category_id}", status_code=204)
def delete_category(category_id: int):
    try:
        get_store().delete_category(category_id)
    except NotFoundError:
        raise HTTPException(status_code=404, detail=f"Category {category_id} not found")
    except ConflictError as e:
        raise HTTPException(status_code=409, detail=str(e))
    return None


