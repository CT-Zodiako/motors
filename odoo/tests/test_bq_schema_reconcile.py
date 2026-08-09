"""BQ ensure_schema reconcile for odoo_dashboards (PR-1, task 1.9).

Exercises BigQueryConfigStore.ensure_schema against a fake client: existing
legacy tables must be reconciled additively (ADD COLUMN IF NOT EXISTS for
definition/updated_at, embed_url REQUIRED -> NULLABLE relax), idempotently.
"""
import os

import pytest
from google.cloud import bigquery
from google.cloud.bigquery import SchemaField

from config_store import codecs
from config_store.bq_store import BigQueryConfigStore


class _FakeJob:
    def result(self):
        return []


class _FakeClient:
    """Minimal BigQuery client stub: one pre-existing odoo_dashboards table."""

    def __init__(self, dashboards_table=None):
        self.project = "test-project"
        self._table = dashboards_table
        self.created_tables = []
        self.updated_tables = []
        self.queries = []

    def get_dataset(self, ref):
        return object()

    def get_table(self, ref):
        if ref.table_id == "odoo_dashboards" and self._table is not None:
            return self._table
        raise Exception("Not found")

    def create_table(self, table, exists_ok=False):
        self.created_tables.append(table)
        return table

    def update_table(self, table, fields):
        self.updated_tables.append((table, fields))
        return table

    def query(self, stmt, job_config=None):
        self.queries.append(stmt)
        return _FakeJob()


def _table(schema):
    ref = bigquery.DatasetReference("test-project", "config").table("odoo_dashboards")
    return bigquery.Table(ref, schema=schema)


def _legacy_table():
    return _table([
        SchemaField("id", "INT64", mode="REQUIRED"),
        SchemaField("menu_key", "STRING", mode="REQUIRED"),
        SchemaField("name", "STRING", mode="REQUIRED"),
        SchemaField("embed_url", "STRING", mode="REQUIRED"),
        SchemaField("active", "BOOL", mode="REQUIRED"),
        SchemaField("created_at", "TIMESTAMP", mode="REQUIRED"),
    ])


def _current_table():
    return _table([
        SchemaField(c["name"], c["type"], mode=c["mode"])
        for c in codecs.TABLE_SCHEMAS["odoo_dashboards"]
    ])


@pytest.fixture(autouse=True)
def _dataset_env(monkeypatch):
    monkeypatch.setenv("BQ_CONFIG_DATASET", "config")


class TestEnsureSchemaReconcile:
    def test_adds_missing_columns_via_alter(self):
        client = _FakeClient(_legacy_table())
        BigQueryConfigStore(client=client).ensure_schema()
        alters = [q for q in client.queries if q.startswith("ALTER TABLE")]
        assert any("ADD COLUMN IF NOT EXISTS definition JSON" in q for q in alters)
        assert any("ADD COLUMN IF NOT EXISTS updated_at TIMESTAMP" in q for q in alters)

    def test_relaxes_embed_url_mode_via_merged_schema(self):
        client = _FakeClient(_legacy_table())
        BigQueryConfigStore(client=client).ensure_schema()
        assert len(client.updated_tables) == 1
        table, fields = client.updated_tables[0]
        assert fields == ["schema"]
        merged = {f.name: f for f in table.schema}
        assert merged["embed_url"].mode == "NULLABLE"
        # Merged schema must not drop any column (new columns included so the
        # update does not try to remove what the ALTER just added).
        assert set(merged) == {
            "id", "menu_key", "name", "embed_url", "definition",
            "active", "created_at", "updated_at",
        }

    def test_idempotent_noop_when_schema_current(self):
        client = _FakeClient(_current_table())
        BigQueryConfigStore(client=client).ensure_schema()
        alters = [q for q in client.queries if q.startswith("ALTER TABLE")]
        assert alters == []
        assert client.updated_tables == []

    def test_creates_table_when_missing(self):
        client = _FakeClient(None)
        BigQueryConfigStore(client=client).ensure_schema()
        created = {t.table_id for t in client.created_tables}
        assert "odoo_dashboards" in created
