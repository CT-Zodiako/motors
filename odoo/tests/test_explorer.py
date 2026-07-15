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
