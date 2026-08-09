"""Store-agnostic dashboard CRUD contract suite (DD7, spec §2).

The suite is written against the ConfigStore dashboard contract and is
parameterized over a store factory:

- InMemoryConfigStore: always on (CI/local default), no credentials needed.
- BigQueryConfigStore: only when BQ_CONTRACT_TESTS=1 (env-gated live run,
  mirroring the BQ_LIVE_TESTS convention) against BQ_CONFIG_DATASET=config_test.

Both backends MUST exhibit identical observable behavior for every case here.
"""
import os
import time
from datetime import datetime, timezone

import pytest

from config_store.errors import ConflictError, NotFoundError
from config_store.memory_store import InMemoryConfigStore

NATIVE_DEFINITION = {
    "model": "sale.order",
    "fields": ["amount_total"],
    "group_by": ["user_id"],
    "domain": [["state", "=", "sale"]],
    "aggregations": {"amount_total": "sum"},
}


def _key(prefix: str) -> str:
    """Unique menu_key per run (BQ live runs share the sandbox dataset)."""
    return f"contract-{prefix}-{time.time_ns()}"


@pytest.fixture(
    params=[
        "memory",
        pytest.param(
            "bq",
            marks=pytest.mark.skipif(
                os.getenv("BQ_CONTRACT_TESTS") != "1",
                reason="BQ_CONTRACT_TESTS not set to 1",
            ),
        ),
    ]
)
def store(request, monkeypatch):
    if request.param == "memory":
        yield InMemoryConfigStore()
        return
    # Live BigQuery run: isolate in the config_test sandbox dataset.
    monkeypatch.setenv("BQ_CONFIG_DATASET", "config_test")
    from config_store.bq_store import BigQueryConfigStore

    s = BigQueryConfigStore()
    s.ensure_schema()
    yield s
    # Best-effort cleanup of contract rows.
    for row in s.list_dashboards(include_unpublished=True):
        if row.get("menu_key", "").startswith("contract-"):
            try:
                s.delete_dashboard(row["menu_key"])
            except NotFoundError:
                pass


