# Odoo Bridge API

API que actúa como puente entre Odoo (vía XML-RPC) y BigQuery. Las consultas a Odoo son controladas — solo se ejecutan las que están registradas en el catálogo de BigQuery.

## Stack

- **Python 3.14** + FastAPI + Uvicorn
- **BigQuery** como capa de configuración y destino de datos (`config_store`)
- **JWT** en cookie `HttpOnly` para autenticación
- **openpyxl** para exportación a Excel
- **google-cloud-bigquery** para sincronización con BigQuery

## Requisitos previos

- Python 3.12+
- Credenciales de una instancia de Odoo (SaaS o local)
- Proyecto de Google Cloud con BigQuery habilitado y cuenta de servicio con acceso al dataset de configuración

---

## 1. Clonar y crear el entorno virtual

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

---

## 2. Configurar variables de entorno

Crear un archivo `.env` en la raíz del proyecto (`odoo/.env`):

```env
# Obligatorio para JWT
SECRET_KEY=una_clave_secreta_larga_y_aleatoria

# Odoo
ODOO_URL=https://tu-empresa.odoo.com
ODOO_DB=nombre_de_tu_base
ODOO_USERNAME=tu@email.com
ODOO_PASSWORD=tu_password_o_api_key

# BigQuery
BQ_CONFIG_DATASET=config_store

# Opcional: ruta a la clave JSON de la cuenta de servicio.
# Si no se define, el sistema busca odoo/bigquery.txt (agregado a .gitignore).
GOOGLE_APPLICATION_CREDENTIALS=/ruta/absoluta/a/service-account.json
```

## Configuración de BigQuery

La app se conecta a BigQuery usando una cuenta de servicio de Google Cloud:

1. Crear o descargar la clave JSON de la cuenta de servicio.
2. Configurar la variable de entorno `GOOGLE_APPLICATION_CREDENTIALS` apuntando a la clave **fuera del repositorio**.
3. Si no se define la variable, el sistema busca `odoo/bigquery.txt`, que está agregado a `.gitignore` para evitar commits accidentales.
4. El dataset de configuración se define en `BQ_CONFIG_DATASET` (default: `config`).

Al iniciar, el backend crea automáticamente las tablas necesarias si no existen:

- `odoo_queries` — catálogo de queries
- `query_categories` — categorías de queries
- `query_schedules` — tareas programadas
- `query_schedule_runs` — ejecuciones de schedules
- `query_destinations` — destinos BigQuery sincronizados
- `odoo_users` — usuarios de la app
- `odoo_permissions` — permisos de menú
- `odoo_user_permissions` — asignación de permisos por usuario

---

## 3. Levantar la API

```bash
source .venv/bin/activate
uvicorn main:app --reload
```

La API queda disponible en `http://localhost:8000`.

Documentación interactiva: `http://localhost:8000/docs`

---

## 4. Usuario inicial

Al primer arranque se crea automáticamente un usuario admin:

- **Email:** `soporte@gmail.com`
- **Password:** `123456`
- **Rol:** `admin`

Si el usuario ya existía antes de agregar el sistema de permisos, es posible que no tenga permisos asignados. Para asignarle todos los permisos del catálogo, ejecutar:

```bash
source .venv/bin/activate
python grant_soporte_perms.py
```

Ese script es de un solo uso y no es necesario volver a ejecutarlo salvo que se borren los permisos.

---

## Endpoints principales

### Autenticación

| Método | Ruta | Descripción |
|--------|------|-------------|
| `POST` | `/auth/login` | Inicia sesión y recibe cookie JWT |
| `POST` | `/auth/logout` | Cierra sesión |
| `GET` | `/auth/me` | Devuelve el usuario actual |
| `GET` | `/auth/permissions` | Devuelve los permisos del usuario actual |
| `POST` | `/auth/change-password` | Cambia la contraseña |

### Queries

| Método | Ruta | Descripción |
|--------|------|-------------|
| `GET` | `/queries/` | Lista todos los queries registrados |
| `GET` | `/queries/{name}` | Devuelve un query |
| `POST` | `/queries/` | Registra o actualiza un query |
| `PATCH` | `/queries/{name}` | Actualiza campos de un query |
| `DELETE` | `/queries/{name}` | Elimina un query |

### Ejecución y exportación

| Método | Ruta | Descripción |
|--------|------|-------------|
| `GET` | `/run/{name}` | Ejecuta un query contra Odoo |
| `GET` | `/export/csv/{name}` | Exporta a CSV |
| `GET` | `/export/excel/{name}` | Exporta a Excel |
| `GET` | `/export/sql/{name}?target=postgres\|oracle` | Exporta a SQL con CREATE TABLE |

### Exploración de Odoo

| Método | Ruta | Descripción |
|--------|------|-------------|
| `GET` | `/explore/models` | Lista todos los modelos de Odoo |
| `GET` | `/explore/fields/{model}` | Lista los campos de un modelo |

### BigQuery

| Método | Ruta | Descripción |
|--------|------|-------------|
| `GET` | `/bigquery/datasets` | Lista los datasets accesibles |
| `GET` | `/bigquery/tables/{dataset_id}` | Lista las tablas de un dataset |
| `POST` | `/bigquery/upload/{dataset_id}/{table_id}` | Carga filas en una tabla |
| `POST` | `/bigquery/upload-file/inspect` | Inspecciona un archivo CSV/XLSX |
| `POST` | `/bigquery/upload-file/preview` | Preview de un archivo CSV/XLSX |
| `POST` | `/bigquery/upload-file/load` | Carga un archivo CSV/XLSX a BigQuery |

### Schedules

| Método | Ruta | Descripción |
|--------|------|-------------|
| `GET` | `/schedules` | Lista tareas programadas |
| `POST` | `/schedules` | Crea una tarea programada |
| `PATCH` | `/schedules/{id}` | Edita una tarea programada |
| `DELETE` | `/schedules/{id}` | Elimina una tarea programada |
| `POST` | `/schedules/{id}/run` | Ejecuta una tarea programada ahora |

### Administración de usuarios y permisos

| Método | Ruta | Descripción |
|--------|------|-------------|
| `GET` | `/admin/users` | Lista usuarios |
| `POST` | `/admin/users` | Crea un usuario |
| `GET` | `/admin/users/{id}` | Devuelve usuario + permisos |
| `PATCH` | `/admin/users/{id}` | Edita rol/activo de un usuario |
| `POST` | `/admin/users/{id}/reset-password` | Resetea contraseña |
| `POST` | `/admin/users/{id}/permissions` | Asigna o revoca un permiso |
| `GET` | `/admin/permissions` | Lista permisos disponibles |

---

## Permisos de menú

El acceso a cada menú se controla por permisos asignados directamente a cada usuario. Los permisos sembrados por defecto son:

| Permiso | Menú |
|---|---|
| `menu.consultar.queries` | Queries |
| `menu.consultar.ejecutar` | Ejecutar |
| `menu.consultar.programar` | Programar |
| `menu.cargar.create` | Nuevo Query |
| `menu.cargar.upload` | Cargar archivo |
| `menu.cuenta.change_password` | Cambiar contraseña |
| `menu.admin.usuarios` | Administración → Usuarios |

Para asignar permisos, usar la pantalla **Administración → Usuarios** del frontend (requiere `menu.admin.usuarios`) o los endpoints de admin directamente.

---

## Parámetro opcional de columnas en exports

Todos los endpoints de export aceptan `?columns=col1,col2,col3` para filtrar columnas.
