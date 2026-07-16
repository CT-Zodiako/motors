"""Tests for InMemoryConfigStore — RED→GREEN→TRIANGULATE.

Covers: CRUD, app-enforced integrity (uniqueness, FK, cascades, General protection),
cache invalidation, next_id monotonic, seed_defaults idempotency.
"""
import pytest
from config_store.memory_store import InMemoryConfigStore
from config_store.errors import ConflictError, NotFoundError, ValidationError


@pytest.fixture
def store():
    s = InMemoryConfigStore()
    s.seed_defaults()
    return s


class TestCategories:
    def test_list_after_seed(self, store):
        cats = store.list_categories()
        assert any(c["name"] == "General" for c in cats)

    def test_create_category(self, store):
        c = store.create_category("Finance", "Money stuff")
        assert c["name"] == "Finance"
        assert c["description"] == "Money stuff"
        assert c["id"] is not None

    def test_duplicate_category_raises_conflict(self, store):
        store.create_category("Finance")
        with pytest.raises(ConflictError):
            store.create_category("Finance")

    def test_delete_unreferenced_category(self, store):
        c = store.create_category("Temp")
        store.delete_category(c["id"])
        assert not any(x["name"] == "Temp" for x in store.list_categories())

    def test_delete_general_raises_conflict(self, store):
        gen = [c for c in store.list_categories() if c["name"] == "General"][0]
        with pytest.raises(ConflictError):
            store.delete_category(gen["id"])

    def test_delete_referenced_category_raises_conflict(self, store):
        # Seed queries reference Clientes, Productos, etc.
        cat = [c for c in store.list_categories() if c["name"] == "Clientes"][0]
        with pytest.raises(ConflictError):
            store.delete_category(cat["id"])


class TestQueries:
    def test_list_queries_after_seed(self, store):
        qs = store.list_queries()
        assert len(qs) == 4
        for q in qs:
            assert q["category"] is not None

    def test_get_query(self, store):
        q = store.get_query("clientes_activos")
        assert q["model"] == "res.partner"
        assert q["category"]["name"] == "Clientes"

    def test_upsert_new_query(self, store):
        gen = [c for c in store.list_categories() if c["name"] == "General"][0]
        q = store.upsert_query({
            "name": "test_q",
            "description": "",
            "model": "res.partner",
            "method": "search_read",
            "domain": [],
            "fields": ["name"],
            "limit_val": 10,
            "active": True,
            "category_id": gen["id"],
        })
        assert q["name"] == "test_q"
        assert q["category"]["name"] == "General"

    def test_upsert_invalid_category(self, store):
        with pytest.raises(ValidationError):
            store.upsert_query({
                "name": "bad",
                "description": "",
                "model": "x",
                "method": "search_read",
                "domain": [],
                "fields": [],
                "limit_val": 10,
                "active": True,
                "category_id": 99999,
            })

    def test_patch_query(self, store):
        q = store.patch_query("clientes_activos", {"limit_val": 99})
        assert q["limit_val"] == 99
        assert q["name"] == "clientes_activos"  # unchanged

    def test_deactivate_query_cascades_destinations(self, store):
        # First create a destination
        store.upsert_destination({
            "query_name": "clientes_activos",
            "dataset_id": "ds",
            "table_id": "tbl",
            "origin": "manual",
        })
        store.deactivate_query("clientes_activos")
        assert not any(d["query_name"] == "clientes_activos" for d in store.list_destinations())


class TestSchedules:
    def test_create_schedule(self, store):
        s = store.create_schedule({
            "name": "daily",
            "query_name": "clientes_activos",
            "dataset_id": "analytics",
            "table_id": "clients",
            "frequency": "daily",
            "hour": 3,
            "minute": 0,
            "active": True,
        })
        assert s["frequency"] == "daily"
        assert s["hour"] == 3

    def test_invalid_frequency(self, store):
        with pytest.raises(ValidationError):
            store.create_schedule({
                "name": "bad",
                "query_name": "clientes_activos",
                "dataset_id": "d",
                "table_id": "t",
                "frequency": "minutely",
            })

    def test_hour_out_of_range(self, store):
        with pytest.raises(ValidationError):
            store.create_schedule({
                "name": "bad",
                "query_name": "clientes_activos",
                "dataset_id": "d",
                "table_id": "t",
                "frequency": "daily",
                "hour": 24,
            })

    def test_delete_schedule_cascades_runs(self, store):
        s = store.create_schedule({
            "name": "temp",
            "query_name": "clientes_activos",
            "dataset_id": "d",
            "table_id": "t",
            "frequency": "hourly",
            "interval_hours": 1,
        })
        run = store.insert_run({"schedule_id": s["id"], "status": "running"})
        store.delete_schedule(s["id"])
        assert store.get_schedule(s["id"]) is None
        assert store.list_runs(s["id"]) == []


