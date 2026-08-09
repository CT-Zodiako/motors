"""Explorer endpoint tests: /explore/models must return EVERY Odoo model.

Odoo instances commonly have 1000+ ir.model rows; the endpoint must not
impose a search_read limit (regression: it used to send limit=500).
"""
import os
import sys

from fastapi.testclient import TestClient

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from main import app  # noqa: E402
from routers import explorer  # noqa: E402

ALL_MODELS = [
    {"name": f"Model {i}", "model": f"model.{i}", "info": ""} for i in range(1001)
]


def test_models_endpoint_returns_every_odoo_model(monkeypatch):
    """The endpoint must not cap results: no 'limit' kwarg reaches Odoo."""
    captured = {}

    def fake_execute(model, method, args, kwargs=None):
        kwargs = kwargs or {}
        captured["kwargs"] = kwargs
        # Simulate real Odoo semantics: apply the limit if one is sent.
        limit = kwargs.get("limit")
        return ALL_MODELS if limit is None else ALL_MODELS[:limit]

    monkeypatch.setattr(explorer, "odoo_execute", fake_execute)

    client = TestClient(app, raise_server_exceptions=False)
    res = client.get("/explore/models")

    assert res.status_code == 200
    body = res.json()
    assert body["total"] == 1001
    assert len(body["models"]) == 1001
    assert "limit" not in captured["kwargs"], (
        "no limit kwarg must reach Odoo — instances have 1000+ models"
    )


def test_fields_endpoint_requests_enriched_field_attributes(monkeypatch):
    """/explore/fields must fetch the metadata shown on field cards."""
    captured = {}

    def fake_execute(model, method, args, kwargs=None):
        captured["model"] = model
        captured["method"] = method
        captured["kwargs"] = kwargs or {}
        return {}

    monkeypatch.setattr(explorer, "odoo_execute", fake_execute)

    client = TestClient(app, raise_server_exceptions=False)
    res = client.get("/explore/fields/sale.order")

    assert res.status_code == 200
    assert captured["model"] == "sale.order"
    assert captured["method"] == "fields_get"
    attributes = captured["kwargs"].get("attributes", [])
    for expected in ["string", "type", "required", "readonly", "relation", "help"]:
        assert expected in attributes, f"fields_get must request '{expected}'"


class TestDualPermissionGuards:
    """dashboard-crud-menu: /explore/models + /explore/fields accept EITHER
    menu.cargar.create OR menu.admin.dashboards."""

    def _mock_odoo(self, monkeypatch):
        def fake_execute(model, method, args, kwargs=None):
            if method == "fields_get":
                return {"name": {"type": "char", "string": "Name"}}
            return [{"name": "Sale Order", "model": "sale.order", "info": ""}]

        monkeypatch.setattr(explorer, "odoo_execute", fake_execute)

    def _revoke(self, store, *permission_ids):
        for pid in permission_ids:
            store.revoke_user_permission("test-user-id", pid)

    def test_admin_dashboards_permission_grants_models_access(self, client, store, monkeypatch):
        self._mock_odoo(monkeypatch)
        self._revoke(store, "menu.cargar.create")
        res = client.get("/explore/models")
        assert res.status_code == 200

    def test_admin_dashboards_permission_grants_fields_access(self, client, store, monkeypatch):
        self._mock_odoo(monkeypatch)
        self._revoke(store, "menu.cargar.create")
        res = client.get("/explore/fields/sale.order")
        assert res.status_code == 200

    def test_cargar_only_behavior_unchanged(self, client, store, monkeypatch):
        self._mock_odoo(monkeypatch)
        self._revoke(store, "menu.admin.dashboards")
        assert client.get("/explore/models").status_code == 200
        assert client.get("/explore/fields/sale.order").status_code == 200

    def test_neither_permission_403(self, client, store, monkeypatch):
        self._mock_odoo(monkeypatch)
        self._revoke(store, "menu.cargar.create", "menu.admin.dashboards")
        assert client.get("/explore/models").status_code == 403
        assert client.get("/explore/fields/sale.order").status_code == 403
