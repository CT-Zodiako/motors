import pytest
from fastapi.testclient import TestClient

from auth import get_current_user, get_password_hash
from main import app


@pytest.fixture
def auth_client(store):
    """TestClient without the global auth override so we can test auth explicitly.

    No context manager: avoids lifespan startup (which would replace the test store).
    """
    app.dependency_overrides.pop(get_current_user, None)
    client = TestClient(app, raise_server_exceptions=False)
    yield client
    # restore default override after test
    app.dependency_overrides[get_current_user] = lambda: store.get_user_by_email("test@example.com")


@pytest.fixture
def default_user(store):
    """Return the default seeded support user."""
    return store.get_user_by_email("soporte@gmail.com")


class TestLogin:
    def test_login_success(self, auth_client, default_user):
        res = auth_client.post("/auth/login", json={
            "email": "soporte@gmail.com",
            "password": "123456",
        })
        assert res.status_code == 200
        body = res.json()
        assert body["user"]["email"] == "soporte@gmail.com"
        assert body["user"]["role"] == "admin"
        assert "access_token" in res.cookies

    def test_login_invalid_password(self, auth_client):
        res = auth_client.post("/auth/login", json={
            "email": "soporte@gmail.com",
            "password": "wrong",
        })
        assert res.status_code == 401
        assert "access_token" not in res.cookies

    def test_login_unknown_email(self, auth_client):
        res = auth_client.post("/auth/login", json={
            "email": "nobody@gmail.com",
            "password": "123456",
        })
        assert res.status_code == 401


class TestLogout:
    def test_logout_clears_cookie(self, auth_client, default_user):
        login = auth_client.post("/auth/login", json={
            "email": "soporte@gmail.com",
            "password": "123456",
        })
        assert login.status_code == 200
        assert "access_token" in auth_client.cookies

        res = auth_client.post("/auth/logout")
        assert res.status_code == 200
        assert res.json()["ok"] is True
        # Cookie is cleared by response directive


class TestMe:
    def test_me_authenticated(self, auth_client, default_user):
        auth_client.post("/auth/login", json={
            "email": "soporte@gmail.com",
            "password": "123456",
        })
        res = auth_client.get("/auth/me")
        assert res.status_code == 200
        body = res.json()
        assert body["email"] == "soporte@gmail.com"
        assert body["role"] == "admin"

    def test_me_unauthenticated(self, auth_client):
        app.dependency_overrides.pop(get_current_user, None)
        res = auth_client.get("/auth/me")
        assert res.status_code == 401


class TestChangePassword:
    def test_change_password_success(self, auth_client, default_user):
        auth_client.post("/auth/login", json={
            "email": "soporte@gmail.com",
            "password": "123456",
        })
        res = auth_client.post("/auth/change-password", json={
            "current_password": "123456",
            "new_password": "newsecret",
        })
        assert res.status_code == 200

        # subsequent login with new password works
        logout = auth_client.post("/auth/logout")
        assert logout.status_code == 200
        login = auth_client.post("/auth/login", json={
            "email": "soporte@gmail.com",
            "password": "newsecret",
        })
        assert login.status_code == 200

    def test_change_password_wrong_current(self, auth_client, default_user):
        auth_client.post("/auth/login", json={
            "email": "soporte@gmail.com",
            "password": "123456",
        })
        res = auth_client.post("/auth/change-password", json={
            "current_password": "wrong",
            "new_password": "newsecret",
        })
        assert res.status_code == 401

    def test_change_password_same_as_current(self, auth_client, default_user):
        auth_client.post("/auth/login", json={
            "email": "soporte@gmail.com",
            "password": "123456",
        })
        res = auth_client.post("/auth/change-password", json={
            "current_password": "123456",
            "new_password": "123456",
        })
        assert res.status_code == 400


class TestRouteProtection:
    def test_protected_route_requires_auth(self, auth_client):
        app.dependency_overrides.pop(get_current_user, None)
        res = auth_client.get("/queries/")
        assert res.status_code == 401

    def test_protected_route_with_auth(self, auth_client, default_user):
        auth_client.post("/auth/login", json={
            "email": "soporte@gmail.com",
            "password": "123456",
        })
        res = auth_client.get("/queries/")
        assert res.status_code == 200


class TestDefaultUser:
    def test_default_user_seeded(self, store):
        user = store.get_user_by_email("soporte@gmail.com")
        assert user is not None
        assert user["email"] == "soporte@gmail.com"
        assert user["role"] == "admin"
        assert user["active"] is True
        assert verify_password("123456", user["password_hash"])