class TestRuns:
    def test_insert_and_finish_run(self, store):
        s = store.create_schedule({
            "name": "s1",
            "query_name": "clientes_activos",
            "dataset_id": "d",
            "table_id": "t",
            "frequency": "hourly",
            "interval_hours": 1,
        })
        run = store.insert_run({"schedule_id": s["id"], "status": "running"})
        assert run["status"] == "running"
        store.finish_run(run["id"], {"status": "success", "rows_loaded": 42})
        finished = store.list_runs(s["id"])[0]
        assert finished["status"] == "success"
        assert finished["rows_loaded"] == 42
        # schedule last_run_* updated
        sched = store.get_schedule(s["id"])
        assert sched["last_run_status"] == "success"


class TestDestinations:
    def test_upsert_destination(self, store):
        d = store.upsert_destination({
            "query_name": "clientes_activos",
            "dataset_id": "ds",
            "table_id": "tbl",
            "origin": "manual",
        })
        assert d["query_name"] == "clientes_activos"

    def test_mark_stale_and_ok(self, store):
        d = store.upsert_destination({
            "query_name": "clientes_activos",
            "dataset_id": "ds",
            "table_id": "tbl",
            "origin": "manual",
        })
        store.mark_destination_stale(d["id"], "oops")
        d = store.list_destinations()[0]
        assert d["stale"] is True
        assert d["last_error"] == "oops"
        store.mark_destination_ok(d["id"], schema={"a": "STRING"})
        d = store.list_destinations()[0]
        assert d["stale"] is False
        assert d["last_schema"] == {"a": "STRING"}

    def test_seed_destinations_from_schedules(self, store):
        s = store.create_schedule({
            "name": "s1",
            "query_name": "clientes_activos",
            "dataset_id": "d1",
            "table_id": "t1",
            "frequency": "hourly",
            "interval_hours": 1,
        })
        count = store.seed_destinations_from_schedules()
        assert count >= 1
        ds = store.list_destinations()
        assert any(d["query_name"] == "clientes_activos" and d["dataset_id"] == "d1" for d in ds)


class TestCache:
    def test_cache_invalidation_on_category_create(self, store):
        store.list_categories()  # warm cache
        store.create_category("NewCat")
        # Cache should be invalidated; list returns fresh data
        cats = store.list_categories()
        assert any(c["name"] == "NewCat" for c in cats)

    def test_cache_invalidation_on_query_upsert(self, store):
        store.list_queries()  # warm cache
        gen = [c for c in store.list_categories() if c["name"] == "General"][0]
        store.upsert_query({
            "name": "new_q",
            "description": "",
            "model": "x",
            "method": "search_read",
            "domain": [],
            "fields": [],
            "limit_val": 10,
            "active": True,
            "category_id": gen["id"],
        })
        qs = store.list_queries()
        assert any(q["name"] == "new_q" for q in qs)


class TestIdMonotonic:
    def test_next_id_increases(self):
        s = InMemoryConfigStore()
        id1 = s._new_id()
        id2 = s._new_id()
        assert id2 > id1

    def test_next_id_under_fast_loop(self):
        s = InMemoryConfigStore()
        ids = [s._new_id() for _ in range(100)]
        assert len(set(ids)) == 100
        assert all(ids[i] < ids[i+1] for i in range(len(ids)-1))


class TestBootstrapIdempotency:
    def test_seed_defaults_twice(self):
        s = InMemoryConfigStore()
        s.seed_defaults()
        cats1 = len(s.list_categories())
        qs1 = len(s.list_queries())
        s.seed_defaults()
        assert len(s.list_categories()) == cats1
        assert len(s.list_queries()) == qs1


