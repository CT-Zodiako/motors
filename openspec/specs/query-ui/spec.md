# query-ui Specification

## Purpose

Defines the Angular frontend behavior for query categories: category selection
and inline creation in the save wizard, category grouping and recategorization
in the query list, category grouping in the runner selector, and the default
query limit bugfix. Out of scope: per-category permissions/roles, cascade
delete, custom category ordering, and category rename UI.

## Requirements

### Requirement: Wizard Category Selection

The wizard Save step MUST present a category selector with "General"
preselected by default. The selector MUST offer inline "Nueva categoría…"
creation that POSTs the new category and preselects it in the wizard. Duplicate
category names MUST be handled gracefully with user-visible feedback and
without losing wizard state.

#### Scenario: General preselected by default

- GIVEN the user reaches the Save step of the wizard
- WHEN the category selector renders
- THEN "General" MUST be the preselected value

#### Scenario: Inline category creation preselects the new category

- GIVEN the Save step category selector
- WHEN the user chooses "Nueva categoría…", enters "Finance", and confirms
- THEN the UI MUST POST the new category to the backend
- AND "Finance" MUST become the selected category in the wizard

#### Scenario: Duplicate category name handled gracefully

- GIVEN a category named "Finance" already exists
- WHEN the user attempts inline creation of "Finance"
- THEN the UI MUST show user-visible feedback about the duplicate name
- AND the wizard MUST retain its current state (query definition and selections)

### Requirement: Query List Grouped by Category

The query list MUST group rows by category using groupRowsBy, with groups
ordered alphabetically by category name. Each row MUST expose a recategorize
action that changes the query's category.

#### Scenario: Groups ordered alphabetically by category name

- GIVEN queries in categories "Finance", "General", and "Audit"
- WHEN the query list renders
- THEN groups MUST appear in alphabetical order: "Audit", "Finance", "General"
- AND each row MUST appear under its query's category group

#### Scenario: Recategorize from the list

- GIVEN a query row under the "General" group and a category "Finance"
- WHEN the user invokes the row's recategorize action and selects "Finance"
- THEN the query MUST move to the "Finance" group in the list
- AND the change MUST persist to the backend

### Requirement: Runner Selector Grouped by Category

The runner's query selector MUST group its options by category.

#### Scenario: Options grouped by category

- GIVEN saved queries in categories "General" and "Finance"
- WHEN the user opens the runner query selector
- THEN options MUST be grouped under their category names
- AND each query MUST appear under its assigned category group

### Requirement: Default Query Limit on Save

Saved queries MUST NOT persist `limit_val: 0`. When the user does not set an
explicit limit, the wizard MUST store the default limit of 100.

#### Scenario: Save without explicit limit stores default

- GIVEN the user completes the wizard without setting a limit
- WHEN the query is saved
- THEN the stored query MUST have `limit_val` 100, not 0

#### Scenario: Explicit limit preserved

- GIVEN the user sets a limit of 250 in the wizard
- WHEN the query is saved
- THEN the stored query MUST have `limit_val` 250