class TestPermissions:
    def test_permissions_endpoint(self, auth_client, default_user):
        auth_client.post("/auth/login", json={
            "email": "soporte@gmail.com",
            "password": "123456",
        })
        res = auth_client.get("/auth/permissions")
        assert res.status_code == 200
        body = res.json()
        assert "permissions" in body
        assert "menu.consultar.queries" in body["permissions"]
        assert "menu.consultar.ejecutar" in body["permissions"]

    def test_permissions_without_auth(self, auth_client):
        app.dependency_overrides.pop(get_current_user, None)
        res = auth_client.get("/auth/permissions")
        assert res.status_code == 401

    def test_protected_route_denies_without_permission(self, auth_client, store):
        # Create a user with no permissions
        user = store.create_user({
            "id": "no-perms-user",
            "email": "noperms@example.com",
            "password_hash": get_password_hash("secret"),
            "role": "user",
            "active": True,
            "created_at": None,
            "updated_at": None,
        })
        app.dependency_overrides[get_current_user] = lambda: user
        client = TestClient(app, raise_server_exceptions=False)
        res = client.get("/queries/")
        assert res.status_code == 403


class TestUserCreatedFromFrontendScenario:
    """Reproduce the reported scenario: create a user from the admin panel,
    assign a permission, logout, and login from scratch.
    """

    def test_created_user_can_login_and_needs_query_permission(self, auth_client, store):
        # Admin (soporte@gmail.com) creates a new user with a known password.
        auth_client.post("/auth/login", json={
            "email": "soporte@gmail.com",
            "password": "123456",
        })
        create_res = auth_client.post("/admin/users", json={
            "email": "usuario@gmail.com",
            "password": "123456",
            "role": "user",
            "active": True,
        })
        assert create_res.status_code == 201, create_res.text
        new_user = create_res.json()
        new_user_id = new_user["id"]

        # Assign only the 'Nuevo Query' permission.
        perm_res = auth_client.post(f"/admin/users/{new_user_id}/permissions", json={
            "permission_id": "menu.cargar.create",
            "granted": True,
        })
        assert perm_res.status_code == 200, perm_res.text

        # Logout admin.
        logout_res = auth_client.post("/auth/logout")
        assert logout_res.status_code == 200

        # New user logs in.
        login_res = auth_client.post("/auth/login", json={
            "email": "usuario@gmail.com",
            "password": "123456",
        })
        assert login_res.status_code == 200, login_res.text
        assert "access_token" in login_res.cookies

        # User can hit /auth/me.
        me_res = auth_client.get("/auth/me")
        assert me_res.status_code == 200
        assert me_res.json()["email"] == "usuario@gmail.com"

        # User lacks menu.consultar.queries -> 403.
        queries_res = auth_client.get("/queries/")
        assert queries_res.status_code == 403

        # Admin assigns menu.consultar.queries.
        auth_client.post("/auth/login", json={
            "email": "soporte@gmail.com",
            "password": "123456",
        })
        grant_res = auth_client.post(f"/admin/users/{new_user_id}/permissions", json={
            "permission_id": "menu.consultar.queries",
            "granted": True,
        })
        assert grant_res.status_code == 200, grant_res.text

        # New user logs back in and now can list queries.
        auth_client.post("/auth/logout")
        login2 = auth_client.post("/auth/login", json={
            "email": "usuario@gmail.com",
            "password": "123456",
        })
        assert login2.status_code == 200
        queries2 = auth_client.get("/queries/")
        assert queries2.status_code == 200

    def test_user_with_no_permissions_can_login(self, auth_client, store):
        """A user with no permissions must still be able to log in and
        authenticate; they just won't see any menu items."""
        # Admin creates a new user without assigning any permission.
        auth_client.post("/auth/login", json={
            "email": "soporte@gmail.com",
            "password": "123456",
        })
        create_res = auth_client.post("/admin/users", json={
            "email": "noperm@example.com",
            "password": "123456",
            "role": "user",
            "active": True,
        })
        assert create_res.status_code == 201, create_res.text

        # Logout admin and login with the new user.
        auth_client.post("/auth/logout")
        login_res = auth_client.post("/auth/login", json={
            "email": "noperm@example.com",
            "password": "123456",
        })
        assert login_res.status_code == 200, login_res.text
        assert "access_token" in login_res.cookies

        # /auth/me works.
        me_res = auth_client.get("/auth/me")
        assert me_res.status_code == 200
        assert me_res.json()["email"] == "noperm@example.com"

        # /permissions is empty.
        perms_res = auth_client.get("/auth/permissions")
        assert perms_res.status_code == 200
        assert perms_res.json()["permissions"] == []

        # Protected routes are forbidden, not unauthenticated.
        queries_res = auth_client.get("/queries/")
        assert queries_res.status_code == 403


from auth import verify_password
