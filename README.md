# Motors — Odoo Bridge

Motors es un proyecto full stack para consultar datos de Odoo de forma controlada. La aplicación permite registrar consultas permitidas, ejecutarlas contra Odoo vía XML-RPC, visualizar resultados desde una interfaz web y exportarlos en distintos formatos.

## Resumen rápido

| Parte | Carpeta | Tecnología | URL local |
|-------|---------|------------|-----------|
| Backend API | `odoo/` | Python, FastAPI, BigQuery, XML-RPC | `http://localhost:8000` |
| Frontend UI | `odoo-ui/` | Angular 21, PrimeNG, TypeScript | `http://localhost:4200` |
| Configuración | BigQuery | `BQ_CONFIG_DATASET` | Google Cloud |

## ¿De qué se trata?

El sistema funciona como un puente entre una instancia de Odoo y Google BigQuery.

La idea principal es **no ejecutar consultas arbitrarias contra Odoo**. En cambio:

1. El backend guarda consultas registradas en BigQuery (config store).
2. La API ejecuta solo esas consultas permitidas contra Odoo.
3. El frontend permite crear, listar, ejecutar y desactivar consultas.
4. Los resultados pueden exportarse como CSV, Excel o SQL para PostgreSQL/Oracle.

## Tecnologías principales

### Backend

- Python 3.12+
- FastAPI
- Uvicorn
- Google Cloud BigQuery (configuración y datos)
- `python-dotenv` para variables de entorno
- `openpyxl` para exportación a Excel
- XML-RPC para conexión con Odoo

### Frontend

- Angular 21
- TypeScript 5.9
- PrimeNG 21
- PrimeIcons
- RxJS
- npm

## Requisitos previos

Antes de levantar el proyecto necesitás tener instalado:

- Python 3.12 o superior
- Node.js 18 o superior
- npm
- Credenciales de una instancia de Odoo
- Credenciales de Google Cloud (BigQuery) exportadas en `GOOGLE_APPLICATION_CREDENTIALS`
- Git, si vas a clonar el repositorio

## Estructura del proyecto

```text
motors/
├── odoo/              # Backend FastAPI + conexión a Odoo + BigQuery config store
│   ├── config_store/  # Protocolo, implementaciones en memoria y BigQuery
│   └── routers/       # Endpoints de la API
├── odoo-ui/           # Frontend Angular
└── README.md          # Guía general del proyecto
```

## 1. Configurar el backend

Entrá a la carpeta del backend:

```bash
cd odoo
```

Creá y activá el entorno virtual:

```bash
python3 -m venv .venv
source .venv/bin/activate
```

Instalá dependencias:

```bash
pip install -r requirements.txt
```

Creá el archivo `.env` tomando como referencia `odoo/.env.example` o usando esta estructura:

```env
# Odoo
ODOO_URL=https://tu-empresa.odoo.com
ODOO_DB=nombre_de_tu_base
ODOO_USERNAME=tu@email.com
ODOO_PASSWORD=tu_password_o_api_key

# BigQuery config store
BQ_CONFIG_DATASET=config
GOOGLE_APPLICATION_CREDENTIALS=/ruta/a/tu/credencial.json
```

Levantá la API:

```bash
uvicorn main:app --reload
```

La API queda disponible en:

- API: `http://localhost:8000`
- Swagger / documentación interactiva: `http://localhost:8000/docs`

Al arrancar, el backend crea el dataset y las tablas de configuración en BigQuery si no existen, e inyecta el `BigQueryConfigStore` como capa de persistencia.

## 2. Levantar el frontend

En otra terminal, desde la raíz del proyecto:

```bash
cd odoo-ui
npm install
npm start
```

También podés usar directamente:

```bash
ng serve
```

La aplicación queda disponible en:

```text
http://localhost:4200
```

> Importante: el backend debe estar corriendo en `http://localhost:8000` para que la UI pueda consultar datos.

## Flujo recomendado para desarrollo

Terminal 1 — backend:

```bash
cd odoo
source .venv/bin/activate
uvicorn main:app --reload
```

Terminal 2 — frontend:

```bash
cd odoo-ui
npm start
```

Luego abrí:

```text
http://localhost:4200
```

## Funcionalidades principales

### Backend API

| Método | Ruta | Descripción |
|--------|------|-------------|
| `GET` | `/queries/` | Lista las consultas registradas |
| `POST` | `/queries/` | Registra una consulta nueva |
| `DELETE` | `/queries/{name}` | Desactiva una consulta |
| `GET` | `/run/{name}` | Ejecuta una consulta contra Odoo |
| `GET` | `/export/csv/{name}` | Exporta resultados a CSV |
| `GET` | `/export/excel/{name}` | Exporta resultados a Excel |
| `GET` | `/export/sql/{name}?target=postgres\|oracle` | Exporta SQL para PostgreSQL u Oracle |
| `GET` | `/explore/models` | Lista modelos disponibles de Odoo |
| `GET` | `/explore/fields/{model}` | Lista campos de un modelo |
| `POST` | `/bigquery/upload/{dataset_id}/{table_id}` | Carga datos en BigQuery |

Los endpoints de exportación aceptan el parámetro opcional `columns`:

```text
/export/csv/nombre_query?columns=id,name,email
```

### Frontend UI

La interfaz tiene tres secciones principales:

- **Queries**: lista consultas registradas, muestra modelo, método, límite y estado, y permite desactivarlas.
- **Nuevo Query**: wizard para crear consultas sin escribir JSON manualmente.
- **Ejecutar**: permite ejecutar una consulta, ver resultados en tabla y exportarlos.

El wizard de creación guía estos pasos:

1. Seleccionar o buscar modelo de Odoo.
2. Elegir campos disponibles.
3. Armar filtros visuales.
4. Guardar nombre, límite y configuración.

## Build de producción del frontend

```bash
cd odoo-ui
npm run build
```

El build queda en:

```text
odoo-ui/dist/odoo-ui/
```

## Archivos importantes

| Archivo | Descripción |
|---------|-------------|
| `odoo/main.py` | Entrada principal de FastAPI |
| `odoo/odoo_client.py` | Cliente de conexión con Odoo |
| `odoo/config_store/` | Capa de persistencia configurable (protocolo, memoria, BigQuery) |
| `odoo/config_store/bq_store.py` | Implementación de producción sobre BigQuery |
| `odoo/config_store/memory_store.py` | Implementación en memoria para tests |
| `odoo-ui/src/app/services/odoo-queries.ts` | Servicio HTTP del frontend hacia la API |
| `odoo-ui/src/app/pages/` | Pantallas principales de Angular |

## Notas importantes

- No subas el archivo `.env` al repositorio: contiene credenciales de Odoo y Google Cloud.
- El backend espera credenciales de BigQuery válidas en `GOOGLE_APPLICATION_CREDENTIALS`.
- La UI espera que la API esté disponible en `http://localhost:8000`.
- El dataset de configuración por defecto es `config`; se puede cambiar con `BQ_CONFIG_DATASET`.

