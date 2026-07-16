"""SQL templates — parameterized BigQuery DML statements.

All templates use @param style for ScalarQueryParameter binding.
Table names are module constants (never user-input for config tables).
"""
from __future__ import annotations

import os
import re

# ---------------------------------------------------------------------------
# Dataset — single source of truth for the config dataset name (D-A)
# ---------------------------------------------------------------------------
_DATASET_RE = re.compile(r"^[A-Za-z0-9_]+$")


def _dataset() -> str:
    """Return the config dataset name from env var (evaluated at call time, not import)."""
    val = os.getenv("BQ_CONFIG_DATASET", "config")
    if not _DATASET_RE.match(val):
        raise ValueError(f"BQ_CONFIG_DATASET must match ^[A-Za-z0-9_]+$: {val!r}")
    return val


def _t(table: str) -> str:
    """Return fully-qualified table name for the config dataset."""
    return f"{_dataset()}.{table}"


# ---------------------------------------------------------------------------
# Table name helpers (D-A: dynamic dataset resolution)
# ---------------------------------------------------------------------------
def T_QUERIES() -> str:
    return _t("odoo_queries")


def T_CATEGORIES() -> str:
    return _t("query_categories")


def T_SCHEDULES() -> str:
    return _t("query_schedules")


def T_RUNS() -> str:
    return _t("query_schedule_runs")


def T_DESTINATIONS() -> str:
    return _t("query_destinations")


# ---------------------------------------------------------------------------
# Categories
# ---------------------------------------------------------------------------
SQL_LIST_CATEGORIES = lambda: f"SELECT * FROM `{_t('query_categories')}` ORDER BY lower(name)"
SQL_GET_CATEGORY_BY_ID = lambda: f"SELECT * FROM `{_t('query_categories')}` WHERE id = @id"
SQL_GET_CATEGORY_BY_NAME = lambda: f"SELECT * FROM `{_t('query_categories')}` WHERE name = @name"
SQL_INSERT_CATEGORY = lambda: f"""
INSERT INTO `{_t('query_categories')}` (id, name, description, created_at)
VALUES (@id, @name, @description, @created_at)
"""
SQL_DELETE_CATEGORY = lambda: f"DELETE FROM `{_t('query_categories')}` WHERE id = @id"
SQL_COUNT_CATEGORIES_BY_NAME = lambda: f"SELECT COUNT(*) AS n FROM `{_t('query_categories')}` WHERE name = @name"
SQL_COUNT_CATEGORIES = lambda: f"SELECT COUNT(*) AS n FROM `{_t('query_categories')}`"
SQL_COUNT_QUERIES_BY_CATEGORY = lambda: f"SELECT COUNT(*) AS n FROM `{_t('odoo_queries')}` WHERE category_id = @category_id"
SQL_COUNT_QUERIES = lambda: f"SELECT COUNT(*) AS n FROM `{_t('odoo_queries')}`"

