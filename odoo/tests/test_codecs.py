"""Tests for config_store codecs — RED phase (no implementation yet)."""
import pytest
from config_store.codecs import TABLE_SCHEMAS, encode_row, decode_row
from config_store.errors import ValidationError


class TestTableSchemas:
    """V1: exact columns from init_db.py DDL."""

    def test_odoo_queries_columns(self):
        cols = TABLE_SCHEMAS["odoo_queries"]
        names = [c["name"] for c in cols]
        assert names == [
            "id", "name", "description", "model", "method",
            "domain", "fields", "limit_val", "active", "created_at", "category_id",
        ]
        assert cols[0]["type"] == "INT64"   # id
        assert cols[1]["type"] == "STRING"  # name
        assert cols[5]["type"] == "JSON"   # domain
        assert cols[6]["type"] == "JSON"   # fields
        assert cols[8]["type"] == "BOOL"    # active
        assert cols[10]["type"] == "INT64" # category_id

    def test_query_schedules_columns(self):
        cols = TABLE_SCHEMAS["query_schedules"]
        names = [c["name"] for c in cols]
        assert "frequency" in names
        assert "hour" in names
        assert "minute" in names
        assert "day_of_week" in names
        assert "day_of_month" in names
        assert "interval_hours" in names
        assert "last_run_at" in names
        assert "last_run_status" in names
        assert "last_run_message" in names

    def test_query_schedule_runs_columns(self):
        cols = TABLE_SCHEMAS["query_schedule_runs"]
        names = [c["name"] for c in cols]
        assert "schedule_id" in names
        assert "started_at" in names
        assert "finished_at" in names
        assert "status" in names
        assert "message" in names
        assert "rows_loaded" in names

    def test_query_categories_columns(self):
        cols = TABLE_SCHEMAS["query_categories"]
        names = [c["name"] for c in cols]
        assert names == ["id", "name", "description", "created_at"]

    def test_query_destinations_columns(self):
        cols = TABLE_SCHEMAS["query_destinations"]
        names = [c["name"] for c in cols]
        assert "query_name" in names
        assert "dataset_id" in names
        assert "table_id" in names
        assert "origin" in names
        assert "stale" in names
        assert "last_error" in names
        assert "last_sync_at" in names
        assert "last_schema" in names


class TestEncodeDecode:
    """Round-trip encoding/decoding for all types."""

    def test_json_key_order_roundtrip(self):
        """JSON values must round-trip with key order preserved."""
        row = {"id": 1, "domain": [["a", "=", 1], ["b", ">", 2]]}
        encoded = encode_row("odoo_queries", row)
        decoded = decode_row("odoo_queries", encoded)
        assert decoded["domain"] == [["a", "=", 1], ["b", ">", 2]]

    def test_timestamp_tz_to_utc(self):
        """TIMESTAMP with timezone must normalize to UTC naive."""
        from datetime import datetime, timezone
        dt = datetime(2024, 1, 15, 12, 0, 0, tzinfo=timezone.utc)
        row = {"id": 1, "created_at": dt}
        encoded = encode_row("odoo_queries", row)
        # Should be UTC normalized string
        decoded = decode_row("odoo_queries", encoded)
        assert decoded["created_at"].tzinfo is None  # UTC naive

    def test_bool_roundtrip(self):
        row = {"id": 1, "active": True}
        encoded = encode_row("odoo_queries", row)
        decoded = decode_row("odoo_queries", encoded)
        assert decoded["active"] is True

    def test_int64_roundtrip(self):
        row = {"id": 9999999999999, "limit_val": 50}
        encoded = encode_row("odoo_queries", row)
        decoded = decode_row("odoo_queries", encoded)
        assert decoded["id"] == 9999999999999
        assert decoded["limit_val"] == 50


class TestValidators:
    """Ex-CHECK constraints ported from init_db.py."""

    def test_frequency_check(self):
        from config_store.validators import validate_schedule
        validate_schedule({"frequency": "hourly"})  # ok
        with pytest.raises(ValidationError):
            validate_schedule({"frequency": "minutely"})

    def test_hour_range(self):
        from config_store.validators import validate_schedule
        validate_schedule({"hour": 0})
        validate_schedule({"hour": 23})
        with pytest.raises(ValidationError):
            validate_schedule({"hour": 24})
        with pytest.raises(ValidationError):
            validate_schedule({"hour": -1})

    def test_minute_range(self):
        from config_store.validators import validate_schedule
        validate_schedule({"minute": 0})
        validate_schedule({"minute": 59})
        with pytest.raises(ValidationError):
            validate_schedule({"minute": 60})

    def test_day_of_week_range(self):
        from config_store.validators import validate_schedule
        validate_schedule({"day_of_week": 0})
        validate_schedule({"day_of_week": 6})
        with pytest.raises(ValidationError):
            validate_schedule({"day_of_week": 7})

    def test_day_of_month_range(self):
        from config_store.validators import validate_schedule
        validate_schedule({"day_of_month": 1})
        validate_schedule({"day_of_month": 31})
        with pytest.raises(ValidationError):
            validate_schedule({"day_of_month": 32})
        with pytest.raises(ValidationError):
            validate_schedule({"day_of_month": 0})

    def test_interval_hours_range(self):
        from config_store.validators import validate_schedule
        validate_schedule({"interval_hours": 1})
        validate_schedule({"interval_hours": 24})
        with pytest.raises(ValidationError):
            validate_schedule({"interval_hours": 25})
        with pytest.raises(ValidationError):
            validate_schedule({"interval_hours": 0})
