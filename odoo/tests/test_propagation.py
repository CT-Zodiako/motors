"""Tests for query_propagation.py — synchronous destination reload on edit."""
import pytest
from unittest.mock import MagicMock

from routers import runner, bigquery
import query_registry
import query_propagation


class FakeOdoo:
    def __init__(self, rows=None, exc=None):
        self.rows = rows or [{"id": 1, "name": "A"}]
        self.exc = exc
        self.calls = []

    def execute(self, model, method, args, kwargs):
        self.calls.append({"model": model, "method": method, "args": args, "kwargs": kwargs})
        if self.exc:
            raise self.exc
        return list(self.rows)


class FakeBQClient:
    project = "test-project"
    def __init__(self, load_exc=None, fail_for=None):
        self.load_exc = load_exc
        self.fail_for = fail_for or set()  # set of table_refs to fail
        self.jobs = []

    def get_table(self, table_ref):
        t = MagicMock()
        t.num_rows = 0
        return t

    def load_table_from_json(self, rows, table_ref, job_config):
        job = MagicMock()
        if table_ref in self.fail_for or self.load_exc:
            job.result.side_effect = self.load_exc or Exception("BQ error")
        else:
            job.result.return_value = None
            job.output_rows = len(rows)
        self.jobs.append({"rows": rows, "table_ref": table_ref, "job_config": job_config, "job": job})
        return job


@pytest.fixture
def fake_odoo(monkeypatch):
    f = FakeOdoo()
    monkeypatch.setattr(runner, "odoo_execute", f.execute)
    return f


@pytest.fixture
def fake_bq(monkeypatch):
    f = FakeBQClient()
    monkeypatch.setattr(query_propagation, "get_bigquery_client", lambda: f)
    return f


@pytest.fixture
def clean_registry(monkeypatch):
    """Ensure list_destinations returns controlled data per test."""
    # We will monkeypatch list_destinations inside each test
    pass


# ── RED: module doesn't exist yet ──

def test_propagate_single_destination_ok(fake_odoo, fake_bq, monkeypatch):
    """One destination, fetch succeeds, load succeeds → status 'ok'."""
    from query_propagation import propagate_query_edit

    monkeypatch.setattr(
        query_registry, "list_destinations",
        lambda name: [{"id": 7, "dataset_id": "ds", "table_id": "tbl"}],
    )
    monkeypatch.setattr(query_registry, "mark_ok", lambda dest_id, schema: None)
    monkeypatch.setattr(query_registry, "mark_stale", lambda dest_id, error: None)

    q = {
        "model": "res.partner",
        "method": "search_read",
        "domain": [],
        "fields": ["name"],
        "limit_val": None,
    }
    report = propagate_query_edit(q)
    assert report["total"] == 1
    assert report["ok"] == 1
    assert report["failed"] == 0
    assert report["destinations"][0]["status"] == "ok"
    assert report["destinations"][0]["dataset_id"] == "ds"
    assert report["destinations"][0]["table_id"] == "tbl"


def test_propagate_odoo_failure_marks_all_stale(fake_odoo, monkeypatch):
    """Odoo fetch raises → all destinations 'failed', edit still saved (caller responsibility)."""
    from query_propagation import propagate_query_edit

    fake_odoo.exc = Exception("Odoo down")
    monkeypatch.setattr(
        query_registry, "list_destinations",
        lambda name: [{"id": 7, "dataset_id": "ds", "table_id": "tbl"}],
    )
    stale_calls = []
    monkeypatch.setattr(query_registry, "mark_ok", lambda dest_id, schema: None)
    monkeypatch.setattr(query_registry, "mark_stale", lambda dest_id, error: stale_calls.append((dest_id, error)))

    q = {
        "model": "res.partner",
        "method": "search_read",
        "domain": [],
        "fields": ["name"],
        "limit_val": None,
    }
    report = propagate_query_edit(q)
    assert report["total"] == 1
    assert report["ok"] == 0
    assert report["failed"] == 1
    assert report["destinations"][0]["status"] == "failed"
    assert "Odoo down" in report["destinations"][0]["error"]
    assert stale_calls == [(7, "Odoo down")]


