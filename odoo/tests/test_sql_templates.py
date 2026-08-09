"""SQL snapshot tests — assert exact statement text per operation (D13)."""
from config_store import sql


class TestSqlTemplates:
    """Verify SQL templates are parameterized and do not interpolate values."""

    def test_dataset_derives_from_env(self, monkeypatch):
        """D-A: table references must derive from BQ_CONFIG_DATASET env var."""
        monkeypatch.setenv("BQ_CONFIG_DATASET", "sentinel_dataset")
        # Force re-import by clearing cache and re-importing
        import importlib
        import sys
        # Remove cached module if present
        if "config_store.sql" in sys.modules:
            del sys.modules["config_store.sql"]
        from config_store import sql as sql_mod
        assert "sentinel_dataset.odoo_queries" in sql_mod.T_QUERIES()
        assert "sentinel_dataset.query_categories" in sql_mod.T_CATEGORIES()
        assert "sentinel_dataset.query_schedules" in sql_mod.T_SCHEDULES()
        assert "sentinel_dataset.query_schedule_runs" in sql_mod.T_RUNS()
        assert "sentinel_dataset.query_destinations" in sql_mod.T_DESTINATIONS()

    def test_list_categories_ordering(self):
        stmt = sql.SQL_LIST_CATEGORIES()
        assert "ORDER BY lower(name)" in stmt
        assert "config.query_categories" in stmt

    def test_get_category_by_id_parameterized(self):
        stmt = sql.SQL_GET_CATEGORY_BY_ID()
        assert "@id" in stmt
        assert "'" not in stmt  # no string literals

    def test_merge_query_uses_parse_json(self):
        stmt = sql.SQL_MERGE_QUERY()
        assert "PARSE_JSON(@domain)" in stmt
        assert "PARSE_JSON(@fields)" in stmt

    def test_insert_run_parameterized(self):
        stmt = sql.SQL_INSERT_RUN()
        assert "@id" in stmt
        assert "@schedule_id" in stmt
        assert "@started_at" in stmt
        assert "@status" in stmt

    def test_update_run_parameterized(self):
        stmt = sql.SQL_UPDATE_RUN()
        assert "@finished_at" in stmt
        assert "@status" in stmt
        assert "@message" in stmt
        assert "@rows_loaded" in stmt
        assert "@id" in stmt

    def test_merge_destination_compound_key(self):
        stmt = sql.SQL_MERGE_DESTINATION()
        assert "target.query_name = source.query_name" in stmt
        assert "target.dataset_id = source.dataset_id" in stmt
        assert "target.table_id = source.table_id" in stmt

    def test_delete_runs_by_schedule_parameterized(self):
        stmt = sql.SQL_DELETE_RUNS_BY_SCHEDULE()
        assert "@schedule_id" in stmt

    def test_delete_destinations_by_query_parameterized(self):
        stmt = sql.SQL_DELETE_DESTINATIONS_BY_QUERY()
        assert "@query_name" in stmt



class TestDashboardSqlTemplates:
    """dashboard-crud-menu PR-1: dashboard CRUD templates (design §3.2)."""

    def test_list_dashboards_published_only(self):
        stmt = sql.SQL_LIST_DASHBOARDS()
        assert "active = true" in stmt
        assert "ORDER BY lower(name)" in stmt
        assert "config.odoo_dashboards" in stmt

    def test_list_all_dashboards(self):
        stmt = sql.SQL_LIST_ALL_DASHBOARDS()
        assert "active = true" not in stmt
        assert "ORDER BY lower(name)" in stmt

    def test_get_dashboard_any_by_menu_key(self):
        stmt = sql.SQL_GET_DASHBOARD_ANY_BY_MENU_KEY()
        assert "@menu_key" in stmt
        assert "active" not in stmt

    def test_count_dashboards_by_menu_key(self):
        stmt = sql.SQL_COUNT_DASHBOARDS_BY_MENU_KEY()
        assert "COUNT(*)" in stmt
        assert "@menu_key" in stmt

    def test_insert_dashboard_nullable_json_guard(self):
        stmt = sql.SQL_INSERT_DASHBOARD()
        assert "IF(@definition IS NULL, NULL, PARSE_JSON(@definition))" in stmt
        for p in ("@id", "@menu_key", "@name", "@embed_url", "@active", "@created_at", "@updated_at"):
            assert p in stmt

    def test_update_dashboard_keyed_on_id(self):
        stmt = sql.SQL_UPDATE_DASHBOARD()
        assert "IF(@definition IS NULL, NULL, PARSE_JSON(@definition))" in stmt
        assert "WHERE id = @id" in stmt
        assert "updated_at = @updated_at" in stmt

    def test_delete_dashboard_keyed_on_id(self):
        stmt = sql.SQL_DELETE_DASHBOARD()
        assert "DELETE FROM" in stmt
        assert "WHERE id = @id" in stmt
