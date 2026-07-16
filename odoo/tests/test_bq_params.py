"""Deterministic unit tests for bq_store parameter builders (P1).

These are the first tests that import bq_store directly and exercise _json_param
without a real BigQuery client.
"""
import pytest
from config_store.bq_store import _json_param, _build_params
from google.cloud import bigquery


class TestJsonParam:
    def test_json_param_returns_scalar_query_parameter(self):
        p = _json_param("domain", [["customer_rank", ">", 0]])
        assert isinstance(p, bigquery.ScalarQueryParameter)
        assert p.name == "domain"
        assert p.type_ == "STRING"
        assert isinstance(p.value, str)
        assert "customer_rank" in p.value

    def test_json_param_compact_separators(self):
        p = _json_param("fields", ["name", "email"])
        # separators=(",", ":") removes spaces after colon/comma
        assert p.value == '["name","email"]'

    def test_json_param_non_ascii(self):
        p = _json_param("description", {"label": "Facturación"})
        assert "Facturación" in p.value

    def test_json_param_none(self):
        p = _json_param("last_schema", None)
        assert p.value == "null"


class TestBuildParams:
    def test_build_params_odoo_queries(self):
        row = {
            "id": 1,
            "name": "q1",
            "description": None,
            "model": "res.partner",
            "method": "search_read",
            "domain": [["active", "=", True]],
            "fields": ["name"],
            "limit_val": 10,
            "active": True,
            "created_at": None,
            "category_id": 2,
        }
        params = _build_params("odoo_queries", row)
        names = {p.name for p in params}
        assert names == set(row.keys())
        domain_p = [p for p in params if p.name == "domain"][0]
        assert domain_p.type_ == "STRING"
        assert "active" in domain_p.value

    def test_build_params_query_destinations(self):
        row = {
            "id": 1,
            "query_name": "q1",
            "dataset_id": "ds",
            "table_id": "tbl",
            "origin": "schedule",
            "stale": False,
            "last_error": None,
            "last_sync_at": None,
            "last_schema": {"a": "STRING"},
            "created_at": None,
        }
        params = _build_params("query_destinations", row)
        schema_p = [p for p in params if p.name == "last_schema"][0]
        assert schema_p.type_ == "STRING"
        assert schema_p.value == '{"a":"STRING"}'
