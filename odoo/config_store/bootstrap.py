"""Bootstrap: create_dataset/create_table + seed_defaults (D14).

Seed queries are copied verbatim from seeds.py (V7).
"""
from __future__ import annotations

from typing import Any

from . import codecs
from .errors import ConflictError

# ---------------------------------------------------------------------------
# V7: 4 seed queries verbatim from seeds.py
# ---------------------------------------------------------------------------
_SEED_QUERIES: list[dict[str, Any]] = [
    {
        "name": "clientes_activos",
        "description": "Partners con customer_rank > 0",
        "model": "res.partner",
        "method": "search_read",
        "domain": [["customer_rank", ">", 0]],
        "fields": ["name", "email", "phone", "city"],
        "limit_val": 50,
        "category": "Clientes",
    },
    {
        "name": "productos_todos",
        "description": "Todos los productos publicados",
        "model": "product.template",
        "method": "search_read",
        "domain": [],
        "fields": ["name", "list_price", "type", "categ_id"],
        "limit_val": 100,
        "category": "Productos",
    },
    {
        "name": "ventas_confirmadas",
        "description": "Órdenes de venta en estado 'sale'",
        "model": "sale.order",
        "method": "search_read",
        "domain": [["state", "=", "sale"]],
        "fields": ["name", "partner_id", "amount_total", "date_order"],
        "limit_val": 50,
        "category": "Ventas",
    },
    {
        "name": "facturas_emitidas",
        "description": "Facturas de venta emitidas",
        "model": "account.move",
        "method": "search_read",
        "domain": [["move_type", "=", "out_invoice"]],
        "fields": ["name", "partner_id", "amount_total", "state", "invoice_date"],
        "limit_val": 50,
        "category": "Facturación",
    },
]


# -----------------------------------------------------------------------------
# V8: seed permissions for the menu system (idempotent)
# -----------------------------------------------------------------------------
_SEED_PERMISSIONS: list[dict[str, Any]] = [
    {"id": "menu.consultar.queries", "label": "Ver listado de queries", "category": "consultar"},
    {"id": "menu.consultar.ejecutar", "label": "Ejecutar queries", "category": "consultar"},
    {"id": "menu.consultar.programar", "label": "Programar tareas", "category": "consultar"},
    {"id": "menu.cargar.create", "label": "Crear nuevo query", "category": "cargar"},
    {"id": "menu.cargar.upload", "label": "Cargar archivos", "category": "cargar"},
    {"id": "menu.cuenta.change_password", "label": "Cambiar contraseña", "category": "cuenta"},
    {"id": "menu.admin.usuarios", "label": "Administrar usuarios", "category": "admin"},
    {"id": "menu.admin.dashboards", "label": "Administrar dashboards", "category": "admin"},
    {"id": "menu.visualizaciones.dashboards", "label": "Ver dashboards", "category": "visualizaciones"},
    {"id": "menu.visualizaciones.ventas", "label": "Ver dashboard de ventas", "category": "visualizaciones"},
]


# System 2 options are demo navigation entries, not new executable API routes.
_SEED_PERMISSIONS += [
    {"id": "menu.operaciones.ventas", "label": "Pedidos de venta", "category": "operaciones"},
    {"id": "menu.operaciones.inventario", "label": "Existencias", "category": "operaciones"},
    {"id": "menu.operaciones.reportes", "label": "Resumen comercial", "category": "operaciones"},
    {"id": "menu.operaciones.procesos", "label": "Procesos", "category": "operaciones"},
]

_SEED_PERMISSIONS += [
    {"id": "menu.procesos.bizagi", "label": "Procesos", "category": "procesos"},
]

_SEED_SYSTEMS = [
    {"id": "1", "name": "Sistema 1 - Odoo Bridge", "active": True, "sort_order": 1},
    {"id": "2", "name": "Sistema 2 - Operaciones", "active": True, "sort_order": 2},
]
_SEED_MODULES = [
    {"id": f"1-{key}", "system_id": "1", "name": name, "active": True, "sort_order": i}
    for i, (key, name) in enumerate([
        ("consultar", "Consultar"), ("cargar", "Cargar"), ("cuenta", "Cuenta"),
        ("admin", "Administración"), ("visualizaciones", "Visualizaciones"),
        ("procesos", "Procesos"),
    ])
] + [
    {"id": f"2-{key}", "system_id": "2", "name": name, "active": True, "sort_order": i}
    for i, (key, name) in enumerate([
        ("ventas", "Ventas"), ("inventario", "Inventario"), ("reportes", "Reportes"),
        ("procesos", "Procesos"),
    ])
]
_SEED_MENU_OPTIONS = [
    {
        "id": perm["id"],
        "module_id": (f"2-{perm['id'].split('.')[-1]}" if perm["category"] == "operaciones"
                      else f"1-{perm['category']}"),
        "name": perm["label"],
        "menu_key": perm["id"].removeprefix("menu."),
        "permission_id": perm["id"],
        # Dashboards remain deactivated; retaining their permissions is intentional.
        "active": perm["category"] != "visualizaciones" and perm["id"] != "menu.admin.dashboards",
        "sort_order": i,
    }
    for i, perm in enumerate(_SEED_PERMISSIONS)
]
NAVIGATION_SEEDS = {
    "odoo_systems": _SEED_SYSTEMS,
    "odoo_modules": _SEED_MODULES,
    "odoo_menu_options": _SEED_MENU_OPTIONS,
}


def seed_permission_defaults(store: Any) -> None:
    """Idempotent seeding of menu permissions (per-row: inserts only missing ids)."""
    store.seed_permission_defaults()


# -----------------------------------------------------------------------------
# dashboard-crud-menu: admin grant + legacy dashboard seeds
# -----------------------------------------------------------------------------
_SEED_DASHBOARDS: list[dict[str, Any]] = [
    {"menu_key": "dashboards", "name": "Dashboards", "env": "SEED_DASHBOARD_EMBED_URL"},
    {"menu_key": "dashboards-ventas", "name": "Ventas", "env": "SEED_DASHBOARD_VENTAS_EMBED_URL"},
]


def grant_admin_permissions(store: Any) -> None:
    """Grant every menu.admin.* permission to all admin-role users (idempotent)."""
    admin_permission_ids = [
        p["id"] for p in store.list_permissions() if p["id"].startswith("menu.admin.")
    ]
    for user in store.list_users():
        if user.get("role") != "admin":
            continue
        held = store.get_user_permissions(user["id"])
        for pid in admin_permission_ids:
            if pid not in held:
                store.assign_user_permission(user["id"], pid)


def seed_dashboard_defaults(store: Any) -> None:
    """Seed the two legacy embed dashboards (idempotent).

    Skips a seed when its menu_key already exists (production rows untouched)
    or when its env var is unset (fresh dev environments seed nothing).
    """
    import os

    for seed in _SEED_DASHBOARDS:
        if store.get_dashboard_any(seed["menu_key"]) is not None:
            continue
        url = os.getenv(seed["env"])
        if not url:
            continue
        store.create_dashboard({
            "menu_key": seed["menu_key"],
            "name": seed["name"],
            "embed_url": url,
            "definition": None,
            "active": True,
        })


def ensure_schema(store: Any) -> None:
    """Idempotent schema creation via store.ensure_schema()."""
    store.ensure_schema()


def seed_defaults(store: Any) -> None:
    """Idempotent seeding: General category + 4 seed queries if tables empty."""
    store.seed_defaults()
    store.seed_permission_defaults()
    store.seed_navigation_defaults()
