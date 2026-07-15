# Design — Query Categories (`query-categories`)

## Context

Approved proposal: `openspec/changes/query-categories/proposal.md`.
Specs to satisfy: `specs/query-catalog/spec.md` (6 requirements), `specs/query-ui/spec.md` (4 requirements).

Backend: FastAPI + psycopg2 (`odoo/db.py` helpers `query()`/`execute()`), routers registered in `odoo/main.py`. Frontend: Angular standalone, tab navigation, PrimeNG, one service per backend area in `odoo-ui/src/app/services/`.

## Goals / Non-goals

Goals: the 10 approved decisions, implemented per the two specs.
Non-goals: category permissions, cascade delete, custom ordering, category rename UI, Alembic-style migration tooling.

## Decision D1 — Migration lives in `init_db.py` as idempotent steps

Extend `init_db()` with ordered, re-runnable steps:

```sql
-- 1. new table
CREATE TABLE IF NOT EXISTS query_categories (
    id          SERIAL PRIMARY KEY,
    name        VARCHAR(100) NOT NULL UNIQUE,
    description TEXT,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
-- 2. new column (live DBs: CREATE TABLE IF NOT EXISTS never alters)
ALTER TABLE odoo_queries
    ADD COLUMN IF NOT EXISTS category_id INTEGER REFERENCES query_categories(id);
-- 3. protected default
INSERT INTO query_categories (name, description)
VALUES ('General', 'Default category')
ON CONFLICT (name) DO NOTHING;
-- 4. backfill
UPDATE odoo_queries
SET category_id = (SELECT id FROM query_categories WHERE name = 'General')
WHERE category_id IS NULL;
```

Ordering is mandatory: table → column → General → backfill.
**Tradeoff**: extending `init_db.py` (chosen) vs adding Alembic. The project has no migration tool; four idempotent statements cover this change. Alembic is rejected as scope creep (non-goal), but the pattern established here (ordered idempotent steps in init_db) is the documented convention until a migration tool is adopted.
**Rejected alternative**: making `category_id NOT NULL DEFAULT` — not possible portably on existing rows without the backfill first; the column stays nullable at DB level, "every query has a category" is enforced at API level (default General on create, JOIN with COALESCE/INNER JOIN on read).

## Decision D2 — Categories API in a new router `odoo/routers/categories.py`

`APIRouter(prefix="/categories", tags=["categories"])`, registered in `main.py` next to the existing routers. Models:

```python
class CategoryIn(BaseModel):      # POST body
    name: str = Field(min_length=1, max_length=100)
    description: str | None = None

class CategoryOut(BaseModel):     # response
    id: int
    name: str
    description: str | None
    created_at: datetime
```

Endpoints:
- `GET /categories/` → `SELECT ... ORDER BY name ASC` (alphabetical, per UI grouping decision).
- `POST /categories/` → 201; catch `psycopg2.errors.UniqueViolation` → 409 `{"detail": "Category name already exists"}`.
- `DELETE /categories/{id}` → 404 if missing; 409 if name = 'General'; 409 if `SELECT COUNT(*) FROM odoo_queries WHERE category_id = %s` > 0 (counts inactive rows too — per spec); else delete, 204.

**Tradeoff**: 409 for General-delete (chosen, per spec assumption) vs 403. Single error shape (`409 Conflict`) for all "cannot delete" cases keeps frontend handling trivial: one branch shows "no se puede borrar esta categoría".

## Decision D3 — `catalog.py` becomes category-aware

- `QueryIn` gains `category_id: int | None = None`.
- `register_query` (POST upsert):
  - Validate `category_id` when provided: `SELECT id FROM query_categories WHERE id = %s` → 422 if missing.
  - INSERT branch: `COALESCE(%s, (SELECT id FROM query_categories WHERE name='General'))` for category (omitted-on-create → General).
  - `ON CONFLICT (name) DO UPDATE`: category assignment uses `COALESCE(EXCLUDED.category_id, odoo_queries.category_id)` (omitted-on-update preserves).
- `PATCH /queries/{name}` with body `{"category_id": int}`: 404 unknown query (check `active = TRUE` — recategorizing soft-deleted queries is not exposed), 422 invalid category, else `UPDATE ... SET category_id` and return the updated query.
- `GET /queries/` and `GET /queries/{name}`: `LEFT JOIN query_categories` and embed `"category": {"id": ..., "name": ...}` via a `QueryOut` response model.

**Tradeoff**: embedded category object `{id, name}` (chosen) vs flat `category_name` string. The object survives a future category rename without breaking consumers and gives the UI the id for recategorize calls without a second lookup. Cost: a response-shape change — additive, existing fields untouched (spec R6).

## Decision D4 — Frontend service split per project convention

New `odoo-ui/src/app/services/categories.ts` (`CategoriesService`): `list()`, `create(name, description?)`, `remove(id)`. `odoo-queries.ts` gains: `category` on `OdooQuery` (`{id: number; name: string}`), `categoryId?` on `CreateQueryPayload`, and `updateCategory(name, categoryId)` → `PATCH`.
**Tradeoff**: separate service (chosen, matches "one service per backend area") vs extending `OdooQueriesService` — rejected, it would mix two backend routers in one client.

