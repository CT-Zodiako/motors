"""Characterization + limit enforcement tests for fetch_query_rows."""
import pytest
from routers import runner


class FakeOdoo:
    """Records every call so we can assert on the limit param."""
    def __init__(self):
        self.calls = []

    def execute(self, model, method, args, kwargs):
        self.calls.append({"model": model, "method": method, "args": args, "kwargs": kwargs})
        return [{"id": 1, "name": "A"}, {"id": 2, "name": "B"}]


@pytest.fixture
def fake_odoo(monkeypatch):
    f = FakeOdoo()
    monkeypatch.setattr(runner, "odoo_execute", f.execute)
    return f


# ── Characterization: current runner path produces rows ──

def test_fetch_query_rows_returns_rows(fake_odoo):
    q = {
        "model": "res.partner",
        "method": "search_read",
        "domain": [["active", "=", True]],
        "fields": ["name"],
        "limit_val": None,
    }
    rows = runner.fetch_query_rows(q)
    assert rows == [{"id": 1, "name": "A"}, {"id": 2, "name": "B"}]
    assert fake_odoo.calls[0]["kwargs"]["limit"] is False


# ── RED: limit_val honored ──

def test_fetch_query_rows_with_limit(fake_odoo):
    q = {
        "model": "res.partner",
        "method": "search_read",
        "domain": [],
        "fields": ["name"],
        "limit_val": 5,
    }
    rows = runner.fetch_query_rows(q)
    assert fake_odoo.calls[0]["kwargs"]["limit"] == 5


def test_fetch_query_rows_none_limit_is_false(fake_odoo):
    q = {
        "model": "res.partner",
        "method": "search_read",
        "domain": [],
        "fields": ["name"],
        "limit_val": None,
    }
    runner.fetch_query_rows(q)
    assert fake_odoo.calls[0]["kwargs"]["limit"] is False


def test_fetch_query_rows_zero_limit_is_false(fake_odoo):
    q = {
        "model": "res.partner",
        "method": "search_read",
        "domain": [],
        "fields": ["name"],
        "limit_val": 0,
    }
    runner.fetch_query_rows(q)
    assert fake_odoo.calls[0]["kwargs"]["limit"] is False


# ── TRIANGULATE: string coercion, negative treated as no-limit ──

def test_fetch_query_rows_string_limit_coerced(fake_odoo):
    q = {
        "model": "res.partner",
        "method": "search_read",
        "domain": [],
        "fields": ["name"],
        "limit_val": "5",
    }
    runner.fetch_query_rows(q)
    assert fake_odoo.calls[0]["kwargs"]["limit"] == 5


def test_fetch_query_rows_negative_limit_is_false(fake_odoo):
    """Negative is treated as no-limit (PATCH rejects it in WU5)."""
    q = {
        "model": "res.partner",
        "method": "search_read",
        "domain": [],
        "fields": ["name"],
        "limit_val": -3,
    }
    runner.fetch_query_rows(q)
    assert fake_odoo.calls[0]["kwargs"]["limit"] is False


# ── Schedule executor path uses the same helper ──

def test_runner_final_page_reports_exact_total_and_uses_offset_page_size(monkeypatch):
    from routers.runner import run_query

    query = {
        "model": "account.move",
        "method": "search_read",
        "domain": [],
        "fields": ["id"],
        "limit_val": None,
        "active": True,
    }
    monkeypatch.setattr(runner, "_fetch_registered", lambda name: query)
    calls = []

    def fetch(registered, offset, limit):
        calls.append((offset, limit))
        return [{"id": 102743}, {"id": 102744}]

    monkeypatch.setattr(runner, "fetch_query_rows", fetch)
    result = run_query("LineasFacturasEmitidas", offset=102742, page_size=20, user={})

    assert calls == [(102742, 21)]
    assert result["data"] == [{"id": 102743}, {"id": 102744}]
    assert result["has_more"] is False
    assert result["total"] == 102744
    assert result["total_known"] is True


def test_runner_stored_limit_is_only_upper_bound_while_more(monkeypatch):
    from routers.runner import run_query

    query = {"model": "x", "method": "search_read", "domain": [], "fields": [], "limit_val": 100, "active": True}
    monkeypatch.setattr(runner, "_fetch_registered", lambda name: query)
    monkeypatch.setattr(runner, "fetch_query_rows", lambda *args, **kwargs: [{"id": i} for i in range(21)])

    result = run_query("q", offset=0, page_size=20, user={})
    assert result["has_more"] is True
    assert result["total"] == 100
    assert result["total_known"] is False


def test_schedule_executor_routes_through_fetch_query_rows(fake_odoo, monkeypatch):
    """After WU3, schedules.py must call fetch_query_rows instead of inline odoo_execute."""
    from routers import schedules, runner

    # fetch_query_rows calls runner.odoo_execute internally
    monkeypatch.setattr(runner, "odoo_execute", fake_odoo.execute)

    # We cannot easily run _execute_schedule without a full DB + BQ client,
    # but we can at least verify the helper is imported and callable.
    assert hasattr(schedules, "fetch_query_rows")
    q = {
        "model": "res.partner",
        "method": "search_read",
        "domain": [],
        "fields": ["name"],
        "limit_val": 10,
    }
    rows = schedules.fetch_query_rows(q)
    assert fake_odoo.calls[0]["kwargs"]["limit"] == 10
    assert rows == [{"id": 1, "name": "A"}, {"id": 2, "name": "B"}]
