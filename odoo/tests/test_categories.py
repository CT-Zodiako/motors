"""Group 3 — /categories API tests (query-categories change).

Covers spec `query-catalog` requirement: Category Management API (+ General guard).
"""
import uuid


def _uid() -> str:
    return uuid.uuid4().hex[:8]


def test_list_categories_includes_general(client):
    res = client.get("/categories/")
    assert res.status_code == 200
    body = res.json()
    items = body if isinstance(body, list) else body.get("categories", [])
    names = [c["name"] for c in items]
    assert "General" in names
    for c in items:
        assert "id" in c and "name" in c


def test_list_categories_alphabetical(client):
    for n in (f"t_zz_{_uid()}", f"t_aa_{_uid()}"):
        assert client.post("/categories/", json={"name": n}).status_code == 201
    res = client.get("/categories/")
    items = res.json() if isinstance(res.json(), list) else res.json().get("categories", [])
    names = [c["name"] for c in items]
    assert names == sorted(names, key=str.lower)


def test_create_category_201(client):
    name = f"t_finance_{_uid()}"
    res = client.post("/categories/", json={"name": name, "description": "d"})
    assert res.status_code == 201
    body = res.json()
    created = body if "id" in body else body.get("category", {})
    assert created["name"] == name and created["id"]


def test_create_duplicate_category_409(client):
    name = f"t_dup_{_uid()}"
    assert client.post("/categories/", json={"name": name}).status_code == 201
    res = client.post("/categories/", json={"name": name})
    assert res.status_code == 409


def test_delete_missing_category_404(client):
    res = client.delete("/categories/999999999")
    assert res.status_code == 404


def test_delete_general_409(client):
    items = client.get("/categories/").json()
    items = items if isinstance(items, list) else items.get("categories", [])
    general_id = next(c["id"] for c in items if c["name"] == "General")
    res = client.delete(f"/categories/{general_id}")
    assert res.status_code == 409
    # General MUST still exist
    items = client.get("/categories/").json()
    items = items if isinstance(items, list) else items.get("categories", [])
    assert any(c["name"] == "General" for c in items)


def test_delete_referenced_category_409_including_inactive_queries(client):
    cat = client.post("/categories/", json={"name": f"t_ref_{_uid()}"}).json()
    cat_id = cat["id"] if "id" in cat else cat["category"]["id"]
    qname = f"t_qref_{_uid()}"
    assert (
        client.post(
            "/queries/",
            json={"name": qname, "model": "res.partner", "category_id": cat_id},
        ).status_code
        == 201
    )
    # referenced by an ACTIVE query
    assert client.delete(f"/categories/{cat_id}").status_code == 409
    # soft-delete the query — category MUST STILL be blocked (inactive rows count)
    assert client.delete(f"/queries/{qname}").status_code == 200
    assert client.delete(f"/categories/{cat_id}").status_code == 409


def test_delete_unreferenced_category_204(client):
    cat = client.post("/categories/", json={"name": f"t_free_{_uid()}"}).json()
    cat_id = cat["id"] if "id" in cat else cat["category"]["id"]
    res = client.delete(f"/categories/{cat_id}")
    assert res.status_code == 204
