# Odoo Bridge UI

Frontend en Angular para gestionar y ejecutar consultas registradas en la base de datos PostgreSQL local, que actúan como puente hacia la API de Odoo.

## Stack

- **Angular 21** (standalone components, signals)
- **Node.js 24**

## Requisitos previos

- Node.js 18+
- Angular CLI 21: `npm install -g @angular/cli`
- La API del backend corriendo en `http://localhost:8000`

---

## 1. Instalar dependencias

```bash
npm install
```

---

## 2. Levantar el servidor de desarrollo

```bash
ng serve
```

La app queda disponible en `http://localhost:4200`.

> El backend debe estar corriendo en `http://localhost:8000` para que las llamadas funcionen.

---

## 3. Build para producción

```bash
ng build
```

Los archivos compilados quedan en `dist/odoo-ui/`.

---

## Secciones de la app

### Queries
Lista todos los queries registrados en la base de datos PostgreSQL con su modelo, método, límite y estado. Permite desactivar queries desde la tabla.

### Nuevo Query
Wizard de 4 pasos para crear consultas sin conocimiento técnico:

1. **Modelo** — elige entre los más usados o busca cualquier módulo de Odoo
2. **Campos** — checkboxes con los campos disponibles, cargados en vivo desde Odoo
3. **Filtros** — constructor visual de condiciones (sin JSON)
4. **Guardar** — nombre, límite y confirmación

### Ejecutar
Seleccioná un query registrado, ejecutalo contra Odoo y visualizá los resultados en tabla.

Permite elegir qué columnas mostrar y exportar en:
- **CSV**
- **Excel**
- **SQL para PostgreSQL** (con `CREATE TABLE IF NOT EXISTS`)
- **SQL para Oracle** (con bloque de excepción para tabla existente)

---

## Estructura del proyecto

```
src/app/
├── pages/
│   ├── query-list/      # Listado y desactivación de queries
│   ├── query-create/    # Wizard de creación
│   └── query-runner/    # Ejecución y exportación
└── services/
    └── odoo-queries.ts  # Servicio HTTP hacia el backend
```
