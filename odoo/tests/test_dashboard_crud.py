"""CRUD endpoint tests for /dashboards (PR-2: create/list/patch/delete + permissions)."""
import pytest

from main import app
from auth import get_current_user
import dashboard_validation


FIELDS_META = {
    "name": {"type": "char", "string": "Name"},
    "amount_total": {"type": "monetary", "string": "Total"},
    "user_id": {"type": "many2one", "string": "Salesperson"},
    "state": {"type": "selection", "string": "Status"},
}


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
def mock_odoo(monkeypatch):
    """Canned Odoo boundary: model exists, fields_get returns FIELDS_META."""

    def fake_execute(model, method, args, kwargs=None):
        if model == "ir.model":
            return [{"model": "sale.order"}]
        if method == "fields_get":
            return FIELDS_META
        raise AssertionError(f"unexpected Odoo call {model}.{method}")

    monkeypatch.setattr(dashboard_validation, "odoo_execute", fake_execute)
    return fake_execute


def _revoke(store, *permission_ids):
    for pid in permission_ids:
        store.revoke_user_permission("test-user-id", pid)


def _seed(store, menu_key, name="Dash", active=True, definition=None, embed_url="https://example.com/embed"):
    return store.create_dashboard({
        "menu_key": menu_key,
        "name": name,
        "embed_url": embed_url if definition is None else None,
        "definition": definition,
        "active": active,
    })


class TestCreate:
    def test_create_embed_201_defaults_unpublished(self, client):
        res = client.post("/dashboards/", json={
            "menu_key": "new-embed",
            "name": "New Embed",
            "embed_url": "https://example.com/embed",
        })
        assert res.status_code == 201
        body = res.json()
        assert body["menu_key"] == "new-embed"
        assert body["embed_url"] == "https://example.com/embed"
        assert body["definition"] is None
        assert body["active"] is False

    def test_create_native_201(self, client, mock_odoo):
        res = client.post("/dashboards/", json={
            "menu_key": "ventas-por-vendedor",
            "name": "Ventas por vendedor",
            "definition": _definition(),
        })
        assert res.status_code == 201
        body = res.json()
        assert body["embed_url"] is None
        assert body["definition"]["model"] == "sale.order"
        assert body["active"] is False

    def test_create_both_embed_and_definition_422(self, client):
        res = client.post("/dashboards/", json={
            "menu_key": "bad-xor",
            "name": "Bad",
            "embed_url": "https://example.com/embed",
            "definition": _definition(),
        })
        assert res.status_code == 422

    def test_create_neither_embed_nor_definition_422(self, client):
        res = client.post("/dashboards/", json={"menu_key": "bad-xor", "name": "Bad"})
        assert res.status_code == 422

    def test_create_unknown_model_422(self, client, monkeypatch):
        def fake_execute(model, method, args, kwargs=None):
            if model == "ir.model":
                return []
            raise AssertionError(f"unexpected Odoo call {model}.{method}")

        monkeypatch.setattr(dashboard_validation, "odoo_execute", fake_execute)
        res = client.post("/dashboards/", json={
            "menu_key": "ghost",
            "name": "Ghost",
            "definition": _definition(model="ghost.model"),
        })
        assert res.status_code == 422
        detail = res.json()["detail"]
        assert detail["model"] == "ghost.model"

    def test_create_unknown_field_422_names_field(self, client, mock_odoo):
        res = client.post("/dashboards/", json={
            "menu_key": "bad-field",
            "name": "Bad Field",
            "definition": _definition(fields=["x_ghost"], aggregations={"x_ghost": "count"}),
        })
        assert res.status_code == 422
        assert res.json()["detail"]["field"] == "x_ghost"

    def test_create_invalid_menu_key_422(self, client):
        res = client.post("/dashboards/", json={
            "menu_key": "Bad Key!",
            "name": "Bad",
            "embed_url": "https://example.com/embed",
        })
        assert res.status_code == 422

    def test_create_duplicate_menu_key_409(self, client, store):
        _seed(store, "taken")
        res = client.post("/dashboards/", json={
            "menu_key": "taken",
            "name": "Dupe",
            "embed_url": "https://example.com/other",
        })
        assert res.status_code == 409


