# Manual de Usuario — Odoo Bridge

Sistema para conectar Odoo con BigQuery y generar exports SQL. Este manual describe paso a paso todas las funcionalidades disponibles.

---

## 1. Instalación y primeros pasos

### 1.1 Requisitos

- Node.js 20+ y npm.
- Python 3.11+.
- PostgreSQL.
- Cuenta de Google Cloud con acceso a BigQuery.
- ngrok opcional si querés compartir la app por internet.

### 1.2 Configurar backend

```bash
cd odoo
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

Copiá el archivo de variables de entorno y completalo:

```bash
cp .env.example .env
```

Editá `.env` con los datos de PostgreSQL, Odoo y Google Cloud.

### 1.3 Crear base de datos

```bash
cd odoo
source .venv/bin/activate
python init_db.py
```

Esto crea las tablas `odoo_queries`, `query_schedules` y `query_schedule_runs`.

### 1.4 Configurar credenciales de BigQuery

```bash
cd odoo
```

Creá un archivo `bigquery.txt` con el contenido del JSON de la service account de Google Cloud. También podés usar la variable de entorno:

```bash
export GOOGLE_APPLICATION_CREDENTIALS=/ruta/al/archivo.json
```

### 1.5 Levantar backend

```bash
cd odoo
source .venv/bin/activate
python -m uvicorn main:app --host 0.0.0.0 --port 8000 --reload
```

El backend queda disponible en `http://localhost:8000`.

### 1.6 Levantar frontend

```bash
cd odoo-ui
npm install
npm start
```

La aplicación web queda disponible en `http://localhost:4200`.

---

## 2. Navegación general

La app tiene un menú lateral con las siguientes secciones:

| Sección | Descripción |
|---------|-------------|
| Queries | Lista de queries guardados. |
| Nuevo Query | Crear un nuevo query de Odoo. |
| Ejecutar | Correr queries y exportar resultados. |
| BigQuery | Ver datasets/tablas y sincronizar desde BigQuery a Postgres. |
| Programar | Gestionar ejecuciones automáticas a BigQuery. |

---

## 3. Queries

### 3.1 Ver queries existentes

En **Queries** se muestra la lista de queries guardados. Cada tarjeta muestra:

- Nombre.
- Descripción.
- Modelo de Odoo.
- Método (generalmente `search_read`).
- Cantidad de registros configurados como límite.

Acciones disponibles:

- **Editar**: modifica los campos del query.
- **Desactivar**: desactiva el query sin borrarlo.

### 3.2 Crear un nuevo query

1. Andá a **Nuevo Query**.
2. Completá:
   - **Nombre**: identificador único del query.
   - **Descripción**: texto explicativo.
   - **Modelo**: modelo de Odoo, por ejemplo `res.partner`, `sale.order`, `product.template`.
   - **Método**: generalmente `search_read`.
   - **Dominio**: filtro en formato JSON de Odoo. Por ejemplo:
     ```json
     [["customer_rank", ">", 0]]
     ```
   - **Campos**: lista de campos a traer en formato JSON. Por ejemplo:
     ```json
     ["name", "email", "phone", "create_date"]
     ```
   - **Límite**: cantidad máxima de registros. Para traer todos, dejar en un número alto.
3. Clic en **Guardar**.

> Los campos y el dominio se pueden autocompletar seleccionando primero el modelo. El sistema consulta Odoo y muestra los campos disponibles.

---

## 4. Ejecutar queries

### 4.1 Ejecutar un query

1. Andá a **Ejecutar**.
2. Seleccioná un query del dropdown.
3. Clic en **Ejecutar**.
4. El resultado se muestra en una tabla paginada.

### 4.2 Seleccionar columnas a exportar

Debajo de la barra de resultados aparecen chips con los nombres de las columnas. Clickeando un chip se marca/desmarca. También podés usar **Seleccionar todo** o **Deseleccionar todo**.

Las exportaciones y envíos a BigQuery respetan solo las columnas activas.

### 4.3 Exportar resultados

El botón **Exportar** tiene un menú desplegable con estas opciones:

- **CSV**: descarga archivo `.csv`.
- **Excel**: descarga archivo `.xlsx`.
- **SQL Postgres**: genera script `CREATE TABLE` + `INSERT INTO` compatible con PostgreSQL.
- **SQL Oracle**: genera script compatible con Oracle.

Si seleccionaste menos columnas de las totales, el export solo incluye esas columnas.

### 4.4 Generar INSERT SQL

Al lado del botón **Exportar** está **Generar INSERT**. Esto abre un diálogo donde:

1. Escribís el nombre de la tabla destino.
2. Clic en **Generar**.
3. El sistema arma automáticamente:
   - `CREATE TABLE IF NOT EXISTS tu_tabla (...)`
   - Un `INSERT INTO tu_tabla (...) VALUES (...);` por cada fila.
4. Podés copiar el SQL con el botón **Copiar**.

---

## 5. Enviar a BigQuery

El botón **Enviar a BigQuery** permite subir el resultado del query a una tabla de BigQuery.

### 5.1 Enviar ahora

1. Ejecutá el query.
2. Clic en **Enviar a BigQuery**.
3. Seleccioná el **dataset**.
4. Elegí el modo de tabla:
   - **Usar tabla existente**: seleccioná una tabla del dropdown.
   - **Crear nueva tabla**: escribí el nombre de la nueva tabla.
5. En el selector **Acción**, dejá **Enviar ahora**.
6. Clic en **Confirmar**.

El sistema crea o sobrescribe la tabla (`WRITE_TRUNCATE`) con los datos del query.

### 5.2 Programar envío

Desde el mismo diálogo podés programar que el envío se repita automáticamente:

1. Ejecutá el query.
2. Clic en **Enviar a BigQuery**.
3. Seleccioná dataset y tabla.
4. En **Acción** elegí **Programar envío**.
5. Completá:
   - **Nombre de la programación** (opcional).
   - **Frecuencia**:
     - Cada X horas.
     - Diario.
     - Semanal.
     - Mensual.
   - **Hora y minuto**: el campo muestra **Hora (24h)** y debajo aparece el equivalente AM/PM.
   - **Día de la semana** o **día del mes** según la frecuencia.
6. Clic en **Programar**.

El backend ejecutará el query y subirá los resultados a BigQuery según la frecuencia indicada.

---

## 6. Programar ejecuciones

La sección **Programar** muestra todas las programaciones creadas.

### 6.1 Ver programaciones

La tabla muestra:

- Nombre.
- Query asociado.
- Destino (`dataset.tabla`).
- Frecuencia resumida.
- Última ejecución.
- Estado de la última ejecución.

### 6.2 Acciones por programación

| Icono | Acción |
|-------|--------|
| ▶ / ⏸ | Activar o pausar la programación. |
| 🕐 | Ver historial de ejecuciones. |
| ▶️ | Ejecutar ahora manualmente. |
| ✏️ | Editar la programación. |
| 🗑️ | Eliminar la programación. |

### 6.3 Historial de ejecuciones

Al clickear el icono de historial se abre un diálogo con:

- Fecha/hora de inicio.
- Fecha/hora de fin.
- Estado (`success`, `error`, `running`).
- Filas cargadas.
- Mensaje detallado en caso de error.

### 6.4 Crear programación desde la sección Programar

1. Clic en **Nueva programación**.
2. Completá los campos del formulario.
3. Guardá.

> También podés crear programaciones directamente desde el diálogo **Enviar a BigQuery** en la sección Ejecutar.

---

## 7. BigQuery Sync

La sección **BigQuery** permite ver datasets y tablas existentes en BigQuery y copiarlas a PostgreSQL local.

### 7.1 Ver datasets y tablas

1. Seleccioná un dataset del dropdown.
2. El sistema carga las tablas con:
   - Nombre.
   - Cantidad de filas.
   - Tamaño en bytes.
   - Columnas con tipos.

### 7.2 Sincronizar tabla a PostgreSQL

1. Seleccioná un dataset.
2. En la tabla que querés traer, clic en **Sync**.
3. El sistema crea una tabla local llamada `{dataset}_{tabla}` con los datos de BigQuery.

