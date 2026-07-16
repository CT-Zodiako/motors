"""Live BigQuery config store tests — env-gated (D13).

Skipped unless BQ_LIVE_TESTS=1 and credentials available.
Uses BQ_CONFIG_DATASET=config_test for isolation (D-A).
"""
import os
import time
import pytest

pytestmark = pytest.mark.skipif(
    os.getenv("BQ_LIVE_TESTS") != "1",
    reason="BQ_LIVE_TESTS not set to 1",
)


class TestLiveConfigStore:
    """Smoke CRUD against real BigQuery dataset config_test."""

    @pytest.fixture(autouse=True)
    def _use_config_test_dataset(self, monkeypatch):
        # D-A: redirect ALL config-store access (SQL templates + load jobs) to the
        # sandbox dataset for the duration of each test, without leaking env at
        # collection time (module-level os.environ writes pollute the suite).
        monkeypatch.setenv("BQ_CONFIG_DATASET", "config_test")

    def _store(self):
        from config_store.bq_store import BigQueryConfigStore
        return BigQueryConfigStore()

    def test_ensure_schema(self):
        store = self._store()
        store.ensure_schema()

    def test_seed_defaults(self):
        store = self._store()
        store.ensure_schema()
        store.seed_defaults()
        cats = store.list_categories()
        assert any(c["name"] == "General" for c in cats)

    def test_create_and_list_category(self):
        store = self._store()
        store.ensure_schema()
        # Unique per run: config_test persists between executions, so a fixed
        # name would collide on re-runs (ConflictError by design).
        name = f"LiveTest_{int(time.time())}"
        c = store.create_category(name, "desc")
        assert c["name"] == name
        cats = store.list_categories()
        assert any(x["name"] == name for x in cats)

    def test_idempotent_re_run(self):
        """D-A/D14: second run must not duplicate seeds or categories."""
        store = self._store()
        store.ensure_schema()
        store.seed_defaults()
        cats1 = len(store.list_categories())
        qs1 = len(store.list_queries())
        store.seed_defaults()
        assert len(store.list_categories()) == cats1
        assert len(store.list_queries()) == qs1