# ---------------------------------------------------------------------------
# Queries
# ---------------------------------------------------------------------------
SQL_LIST_QUERIES = lambda: f"SELECT * FROM `{_t('odoo_queries')}` ORDER BY id"
SQL_GET_QUERY_BY_NAME = lambda: f"SELECT * FROM `{_t('odoo_queries')}` WHERE name = @name"
SQL_MERGE_QUERY = lambda: f"""
MERGE `{_t('odoo_queries')}` AS target
USING (SELECT @id AS id, @name AS name, @description AS description,
       @model AS model, @method AS method,
       PARSE_JSON(@domain) AS domain, PARSE_JSON(@fields) AS fields,
       @limit_val AS limit_val, @active AS active,
       @created_at AS created_at, @category_id AS category_id) AS source
ON target.name = source.name
WHEN MATCHED THEN UPDATE SET
  id = source.id, description = source.description, model = source.model,
  method = source.method, domain = source.domain, fields = source.fields,
  limit_val = source.limit_val, active = source.active,
  created_at = source.created_at, category_id = source.category_id
WHEN NOT MATCHED THEN INSERT (id, name, description, model, method, domain, fields, limit_val, active, created_at, category_id)
VALUES (source.id, source.name, source.description, source.model, source.method, source.domain, source.fields, source.limit_val, source.active, source.created_at, source.category_id)
"""
SQL_UPDATE_QUERY = lambda: f"""
UPDATE `{_t('odoo_queries')}`
SET description = @description, domain = PARSE_JSON(@domain), fields = PARSE_JSON(@fields),
    limit_val = @limit_val, category_id = @category_id
WHERE name = @name
"""
SQL_DEACTIVATE_QUERY = lambda: f"UPDATE `{_t('odoo_queries')}` SET active = FALSE WHERE name = @name"
# ---------------------------------------------------------------------------
# Schedules
# ---------------------------------------------------------------------------
SQL_LIST_SCHEDULES = lambda: f"SELECT * FROM `{_t('query_schedules')}` ORDER BY id"
SQL_GET_SCHEDULE_BY_ID = lambda: f"SELECT * FROM `{_t('query_schedules')}` WHERE id = @id"
SQL_INSERT_SCHEDULE = lambda: f"""
INSERT INTO `{_t('query_schedules')}` (id, name, query_name, dataset_id, table_id, frequency,
  hour, minute, day_of_week, day_of_month, interval_hours, active, created_at)
VALUES (@id, @name, @query_name, @dataset_id, @table_id, @frequency,
  @hour, @minute, @day_of_week, @day_of_month, @interval_hours, @active, @created_at)
"""
SQL_UPDATE_SCHEDULE = lambda: f"""
UPDATE `{_t('query_schedules')}`
SET name = @name, query_name = @query_name, dataset_id = @dataset_id, table_id = @table_id,
    frequency = @frequency, hour = @hour, minute = @minute, day_of_week = @day_of_week,
    day_of_month = @day_of_month, interval_hours = @interval_hours, active = @active
WHERE id = @id
"""
SQL_DELETE_SCHEDULE = lambda: f"DELETE FROM `{_t('query_schedules')}` WHERE id = @id"
# ---------------------------------------------------------------------------
# Runs
# ---------------------------------------------------------------------------
SQL_LIST_RUNS = lambda: f"SELECT * FROM `{_t('query_schedule_runs')}` WHERE schedule_id = @schedule_id ORDER BY id DESC"
SQL_INSERT_RUN = lambda: f"""
INSERT INTO `{_t('query_schedule_runs')}` (id, schedule_id, started_at, status)
VALUES (@id, @schedule_id, @started_at, @status)
"""
SQL_UPDATE_RUN = lambda: f"""
UPDATE `{_t('query_schedule_runs')}`
SET finished_at = @finished_at, status = @status, message = @message, rows_loaded = @rows_loaded
WHERE id = @id
"""
SQL_DELETE_RUNS_BY_SCHEDULE = lambda: f"DELETE FROM `{_t('query_schedule_runs')}` WHERE schedule_id = @schedule_id"
SQL_GET_RUN_BY_ID = lambda: f"SELECT * FROM `{_t('query_schedule_runs')}` WHERE id = @id"
SQL_UPDATE_SCHEDULE_LAST_RUN = lambda: f"""
UPDATE `{_t('query_schedules')}`
SET last_run_at = @last_run_at, last_run_status = @last_run_status, last_run_message = @last_run_message
WHERE id = @id
"""

# ---------------------------------------------------------------------------
# Destinations
# ---------------------------------------------------------------------------
SQL_LIST_DESTINATIONS = lambda: f"SELECT * FROM `{_t('query_destinations')}` ORDER BY id"
SQL_GET_DESTINATION = lambda: f"""
SELECT * FROM `{_t('query_destinations')}`
WHERE query_name = @query_name AND dataset_id = @dataset_id AND table_id = @table_id
"""
SQL_MERGE_DESTINATION = lambda: f"""
MERGE `{_t('query_destinations')}` AS target
USING (SELECT @id AS id, @query_name AS query_name, @dataset_id AS dataset_id, @table_id AS table_id,
       @origin AS origin, @stale AS stale, @last_error AS last_error,
       @last_sync_at AS last_sync_at, PARSE_JSON(@last_schema) AS last_schema, @created_at AS created_at) AS source
ON target.query_name = source.query_name AND target.dataset_id = source.dataset_id AND target.table_id = source.table_id
WHEN MATCHED THEN UPDATE SET
  id = source.id, origin = source.origin, stale = source.stale, last_error = source.last_error,
  last_sync_at = source.last_sync_at, last_schema = source.last_schema, created_at = source.created_at
WHEN NOT MATCHED THEN INSERT (id, query_name, dataset_id, table_id, origin, stale, last_error, last_sync_at, last_schema, created_at)
VALUES (source.id, source.query_name, source.dataset_id, source.table_id, source.origin, source.stale, source.last_error, source.last_sync_at, source.last_schema, source.created_at)
"""
SQL_UPDATE_DESTINATION_STALE = lambda: f"""
UPDATE `{_t('query_destinations')}`
SET stale = @stale, last_error = @last_error
WHERE query_name = @query_name AND dataset_id = @dataset_id AND table_id = @table_id
"""
SQL_DELETE_DESTINATIONS_BY_QUERY = lambda: f"DELETE FROM `{_t('query_destinations')}` WHERE query_name = @query_name"