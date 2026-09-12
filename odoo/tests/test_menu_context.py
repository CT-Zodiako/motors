"""Navigation contracts, authorization boundaries, and repeatable bootstrap."""
from unittest.mock import MagicMock, Mock

import pytest
from fastapi.testclient import TestClient

from auth import create_access_token, get_current_user
from auth_seed import (
    DEFAULT_USER_PASSWORD,
    grant_seeded_permissions_to_existing_user,
    seed_support_user,
)
from config_store import codecs, sql
from config_store.bootstrap import NAVIGATION_SEEDS, _SEED_PERMISSIONS, seed_defaults
from config_store.bq_store import BigQueryConfigStore
from main import app


def test_context_seeded_hierarchy(client):
    response = client.get("/auth/context")
    assert response.status_code == 200
    systems = response.json()["systems"]
    assert [s["id"] for s in systems] == ["1", "2"]
    assert systems[1]["name"] == "Sistema 2 - Operaciones"
    assert [m["name"] for m in systems[1]["modules"]] == ["Ventas", "Inventario", "Reportes", "Procesos"]
    assert all(m["menu"] for m in systems[1]["modules"])
    assert not any("dashboard" in o["id"] or o["id"].startswith("menu.visualizaciones.")
                   for o in response.json()["menu"])
    assert client.get("/dashboards").status_code == 404


@pytest.mark.parametrize("system_id,permission_id", [
    ("1", "menu.procesos.bizagi"), ("2", "menu.operaciones.procesos"),
])
def test_workflow_url_is_fixed_and_permission_filtered(client, store, system_id, permission_id):
    params = {"system_id": system_id, "module_id": f"{system_id}-procesos"}
    response = client.get("/menu", params=params)
    assert response.status_code == 200
    assert len(response.json()["menu"]) == 1
    option = response.json()["menu"][0]
    assert option["name"] == "Procesos Bizagi"
    assert option["workflow_url"] == "/WorkFlow/index.html"
    assert option["permission_id"] == permission_id
    assert option["id"] == permission_id
    demo = client.get("/menu", params={"system_id": "2", "module_id": "2-ventas"})
    assert demo.json()["menu"][0]["workflow_url"] is None
    store.revoke_user_permission("test-user-id", option["permission_id"])
    assert client.get("/menu", params=params).status_code == 403
    remaining = client.get("/auth/context").json()["menu"]
    assert not any(o["id"] == permission_id for o in remaining)
    assert sum(bool(o["workflow_url"]) for o in remaining) == 1


@pytest.mark.parametrize("field,value", [
    ("id", "menu.procesos.other"),
    ("module_id", "1-consultar"),
    ("permission_id", "menu.consultar.queries"),
])
def test_workflow_allowlist_rejects_mismatched_option(client, store, field, value):
    option = next(o for o in store._data["odoo_menu_options"]
                  if o["id"] == "menu.procesos.bizagi")
    option[field] = value
    option["workflow_url"] = "https://example.com"
    response = client.get("/menu", params={"system_id": "1", "module_id": option["module_id"]})
    assert response.status_code == 200
    returned = next(o for o in response.json()["menu"] if o["id"] == option["id"])
    assert returned["workflow_url"] is None


def test_context_filters_without_admin_bypass(client, store):
    uid = "test-user-id"
    for pid in store.get_user_permissions(uid):
        store.revoke_user_permission(uid, pid)
    assert client.get("/auth/context").json()["systems"] == []
    store.assign_user_permission(uid, "menu.operaciones.ventas")
    result = client.get("/auth/context").json()
    assert [s["id"] for s in result["systems"]] == ["2"]
    assert [m["id"] for m in result["systems"][0]["modules"]] == ["2-ventas"]
    assert [o["id"] for o in result["menu"]] == ["menu.operaciones.ventas"]
    store.revoke_user_permission(uid, "menu.operaciones.ventas")
    assert client.get("/menu", params={"system_id": "2", "module_id": "2-ventas"}).status_code == 403


@pytest.mark.parametrize("params,status", [
    ({"module_id": "2-ventas"}, 400),
    ({"system_id": "missing"}, 403),
    ({"system_id": "1", "module_id": "2-ventas"}, 403),
    ({"system_id": "2", "module_id": "missing"}, 403),
])
def test_invalid_selection(client, params, status):
    assert client.get("/auth/context", params=params).status_code == status


