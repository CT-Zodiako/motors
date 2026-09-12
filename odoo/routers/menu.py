"""Permission-filtered navigation; never a replacement for route permission guards."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException

from auth import get_current_user
from config_store import get_store

router = APIRouter(prefix="/menu", tags=["menu"])


def navigation_context(user: dict, system_id: str | None = None,
                       module_id: str | None = None) -> dict:
    """Return the permitted tree and optionally scope menu to a validated selection.

    IDs are opaque strings. Systems/modules without permitted active options are
    omitted. A module selection requires its system; unknown, inactive, mismatched,
    and forbidden selections all fail closed with 403.
    """
    if module_id is not None and system_id is None:
        raise HTTPException(400, "A system_id is required with module_id")
    store = get_store()
    permissions = store.get_user_permissions(user["id"])
    options_by_module: dict[str, list[dict]] = {}
    for option in store.list_menu_options():
        if option.get("active") and option["permission_id"] in permissions:
            # Only this fixed local viewer is embeddable; never forward stored URLs.
            workflow_url = (
                "/WorkFlow/index.html"
                if (option["id"], option["module_id"], option["permission_id"]) in {
                    ("menu.procesos.bizagi", "1-procesos", "menu.procesos.bizagi"),
                    ("menu.operaciones.procesos", "2-procesos", "menu.operaciones.procesos"),
                }
                else None
            )
            # Normalize existing stored labels without requiring reseeding or mutation.
            options_by_module.setdefault(option["module_id"], []).append(
                {**option, "name": "Procesos" if workflow_url else option["name"],
                 "workflow_url": workflow_url}
            )
    modules_by_system: dict[str, list[dict]] = {}
    for module in store.list_modules():
        menu = options_by_module.get(module["id"], [])
        if module.get("active") and menu:
            modules_by_system.setdefault(module["system_id"], []).append({**module, "menu": menu})
    systems = [
        {**system, "modules": modules_by_system[system["id"]]}
        for system in store.list_systems()
        if system.get("active") and modules_by_system.get(system["id"])
    ]
    selected = systems
    if system_id is not None:
        selected = [s for s in systems if s["id"] == system_id]
        if not selected:
            raise HTTPException(403, "System unavailable")
    modules = [m for s in selected for m in s["modules"]]
    if module_id is not None:
        modules = [m for m in modules if m["id"] == module_id]
        if not modules:
            raise HTTPException(403, "Module unavailable in selected system")
    return {
        "systems": systems,
        "selected_system_id": system_id,
        "selected_module_id": module_id,
        "menu": [option for module in modules for option in module["menu"]],
    }


@router.get("")
def menu(system_id: str, module_id: str, user: dict = Depends(get_current_user)) -> dict:
    return {"menu": navigation_context(user, system_id, module_id)["menu"]}


@router.get("/{option_id}")
def menu_option(option_id: str, system_id: str, module_id: str,
                user: dict = Depends(get_current_user)) -> dict:
    for option in navigation_context(user, system_id, module_id)["menu"]:
        if option["id"] == option_id:
            return option
    raise HTTPException(403, "Menu option unavailable in selected module")
