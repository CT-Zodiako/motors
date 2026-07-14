# Cómo agregar queries al sistema

Todas las consultas a Odoo se registran en la tabla `odoo_queries` de PostgreSQL.
Ninguna ruta a Odoo existe en el código — todo pasa por esta tabla.

## Flujo

```
POST /queries/  →  guarda en odoo_db  →  GET /run/{name}  →  consulta Odoo  →  devuelve datos
```

---

## Campos de un query

| Campo         | Tipo    | Descripción                                      | Ejemplo                          |
|---------------|---------|--------------------------------------------------|----------------------------------|
| `name`        | string  | Identificador único (se usa en la URL)           | `clientes_activos`               |
| `description` | string  | Qué devuelve este query                          | "Partners con customer_rank > 0" |
| `model`       | string  | Modelo de Odoo                                   | `res.partner`                    |
| `method`      | string  | Método XML-RPC (casi siempre `search_read`)      | `search_read`                    |
| `domain`      | array   | Filtros en formato Odoo domain                   | `[["customer_rank", ">", 0]]`    |
| `fields`      | array   | Campos a traer                                   | `["name", "email", "phone"]`     |
| `limit_val`   | integer | Máximo de registros a devolver                   | `50`                             |
| `category_id` | integer | Categoría del query (ver `/categories/`)         | `2`                              |

> Si omitís `category_id` al crear, el query cae en la categoría **General**.
> Si lo omitís al actualizar (mismo `name`), se preserva la categoría existente.
> Las respuestas de `GET /queries/` y `GET /queries/{name}` incluyen el objeto `category: {id, name}`.

---

## Categorías

Los queries se agrupan por categoría (tabla `query_categories`). La categoría **General** es la default y no se puede borrar.

```bash
# Listar categorías (orden alfabético)
curl http://localhost:8000/categories/

# Crear categoría (nombre único; duplicado → 409)
curl -X POST http://localhost:8000/categories/ \
  -H "Content-Type: application/json" \
  -d '{"name": "Finanzas", "description": "Reportes financieros"}'

# Borrar categoría (409 si tiene queries asociados — recategorizá primero)
curl -X DELETE http://localhost:8000/categories/3

# Recategorizar un query existente
curl -X PATCH http://localhost:8000/queries/clientes_activos \
  -H "Content-Type: application/json" \
  -d '{"category_id": 2}'
```

> La migración es idempotente: `python init_db.py` crea `query_categories`, agrega la columna `category_id`, seedea `General` y asigna los queries existentes a `General`. Se puede correr cuantas veces haga falta.

---

## Opción 1 — API REST

```bash
curl -X POST http://localhost:8000/queries/ \
  -H "Content-Type: application/json" \
  -d '{
    "name": "clientes_activos",
    "description": "Partners con customer_rank > 0",
    "model": "res.partner",
    "method": "search_read",
    "domain": [["customer_rank", ">", 0]],
    "fields": ["name", "email", "phone", "city"],
    "limit_val": 50
  }'
```

> Si el `name` ya existe, lo actualiza. Si no existe, lo crea.

---

## Opción 2 — seeds.py

Agregá el query al array `SEEDS` en `seeds.py` y ejecutá:

```python
{
    "name": "mi_query",
    "description": "Lo que devuelve",
    "model": "sale.order",
    "method": "search_read",
    "domain": [["state", "=", "sale"]],
    "fields": ["name", "partner_id", "amount_total"],
    "limit_val": 100,
},
```

```bash
python3 seeds.py
```

---

## Opción 3 — SQL directo

```sql
INSERT INTO odoo_queries (name, description, model, method, domain, fields, limit_val)
VALUES (
  'mi_query',
  'Lo que devuelve',
  'sale.order',
  'search_read',
  '[["state", "=", "sale"]]',
  '["name", "partner_id", "amount_total"]',
  100
);
```

---

## Ejecutar un query registrado

```bash
GET /run/{name}
```

```bash
curl http://localhost:8000/run/clientes_activos
```

Respuesta:

```json
{
  "query": "clientes_activos",
  "total": 12,
  "data": [...]
}
```

---

## Desactivar un query

```bash
DELETE /queries/{name}
```

No borra el registro — lo marca como `active = false`. Para reactivarlo usá `POST /queries/` con el mismo `name`.

---

## Modelos comunes de Odoo

| Modelo             | Qué es            |
|--------------------|-------------------|
| `res.partner`      | Clientes / Proveedores |
| `product.template` | Productos         |
| `sale.order`       | Órdenes de venta  |
| `account.move`     | Facturas          |
| `stock.picking`    | Remitos / Picking |
| `purchase.order`   | Órdenes de compra |