> Esta funcionalidad es BigQuery → Postgres. No sube datos a BigQuery.

---

## 8. Compartir la app por internet

Si querés mostrarle la app a alguien externo, podés exponer el frontend con ngrok.

### 8.1 Requisitos

- Tener ngrok instalado.
- Tener una cuenta de ngrok con authtoken.

### 8.2 Comandos

Terminal 1 — backend:
```bash
cd odoo
source .venv/bin/activate
python -m uvicorn main:app --host 0.0.0.0 --port 8000
```

Terminal 2 — frontend:
```bash
cd odoo-ui
ng serve --host 0.0.0.0 --port 4200
```

Terminal 3 — ngrok:
```bash
ngrok http 4200
```

Copiá la URL pública que te da ngrok y compartila.

> El frontend hace requests a `http://localhost:8000`. Si el usuario externo necesita que todo funcione, también necesitás exponer el backend con otro túnel de ngrok y cambiar la URL base en los servicios de Angular.

---

## 9. Notas técnicas importantes

### 9.1 Sobrescritura de tablas en BigQuery

Tanto el envío manual como el programado usan `WRITE_TRUNCATE`. Esto significa que la tabla destino se reemplaza completamente con los nuevos datos.

### 9.2 Tipos de datos

El sistema infiere el schema de BigQuery automáticamente a partir de los datos:

- Booleanos → `BOOLEAN`.
- Enteros → `INTEGER`.
- Decimales → `FLOAT`.
- Fechas ISO → `DATE` o `TIMESTAMP`.
- Texto u otros → `STRING`.

Si una columna tiene valores mixtos (por ejemplo, enteros y decimales), se promociona a `FLOAT` para evitar errores de carga.

### 9.3 Arrays y objetos

Si un campo de Odoo devuelve un array (por ejemplo `[id, "Nombre"]`) u objeto, se convierte a string JSON antes de subirse a BigQuery.

### 9.4 Límite de filas

El envío a BigQuery tiene un límite de **100.000 filas** por request. Para volúmenes mayores, contactar al equipo de desarrollo.

### 9.5 Schedulers y reinicios

El scheduler de APScheduler arranca automáticamente con el backend. Si reiniciás el servidor, las programaciones activas se recargan desde la base de datos.

---

## 10. Solución de problemas

### 10.1 El frontend no puede conectarse al backend

Verificá que:

- El backend esté corriendo en `http://localhost:8000`.
- No haya un firewall bloqueando el puerto.
- Si usás ngrok, el backend debe aceptar el origen del frontend ngrok.

### 10.2 Error de autenticación de BigQuery

Verificá que:

- El archivo `odoo/bigquery.txt` tenga el JSON válido de la service account.
- La variable `GOOGLE_APPLICATION_CREDENTIALS` apunte al archivo correcto.
- La service account tenga permisos de escritura en BigQuery.

### 10.3 Error "Could not convert value to integer"

Esto ocurre cuando el schema infiere un campo como entero pero aparece un decimal. Ya fue corregido escaneando todas las filas y promocionando a `FLOAT`. Si persiste, revisá que los datos no tengan strings no numéricos en campos numéricos.

### 10.4 El modal de BigQuery se corta o no deja seleccionar

Asegurate de tener la última versión del código. El modal usa `appendTo="body"` en los selects para evitar problemas de scroll y corte.

---

## 11. Glosario

| Término | Significado |
|---------|-------------|
| Query | Consulta guardada contra Odoo. |
| Dataset | Grupo de tablas dentro de BigQuery. |
| Tabla | Destino de datos dentro de un dataset. |
| Schedule | Programación automática de ejecución. |
| Run | Ejecución puntual de una schedule. |
| WRITE_TRUNCATE | Modo de escritura que reemplaza la tabla. |
| Domain | Filtro de Odoo en formato JSON. |

---

## 12. Contacto y soporte

Ante cualquier problema que no esté cubierto en este manual, contactá al equipo de desarrollo con:

- Versión del código (commit de Git).
- Mensaje de error completo.
- Pasos para reproducir el problema.
