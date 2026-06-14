# Referencia Odoo XML-RPC

Todo lo que necesitás saber para registrar queries en `odoo_queries`.

---

## Métodos disponibles (`method`)

| Método           | Qué hace                                      | Devuelve          |
|------------------|-----------------------------------------------|-------------------|
| `search_read`    | Filtra y trae campos en una sola llamada      | lista de objetos  |
| `search`         | Solo devuelve IDs de los registros            | lista de IDs      |
| `search_count`   | Cuenta registros sin traerlos                 | número entero     |
| `read`           | Trae campos de IDs específicos                | lista de objetos  |
| `fields_get`     | Lista todos los campos del modelo             | diccionario       |
| `check_access_rights` | Verifica si tenés permiso sobre un modelo | true / false  |

> En este sistema el más usado es `search_read` — filtra y trae datos en una sola llamada.

---

## Domain — filtros (`domain`)

Un domain es una lista de condiciones. Cada condición tiene la forma:

```json
["campo", "operador", "valor"]
```

### Operadores de comparación

| Operador   | Significado                        | Ejemplo                                      |
|------------|------------------------------------|----------------------------------------------|
| `=`        | Igual                              | `["state", "=", "sale"]`                     |
| `!=`       | Distinto                           | `["state", "!=", "cancel"]`                  |
| `>`        | Mayor que                          | `["amount_total", ">", 1000]`                |
| `>=`       | Mayor o igual                      | `["customer_rank", ">=", 1]`                 |
| `<`        | Menor que                          | `["amount_total", "<", 500]`                 |
| `<=`       | Menor o igual                      | `["amount_total", "<=", 500]`                |
| `like`     | Contiene (case-sensitive)          | `["name", "like", "Acme"]`                   |
| `ilike`    | Contiene (case-insensitive)        | `["name", "ilike", "acme"]`                  |
| `not like` | No contiene (case-sensitive)       | `["name", "not like", "Test"]`               |
| `in`       | Está en la lista                   | `["state", "in", ["sale", "done"]]`          |
| `not in`   | No está en la lista                | `["state", "not in", ["cancel", "draft"]]`   |
| `child_of` | Es hijo de un registro             | `["category_id", "child_of", 5]`             |

### Operadores lógicos

Por defecto múltiples condiciones se unen con `AND`. Para cambiar eso:

| Símbolo | Significado | Uso                                                    |
|---------|-------------|--------------------------------------------------------|
| `&`     | AND (default) | `["&", ["state", "=", "sale"], ["amount_total", ">", 0]]` |
| `\|`    | OR          | `["\|", ["state", "=", "sale"], ["state", "=", "done"]]`  |
| `!`     | NOT         | `["!", ["state", "=", "cancel"]]`                      |

### Ejemplos de domain

```json
// Sin filtro — trae todo
[]

// Un solo filtro
[["customer_rank", ">", 0]]

// Múltiples filtros (AND implícito)
[["customer_rank", ">", 0], ["active", "=", true]]

// OR explícito
["|", ["state", "=", "sale"], ["state", "=", "done"]]

// Contiene texto
[["name", "ilike", "empresa"]]

// En una lista de valores
[["state", "in", ["sale", "done"]]]
```

---

## Modelos comunes (`model`)

### Clientes y proveedores
| Modelo        | Descripción               |
|---------------|---------------------------|
| `res.partner` | Clientes, proveedores, contactos |

Campos útiles: `name`, `email`, `phone`, `mobile`, `city`, `country_id`, `vat`, `customer_rank`, `supplier_rank`, `active`, `street`, `website`

---

### Ventas
| Modelo             | Descripción               |
|--------------------|---------------------------|
| `sale.order`       | Órdenes de venta          |
| `sale.order.line`  | Líneas de orden de venta  |

Campos útiles `sale.order`: `name`, `partner_id`, `amount_total`, `amount_untaxed`, `state`, `date_order`, `user_id`, `team_id`, `order_line`

Estados de `sale.order`:

| Estado     | Significado     |
|------------|-----------------|
| `draft`    | Presupuesto     |
| `sent`     | Enviado         |
| `sale`     | Confirmada      |
| `done`     | Bloqueada       |
| `cancel`   | Cancelada       |

---

### Facturas
| Modelo          | Descripción               |
|-----------------|---------------------------|
| `account.move`  | Facturas, notas de crédito |
| `account.move.line` | Líneas de factura     |

Campos útiles: `name`, `partner_id`, `amount_total`, `state`, `invoice_date`, `move_type`, `payment_state`

Tipos de `account.move` (`move_type`):

| Valor             | Significado          |
|-------------------|----------------------|
| `out_invoice`     | Factura de venta     |
| `in_invoice`      | Factura de compra    |
| `out_refund`      | Nota de crédito venta |
| `in_refund`       | Nota de crédito compra |

---

### Productos
| Modelo               | Descripción               |
|----------------------|---------------------------|
| `product.template`   | Producto (plantilla)      |
| `product.product`    | Variante de producto      |
| `product.category`   | Categorías de producto    |

Campos útiles: `name`, `list_price`, `standard_price`, `type`, `categ_id`, `active`, `description`, `uom_id`

---

### Inventario
| Modelo           | Descripción               |
|------------------|---------------------------|
| `stock.picking`  | Remitos / Picking         |
| `stock.move`     | Movimientos de stock      |
| `stock.quant`    | Stock disponible          |

---

### Compras
| Modelo               | Descripción               |
|----------------------|---------------------------|
| `purchase.order`     | Órdenes de compra         |
| `purchase.order.line`| Líneas de orden de compra |

---

### Empleados y RRHH
| Modelo           | Descripción               |
|------------------|---------------------------|
| `hr.employee`    | Empleados                 |
| `hr.leave`       | Ausencias / Vacaciones    |
| `hr.payslip`     | Recibos de sueldo         |

---

### CRM
| Modelo      | Descripción               |
|-------------|---------------------------|
| `crm.lead`  | Oportunidades / Leads     |

---

### Proyectos
| Modelo           | Descripción               |
|------------------|---------------------------|
| `project.project`| Proyectos                 |
| `project.task`   | Tareas                    |

---

## Descubrir campos de cualquier modelo

Tu API tiene un endpoint para ver los campos disponibles de cualquier modelo en vivo:

```bash
GET /fields/{model}
```

```bash
# Ejemplo
curl http://localhost:8000/fields/res.partner
curl http://localhost:8000/fields/sale.order
curl http://localhost:8000/fields/account.move
```

Respuesta:
```json
{
  "model": "res.partner",
  "fields": {
    "name": { "type": "char", "string": "Name" },
    "email": { "type": "char", "string": "Email" },
    "customer_rank": { "type": "integer", "string": "Customer Rank" },
    ...
  }
}
```

---

## Descubrir todos los modelos de tu Odoo

```bash
GET /models
```

Lista todos los modelos disponibles en tu instancia de Odoo.

---

## Ejemplo completo registrando un query

```json
POST /queries/
{
  "name": "ventas_mes_actual",
  "description": "Órdenes de venta confirmadas del mes actual",
  "model": "sale.order",
  "method": "search_read",
  "domain": [
    ["state", "in", ["sale", "done"]],
    ["date_order", ">=", "2026-06-01"]
  ],
  "fields": ["name", "partner_id", "amount_total", "date_order", "state"],
  "limit_val": 100
}
```

Ejecutarlo:
```bash
GET /run/ventas_mes_actual
```
