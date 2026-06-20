# Odoo Bridge API

API que actúa como puente entre Odoo (vía XML-RPC) y una base de datos PostgreSQL local.
Las consultas a Odoo son controladas — solo se ejecutan las que están registradas en la DB.

## Stack

- **Python 3.14** + FastAPI + Uvicorn
- **PostgreSQL 17** (Docker)
- **psycopg2** para conexión a Postgres
- **openpyxl** para exportación a Excel
- **google-cloud-bigquery** para sincronización con BigQuery

## Requisitos previos

- Python 3.12+
- Docker Desktop corriendo
- Credenciales de una instancia de Odoo (SaaS o local)

---

## 1. Clonar y crear el entorno virtual

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

---

## 2. Levantar la base de datos

```bash
docker run -d \
  --name postgres17 \
  -e POSTGRES_USER=postgres \
  -e POSTGRES_PASSWORD=123456 \
  -e POSTGRES_DB=mi_db \
  -p 5432:5432 \
  -v backend_postgres_data:/var/lib/postgresql/data \
  --restart always \
  postgres:17
```

Crear la base de datos del proyecto:

```bash
docker exec postgres17 psql -U postgres -c "CREATE DATABASE odoo_db;"
```

Crear la tabla de queries:

```bash
python init_db.py
```

Cargar queries de ejemplo:

```bash
python seeds.py
```

---

## 3. Configurar variables de entorno

Crear un archivo `.env` en la raíz del proyecto:

```env
# Odoo
ODOO_URL=https://tu-empresa.odoo.com
ODOO_DB=nombre_de_tu_base
ODOO_USERNAME=tu@email.com
ODOO_PASSWORD=tu_password_o_api_key

# PostgreSQL local
PG_HOST=localhost
PG_PORT=5432
PG_DB=odoo_db
PG_USER=postgres
PG_PASSWORD=123456

# BigQuery (opcional)
GOOGLE_APPLICATION_CREDENTIALS=/ruta/absoluta/a/service-account.json
```

## Configuración de BigQuery

El sync requiere una cuenta de servicio de Google Cloud con permisos de lectura sobre los datasets/tables deseados. Recomendado:

1. Crear o descargar la clave JSON de la cuenta de servicio.
2. Configurar la variable de entorno `GOOGLE_APPLICATION_CREDENTIALS` apuntando a la clave **fuera del repositorio**.
3. Si no se define la variable, el sistema busca `odoo/bigquery.txt`, que está agregado a `.gitignore` para evitar commits accidentales.

---

## 4. Levantar la API

```bash
source .venv/bin/activate
uvicorn main:app --reload
```

La API queda disponible en `http://localhost:8000`.

Documentación interactiva: `http://localhost:8000/docs`

---

## Endpoints principales

| Método | Ruta | Descripción |
|--------|------|-------------|
| `GET` | `/queries/` | Lista todos los queries registrados |
| `POST` | `/queries/` | Registra un query nuevo |
| `DELETE` | `/queries/{name}` | Desactiva un query |
| `GET` | `/run/{name}` | Ejecuta un query contra Odoo |
| `GET` | `/export/csv/{name}` | Exporta a CSV |
| `GET` | `/export/excel/{name}` | Exporta a Excel |
| `GET` | `/export/sql/{name}?target=postgres\|oracle` | Exporta a SQL con CREATE TABLE |
| `GET` | `/explore/models` | Lista todos los modelos de Odoo |
| `GET` | `/explore/fields/{model}` | Lista los campos de un modelo |
| `GET` | `/bigquery/datasets` | Lista los datasets accesibles en BigQuery |
| `GET` | `/bigquery/tables/{dataset_id}` | Lista las tablas de un dataset |
| `POST` | `/bigquery/sync/{dataset_id}/{table_id}` | Sincroniza una tabla de BigQuery a PostgreSQL |

### Parámetro opcional de columnas en exports

Todos los endpoints de export aceptan `?columns=col1,col2,col3` para filtrar columnas.

---

## Conexión a la DB desde DBeaver

| Campo | Valor |
|-------|-------|
| Host | `localhost` |
| Port | `5432` |
| Database | `odoo_db` |
| User | `postgres` |
| Password | `123456` |