class TestOrdering:
    def test_list_categories_sorted_by_lower_name(self, store):
        store.create_category("Zebra")
        store.create_category("alpha")
        names = [c["name"] for c in store.list_categories()]
        assert names.index("alpha") < names.index("Zebra")
        assert names.index("General") < names.index("Zebra")

    def test_list_runs_descending_by_id(self, store):
        s = store.create_schedule({
            "name": "s1",
            "query_name": "clientes_activos",
            "dataset_id": "d",
            "table_id": "t",
            "frequency": "hourly",
            "interval_hours": 1,
        })
        r1 = store.insert_run({"schedule_id": s["id"], "status": "running"})
        r2 = store.insert_run({"schedule_id": s["id"], "status": "running"})
        runs = store.list_runs(s["id"])
        assert [run["id"] for run in runs] == [r2["id"], r1["id"]]


class TestSeedDestinationGuard:
    def test_re_seed_preserves_destination_state(self, store):
        s = store.create_schedule({
            "name": "s1",
            "query_name": "clientes_activos",
            "dataset_id": "d1",
            "table_id": "t1",
            "frequency": "hourly",
            "interval_hours": 1,
        })
        store.seed_destinations_from_schedules()
        d = [x for x in store.list_destinations() if x["dataset_id"] == "d1"][0]
        store.mark_destination_stale(d["id"], "schema drift")
        store.seed_destinations_from_schedules()
        d = [x for x in store.list_destinations() if x["dataset_id"] == "d1"][0]
        assert d["stale"] is True
        assert d["last_error"] == "schema drift"


class TestNotFoundErrors:
    def test_patch_query_missing(self, store):
        with pytest.raises(NotFoundError):
            store.patch_query("nonexistent", {"limit_val": 1})

    def test_deactivate_query_missing(self, store):
        with pytest.raises(NotFoundError):
            store.deactivate_query("nonexistent")

    def test_update_schedule_missing(self, store):
        with pytest.raises(NotFoundError):
            store.update_schedule(99999, {"hour": 1})

    def test_delete_schedule_missing(self, store):
        with pytest.raises(NotFoundError):
            store.delete_schedule(99999)

    def test_finish_run_missing(self, store):
        with pytest.raises(NotFoundError):
            store.finish_run(99999, {"status": "success"})


class TestFkValidation:
    def test_create_schedule_unknown_query(self, store):
        with pytest.raises(ValidationError):
            store.create_schedule({
                "name": "bad",
                "query_name": "no_such_query",
                "dataset_id": "d",
                "table_id": "t",
                "frequency": "daily",
            })


class TestEmptyLists:
    def test_empty_categories(self):
        s = InMemoryConfigStore()
        assert s.list_categories() == []

    def test_empty_queries(self):
        s = InMemoryConfigStore()
        assert s.list_queries() == []

    def test_empty_schedules(self):
        s = InMemoryConfigStore()
        assert s.list_schedules() == []

    def test_empty_destinations(self):
        s = InMemoryConfigStore()
        assert s.list_destinations() == []

    def test_empty_runs(self, store):
        s = store.create_schedule({
            "name": "s1",
            "query_name": "clientes_activos",
            "dataset_id": "d",
            "table_id": "t",
            "frequency": "hourly",
            "interval_hours": 1,
        })
        assert store.list_runs(s["id"]) == []


class TestCacheInvalidationSchedulesRunsDestinations:
    def test_cache_invalidation_on_schedule_create(self, store):
        store.list_schedules()  # warm cache
        store.create_schedule({
            "name": "s2",
            "query_name": "clientes_activos",
            "dataset_id": "d",
            "table_id": "t",
            "frequency": "hourly",
            "interval_hours": 1,
        })
        assert any(s["name"] == "s2" for s in store.list_schedules())

    def test_cache_invalidation_on_run_finish(self, store):
        s = store.create_schedule({
            "name": "s1",
            "query_name": "clientes_activos",
            "dataset_id": "d",
            "table_id": "t",
            "frequency": "hourly",
            "interval_hours": 1,
        })
        run = store.insert_run({"schedule_id": s["id"], "status": "running"})
        store.list_runs(s["id"])  # warm cache
        store.finish_run(run["id"], {"status": "success"})
        finished = store.list_runs(s["id"])[0]
        assert finished["status"] == "success"

    def test_cache_invalidation_on_destination_mark_stale(self, store):
        d = store.upsert_destination({
            "query_name": "clientes_activos",
            "dataset_id": "ds",
            "table_id": "tbl",
            "origin": "manual",
        })
        store.list_destinations()  # warm cache
        store.mark_destination_stale(d["id"], "err")
        d = store.list_destinations()[0]
        assert d["stale"] is True
