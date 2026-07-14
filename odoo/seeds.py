import json
from db import execute

# query-categories change: seed categories first, then queries referencing them.
CATEGORIES = ["Clientes", "Productos", "Ventas", "Facturación"]

SEEDS = [
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


def seed():
    for c in CATEGORIES:
        execute(
            """
            INSERT INTO query_categories (name)
            VALUES (%s)
            ON CONFLICT (name) DO NOTHING
            """,
            (c,),
        )
    for q in SEEDS:
        execute(
            """
            INSERT INTO odoo_queries (name, description, model, method, domain, fields, limit_val, category_id)
            VALUES (%s, %s, %s, %s, %s::jsonb, %s::jsonb, %s,
                    (SELECT id FROM query_categories WHERE name = %s))
            ON CONFLICT (name) DO NOTHING
            """,
            (
                q["name"],
                q["description"],
                q["model"],
                q["method"],
                json.dumps(q["domain"]),
                json.dumps(q["fields"]),
                q["limit_val"],
                q["category"],
            ),
        )
    print(f"Seeded {len(CATEGORIES)} categories and {len(SEEDS)} queries.")


if __name__ == "__main__":
    seed()