def test_option_selection_checks_parent_and_permission(client, store):
    params = {"system_id": "2", "module_id": "2-ventas"}
    assert client.get("/menu/menu.operaciones.ventas", params=params).status_code == 200
    assert client.get("/menu/menu.operaciones.inventario", params=params).status_code == 403
    assert client.get("/menu/missing", params=params).status_code == 403
    store.revoke_user_permission("test-user-id", "menu.operaciones.ventas")
    assert client.get("/menu/menu.operaciones.ventas", params=params).status_code == 403


@pytest.mark.parametrize("table,row_id", [
    ("odoo_systems", "2"), ("odoo_modules", "2-ventas"),
    ("odoo_menu_options", "menu.operaciones.ventas"),
])
def test_deactivated_hierarchy_fails_closed(client, store, table, row_id):
    row = next(r for r in store._data[table] if r["id"] == row_id)
    row["active"] = False
    response = client.get("/menu", params={"system_id": "2", "module_id": "2-ventas"})
    assert response.status_code == 403


@pytest.mark.parametrize("path", ["/auth/context", "/menu", "/menu/menu.operaciones.ventas"])
def test_navigation_requires_active_authenticated_user(store, path):
    app.dependency_overrides.pop(get_current_user, None)
    client = TestClient(app, raise_server_exceptions=False)
    params = {"system_id": "2", "module_id": "2-ventas"}
    assert client.get(path, params=params).status_code == 401
    user = store.get_user_by_id("test-user-id")
    client.cookies.set("access_token", create_access_token(user["id"], user["email"], user["role"]))
    assert client.get(path, params=params).status_code == 200
    store.update_user(user["id"], {"active": False})
    assert client.get(path, params=params).status_code == 401


def test_navigation_seed_preserves_rows_and_returns_copies(store):
    for table, seeds in NAVIGATION_SEEDS.items():
        store._data[table][0]["name"] = "Customized"
        store._data[table][0]["active"] = False
        store._data[table].pop()
    seed_defaults(store)
    seed_defaults(store)
    for table, seeds in NAVIGATION_SEEDS.items():
        assert len(store._data[table]) == len(seeds)
        assert store._data[table][0]["name"] == "Customized"
        assert store._data[table][0]["active"] is False
    store.list_systems()[0]["name"] = "Not persisted"
    assert store.list_systems()[0]["name"] == "Customized"


def test_support_created_separately_and_idempotently(store):
    legacy = store.get_user_by_email("soporte@gmail.com")
    hasher = Mock(return_value="demo-hash")
    seed_support_user(store, hasher)
    seed_support_user(store, hasher)
    user = store.get_user_by_email("support@gmail.com")
    assert user["active"] is True and user["role"] == "admin"
    assert user["id"] != legacy["id"]
    assert store.get_user_by_email("soporte@gmail.com") == legacy
    hasher.assert_called_once_with(DEFAULT_USER_PASSWORD)
    assert {p["id"] for p in _SEED_PERMISSIONS} <= store.get_user_permissions(user["id"])


def test_support_existing_password_preserved_and_grants_repaired(store):
    store.create_user({"id": "support", "email": "SUPPORT@gmail.com",
                       "password_hash": "existing-hash", "active": False, "role": "user"})
    hasher = Mock(side_effect=AssertionError("Must not reset existing password"))
    seed_support_user(store, hasher)
    store.revoke_user_permission("support", "menu.procesos.bizagi")
    seed_support_user(store, hasher)
    user = store.get_user_by_id("support")
    assert user["active"] is True and user["role"] == "admin"
    assert user["password_hash"] == "existing-hash"
    assert "menu.procesos.bizagi" in store.get_user_permissions("support")
    hasher.assert_not_called()


