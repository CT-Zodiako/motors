"""Bootstrap tests — idempotent schema + seeding (D14).

Replaces test_migration.py; uses InMemoryConfigStore (no real BQ needed for unit tests).
"""
from config_store.memory_store import InMemoryConfigStore
from config_store.bootstrap import ensure_schema, seed_defaults


class TestBootstrap:
    def test_ensure_schema_idempotent(self):
        s = InMemoryConfigStore()
        ensure_schema(s)
        ensure_schema(s)  # no error

    def test_seed_defaults_creates_general(self):
        s = InMemoryConfigStore()
        ensure_schema(s)
        seed_defaults(s)
        cats = s.list_categories()
        assert any(c["name"] == "General" for c in cats)

    def test_seed_defaults_creates_seed_queries(self):
        s = InMemoryConfigStore()
        ensure_schema(s)
        seed_defaults(s)
        qs = s.list_queries()
        names = {q["name"] for q in qs}
        assert names == {"clientes_activos", "productos_todos", "ventas_confirmadas", "facturas_emitidas"}

    def test_seed_defaults_idempotent(self):
        s = InMemoryConfigStore()
        ensure_schema(s)
        seed_defaults(s)
        cats1 = len(s.list_categories())
        qs1 = len(s.list_queries())
        seed_defaults(s)
        assert len(s.list_categories()) == cats1
        assert len(s.list_queries()) == qs1

    def test_seed_queries_have_categories(self):
        s = InMemoryConfigStore()
        ensure_schema(s)
        seed_defaults(s)
        for q in s.list_queries():
            assert q["category"] is not None
            assert q["category"]["name"] in {"Clientes", "Productos", "Ventas", "Facturación"}

    def test_seed_queries_preserve_user_data_on_re_run(self):
        s = InMemoryConfigStore()
        ensure_schema(s)
        seed_defaults(s)
        # Add a user query
        gen = [c for c in s.list_categories() if c["name"] == "General"][0]
        s.upsert_query({
            "name": "user_query",
            "description": "",
            "model": "x",
            "method": "search_read",
            "domain": [],
            "fields": [],
            "limit_val": 10,
            "active": True,
            "category_id": gen["id"],
        })
        seed_defaults(s)
        assert s.get_query("user_query") is not None
