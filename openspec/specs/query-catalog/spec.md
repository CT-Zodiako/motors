# query-catalog Specification

## Purpose

Defines the backend catalog behavior for categorizing saved Odoo queries: the
`query_categories` storage model, the protected default category, the category
management API, and category-aware query upsert, recategorization, and listing
endpoints. Out of scope: per-category permissions/roles, cascade delete, custom
category ordering, and category rename UI.

## Requirements

### Requirement: Query Category Storage

The system MUST persist query categories in a `query_categories` table with
columns: `id` SERIAL PRIMARY KEY, `name` VARCHAR(100) UNIQUE NOT NULL,
`description` TEXT, and `created_at` TIMESTAMPTZ DEFAULT NOW(). The
`odoo_queries` table MUST gain a `category_id` INTEGER column referencing
`query_categories(id)`. The migration MUST add the column using
`ALTER TABLE ... ADD COLUMN IF NOT EXISTS` semantics so it is idempotent and
re-runnable.

#### Scenario: Fresh migration creates schema

- GIVEN a database without the `query_categories` table
- WHEN the migration runs
- THEN the `query_categories` table exists with the specified columns and constraints
- AND `odoo_queries` has a `category_id` column referencing `query_categories(id)`

#### Scenario: Migration is idempotent

- GIVEN the migration has already been applied once
- WHEN the migration runs again
- THEN it MUST complete without error
- AND no duplicate tables, columns, or constraints are created

#### Scenario: Category name uniqueness enforced

- GIVEN a category named "Reports" already exists
- WHEN an insert attempts to create another category named "Reports"
- THEN the insert MUST be rejected by the unique constraint

### Requirement: Protected Default Category

The system MUST ensure a category named "General" exists after migration, and
the migration MUST backfill every existing `odoo_queries` row to "General".
"General" MUST never be deletable, regardless of whether any query references it.

#### Scenario: Existing queries backfilled to General

- GIVEN existing `odoo_queries` rows before the migration
- WHEN the migration completes
- THEN every pre-existing query MUST reference the "General" category

#### Scenario: General is never deletable

- GIVEN the "General" category exists
- WHEN a client requests `DELETE /categories/{id}` for General's id
- THEN the API MUST reject the request with 409 Conflict
- AND the category MUST remain in the database

### Requirement: Category Management API

The system MUST expose category management endpoints: `GET /categories/`
returns all categories; `POST /categories/` creates a category;
`DELETE /categories/{id}` removes a category only when nothing references it.
Deletion MUST be rejected with 409 Conflict while ANY query row references the
category, including soft-deleted or inactive queries. Creating a category with
a duplicate name MUST be rejected with 409 Conflict.

#### Scenario: List categories

- GIVEN categories exist in the database
- WHEN a client requests `GET /categories/`
- THEN the response MUST contain every category with at least its id and name

#### Scenario: Create category

- GIVEN no category named "Finance" exists
- WHEN a client sends `POST /categories/` with name "Finance"
- THEN the category MUST be created and returned with its generated id

#### Scenario: Duplicate category name rejected

- GIVEN a category named "Finance" already exists
- WHEN a client sends `POST /categories/` with name "Finance"
- THEN the API MUST respond 409 Conflict
- AND no second category with that name is created

#### Scenario: Delete unreferenced category

- GIVEN a category with no referencing query rows
- WHEN a client requests `DELETE /categories/{id}`
- THEN the category MUST be removed from the database

#### Scenario: Delete referenced category rejected

- GIVEN at least one query row references the category, including soft-deleted or inactive queries
- WHEN a client requests `DELETE /categories/{id}`
- THEN the API MUST respond 409 Conflict
- AND the category MUST remain in the database

### Requirement: Query Upsert Category Assignment

`POST /queries/` (upsert by name) MUST accept an optional `category_id`. When
`category_id` is provided on update, the query's category MUST change to it.
When `category_id` is omitted on update, the existing category MUST be
preserved. When `category_id` is omitted on create, the query MUST be assigned
the "General" category. An invalid `category_id` (referencing a nonexistent
category) MUST be rejected with 400 Bad Request or 422 Unprocessable Entity.

#### Scenario: Create with explicit category

- GIVEN a category "Finance" exists
- WHEN a client sends `POST /queries/` for a new query with `category_id` set to Finance's id
- THEN the query MUST be created referencing "Finance"

#### Scenario: Create without category defaults to General

- GIVEN a query name that does not yet exist
- WHEN a client sends `POST /queries/` without `category_id`
- THEN the query MUST be created referencing the "General" category

#### Scenario: Update without category preserves existing assignment

- GIVEN an existing query assigned to "Finance"
- WHEN a client sends `POST /queries/` for that query name without `category_id`
- THEN the query MUST remain assigned to "Finance"

#### Scenario: Update with category changes assignment

- GIVEN an existing query assigned to "General" and a category "Finance"
- WHEN a client sends `POST /queries/` for that query name with `category_id` set to Finance's id
- THEN the query MUST be assigned to "Finance"

#### Scenario: Invalid category rejected

- GIVEN no category with id 99999 exists
- WHEN a client sends `POST /queries/` with `category_id` 99999
- THEN the API MUST respond 400 Bad Request or 422 Unprocessable Entity
- AND the query MUST NOT be created or modified

### Requirement: Query Recategorization Endpoint

The system MUST expose `PATCH /queries/{name}` to change a query's category. An
invalid `category_id` MUST be rejected with 400 Bad Request or 422
Unprocessable Entity. An unknown query name MUST be rejected with 404 Not
Found.

#### Scenario: Recategorize existing query

- GIVEN a query named "daily_sales" assigned to "General" and a category "Finance"
- WHEN a client sends `PATCH /queries/daily_sales` with `category_id` set to Finance's id
- THEN the query's category MUST become "Finance"
- AND the response MUST reflect the updated category

#### Scenario: Unknown query name

- GIVEN no query named "missing_query" exists
- WHEN a client sends `PATCH /queries/missing_query`
- THEN the API MUST respond 404 Not Found

#### Scenario: Invalid category rejected

- GIVEN a query named "daily_sales" and no category with id 99999
- WHEN a client sends `PATCH /queries/daily_sales` with `category_id` 99999
- THEN the API MUST respond 400 Bad Request or 422 Unprocessable Entity
- AND the query's category MUST remain unchanged

### Requirement: Query Listing Includes Category

`GET /queries/` responses MUST include each query's category as an object with
at least `id` and `name`, resolved via join with `query_categories`. Every
listed query MUST have a non-null category.

#### Scenario: Listing embeds category object

- GIVEN a query assigned to category "Finance" with id 3
- WHEN a client requests `GET /queries/`
- THEN that query's entry MUST include a category object with id 3 and name "Finance"
