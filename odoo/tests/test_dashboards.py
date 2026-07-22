"""Group — /dashboards API tests (read-only dashboard embed lookup)."""
from datetime import datetime, timezone

from config_store import codecs


def _seed_dashboard(store, menu_key: str, name: str, embed_url: str, active: bool = True) -> dict:
    row = {
        "id": len(store._data["odoo_dashboards"]) + 1,
        "menu_key": menu_key,
        "name": name,
        "embed_url": embed_url,
        "active": active,
        "created_at": datetime.now(timezone.utc).replace(tzinfo=None),
    }
    store._data["odoo_dashboards"].append(codecs.encode_row("odoo_dashboards", row))
    return row


def test_get_dashboard_200(client, store):
    _seed_dashboard(store, "dashboards", "Ventas", "https://datastudio.google.com/embed/reporting/abc/page/1")
    res = client.get("/dashboards/dashboards")
    assert res.status_code == 200
    body = res.json()
    assert body["name"] == "Ventas"
    assert body["embed_url"] == "https://datastudio.google.com/embed/reporting/abc/page/1"


def test_get_dashboard_unknown_404(client, store):
    res = client.get("/dashboards/unknown_key")
    assert res.status_code == 404


def test_get_dashboard_inactive_404(client, store):
    _seed_dashboard(store, "inactive_dash", "Inactivo", "https://example.com/embed", active=False)
    res = client.get("/dashboards/inactive_dash")
    assert res.status_code == 404
