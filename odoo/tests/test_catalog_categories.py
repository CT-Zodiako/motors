"""Group 4 — category-aware catalog tests (query-categories change).

Covers spec `query-catalog` requirements: Query Upsert Category Assignment,
Query Recategorization Endpoint, Query Listing Includes Category.
"""
import uuid
import pytest


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


@pytest.mark.parametrize("operator", ["=", "!=", ">", ">=", "<", "<=", "=?", "=like", "like", "not like", "=ilike", "ilike", "not ilike", "child_of", "parent_of"])
def test_query_domain_valid_operators(client, operator):
    value = 7 if operator in {"child_of", "parent_of"} else "x"
    name = f"t_op_{_uid()}"
    assert client.post("/queries/", json={"name": name, "model": "res.partner", "domain": [["name", operator, value]]}).status_code == 201


@pytest.mark.parametrize("domain", [["&", ["name", "=", "x"]], [["name", "unknown", "x"]], [["name", "=", "x"], ["name", "=", "y"]]])
def test_query_domain_invalid_operator_or_prefix_grammar(client, domain):
    res = client.post("/queries/", json={"name": f"t_bad_{_uid()}", "model": "res.partner", "domain": domain})
    assert res.status_code == 400


def test_query_domain_accepts_flat_prefix_connectors(client):
    domains = [
        ["&", ["active", "=", True], ["name", "=", "x"]],
        ["|", ["active", "=", True], ["name", "=", "x"]],
        ["!", ["active", "=", True]],
    ]
    for domain in domains:
        assert client.post("/queries/", json={"name": f"t_conn_{_uid()}", "model": "res.partner", "domain": domain}).status_code == 201


@pytest.mark.parametrize("operator", ["in", "not in"])
def test_query_domain_list_operators_require_non_empty_lists(client, operator):
    good = client.post("/queries/", json={"name": f"t_list_{_uid()}", "model": "res.partner", "domain": [["id", operator, [1, "2"]]]})
    assert good.status_code == 201
    bad = client.post("/queries/", json={"name": f"t_list_bad_{_uid()}", "model": "res.partner", "domain": [["id", operator, []]]})
    assert bad.status_code == 400


@pytest.mark.parametrize("value", [True, "", [], 1.5, {"id": 1}, [True], [""]])
def test_hierarchy_values_reject_invalid_shapes(client, value):
    res = client.post("/queries/", json={"name": f"t_hbad_{_uid()}", "model": "res.partner", "domain": [["id", "child_of", value]]})
    assert res.status_code == 400


@pytest.mark.parametrize("value", [1, "7", [1, "7"]])
def test_hierarchy_values_accept_scalar_or_non_empty_list(client, value):
    res = client.post("/queries/", json={"name": f"t_hgood_{_uid()}", "model": "res.partner", "domain": [["id", "parent_of", value]]})
    assert res.status_code == 201


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