class TestList:
    def test_admin_sees_all_including_unpublished(self, client, store):
        _seed(store, "pub-dash", name="Published", active=True)
        _seed(store, "draft-dash", name="Draft", active=False)
        res = client.get("/dashboards/")
        assert res.status_code == 200
        keys = {row["menu_key"] for row in res.json()}
        assert keys == {"pub-dash", "draft-dash"}

    def test_view_only_sees_published(self, client, store):
        _seed(store, "pub-dash", active=True)
        _seed(store, "draft-dash", active=False)
        _revoke(store, "menu.admin.dashboards")
        res = client.get("/dashboards/")
        assert res.status_code == 200
        keys = {row["menu_key"] for row in res.json()}
        assert keys == {"pub-dash"}

    def test_neither_permission_403(self, client, store):
        _revoke(store, "menu.admin.dashboards", "menu.visualizaciones.dashboards")
        assert client.get("/dashboards/").status_code == 403

    def test_view_only_management_endpoints_403(self, client, store):
        _seed(store, "pub-dash")
        _revoke(store, "menu.admin.dashboards")
        assert client.post("/dashboards/", json={
            "menu_key": "x", "name": "X", "embed_url": "https://example.com/e",
        }).status_code == 403
        assert client.patch("/dashboards/pub-dash", json={"name": "Y"}).status_code == 403
        assert client.delete("/dashboards/pub-dash").status_code == 403

    def test_unauthenticated_401(self, client):
        app.dependency_overrides.pop(get_current_user, None)
        assert client.get("/dashboards/").status_code == 401
        assert client.post("/dashboards/", json={}).status_code == 401


class TestGetByKey:
    def test_embed_shape_additive_definition_null(self, client, store):
        _seed(store, "embed-dash", name="Embed Dash")
        res = client.get("/dashboards/embed-dash")
        assert res.status_code == 200
        body = res.json()
        assert body["name"] == "Embed Dash"
        assert body["embed_url"] == "https://example.com/embed"
        assert body["definition"] is None

    def test_native_returns_definition(self, client, store):
        _seed(store, "native-dash", definition=_definition(), active=True)
        res = client.get("/dashboards/native-dash")
        assert res.status_code == 200
        body = res.json()
        assert body["embed_url"] is None
        assert body["definition"]["model"] == "sale.order"

    def test_unpublished_404_for_view_path(self, client, store):
        _seed(store, "draft-dash", active=False)
        assert client.get("/dashboards/draft-dash").status_code == 404


class TestPatch:
    def test_rename(self, client, store):
        _seed(store, "dash-1", name="Old Name")
        res = client.patch("/dashboards/dash-1", json={"name": "New Name"})
        assert res.status_code == 200
        body = res.json()
        assert body["name"] == "New Name"
        assert body["updated_at"] is not None

    def test_rekey(self, client, store):
        _seed(store, "dash-1")
        res = client.patch("/dashboards/dash-1", json={"menu_key": "dash-renamed"})
        assert res.status_code == 200
        assert res.json()["menu_key"] == "dash-renamed"
        assert client.get("/dashboards/dash-renamed").status_code == 200

    def test_rekey_collision_409(self, client, store):
        _seed(store, "dash-1")
        _seed(store, "dash-2")
        res = client.patch("/dashboards/dash-1", json={"menu_key": "dash-2"})
        assert res.status_code == 409

    def test_publish_unpublish(self, client, store):
        _seed(store, "dash-1", active=False)
        assert client.get("/dashboards/dash-1").status_code == 404
        res = client.patch("/dashboards/dash-1", json={"active": True})
        assert res.status_code == 200
        assert res.json()["active"] is True
        assert client.get("/dashboards/dash-1").status_code == 200
        res = client.patch("/dashboards/dash-1", json={"active": False})
        assert res.json()["active"] is False
        assert client.get("/dashboards/dash-1").status_code == 404

    def test_invalid_definition_422(self, client, store, mock_odoo):
        _seed(store, "dash-1", definition=_definition())
        res = client.patch("/dashboards/dash-1", json={
            "definition": _definition(fields=["name"], aggregations={"name": "sum"}),
        })
        assert res.status_code == 422
        assert res.json()["detail"]["field"] == "name"

    def test_xor_violation_after_merge_422(self, client, store):
        _seed(store, "native-1", definition=_definition())
        # Setting embed_url without clearing definition would violate the XOR invariant.
        res = client.patch("/dashboards/native-1", json={"embed_url": "https://example.com/e"})
        assert res.status_code == 422

    def test_type_switch_native_to_embed(self, client, store, mock_odoo):
        _seed(store, "native-1", definition=_definition())
        res = client.patch("/dashboards/native-1", json={
            "embed_url": "https://example.com/e",
            "definition": None,
        })
        assert res.status_code == 200
        body = res.json()
        assert body["embed_url"] == "https://example.com/e"
        assert body["definition"] is None

    def test_missing_404(self, client):
        assert client.patch("/dashboards/nope", json={"name": "X"}).status_code == 404


class TestDelete:
    def test_delete_204_and_gone(self, client, store):
        _seed(store, "dash-1")
        assert client.delete("/dashboards/dash-1").status_code == 204
        assert client.get("/dashboards/dash-1").status_code == 404
        keys = {row["menu_key"] for row in client.get("/dashboards/").json()}
        assert "dash-1" not in keys

    def test_delete_missing_404(self, client):
        assert client.delete("/dashboards/nope").status_code == 404
