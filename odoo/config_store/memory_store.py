"""InMemoryConfigStore — test implementation sharing codecs/validators (D13)."""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from . import codecs, validators
from .cache import Cache
from .errors import ConflictError, NotFoundError, ValidationError


class InMemoryConfigStore:
    """In-memory store for tests; shares codecs/validators with BQ impl."""

    def __init__(self) -> None:
        self._data: dict[str, list[dict[str, Any]]] = {
            "odoo_queries": [],
            "query_categories": [],
            "query_schedules": [],
            "query_schedule_runs": [],
            "query_destinations": [],
        }
        self._cache = Cache(ttl_seconds=30)
        self._next_id = 1

    # ------------------------------------------------------------------
    # ID allocation (epoch-micros for BQ; sequential for memory store)
    # ------------------------------------------------------------------

    def _new_id(self) -> int:
        nid = self._next_id
        self._next_id += 1
        return nid

    # ------------------------------------------------------------------
    # bootstrap
    # ------------------------------------------------------------------

    def ensure_schema(self) -> None:
        pass  # memory tables always exist

    def seed_defaults(self) -> None:
        # General category if empty
        if not self._data["query_categories"]:
            self.create_category("General", "Default category")
        # Seed queries if empty
        if not self._data["odoo_queries"]:
            from .bootstrap import _SEED_QUERIES
            for q in _SEED_QUERIES:
                cat = self._find_category_by_name(q["category"])
                cat_id = cat["id"] if cat else self.create_category(q["category"])["id"]
                row = {
                    "id": self._new_id(),
                    "name": q["name"],
                    "description": q["description"],
                    "model": q["model"],
                    "method": q["method"],
                    "domain": q["domain"],
                    "fields": q["fields"],
                    "limit_val": q["limit_val"],
                    "active": True,
                    "created_at": datetime.now(timezone.utc).replace(tzinfo=None),
                    "category_id": cat_id,
                }
                self._data["odoo_queries"].append(codecs.encode_row("odoo_queries", row))
        self.seed_destinations_from_schedules()

    # ------------------------------------------------------------------
    # categories
    # ------------------------------------------------------------------

    def list_categories(self) -> list[dict]:
        cached = self._cache.get("categories")
        if cached is not None:
            return cached
        rows = [codecs.decode_row("query_categories", r) for r in self._data["query_categories"]]
        rows.sort(key=lambda r: r["name"].lower())
        self._cache.set("categories", rows)
        return rows

    def create_category(self, name: str, description: str | None = None) -> dict:
        if any(r["name"] == name for r in self._data["query_categories"]):
            raise ConflictError(f"Category name already exists: {name}")
        row = {
            "id": self._new_id(),
            "name": name,
            "description": description,
            "created_at": datetime.now(timezone.utc).replace(tzinfo=None),
        }
        self._data["query_categories"].append(codecs.encode_row("query_categories", row))
        self._cache.invalidate_categories()
        return codecs.decode_row("query_categories", row)

    def delete_category(self, category_id: int) -> None:
        gen = [r for r in self._data["query_categories"] if r["id"] == category_id and r["name"] == "General"]
        if gen:
            raise ConflictError("Cannot delete the General category")
        # Ref-count check
        refs = [r for r in self._data["odoo_queries"] if r.get("category_id") == category_id]
        if refs:
            raise ConflictError("Category is referenced by queries")
        self._data["query_categories"] = [r for r in self._data["query_categories"] if r["id"] != category_id]
        self._cache.invalidate_categories()

    def _find_category_by_name(self, name: str) -> dict | None:
        for r in self._data["query_categories"]:
            if r["name"] == name:
                return codecs.decode_row("query_categories", r)
        return None

    def _find_category_by_id(self, category_id: int) -> dict | None:
        for r in self._data["query_categories"]:
            if r["id"] == category_id:
                return codecs.decode_row("query_categories", r)
        return None

    # ------------------------------------------------------------------
    # queries
    # ------------------------------------------------------------------

    def list_queries(self) -> list[dict]:
        cached = self._cache.get("queries")
        if cached is not None:
            return cached
        rows = [codecs.decode_row("odoo_queries", r) for r in self._data["odoo_queries"]]
        # App-side category resolution
        cats = {c["id"]: c for c in self.list_categories()}
        for r in rows:
            r["category"] = cats.get(r.get("category_id"))
        self._cache.set("queries", rows)
        return rows

    def get_query(self, name: str) -> dict | None:
        for r in self._data["odoo_queries"]:
            if r["name"] == name:
                decoded = codecs.decode_row("odoo_queries", r)
                cats = {c["id"]: c for c in self.list_categories()}
                decoded["category"] = cats.get(decoded.get("category_id"))
                return decoded
        return None

    def upsert_query(self, row: dict) -> dict:
        name = row["name"]
        # Validate category_id exists
        cat_id = row.get("category_id")
        if cat_id is not None and self._find_category_by_id(cat_id) is None:
            raise ValidationError(f"Category id {cat_id} does not exist")
        # Check uniqueness
        existing = [r for r in self._data["odoo_queries"] if r["name"] == name]
        # Strip app-side fields before encoding
        clean_row = {k: v for k, v in row.items() if k in [c["name"] for c in codecs.TABLE_SCHEMAS["odoo_queries"]]}
        if existing:
            # Update
            encoded = codecs.encode_row("odoo_queries", clean_row)
            idx = self._data["odoo_queries"].index(existing[0])
            self._data["odoo_queries"][idx] = encoded
        else:
            # Insert
            if "id" not in clean_row:
                clean_row["id"] = self._new_id()
            if "created_at" not in clean_row:
                clean_row["created_at"] = datetime.now(timezone.utc).replace(tzinfo=None)
            self._data["odoo_queries"].append(codecs.encode_row("odoo_queries", clean_row))
        self._cache.invalidate_queries()
        return self.get_query(name)

    def patch_query(self, name: str, patch: dict) -> dict:
        existing = self.get_query(name)
        if existing is None:
            raise NotFoundError(f"Query {name} not found")
        cat_id = patch.get("category_id")
        if cat_id is not None and self._find_category_by_id(cat_id) is None:
            raise ValidationError(f"Category id {cat_id} does not exist")
        updated = {**existing, **patch}
        # Preserve id/created_at/name; strip app-side fields
        updated["id"] = existing["id"]
        updated["name"] = existing["name"]
        updated["created_at"] = existing["created_at"]
        updated.pop("category", None)
        self.upsert_query(updated)
        return self.get_query(name)

    def deactivate_query(self, name: str) -> None:
        existing = self.get_query(name)
        if existing is None:
            raise NotFoundError(f"Query {name} not found")
        existing["active"] = False
        existing.pop("category", None)
        self.upsert_query(existing)
        # Cascade: delete destinations
        self._data["query_destinations"] = [
            r for r in self._data["query_destinations"] if r["query_name"] != name
        ]
        self._cache.invalidate_queries()
        self._cache.invalidate_destinations()

    # ------------------------------------------------------------------
    # schedules
    # ------------------------------------------------------------------

    def list_schedules(self) -> list[dict]:
        cached = self._cache.get("schedules")
        if cached is not None:
            return cached
        rows = [codecs.decode_row("query_schedules", r) for r in self._data["query_schedules"]]
        self._cache.set("schedules", rows)
        return rows

    def get_schedule(self, schedule_id: int) -> dict | None:
        for r in self._data["query_schedules"]:
            if r["id"] == schedule_id:
                return codecs.decode_row("query_schedules", r)
        return None

    def create_schedule(self, row: dict) -> dict:
        validators.validate_schedule(row)
        qn = row.get("query_name")
        if qn and self.get_query(qn) is None:
            raise ValidationError(f"Query {qn} does not exist")
        if "id" not in row:
            row["id"] = self._new_id()
        if "created_at" not in row:
            row["created_at"] = datetime.now(timezone.utc).replace(tzinfo=None)
        self._data["query_schedules"].append(codecs.encode_row("query_schedules", row))
        self._cache.invalidate_schedules()
        return codecs.decode_row("query_schedules", row)

    def update_schedule(self, schedule_id: int, patch: dict) -> dict:
        existing = self.get_schedule(schedule_id)
        if existing is None:
            raise NotFoundError(f"Schedule {schedule_id} not found")
        validators.validate_schedule(patch)
        updated = {**existing, **patch}
        updated["id"] = existing["id"]
        updated["created_at"] = existing["created_at"]
        idx = next(i for i, r in enumerate(self._data["query_schedules"]) if r["id"] == schedule_id)
        self._data["query_schedules"][idx] = codecs.encode_row("query_schedules", updated)
        self._cache.invalidate_schedules(schedule_id)
        return codecs.decode_row("query_schedules", updated)

    def delete_schedule(self, schedule_id: int) -> None:
        if self.get_schedule(schedule_id) is None:
            raise NotFoundError(f"Schedule {schedule_id} not found")
        # Cascade: delete runs
        self._data["query_schedule_runs"] = [
            r for r in self._data["query_schedule_runs"] if r["schedule_id"] != schedule_id
        ]
        self._data["query_schedules"] = [r for r in self._data["query_schedules"] if r["id"] != schedule_id]
        self._cache.invalidate_schedules(schedule_id)

    # ------------------------------------------------------------------
    # runs
    # ------------------------------------------------------------------

    def list_runs(self, schedule_id: int) -> list[dict]:
        key = f"runs:{schedule_id}"
        cached = self._cache.get(key)
        if cached is not None:
            return cached
        rows = [
            codecs.decode_row("query_schedule_runs", r)
            for r in self._data["query_schedule_runs"]
            if r["schedule_id"] == schedule_id
        ]
        rows.sort(key=lambda r: r["id"], reverse=True)
        self._cache.set(key, rows)
        return rows

    def insert_run(self, run: dict) -> dict:
        if "id" not in run:
            run["id"] = self._new_id()
        if "started_at" not in run:
            run["started_at"] = datetime.now(timezone.utc).replace(tzinfo=None)
        self._data["query_schedule_runs"].append(codecs.encode_row("query_schedule_runs", run))
        self._cache.invalidate_runs(run["schedule_id"])
        return codecs.decode_row("query_schedule_runs", run)

    def finish_run(self, run_id: int, result: dict) -> None:
        for r in self._data["query_schedule_runs"]:
            if r["id"] == run_id:
                r["finished_at"] = result.get("finished_at", datetime.now(timezone.utc).replace(tzinfo=None))
                r["status"] = result["status"]
                r["message"] = result.get("message")
                r["rows_loaded"] = result.get("rows_loaded")
                # Update schedule last_run_*
                for s in self._data["query_schedules"]:
                    if s["id"] == r["schedule_id"]:
                        s["last_run_at"] = r["finished_at"]
                        s["last_run_status"] = r["status"]
                        s["last_run_message"] = r["message"]
                self._cache.invalidate_runs(r["schedule_id"])
                return
        raise NotFoundError(f"Run {run_id} not found")

    # ------------------------------------------------------------------
    # destinations
    # ------------------------------------------------------------------

    def list_destinations(self) -> list[dict]:
        cached = self._cache.get("destinations")
        if cached is not None:
            return cached
        rows = [codecs.decode_row("query_destinations", r) for r in self._data["query_destinations"]]
        self._cache.set("destinations", rows)
        return rows

    def upsert_destination(self, dest: dict) -> dict:
        qn, ds, tbl = dest["query_name"], dest["dataset_id"], dest["table_id"]
        existing = [r for r in self._data["query_destinations"]
                    if r["query_name"] == qn and r["dataset_id"] == ds and r["table_id"] == tbl]
        if existing:
            idx = self._data["query_destinations"].index(existing[0])
            self._data["query_destinations"][idx] = codecs.encode_row("query_destinations", dest)
        else:
            if "id" not in dest:
                dest["id"] = self._new_id()
            if "created_at" not in dest:
                dest["created_at"] = datetime.now(timezone.utc).replace(tzinfo=None)
            self._data["query_destinations"].append(codecs.encode_row("query_destinations", dest))
        self._cache.invalidate_destinations()
        return dest

    def mark_destination_stale(self, query_name: str, dataset_id: str, table_id: str, error: str | None = None) -> None:
        for r in self._data["query_destinations"]:
            if r["query_name"] == query_name and r["dataset_id"] == dataset_id and r["table_id"] == table_id:
                r["stale"] = True
                r["last_error"] = error
                self._cache.invalidate_destinations()
                return

    def mark_destination_ok(self, query_name: str, dataset_id: str, table_id: str, schema: dict | None = None) -> None:
        for r in self._data["query_destinations"]:
            if r["query_name"] == query_name and r["dataset_id"] == dataset_id and r["table_id"] == table_id:
                r["stale"] = False
                r["last_error"] = None
                r["last_sync_at"] = datetime.now(timezone.utc).replace(tzinfo=None)
                if schema is not None:
                    r["last_schema"] = schema
                self._cache.invalidate_destinations()
                return

    def seed_destinations_from_schedules(self) -> int:
        """Seed destinations from distinct (query_name, dataset_id, table_id) in schedules.
        Guard: only seeds when the destinations registry is empty.
        """
        if self._data["query_destinations"]:
            return 0
        seen = set()
        count = 0
        for s in self._data["query_schedules"]:
            key = (s["query_name"], s["dataset_id"], s["table_id"])
            if key not in seen:
                seen.add(key)
                self.upsert_destination({
                    "id": self._new_id(),
                    "query_name": s["query_name"],
                    "dataset_id": s["dataset_id"],
                    "table_id": s["table_id"],
                    "origin": "schedule",
                    "stale": False,
                    "last_error": None,
                    "last_sync_at": None,
                    "last_schema": None,
                    "created_at": datetime.now(timezone.utc).replace(tzinfo=None),
                })
                count += 1
        return count
