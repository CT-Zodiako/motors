from fastapi import APIRouter
from odoo_client import execute as odoo_execute

router = APIRouter(prefix="/explore", tags=["explorer"])


@router.get("/fields/{model}")
def get_model_fields(model: str):
    fields = odoo_execute(
        model,
        "fields_get",
        [],
        {"attributes": ["string", "type", "required", "readonly"]},
    )
    return {"model": model, "fields": fields}


@router.get("/models")
def get_all_models():
    models = odoo_execute(
        "ir.model",
        "search_read",
        [[]],
        {"fields": ["name", "model", "info"]},  # no limit: Odoo instances have 1000+ models
    )
    return {"total": len(models), "models": models}