def test_propagate_partial_failure_isolation(fake_odoo, monkeypatch):
    """Destination 1 load fails, destination 2 still processed as 'ok'."""
    from query_propagation import propagate_query_edit

    monkeypatch.setattr(
        query_registry, "list_destinations",
        lambda name: [
            {"id": 8, "dataset_id": "ds1", "table_id": "t1"},
            {"id": 9, "dataset_id": "ds2", "table_id": "t2"},
        ],
    )
    ok_calls = []
    stale_calls = []
    monkeypatch.setattr(query_registry, "mark_ok", lambda dest_id, schema: ok_calls.append(dest_id))
    monkeypatch.setattr(query_registry, "mark_stale", lambda dest_id, error: stale_calls.append((dest_id, error)))

    # Build a fake BQ client that fails only for ds1.t1
    class PartialFailClient:
        project = "test-project"
        jobs = []
        def get_table(self, table_ref):
            t = MagicMock()
            t.num_rows = 0
            return t
        def load_table_from_json(self, rows, table_ref, job_config):
            self.jobs.append(table_ref)
            job = MagicMock()
            if "ds1" in table_ref:
                job.result.side_effect = Exception("BQ permission denied")
            else:
                job.result.return_value = None
            return job

    monkeypatch.setattr(query_propagation, "get_bigquery_client", lambda: PartialFailClient())

    q = {
        "model": "res.partner",
        "method": "search_read",
        "domain": [],
        "fields": ["name"],
        "limit_val": None,
    }
    report = propagate_query_edit(q)
    assert report["total"] == 2
    assert report["ok"] == 1
    assert report["failed"] == 1
    ds1 = next(d for d in report["destinations"] if d["dataset_id"] == "ds1")
    ds2 = next(d for d in report["destinations"] if d["dataset_id"] == "ds2")
    assert ds1["status"] == "failed"
    assert "BQ permission denied" in ds1["error"]
    assert ds2["status"] == "ok"
    assert stale_calls == [(8, "BQ permission denied")]
    assert ok_calls == [9]


def test_propagate_empty_result_no_truncate(fake_odoo, fake_bq, monkeypatch):
    """Empty Odoo result → NO BQ load called, status 'empty', marked stale."""
    from query_propagation import propagate_query_edit

    fake_odoo.rows = []
    monkeypatch.setattr(
        query_registry, "list_destinations",
        lambda name: [{"id": 10, "dataset_id": "ds", "table_id": "tbl"}],
    )
    stale_calls = []
    monkeypatch.setattr(query_registry, "mark_ok", lambda dest_id, schema: None)
    monkeypatch.setattr(query_registry, "mark_stale", lambda dest_id, error: stale_calls.append((dest_id, error)))

    q = {
        "model": "res.partner",
        "method": "search_read",
        "domain": [],
        "fields": ["name"],
        "limit_val": None,
    }
    report = propagate_query_edit(q)
    assert report["total"] == 1
    assert report["ok"] == 0
    assert report["failed"] == 1
    assert report["destinations"][0]["status"] == "empty"
    # BQ load should NOT have been called
    assert fake_bq.jobs == []
    assert stale_calls == [(10, "Empty result set — table not truncated")]


def test_propagate_zero_destinations(fake_odoo, monkeypatch):
    """No registered destinations → total 0, no Odoo fetch."""
    from query_propagation import propagate_query_edit

    monkeypatch.setattr(query_registry, "list_destinations", lambda name: [])
    monkeypatch.setattr(query_registry, "mark_ok", lambda dest_id, schema: None)
    monkeypatch.setattr(query_registry, "mark_stale", lambda dest_id, error: None)

    q = {
        "model": "res.partner",
        "method": "search_read",
        "domain": [],
        "fields": ["name"],
        "limit_val": None,
    }
    report = propagate_query_edit(q)
    assert report == {"total": 0, "ok": 0, "failed": 0, "destinations": []}
    # Odoo should NOT have been called when there are no destinations
    assert fake_odoo.calls == []
