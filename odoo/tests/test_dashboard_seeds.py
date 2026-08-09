"""Seed tests — per-permission guard fix, admin grant, dashboard seeds (PR-1, 1.7).

Covers design risk #1: the whole-table seed guard must become per-row so
existing deployments receive new seed permissions, and the new admin-grant /
dashboard seed bootstrap steps must be idempotent and env-driven.
"""
from datetime import datetime, timezone

from config_store import codecs
from config_store.bootstrap import (
    _SEED_PERMISSIONS,
    grant_admin_permissions,
    seed_dashboard_defaults,
)
from config_store.memory_store import InMemoryConfigStore


def _insert_permission(store, pid: str, label: str = "Legacy label") -> None:
    store._data["odoo_permissions"].append(
        codecs.encode_row("odoo_permissions", {
            "id": pid,
            "label": label,
            "category": "legacy",
            "created_at": datetime.now(timezone.utc).replace(tzinfo=None),
        })
    )


def _create_user(store, user_id: str, role: str) -> dict:
    return store.create_user({
        "id": user_id,
        "email": f"{user_id}@example.com",
        "password_hash": "$2b$12$testhash",
        "role": role,
        "active": True,
    })


class TestPerPermissionSeedGuard:
    def test_reseeds_only_missing_ids_on_prepopulated_store(self):
        s = InMemoryConfigStore()
        _insert_permission(s, "menu.consultar.queries")
        s.seed_permission_defaults()
        perms = {p["id"]: p for p in s.list_permissions()}
        # The pre-existing row is left untouched.
        assert perms["menu.consultar.queries"]["label"] == "Legacy label"
        # Every missing seed id was inserted, including the new admin one.
        for seed in _SEED_PERMISSIONS:
            assert seed["id"] in perms
        assert "menu.admin.dashboards" in perms

    def test_fresh_store_seeds_everything(self):
        s = InMemoryConfigStore()
        s.seed_permission_defaults()
        ids = {p["id"] for p in s.list_permissions()}
        assert ids == {p["id"] for p in _SEED_PERMISSIONS}

    def test_idempotent_no_duplicates(self):
        s = InMemoryConfigStore()
        s.seed_permission_defaults()
        n = len(s.list_permissions())
        s.seed_permission_defaults()
        ids = [p["id"] for p in s.list_permissions()]
        assert len(ids) == n
        assert len(ids) == len(set(ids))


class TestGrantAdminPermissions:
    def test_grants_all_admin_permissions_to_admin_role(self):
        s = InMemoryConfigStore()
        s.seed_permission_defaults()
        _create_user(s, "admin-1", "admin")
        grant_admin_permissions(s)
        perms = s.get_user_permissions("admin-1")
        assert "menu.admin.dashboards" in perms
        assert "menu.admin.usuarios" in perms

    def test_skips_non_admin_users(self):
        s = InMemoryConfigStore()
        s.seed_permission_defaults()
        _create_user(s, "user-1", "user")
        grant_admin_permissions(s)
        assert s.get_user_permissions("user-1") == set()

    def test_idempotent(self):
        s = InMemoryConfigStore()
        s.seed_permission_defaults()
        _create_user(s, "admin-1", "admin")
        grant_admin_permissions(s)
        first = s.get_user_permissions("admin-1")
        grant_admin_permissions(s)
        assert s.get_user_permissions("admin-1") == first


class TestSeedDashboardDefaults:
    def test_creates_active_embed_row_when_env_set(self, monkeypatch):
        monkeypatch.setenv("SEED_DASHBOARD_EMBED_URL", "https://example.com/dash")
        s = InMemoryConfigStore()
        seed_dashboard_defaults(s)
        row = s.get_dashboard_any("dashboards")
        assert row is not None
        assert row["name"] == "Dashboards"
        assert row["embed_url"] == "https://example.com/dash"
        assert row["active"] is True
        assert row.get("definition") is None

    def test_skips_when_env_unset(self, monkeypatch):
        monkeypatch.delenv("SEED_DASHBOARD_EMBED_URL", raising=False)
        monkeypatch.delenv("SEED_DASHBOARD_VENTAS_EMBED_URL", raising=False)
        s = InMemoryConfigStore()
        seed_dashboard_defaults(s)
        assert s.list_dashboards(include_unpublished=True) == []

    def test_skips_existing_menu_key(self, monkeypatch):
        monkeypatch.setenv("SEED_DASHBOARD_EMBED_URL", "https://example.com/new")
        s = InMemoryConfigStore()
        s.create_dashboard({
            "menu_key": "dashboards",
            "name": "Custom",
            "embed_url": "https://example.com/original",
            "active": True,
        })
        seed_dashboard_defaults(s)
        rows = s.list_dashboards(include_unpublished=True)
        assert len(rows) == 1
        assert rows[0]["name"] == "Custom"
        assert rows[0]["embed_url"] == "https://example.com/original"

    def test_idempotent(self, monkeypatch):
        monkeypatch.setenv("SEED_DASHBOARD_EMBED_URL", "https://example.com/dash")
        s = InMemoryConfigStore()
        seed_dashboard_defaults(s)
        seed_dashboard_defaults(s)
        rows = s.list_dashboards(include_unpublished=True)
        assert len(rows) == 1
