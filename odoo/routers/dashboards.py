"""Dashboards router: legacy get-by-key + CRUD + data/preview (dashboard-crud-menu).

Error mapping follows the categories pattern: ConflictError -> 409,
NotFoundError -> 404, DefinitionError -> 422 with structured detail.
"""
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field, model_validator

from auth import get_current_user, require_permission
from config_store import get_store, ConflictError, NotFoundError
from dashboard_validation import DefinitionError, fetch_and_validate, _execute_definition

router = APIRouter(prefix="/dashboards", tags=["dashboards"])

MENU_KEY_RE = r"^[a-z0-9][a-z0-9-]{0,63}$"  # URL-safe; ':' impossible -> tab-key scheme safe

ADMIN_PERMISSION = "menu.admin.dashboards"
VIEW_PERMISSION = "menu.visualizaciones.dashboards"


class DashboardDefinition(BaseModel):
    model: str = Field(min_length=1)
    fields: list[str] = Field(min_length=1)
    group_by: list[str] = []
    domain: list = []
    aggregations: dict[str, str] = {}


class DashboardCreate(BaseModel):
    menu_key: str = Field(pattern=MENU_KEY_RE)
    name: str = Field(min_length=1, max_length=200)
    embed_url: str | None = None
    definition: DashboardDefinition | None = None
    active: bool = False  # default unpublished

    @model_validator(mode="after")
    def _xor(self):
        if (self.embed_url is None) == (self.definition is None):
            raise ValueError("Exactly one of embed_url or definition must be set")
        return self


class DashboardPatch(BaseModel):
    menu_key: str | None = Field(default=None, pattern=MENU_KEY_RE)
    name: str | None = None
    embed_url: str | None = None
    definition: DashboardDefinition | None = None
    active: bool | None = None
    # Post-merge XOR re-validated in the handler before persisting.
    # Explicit nulls (exclude_unset dump) clear embed_url/definition for type switches.


def _definition_http_error(error: DefinitionError, code: str | None = None) -> HTTPException:
    detail = {"message": error.message, "model": error.model, "field": error.field}
    if code is not None:
        detail["code"] = code
    return HTTPException(status_code=422, detail=detail)


def _validate_definition_dict(definition: dict, code: str | None = None) -> dict:
    """Run the Odoo-boundary validation; returns fields_get metadata for labels."""
    try:
        return fetch_and_validate(definition)
    except DefinitionError as e:
        raise _definition_http_error(e, code)
    except HTTPException:
        raise
    except Exception:
        raise HTTPException(status_code=502, detail="Odoo metadata request failed")


@router.get("/")
def list_dashboards(user: dict = Depends(get_current_user)):
    store = get_store()
    permissions = store.get_user_permissions(user["id"])
    if ADMIN_PERMISSION in permissions:
        return store.list_dashboards(include_unpublished=True)
    if VIEW_PERMISSION in permissions:
        return store.list_dashboards(include_unpublished=False)
    raise HTTPException(status_code=403, detail="Permission denied")


@router.post("/", status_code=201)
def create_dashboard(body: DashboardCreate, user: dict = Depends(require_permission(ADMIN_PERMISSION))):
    definition = body.definition.model_dump() if body.definition is not None else None
    if definition is not None:
        _validate_definition_dict(definition)
    try:
        return get_store().create_dashboard({
            "menu_key": body.menu_key,
            "name": body.name,
            "embed_url": body.embed_url,
            "definition": definition,
            "active": body.active,
        })
    except ConflictError:
        raise HTTPException(status_code=409, detail=f"Dashboard {body.menu_key} already exists")


@router.post("/preview")
def preview_dashboard(body: DashboardDefinition, user: dict = Depends(require_permission(ADMIN_PERMISSION))):
    """Admin preview: identical validation + execution as the stored data path."""
    definition = body.model_dump()
    fields_meta = _validate_definition_dict(definition)
    try:
        return _execute_definition(definition, fields_meta)
    except Exception:
        raise HTTPException(status_code=502, detail="Odoo data request failed")


@router.get("/{menu_key}")
def get_dashboard(menu_key: str, user: dict = Depends(require_permission(VIEW_PERMISSION))):
    dashboard = get_store().get_dashboard_by_menu_key(menu_key)
    if dashboard is None:
        raise HTTPException(status_code=404, detail=f"Dashboard {menu_key} not found")
    return {
        "name": dashboard["name"],
        "embed_url": dashboard["embed_url"],
        "definition": dashboard.get("definition"),
    }


@router.get("/{menu_key}/data")
def get_dashboard_data(menu_key: str, user: dict = Depends(require_permission(VIEW_PERMISSION))):
    dashboard = get_store().get_dashboard_by_menu_key(menu_key)
    if dashboard is None:
        raise HTTPException(status_code=404, detail=f"Dashboard {menu_key} not found")
    definition = dashboard.get("definition")
    if definition is None:
        raise HTTPException(status_code=422, detail={
            "message": "Embed dashboards have no data endpoint; they render client-side from embed_url",
            "model": None,
            "field": None,
        })
    fields_meta = _validate_definition_dict(definition, code="stale_definition")
    try:
        data = _execute_definition(definition, fields_meta)
    except Exception:
        raise HTTPException(status_code=502, detail="Odoo data request failed")
    return {"menu_key": dashboard["menu_key"], "name": dashboard["name"], **data}


@router.patch("/{menu_key}")
def update_dashboard(menu_key: str, body: DashboardPatch, user: dict = Depends(require_permission(ADMIN_PERMISSION))):
    store = get_store()
    current = store.get_dashboard_any(menu_key)
    if current is None:
        raise HTTPException(status_code=404, detail=f"Dashboard {menu_key} not found")

    patch = body.model_dump(exclude_unset=True)
    merged = {**current, **patch}
    if (merged.get("embed_url") is None) == (merged.get("definition") is None):
        raise HTTPException(status_code=422, detail={
            "message": "Exactly one of embed_url or definition must be set",
            "model": None,
            "field": None,
        })
    if merged.get("definition") is not None:
        _validate_definition_dict(merged["definition"])
    try:
        return store.update_dashboard(menu_key, patch)
    except NotFoundError:
        raise HTTPException(status_code=404, detail=f"Dashboard {menu_key} not found")
    except ConflictError:
        raise HTTPException(status_code=409, detail=f"Dashboard {patch.get('menu_key')} already exists")


@router.delete("/{menu_key}", status_code=204)
def delete_dashboard(menu_key: str, user: dict = Depends(require_permission(ADMIN_PERMISSION))):
    try:
        get_store().delete_dashboard(menu_key)
    except NotFoundError:
        raise HTTPException(status_code=404, detail=f"Dashboard {menu_key} not found")
    return None
