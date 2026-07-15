"""Tests for extended PATCH /queries/{name} — editable surface + propagation."""
import pytest
from fastapi.testclient import TestClient
from main import app

client = TestClient(app)


@pytest.fixture(autouse=True)
def ensure_general_category():
    """General category must exist for query creation."""
    from db import execute
    execute("INSERT INTO query_categories (name) VALUES ('General') ON CONFLICT DO NOTHING")


@pytest.fixture
def sample_query():
    """Create a query and return its name."""
    from db import execute
    execute(
        """
        INSERT INTO odoo_queries (name, description, model, method, domain, fields, limit_val, category_id, active)
        VALUES ('test_patch_q', 'desc', 'res.partner', 'search_read', '[]', '[\"name\"]', 50, 1, TRUE)
        ON CONFLICT (name) DO UPDATE SET active = TRUE, description = EXCLUDED.description
        """
    )
    return "test_patch_q"


# ── RED: module doesn't exist yet (QueryPatchIn, propagation import) ──

def test_patch_full_edit_success(sample_query, monkeypatch):
    """PATCH updates fields, domain, limit_val, description, category_id and returns propagation report."""
    # Stub propagation so we don't need Odoo/BQ
    monkeypatch.setattr(
        "query_propagation.propagate_query_edit",
        lambda q: {"total": 0, "ok": 0, "failed": 0, "destinations": []},
    )
    payload = {
        "fields": ["name", "email"],
        "domain": [["active", "=", True]],
        "limit_val": 100,
        "description": "updated",
        "category_id": 1,
    }
    r = client.patch(f"/queries/{sample_query}", json=payload)
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["query"]["name"] == sample_query
    assert data["query"]["fields"] == ["name", "email"]
    assert data["query"]["domain"] == [["active", "=", True]]
    assert data["query"]["limit_val"] == 100
    assert data["query"]["description"] == "updated"
    assert "propagation" in data


def test_patch_category_only_backwards_compat(sample_query):
    """PATCH with only category_id still works (existing frontend call)."""
    r = client.patch(f"/queries/{sample_query}", json={"category_id": 1})
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["query"]["category_id"] == 1


def test_patch_immutable_name_rejected(sample_query):
    r = client.patch(f"/queries/{sample_query}", json={"name": "hacked"})
    assert r.status_code == 400, r.text
    assert "name" in r.json()["detail"].lower() or "immutable" in r.json()["detail"].lower()


def test_patch_immutable_model_rejected(sample_query):
    r = client.patch(f"/queries/{sample_query}", json={"model": "sale.order"})
    assert r.status_code == 400, r.text


def test_patch_immutable_method_rejected(sample_query):
    r = client.patch(f"/queries/{sample_query}", json={"method": "read"})
    assert r.status_code == 400, r.text


def test_patch_unknown_query_404():
    r = client.patch("/queries/nonexistent_query_xyz", json={"description": "x"})
    assert r.status_code == 404


def test_patch_negative_limit_400(sample_query):
    r = client.patch(f"/queries/{sample_query}", json={"limit_val": -5})
    assert r.status_code == 400


def test_patch_empty_fields_400(sample_query):
    r = client.patch(f"/queries/{sample_query}", json={"fields": []})
    assert r.status_code == 400


def test_patch_invalid_domain_400(sample_query):
    r = client.patch(f"/queries/{sample_query}", json={"domain": "not_a_list"})
    assert r.status_code in (400, 422)


def test_patch_propagation_in_response(sample_query, monkeypatch):
    """Propagation report shape must match design D7 contract."""
    fake_report = {
        "total": 2,
        "ok": 1,
        "failed": 1,
        "destinations": [
            {"dataset_id": "ds1", "table_id": "t1", "status": "ok"},
            {"dataset_id": "ds2", "table_id": "t2", "status": "failed", "error": "boom"},
        ],
    }
    monkeypatch.setattr("query_propagation.propagate_query_edit", lambda q: fake_report)
    r = client.patch(f"/queries/{sample_query}", json={"description": "x"})
    assert r.status_code == 200
    assert r.json()["propagation"] == fake_report


def test_patch_zero_destinations_propagation(sample_query, monkeypatch):
    """No destinations → propagation total 0, edit still saved."""
    monkeypatch.setattr(
        "query_propagation.propagate_query_edit",
        lambda q: {"total": 0, "ok": 0, "failed": 0, "destinations": []},
    )
    r = client.patch(f"/queries/{sample_query}", json={"description": "no-dest"})
    assert r.status_code == 200
    assert r.json()["propagation"]["total"] == 0
    assert r.json()["query"]["description"] == "no-dest"
def test_patch_same_name_value_ok(sample_query):
    """PATCH with name equal to current value is NOT an immutable violation (200)."""
    r = client.patch(f"/queries/{sample_query}", json={"name": sample_query})
    assert r.status_code == 200, r.text


def test_patch_empty_body_noop(sample_query):
    """Empty PATCH body is a 200 no-op; stored query unchanged."""
    r = client.patch(f"/queries/{sample_query}", json={})
    assert r.status_code == 200, r.text
    assert r.json()["query"]["description"] == "desc"


def test_patch_limit_zero_clears_limit(sample_query):
    """limit_val=0 is accepted and stored (0/None = no-limit convention, D6)."""
    r = client.patch(f"/queries/{sample_query}", json={"limit_val": 0})
    assert r.status_code == 200, r.text
    assert r.json()["query"]["limit_val"] == 0