class TestDashboardStoreContract:
    # ------------------------------------------------------------------
    # create + round-trip
    # ------------------------------------------------------------------

    def test_create_embed_roundtrip(self, store):
        key = _key("embed")
        row = store.create_dashboard({
            "menu_key": key,
            "name": "Embed Dash",
            "embed_url": "https://example.com/embed/1",
            "definition": None,
            "active": True,
        })
        assert row["menu_key"] == key
        assert row["embed_url"] == "https://example.com/embed/1"
        assert row.get("definition") is None
        assert row["active"] is True
        assert row["id"] is not None
        assert row["created_at"] is not None
        fetched = store.get_dashboard_any(key)
        assert fetched["embed_url"] == "https://example.com/embed/1"
        assert fetched.get("definition") is None

    def test_create_native_definition_roundtrip(self, store):
        key = _key("native")
        store.create_dashboard({
            "menu_key": key,
            "name": "Native Dash",
            "embed_url": None,
            "definition": NATIVE_DEFINITION,
            "active": True,
        })
        fetched = store.get_dashboard_any(key)
        assert fetched["embed_url"] is None
        # Definition JSON MUST survive encode/decode unchanged.
        assert fetched["definition"] == NATIVE_DEFINITION

    def test_create_defaults_unpublished(self, store):
        key = _key("draft")
        row = store.create_dashboard({
            "menu_key": key,
            "name": "Draft",
            "embed_url": "https://example.com/embed/2",
        })
        assert row["active"] is False
        assert store.get_dashboard_any(key)["active"] is False

    # ------------------------------------------------------------------
    # list
    # ------------------------------------------------------------------

    def test_list_dashboards_filters_unpublished(self, store):
        store.create_dashboard({
            "menu_key": _key("pub"),
            "name": "Published",
            "embed_url": "https://example.com/e",
            "active": True,
        })
        store.create_dashboard({
            "menu_key": _key("unpub"),
            "name": "Unpublished",
            "embed_url": "https://example.com/e2",
            "active": False,
        })
        published = store.list_dashboards()
        assert [d["name"] for d in published] == ["Published"]
        all_rows = store.list_dashboards(include_unpublished=True)
        assert {d["name"] for d in all_rows} == {"Published", "Unpublished"}

    def test_list_dashboards_ordered_by_lower_name(self, store):
        for name in ("bravo", "Alpha", "charlie"):
            store.create_dashboard({
                "menu_key": _key(name),
                "name": name,
                "embed_url": "https://example.com/e",
                "active": True,
            })
        names = [d["name"] for d in store.list_dashboards()]
        assert names == ["Alpha", "bravo", "charlie"]

    # ------------------------------------------------------------------
    # get
    # ------------------------------------------------------------------

    def test_get_dashboard_any_returns_unpublished(self, store):
        key = _key("any")
        store.create_dashboard({
            "menu_key": key,
            "name": "Hidden",
            "embed_url": "https://example.com/e",
            "active": False,
        })
        assert store.get_dashboard_any(key)["name"] == "Hidden"

    def test_get_dashboard_any_missing_returns_none(self, store):
        assert store.get_dashboard_any(_key("missing")) is None

    def test_get_dashboard_by_menu_key_stays_published_only(self, store):
        pub = _key("pub")
        unpub = _key("unpub")
        store.create_dashboard({
            "menu_key": pub,
            "name": "Pub",
            "embed_url": "https://example.com/e",
            "active": True,
        })
        store.create_dashboard({
            "menu_key": unpub,
            "name": "Unpub",
            "embed_url": "https://example.com/e2",
            "active": False,
        })
        assert store.get_dashboard_by_menu_key(pub)["name"] == "Pub"
        assert store.get_dashboard_by_menu_key(unpub) is None

    # ------------------------------------------------------------------
    # update
    # ------------------------------------------------------------------

    def test_update_merges_patch_only(self, store):
        key = _key("merge")
        store.create_dashboard({
            "menu_key": key,
            "name": "Original",
            "embed_url": "https://example.com/e",
            "active": True,
        })
        updated = store.update_dashboard(key, {"name": "Renamed"})
        assert updated["name"] == "Renamed"
        # Untouched fields preserved by merge semantics.
        assert updated["menu_key"] == key
        assert updated["embed_url"] == "https://example.com/e"
        assert updated["active"] is True

    def test_update_publish_flip_sets_updated_at(self, store):
        key = _key("flip")
        store.create_dashboard({
            "menu_key": key,
            "name": "Flip",
            "embed_url": "https://example.com/e",
            "active": False,
        })
        updated = store.update_dashboard(key, {"active": True})
        assert updated["active"] is True
        assert updated["updated_at"] is not None
        assert store.get_dashboard_by_menu_key(key) is not None
        # Unpublish again.
        updated = store.update_dashboard(key, {"active": False})
        assert updated["active"] is False
        assert store.get_dashboard_by_menu_key(key) is None

    def test_update_can_set_native_definition(self, store):
        key = _key("redef")
        store.create_dashboard({
            "menu_key": key,
            "name": "Redef",
            "embed_url": "https://example.com/e",
            "active": False,
        })
        updated = store.update_dashboard(key, {
            "definition": NATIVE_DEFINITION,
            "embed_url": None,
        })
        assert updated["definition"] == NATIVE_DEFINITION
        assert updated["embed_url"] is None

    def test_update_rekey(self, store):
        old_key = _key("old")
        new_key = _key("new")
        store.create_dashboard({
            "menu_key": old_key,
            "name": "Rekey",
            "embed_url": "https://example.com/e",
        })
        updated = store.update_dashboard(old_key, {"menu_key": new_key})
        assert updated["menu_key"] == new_key
        assert store.get_dashboard_any(old_key) is None
        assert store.get_dashboard_any(new_key)["name"] == "Rekey"

    # ------------------------------------------------------------------
    # conflict / not-found
    # ------------------------------------------------------------------

    def test_create_duplicate_menu_key_conflict(self, store):
        key = _key("dup")
        store.create_dashboard({
            "menu_key": key,
            "name": "First",
            "embed_url": "https://example.com/e",
        })
        with pytest.raises(ConflictError):
            store.create_dashboard({
                "menu_key": key,
                "name": "Second",
                "embed_url": "https://example.com/e2",
            })

    def test_update_rekey_conflict(self, store):
        key_a = _key("a")
        key_b = _key("b")
        store.create_dashboard({
            "menu_key": key_a,
            "name": "A",
            "embed_url": "https://example.com/a",
        })
        store.create_dashboard({
            "menu_key": key_b,
            "name": "B",
            "embed_url": "https://example.com/b",
        })
        with pytest.raises(ConflictError):
            store.update_dashboard(key_a, {"menu_key": key_b})

    def test_update_missing_not_found(self, store):
        with pytest.raises(NotFoundError):
            store.update_dashboard(_key("nope"), {"name": "X"})

    def test_delete_missing_not_found(self, store):
        with pytest.raises(NotFoundError):
            store.delete_dashboard(_key("nope"))

    # ------------------------------------------------------------------
    # delete
    # ------------------------------------------------------------------

    def test_delete_removes_row(self, store):
        key = _key("del")
        store.create_dashboard({
            "menu_key": key,
            "name": "Bye",
            "embed_url": "https://example.com/e",
            "active": True,
        })
        store.delete_dashboard(key)
        assert store.get_dashboard_any(key) is None
        assert all(d["menu_key"] != key for d in store.list_dashboards(include_unpublished=True))
