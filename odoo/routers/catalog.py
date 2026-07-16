from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from datetime import datetime

from config_store import get_store, ConflictError, NotFoundError, ValidationError
from routers.categories import category_exists, general_category_id

router = APIRouter(prefix="/queries", tags=["catalog"])


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
    return get_store().list_queries()


@router.get("/{name}")
def get_query(name: str):
    row = get_store().get_query(name)
    if row is None:
        raise HTTPException(status_code=404, detail=f"Query '{name}' not found")
    return row


@router.post("/", status_code=201)
def register_query(body: QueryIn):
    # Category validation: provided id must exist; omitted means General on INSERT only.
    if body.category_id is not None and not category_exists(body.category_id):
        raise HTTPException(
            status_code=422, detail=f"Category {body.category_id} does not exist"
        )
    row = {
        "name": body.name,
        "description": body.description,
        "model": body.model,
        "method": body.method,
        "domain": body.domain,
        "fields": body.fields,
        "limit_val": body.limit_val,
        "active": True,
    }
    # Only set category_id on INSERT; on UPDATE the store preserves the existing one
    if body.category_id is not None:
        row["category_id"] = body.category_id
    else:
        # Check if this is a new query; if so, default to General
        if get_store().get_query(body.name) is None:
            row["category_id"] = general_category_id()
    try:
        get_store().upsert_query(row)
    except ValidationError as e:
        raise HTTPException(status_code=422, detail=str(e))
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


class QueryDestinationResponse(BaseModel):
    id: int
    query_name: str
    dataset_id: str
    table_id: str
    origin: str | None
    stale: bool
    last_error: str | None
    last_sync_at: datetime | None
    last_schema: list[dict] | None
    created_at: datetime


@router.get("/{name}/destination", response_model=QueryDestinationResponse)
def get_query_destination(name: str):
    from query_registry import get_destination

    row = get_store().get_query(name)
    if row is None:
        raise HTTPException(status_code=404, detail=f"Query '{name}' not found")
    dest = get_destination(name)
    if dest is None:
        raise HTTPException(status_code=404, detail=f"No destination for query '{name}'")
    return dest


@router.patch("/{name}")
def update_query(name: str, body: QueryPatchIn):
    current = get_store().get_query(name)
    if current is None:
        raise HTTPException(status_code=404, detail=f"Query '{name}' not found")

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

    # Build update patch (only provided fields)
    patch = {}
    if body.description is not None:
        patch["description"] = body.description
    if body.domain is not None:
        patch["domain"] = body.domain
    if body.fields is not None:
        patch["fields"] = body.fields
    if body.limit_val is not None:
        patch["limit_val"] = body.limit_val
    if body.category_id is not None:
        patch["category_id"] = body.category_id

    if patch:
        get_store().patch_query(name, patch)

    # Propagation (synchronous, best-effort) — still reads PG destinations via query_registry
    from query_propagation import propagate_query_edit
    updated = get_query(name)
    propagation = propagate_query_edit(updated)
    return {"query": updated, "propagation": propagation}


@router.delete("/{name}")
def deactivate_query(name: str):
    try:
        get_store().deactivate_query(name)
    except NotFoundError:
        raise HTTPException(status_code=404, detail=f"Query '{name}' not found")
    return {"deactivated": name}