def test_legacy_seeded_grants_preserve_accounts_and_repair_permissions(store):
    legacy = store.get_user_by_email("soporte@gmail.com")
    store.update_user(legacy["id"], {"role": "user", "active": False})
    legacy = store.get_user_by_id(legacy["id"])
    seed_support_user(store, Mock(return_value="support-hash"))
    support = store.get_user_by_email("support@gmail.com")
    support_permissions = store.get_user_permissions(support["id"])
    for permission_id in store.get_user_permissions(legacy["id"]):
        store.revoke_user_permission(legacy["id"], permission_id)

    grant_seeded_permissions_to_existing_user(store, "soporte@gmail.com")
    assert {p["id"] for p in _SEED_PERMISSIONS} <= store.get_user_permissions(legacy["id"])
    store.revoke_user_permission(legacy["id"], "menu.procesos.bizagi")
    grant_seeded_permissions_to_existing_user(store, "soporte@gmail.com")
    assert "menu.procesos.bizagi" in store.get_user_permissions(legacy["id"])
    assert store.get_user_by_id(legacy["id"]) == legacy
    assert store.get_user_by_id(support["id"]) == support
    assert store.get_user_permissions(support["id"]) == support_permissions


def test_existing_user_grants_skip_missing_account():
    store = Mock()
    store.get_user_by_email.return_value = None
    grant_seeded_permissions_to_existing_user(store, "soporte@gmail.com")
    store.get_user_by_email.assert_called_once_with("soporte@gmail.com")
    store.create_user.assert_not_called()
    store.assign_user_permission.assert_not_called()


def test_existing_user_grants_only_missing_seeded_permissions():
    store = Mock()
    store.get_user_by_email.return_value = {"id": "legacy"}
    seeded = {p["id"] for p in _SEED_PERMISSIONS}
    store.get_user_permissions.side_effect = [seeded - {"menu.operaciones.procesos"}, seeded]
    grant_seeded_permissions_to_existing_user(store, "soporte@gmail.com")
    grant_seeded_permissions_to_existing_user(store, "soporte@gmail.com")
    store.assign_user_permission.assert_called_once_with("legacy", "menu.operaciones.procesos")
    store.update_user.assert_not_called()
    store.update_user_password.assert_not_called()


def test_bq_navigation_seed_is_parameterized_insert_only(monkeypatch):
    monkeypatch.setenv("BQ_CONFIG_DATASET", "navigation_test")
    store = BigQueryConfigStore(client=MagicMock())
    store._query = Mock(return_value=[])
    store.seed_navigation_defaults()
    calls = store._query.call_args_list
    assert len(calls) == sum(len(rows) for rows in NAVIGATION_SEEDS.values())
    for call in calls:
        statement, params = call.args
        assert "MERGE `navigation_test.odoo_" in statement
        assert "WHEN NOT MATCHED THEN INSERT" in statement
        assert "UPDATE" not in statement
        assert "target.id = source.id" in statement
        values = {p.name: p.value for p in params}
        assert values["name"] not in statement
        assert isinstance(values["active"], bool)
        assert isinstance(values["sort_order"], int)


@pytest.mark.parametrize("table,method", [
    ("odoo_systems", "list_systems"), ("odoo_modules", "list_modules"),
    ("odoo_menu_options", "list_menu_options"),
])
def test_bq_navigation_reads_schema_and_codecs(table, method):
    store = BigQueryConfigStore(client=MagicMock())
    row = NAVIGATION_SEEDS[table][0]
    store._query = Mock(return_value=[codecs.encode_row(table, row)])
    assert getattr(store, method)() == [row]
    store._query.assert_called_once_with(sql.SQL_LIST_NAVIGATION(table))
    assert "ORDER BY sort_order, id" in sql.SQL_LIST_NAVIGATION(table)
    assert set(row) == {c["name"] for c in codecs.TABLE_SCHEMAS[table]}


def test_bq_schema_bootstrap_includes_navigation():
    client = MagicMock(project="test-project")
    client.get_table.side_effect = Exception("Not found")
    BigQueryConfigStore(client=client).ensure_schema()
    tables = {call.args[0].table_id: call.args[0] for call in client.create_table.call_args_list}
    for table in NAVIGATION_SEEDS:
        assert {f.name for f in tables[table].schema} == {c["name"] for c in codecs.TABLE_SCHEMAS[table]}


def test_navigation_sql_rejects_unknown_identifiers():
    for template in (sql.SQL_LIST_NAVIGATION, sql.SQL_SEED_NAVIGATION):
        with pytest.raises(ValueError):
            template("odoo_users; DROP TABLE anything")
