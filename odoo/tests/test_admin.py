import pytest
from fastapi.testclient import TestClient

from auth import get_current_user
from main import app


@pytest.fixture
def admin_client(store):
    """TestClient with an admin user override."""
    app.dependency_overrides[get_current_user] = lambda: store.get_user_by_email("soporte@gmail.com")
    client = TestClient(app, raise_server_exceptions=True)
    yield client
    app.dependency_overrides[get_current_user] = lambda: store.get_user_by_email("test@example.com")


class TestAdminUsers:
    def test_list_users(self, admin_client, store):
        res = admin_client.get("/admin/users")
        assert res.status_code == 200
        body = res.json()
        assert isinstance(body, list)
        assert any(u["email"] == "soporte@gmail.com" for u in body)

    def test_create_user(self, admin_client, store):
        res = admin_client.post("/admin/users", json={
            "email": "newuser@example.com",
            "password": "secret123",
            "role": "user",
            "active": True,
        })
        assert res.status_code == 201
        body = res.json()
        assert body["email"] == "newuser@example.com"
        assert body["role"] == "user"
        assert body["active"] is True

    def test_create_user_duplicate_email(self, admin_client, store):
        res = admin_client.post("/admin/users", json={
            "email": "soporte@gmail.com",
            "password": "secret123",
        })
        assert res.status_code == 409

    def test_get_user(self, admin_client, store):
        default_user = store.get_user_by_email("soporte@gmail.com")
        res = admin_client.get(f"/admin/users/{default_user['id']}")
        assert res.status_code == 200
        body = res.json()
        assert body["email"] == "soporte@gmail.com"
        assert "permissions" in body

    def test_update_user(self, admin_client, store):
        user = store.create_user({
            "id": "update-user",
            "email": "update@example.com",
            "password_hash": "hash",
            "role": "user",
            "active": True,
            "created_at": None,
            "updated_at": None,
        })
        res = admin_client.patch(f"/admin/users/{user['id']}", json={
            "role": "admin",
            "active": False,
        })
        assert res.status_code == 200
        body = res.json()
        assert body["role"] == "admin"
        assert body["active"] is False

    def test_delete_user(self, admin_client, store):
        user = store.create_user({
            "id": "delete-user",
            "email": "delete@example.com",
            "password_hash": "hash",
            "role": "user",
            "active": True,
            "created_at": None,
            "updated_at": None,
        })
        store.assign_user_permission(user["id"], "menu.consultar.queries")
        assert store.get_user_by_id(user["id"]) is not None
        assert "menu.consultar.queries" in store.get_user_permissions(user["id"])

        res = admin_client.delete(f"/admin/users/{user['id']}")
        assert res.status_code == 200
        body = res.json()
        assert body["deleted"] == user["id"]
        assert store.get_user_by_id(user["id"]) is None
        assert store.get_user_permissions(user["id"]) == set()

    def test_delete_user_not_found(self, admin_client, store):
        res = admin_client.delete("/admin/users/nonexistent-user-id")
        assert res.status_code == 404

    def test_set_permission(self, admin_client, store):
        user = store.create_user({
            "id": "perms-user",
            "email": "perms@example.com",
            "password_hash": "hash",
            "role": "user",
            "active": True,
            "created_at": None,
            "updated_at": None,
        })
        res = admin_client.post(f"/admin/users/{user['id']}/permissions", json={
            "permission_id": "menu.consultar.queries",
            "granted": True,
        })
        assert res.status_code == 200
        perms = store.get_user_permissions(user["id"])
        assert "menu.consultar.queries" in perms

        res = admin_client.post(f"/admin/users/{user['id']}/permissions", json={
            "permission_id": "menu.consultar.queries",
            "granted": False,
        })
        assert res.status_code == 200
        perms = store.get_user_permissions(user["id"])
        assert "menu.consultar.queries" not in perms

    def test_admin_requires_permission(self, store):
        no_perms_user = store.create_user({
            "id": "no-admin-user",
            "email": "noadmin@example.com",
            "password_hash": "hash",
            "role": "user",
            "active": True,
            "created_at": None,
            "updated_at": None,
        })
        app.dependency_overrides[get_current_user] = lambda: no_perms_user
        client = TestClient(app, raise_server_exceptions=True)
        res = client.get("/admin/users")
        assert res.status_code == 403
        app.dependency_overrides[get_current_user] = lambda: store.get_user_by_email("test@example.com")

