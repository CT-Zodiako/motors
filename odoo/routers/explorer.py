from fastapi import APIRouter, Depends
from auth import require_permission
from odoo_client import execute as odoo_execute

router = APIRouter(prefix="/explore", tags=["explorer"])


@router.get("/fields/{model}")
def get_model_fields(model: str, user: dict = Depends(require_permission("menu.cargar.create"))):
    fields = odoo_execute(
        model,
        "fields_get",
        [],
        {"attributes": ["string", "type", "required", "readonly", "relation", "help"]},
    )
    return {"model": model, "fields": fields}


@router.get("/models")
def get_all_models(user: dict = Depends(require_permission("menu.cargar.create"))):
    models = odoo_execute(
        "ir.model",
        "search_read",
        [[]],
        {"fields": ["name", "model", "info"]},  # no limit: Odoo instances have 1000+ models
    )
    return {"total": len(models), "models": models}
