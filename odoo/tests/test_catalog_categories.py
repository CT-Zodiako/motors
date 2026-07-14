"""Group 4 — category-aware catalog tests (query-categories change).

Covers spec `query-catalog` requirements: Query Upsert Category Assignment,
Query Recategorization Endpoint, Query Listing Includes Category.
"""
import uuid


def _uid() -> str:
    return uuid.uuid4().hex[:8]


def _mk_category(client) -> int:
    cat = client.post("/categories/", json={"name": f"t_cat_{_uid()}"}).json()
    return cat["id"] if "id" in cat else cat["category"]["id"]


def _general_id(client) -> int:
    items = client.get("/categories/").json()
    items = items if isinstance(items, list) else items.get("categories", [])
    return next(c["id"] for c in items if c["name"] == "General")


def test_create_without_category_defaults_to_general(client):
    name = f"t_q1_{_uid()}"
    assert client.post("/queries/", json={"name": name, "model": "res.partner"}).status_code == 201
    row = client.get(f"/queries/{name}").json()
    assert row["category"]["name"] == "General"


def test_create_with_explicit_category(client):
    cat_id = _mk_category(client)
    name = f"t_q2_{_uid()}"
    assert (
        client.post(
            "/queries/", json={"name": name, "model": "res.partner", "category_id": cat_id}
        ).status_code
        == 201
    )
    row = client.get(f"/queries/{name}").json()
    assert row["category"]["id"] == cat_id


def test_update_without_category_preserves_assignment(client):
    cat_id = _mk_category(client)
    name = f"t_q3_{_uid()}"
    client.post("/queries/", json={"name": name, "model": "res.partner", "category_id": cat_id})
    # re-post same name WITHOUT category_id (upsert)
    assert client.post("/queries/", json={"name": name, "model": "res.partner"}).status_code == 201
    row = client.get(f"/queries/{name}").json()
    assert row["category"]["id"] == cat_id


def test_update_with_category_changes_assignment(client):
    cat_a = _mk_category(client)
    cat_b = _mk_category(client)
    name = f"t_q4_{_uid()}"
    client.post("/queries/", json={"name": name, "model": "res.partner", "category_id": cat_a})
    client.post("/queries/", json={"name": name, "model": "res.partner", "category_id": cat_b})
    row = client.get(f"/queries/{name}").json()
    assert row["category"]["id"] == cat_b


def test_invalid_category_rejected_422_and_row_untouched(client):
    name = f"t_q5_{_uid()}"
    res = client.post(
        "/queries/", json={"name": name, "model": "res.partner", "category_id": 999999999}
    )
    assert res.status_code in (400, 422)
    assert client.get(f"/queries/{name}").status_code == 404
    # and an existing query is not modified by a failed upsert
    cat_id = _mk_category(client)
    client.post("/queries/", json={"name": name, "model": "res.partner", "category_id": cat_id})
    res = client.post(
        "/queries/", json={"name": name, "model": "res.partner", "category_id": 999999999}
    )
    assert res.status_code in (400, 422)
    assert client.get(f"/queries/{name}").json()["category"]["id"] == cat_id


def test_patch_recategorizes_query(client):
    cat_a = _mk_category(client)
    cat_b = _mk_category(client)
    name = f"t_q6_{_uid()}"
    client.post("/queries/", json={"name": name, "model": "res.partner", "category_id": cat_a})
    res = client.patch(f"/queries/{name}", json={"category_id": cat_b})
    assert res.status_code == 200
    assert client.get(f"/queries/{name}").json()["category"]["id"] == cat_b


def test_patch_unknown_query_404(client):
    res = client.patch(f"/queries/t_missing_{_uid()}", json={"category_id": 1})
    assert res.status_code == 404


def test_patch_invalid_category_422_unchanged(client):
    cat_id = _mk_category(client)
    name = f"t_q7_{_uid()}"
    client.post("/queries/", json={"name": name, "model": "res.partner", "category_id": cat_id})
    res = client.patch(f"/queries/{name}", json={"category_id": 999999999})
    assert res.status_code in (400, 422)
    assert client.get(f"/queries/{name}").json()["category"]["id"] == cat_id


def test_list_embeds_category_object(client):
    cat_id = _mk_category(client)
    name = f"t_q8_{_uid()}"
    client.post("/queries/", json={"name": name, "model": "res.partner", "category_id": cat_id})
    rows = client.get("/queries/").json()
    rows = rows if isinstance(rows, list) else rows.get("queries", [])
    assert rows, "expected at least one query"
    for row in rows:
        assert row.get("category") is not None
        assert "id" in row["category"] and "name" in row["category"]
    ours = next(r for r in rows if r["name"] == name)
    assert ours["category"]["id"] == cat_id
