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


def ensure_schema(store: Any) -> None:
    """Idempotent schema creation via store.ensure_schema()."""
    store.ensure_schema()


def seed_defaults(store: Any) -> None:
    """Idempotent seeding: General category + 4 seed queries if tables empty."""
    store.seed_defaults()
