"""Data path tests: GET /dashboards/{menu_key}/data + POST /dashboards/preview."""
import pytest

import dashboard_validation


FIELDS_META = {
    "name": {"type": "char", "string": "Name"},
    "amount_total": {"type": "monetary", "string": "Total"},
    "user_id": {"type": "many2one", "string": "Salesperson"},
    "state": {"type": "selection", "string": "Status"},
}

READ_GROUP_ROWS = [
    {
        "user_id": [7, "J. Perez"],
        "amount_total": 152340.5,
        "__count": 42,
        "__domain": [["user_id", "=", 7]],
    },
    {
        "user_id": [9, "A. Gomez"],
        "amount_total": 80100.0,
        "__count": 17,
        "__domain": [["user_id", "=", 9]],
    },
]


def _definition(**overrides):
    defn = {
        "model": "sale.order",
        "fields": ["amount_total"],
        "group_by": ["user_id"],
        "domain": [["state", "=", "sale"]],
        "aggregations": {"amount_total": "sum"},
    }
    defn.update(overrides)
    return defn


@pytest.fixture
def captured():
    return {}


@pytest.fixture
def mock_odoo(monkeypatch, captured):
    def fake_execute(model, method, args, kwargs=None):
        captured.setdefault("calls", []).append((model, method, args, kwargs))
        if model == "ir.model":
            return [{"model": "sale.order"}]
        if method == "fields_get":
            return FIELDS_META
        if method == "read_group":
            captured["read_group"] = {"model": model, "args": args, "kwargs": kwargs}
            return READ_GROUP_ROWS
        raise AssertionError(f"unexpected Odoo call {model}.{method}")

    monkeypatch.setattr(dashboard_validation, "odoo_execute", fake_execute)
    return fake_execute


def _seed_native(store, menu_key="ventas-por-vendedor", name="Ventas por vendedor", active=True, definition=None):
    return store.create_dashboard({
        "menu_key": menu_key,
        "name": name,
        "embed_url": None,
        "definition": definition if definition is not None else _definition(),
        "active": active,
    })


class TestStoredDataPath:
    def test_data_200_wire_format(self, client, store, mock_odoo):
        _seed_native(store)
        res = client.get("/dashboards/ventas-por-vendedor/data")
        assert res.status_code == 200
        body = res.json()
        assert body["menu_key"] == "ventas-por-vendedor"
        assert body["name"] == "Ventas por vendedor"
        assert body["model"] == "sale.order"
        assert body["columns"] == [
            {"key": "user_id", "label": "Salesperson", "kind": "group"},
            {"key": "amount_total", "label": "Total (sum)", "kind": "aggregate", "function": "sum"},
        ]
        assert len(body["rows"]) == 2
        first = body["rows"][0]
        assert first["user_id"] == [7, "J. Perez"]
        assert first["amount_total"] == 152340.5
        assert first["__count"] == 42
        assert "__domain" not in first

    def test_query_derives_only_from_stored_definition(self, client, store, mock_odoo, captured):
        _seed_native(store)
        res = client.get("/dashboards/ventas-por-vendedor/data")
        assert res.status_code == 200
        call = captured["read_group"]
        assert call["model"] == "sale.order"
        assert call["args"] == [[["state", "=", "sale"]]]
        assert call["kwargs"]["fields"] == ["amount_total:sum"]
        assert call["kwargs"]["groupby"] == ["user_id"]
        assert call["kwargs"]["lazy"] is False

    def test_view_permission_required_403(self, client, store, mock_odoo):
        _seed_native(store)
        store.revoke_user_permission("test-user-id", "menu.visualizaciones.dashboards")
        assert client.get("/dashboards/ventas-por-vendedor/data").status_code == 403

    def test_unpublished_404(self, client, store, mock_odoo):
        _seed_native(store, active=False)
        assert client.get("/dashboards/ventas-por-vendedor/data").status_code == 404

    def test_missing_404(self, client, mock_odoo):
        assert client.get("/dashboards/nope/data").status_code == 404

    def test_embed_dashboard_422(self, client, store, mock_odoo):
        store.create_dashboard({
            "menu_key": "embed-dash",
            "name": "Embed",
            "embed_url": "https://example.com/embed",
            "definition": None,
            "active": True,
        })
        assert client.get("/dashboards/embed-dash/data").status_code == 422

    def test_stale_field_422_stale_definition(self, client, store, monkeypatch):
        _seed_native(store)

        def fake_execute(model, method, args, kwargs=None):
            if model == "ir.model":
                return [{"model": "sale.order"}]
            if method == "fields_get":
                # amount_total disappeared from Odoo after the dashboard was saved.
                return {k: v for k, v in FIELDS_META.items() if k != "amount_total"}
            raise AssertionError(f"unexpected Odoo call {model}.{method}")

        monkeypatch.setattr(dashboard_validation, "odoo_execute", fake_execute)
        res = client.get("/dashboards/ventas-por-vendedor/data")
        assert res.status_code == 422
        detail = res.json()["detail"]
        assert detail["code"] == "stale_definition"
        assert detail["field"] == "amount_total"
        assert detail["model"] == "sale.order"
        assert "amount_total" in detail["message"]

    def test_stale_model_422_stale_definition(self, client, store, monkeypatch):
        _seed_native(store)

        def fake_execute(model, method, args, kwargs=None):
            if model == "ir.model":
                return []
            raise AssertionError(f"unexpected Odoo call {model}.{method}")

        monkeypatch.setattr(dashboard_validation, "odoo_execute", fake_execute)
        res = client.get("/dashboards/ventas-por-vendedor/data")
        assert res.status_code == 422
        detail = res.json()["detail"]
        assert detail["code"] == "stale_definition"
        assert detail["model"] == "sale.order"

    def test_odoo_fault_on_read_group_502(self, client, store, monkeypatch):
        _seed_native(store)
        import xmlrpc.client

        def fake_execute(model, method, args, kwargs=None):
            if model == "ir.model":
                return [{"model": "sale.order"}]
            if method == "fields_get":
                return FIELDS_META
            if method == "read_group":
                raise xmlrpc.client.Fault(1, "Odoo exploded")
            raise AssertionError(f"unexpected Odoo call {model}.{method}")

        monkeypatch.setattr(dashboard_validation, "odoo_execute", fake_execute)
        res = client.get("/dashboards/ventas-por-vendedor/data")
        assert res.status_code == 502


class TestPreviewPath:
    def test_preview_200_same_execution(self, client, mock_odoo, captured):
        res = client.post("/dashboards/preview", json=_definition())
        assert res.status_code == 200
        body = res.json()
        assert body["model"] == "sale.order"
        assert body["columns"][1] == {"key": "amount_total", "label": "Total (sum)", "kind": "aggregate", "function": "sum"}
        assert len(body["rows"]) == 2
        call = captured["read_group"]
        assert call["kwargs"]["lazy"] is False

    def test_preview_invalid_definition_422_same_validation(self, client, mock_odoo):
        res = client.post("/dashboards/preview", json=_definition(
            fields=["name"], aggregations={"name": "sum"},
        ))
        assert res.status_code == 422
        assert res.json()["detail"]["field"] == "name"

    def test_preview_malformed_shape_422(self, client, mock_odoo):
        res = client.post("/dashboards/preview", json={"model": "sale.order"})
        assert res.status_code == 422

    def test_preview_admin_guarded(self, client, store, mock_odoo):
        store.revoke_user_permission("test-user-id", "menu.admin.dashboards")
        assert client.post("/dashboards/preview", json=_definition()).status_code == 403
