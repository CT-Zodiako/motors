"""Tests for query_registry module (editable-queries WU1 / WU3 migration).

Covers spec requirements: Query Destination Registry (R-CAT-4).
"""
import pytest

from config_store import get_store

def _destinations_for(query_name: str) -> list[dict]:
    return [d for d in get_store().list_destinations() if d["query_name"] == query_name]


@pytest.fixture(autouse=True)
def _seed_query(store):
    """Ensure a test query exists in the store before tests that need it."""
    # The store fixture already creates General; tests create their own named queries.
    yield


@pytest.fixture
def sample_query(store):
    """Create a query and return its name."""
    store.upsert_query({
        "name": "t_seed_query",
        "description": "",
        "model": "res.partner",
        "method": "search_read",
        "domain": [],
        "fields": [],
        "limit_val": 100,
        "active": True,
        "category_id": next(c["id"] for c in store.list_categories() if c["name"] == "General"),
    })
    return "t_seed_query"


@pytest.fixture
def sample_schedule(store, sample_query):
    """Create a schedule and return its dict."""
    row = {
        "name": "t_seed_sched",
        "query_name": sample_query,
        "dataset_id": "t_dataset",
        "table_id": "t_table",
        "frequency": "daily",
        "hour": 0,
        "minute": 0,
        "active": True,
    }
    return store.create_schedule(row)


@pytest.fixture
def sample_destination(store, sample_query):
    """Create a destination and return its dict."""
    from query_registry import upsert_destination
    return upsert_destination(sample_query, "ds1", "tbl1", "manual")


def test_init_is_idempotent_for_destinations():
    store = get_store()
    store.seed_defaults()
    count_before = len(store.list_destinations())
    store.seed_defaults()
    count_after = len(store.list_destinations())
    assert count_before == count_after


def test_init_seeds_from_query_schedules(store, sample_query, sample_schedule):
    """Re-initing config_store seeds distinct (query_name, dataset_id, table_id) from schedules."""
    # Clear destinations so seeding has something to do
    store._data["query_destinations"] = []
    store.seed_destinations_from_schedules()
    rows = _destinations_for(sample_query)
    assert len(rows) == 1
    assert rows[0]["dataset_id"] == "t_dataset"
    assert rows[0]["table_id"] == "t_table"
    assert rows[0]["origin"] == "schedule"
    assert rows[0]["stale"] is False


def test_seed_is_idempotent(store, sample_query):
    store.create_schedule({
        "name": "t_seed_idem",
        "query_name": sample_query,
        "dataset_id": "t_ds2",
        "table_id": "t_t2",
        "frequency": "daily",
        "hour": 0,
        "minute": 0,
        "active": True,
    })
    store.seed_destinations_from_schedules()
    count1 = len(get_store().list_destinations())
    store.seed_destinations_from_schedules()
    count2 = len(get_store().list_destinations())
    assert count1 == count2


def test_upsert_destination_insert(sample_query):
    from query_registry import upsert_destination

    upsert_destination(sample_query, "ds1", "tbl1", "manual")
    rows = _destinations_for(sample_query)
    assert len(rows) == 1
    assert rows[0]["dataset_id"] == "ds1"
    assert rows[0]["origin"] == "manual"


def test_upsert_destination_update_origin(sample_query):
    from query_registry import upsert_destination

    upsert_destination(sample_query, "ds1", "tbl1", "manual")
    upsert_destination(sample_query, "ds1", "tbl1", "schedule")
    rows = _destinations_for(sample_query)
    assert len(rows) == 1
    assert rows[0]["origin"] == "schedule"


def test_list_destinations(sample_query):
    from query_registry import list_destinations, upsert_destination

    upsert_destination(sample_query, "ds1", "tbl1", "manual")
    upsert_destination(sample_query, "ds2", "tbl2", "schedule")
    rows = list_destinations(sample_query)
    assert len(rows) == 2
    datasets = {r["dataset_id"] for r in rows}
    assert datasets == {"ds1", "ds2"}


def test_list_destinations_unknown_query():
    from query_registry import list_destinations

    rows = list_destinations("t_noexist")
    assert rows == []


def test_mark_ok_and_stale(sample_query):
    from query_registry import upsert_destination, mark_ok, mark_stale

    dest = upsert_destination(sample_query, "ds1", "tbl1", "manual")
    dest_id = dest["id"]

    mark_stale(dest_id, "connection error")
    row = [d for d in get_store().list_destinations() if d["id"] == dest_id][0]
    assert row["stale"] is True
    assert row["last_error"] == "connection error"

    schema = [{"name": "col1", "type": "STRING"}]
    mark_ok(dest_id, schema)
    row = [d for d in get_store().list_destinations() if d["id"] == dest_id][0]
    assert row["stale"] is False
    assert row["last_error"] is None
    assert row["last_schema"] == schema


def test_seed_with_zero_schedules(store):
    """Seeding when query_schedules has no matching rows is a no-op."""
    store._data["query_destinations"] = []
    count_before = len(get_store().list_destinations())
    store.seed_destinations_from_schedules()
    count_after = len(get_store().list_destinations())
    assert count_before == count_after


def test_deactivate_query_cascades_to_destinations(sample_query):
    """Deactivating a query deletes its destinations."""
    from query_registry import upsert_destination
    from config_store import get_store

    upsert_destination(sample_query, "ds1", "tbl1", "manual")
    assert _destinations_for(sample_query)
    get_store().deactivate_query(sample_query)
    assert _destinations_for(sample_query) == []