## Decision D5 — Wizard: category select + inline create + limit input

Save step (`query-create.html`, lines ~241-256 area):
- `p-select` bound to a `selectedCategoryId` signal; options from `CategoriesService.list()` loaded in `ngOnInit`; default = the option whose name is 'General' (fallback: first option).
- "Nueva categoría…" option/row opens a small inline prompt (PrimeNG `p-dialog` or inline input row); on confirm → `create()` → on 409 show `p-message`/"ya existe" and keep wizard state; on success push into options and select it.
- Limit: add `p-inputnumber` bound to `limitVal` signal, default 100; `save()` sends `limit_val: this.limitVal()` instead of hardcoded 0 (satisfies both limit scenarios: default 100, explicit preserved).

## Decision D6 — Query list: grouped table with inline recategorize

- After `load()`, compute a sorted copy by `category.name` then `name`, and set `groupRowsBy="category.name"` on the `p-table` with a subheader row template rendering the category name.
- Recategorize: a `p-select` of categories in a new "Categoría" column cell; `(onChange)` → `OdooQueriesService.updateCategory(name, id)` → on success update the row + `p-toast` confirm; on error revert the select and toast the detail.

**Tradeoff**: inline row select (chosen) vs a dialog with confirm — inline is one click fewer and the operation is low-risk and reversible; spec only requires "a recategorize action".

## Decision D7 — Runner: grouped select

`query-runner.ts` transforms the flat active-query list into PrimeNG group structure: `[{label: categoryName, items: [...queries]}]` sorted alphabetically by category, then `p-select [group]="true"` with `optionGroupLabel="label"` / `optionGroupChildren="items"`. No backend change (list already embeds category).

## Test strategy (STRICT TDD — `openspec/config.yaml` declares `strict_tdd: true`)

RED → GREEN → TRIANGULATE → REFACTOR with recorded evidence.

- **Frontend** (configured runner: `cd odoo-ui && npm test`): component/service specs for wizard (default category preselected, inline create success + 409 path, limit default 100 / explicit 250), list (group order alphabetical, recategorize calls service and moves row), runner (grouped options shape), service methods (HTTP mocks).
- **Backend gap**: no Python test runner is configured (config `testing.commands.unit` only covers odoo-ui). **Decision**: introduce `pytest` + FastAPI `TestClient` for `odoo/`, tests hitting the real local Postgres via the existing `db.py` (test cases create-and-clean their own fixtures; no prod data touched). Tests: migration idempotency (run `init_db()` twice), backfill, CRUD categories incl. all 409/404 branches, upsert preserve/change/default, PATCH, listing shape. Command: `cd odoo && .venv/bin/python -m pytest -q`. This adds a test layer the repo lacks — recorded as a design risk, and `openspec/config.yaml` should be extended at verify time with the backend unit command.

## File-by-file plan (line estimates for the Review Workload Guard)

| File | Change | Est. lines |
|---|---|---|
| `odoo/init_db.py` | D1 migration steps | +45 |
| `odoo/seeds.py` | seed categories + category_id per query | +30 |
| `odoo/routers/categories.py` | new router (D2) | +95 |
| `odoo/routers/catalog.py` | D3: QueryIn, join, upsert, PATCH | +70/-15 |
| `odoo/main.py` | register router | +2 |
| `odoo/tests/test_categories.py` + `test_catalog_categories.py` | new pytest suites | +160 |
| `odoo/requirements.txt` | pytest, httpx (TestClient dep) | +2 |
| `odoo/QUERIES.md` | document category fields/endpoints | +35 |
| `odoo-ui/.../services/categories.ts` | new service (D4) | +45 |
| `odoo-ui/.../services/odoo-queries.ts` | D4 contract + patch | +25 |
| `odoo-ui/.../query-create.ts/.html` | D5 | +80 |
| `odoo-ui/.../query-list.ts/.html` | D6 | +90 |
| `odoo-ui/.../query-runner.ts/.html` | D7 | +30 |
| frontend specs | D5–D7 tests | +130 |

**Forecast: ≈ 770 changed lines — EXCEEDS the 400-line review budget.**

Recommended delivery (auto-forecast, per chained-pr strategy): two chained PRs —
- **PR1 (backend, ≈ 410 lines)**: migration, seeds, categories router, catalog changes, pytest suites, QUERIES.md.
- **PR2 (frontend, ≈ 360 lines, stacks on PR1)**: services, wizard, list, runner, specs.

## Risks

- **R1** Live DB: migration must run before new backend deploys; it is re-runnable (all steps idempotent).
- **R2** Upsert regression: the `COALESCE(EXCLUDED.category_id, ...)` expression is the highest-risk line — covered by explicit preserve/change tests.
- **R3** New pytest layer: first Python tests in the repo; if the local Postgres is unavailable in CI/dev, backend tests need the documented local DB (`docker-compose.yml`).
- **R4** Grouped `p-table`/`p-select` API differences across PrimeNG versions — verify against the installed PrimeNG major before apply (check `odoo-ui/package.json`).
- **R5** Review workload: forecast exceeds 400 lines; delivery decision (chained vs single) required before `sdd-apply`.
