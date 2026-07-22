from fastapi import APIRouter, HTTPException, Depends

from auth import require_permission
from config_store import get_store

router = APIRouter(prefix="/dashboards", tags=["dashboards"])


@router.get("/{menu_key}")
def get_dashboard(menu_key: str, user: dict = Depends(require_permission("menu.visualizaciones.dashboards"))):
    dashboard = get_store().get_dashboard_by_menu_key(menu_key)
    if dashboard is None:
        raise HTTPException(status_code=404, detail=f"Dashboard {menu_key} not found")
    return {"name": dashboard["name"], "embed_url": dashboard["embed_url"]}
