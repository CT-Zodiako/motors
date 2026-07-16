"""BigQueryConfigStore — BQ-backed implementation of ConfigStore (D9, D10, D11)."""
from __future__ import annotations

import json
import time
from datetime import datetime, timezone
from typing import Any

from google.cloud import bigquery
from google.cloud.bigquery import SchemaField

from . import codecs, sql, validators
from .cache import Cache
from .errors import ConflictError, NotFoundError, ValidationError

# Dataset name is resolved lazily via sql._dataset() at call time (D-A): never cache
# it at module level, or tests/sandboxes cannot redirect the store.


def _get_client() -> bigquery.Client:
    from bigquery_client import get_bigquery_client  # existing helper
    return get_bigquery_client()


def _scalar_param(name: str, bq_type: str, value: Any) -> bigquery.ScalarQueryParameter:
    return bigquery.ScalarQueryParameter(name, bq_type, value)


def _json_param(name: str, value: Any) -> bigquery.ScalarQueryParameter:
    return bigquery.ScalarQueryParameter(name, "STRING", json.dumps(value, separators=(",", ":"), ensure_ascii=False))


def _timestamp_param(name: str, value: datetime | None) -> bigquery.ScalarQueryParameter:
    if value is None:
        return bigquery.ScalarQueryParameter(name, "TIMESTAMP", None)
    if value.tzinfo is not None:
        value = value.astimezone(timezone.utc).replace(tzinfo=None)
    return bigquery.ScalarQueryParameter(name, "TIMESTAMP", value.isoformat(sep=" ", timespec="microseconds"))


def _bool_param(name: str, value: bool | None) -> bigquery.ScalarQueryParameter:
    return bigquery.ScalarQueryParameter(name, "BOOL", value)


def _int64_param(name: str, value: int | None) -> bigquery.ScalarQueryParameter:
    return bigquery.ScalarQueryParameter(name, "INT64", value)


def _string_param(name: str, value: str | None) -> bigquery.ScalarQueryParameter:
    return bigquery.ScalarQueryParameter(name, "STRING", value)


def _build_params(table: str, row: dict[str, Any]) -> list[bigquery.ScalarQueryParameter]:
    """Build ScalarQueryParameter list from a row dict per TABLE_SCHEMAS."""
    params = []
    for col in codecs.TABLE_SCHEMAS[table]:
        name = col["name"]
        value = row.get(name)
        bq_type = col["type"]
        if bq_type == "JSON":
            params.append(_json_param(name, value))
        elif bq_type == "TIMESTAMP":
            params.append(_timestamp_param(name, value))
        elif bq_type == "BOOL":
            params.append(_bool_param(name, value))
        elif bq_type == "INT64":
            params.append(_int64_param(name, value))
        else:
            params.append(_string_param(name, value))
    return params


class BigQueryConfigStore:
    """BQ-backed store: parameterized reads, load-job/DML write matrix."""

    def __init__(self, client: bigquery.Client | None = None) -> None:
        self._client = client or _get_client()
        self._cache = Cache()
        self._last_id = 0

    # ------------------------------------------------------------------
    # ID allocation (epoch-micros with per-process monotonic guard, D11)
    # ------------------------------------------------------------------

    def _next_id(self) -> int:
        t = time.time_ns() // 1000
        if t <= self._last_id:
            t = self._last_id + 1
        self._last_id = t
        return t

    # ------------------------------------------------------------------
    # Internal query helper
    # ------------------------------------------------------------------

    def _query(self, sql_text: str, params: list[bigquery.ScalarQueryParameter] | None = None) -> list[dict]:
        job_config = bigquery.QueryJobConfig(query_parameters=params or [])
        rows = list(self._client.query(sql_text, job_config=job_config).result())
        return [dict(r) for r in rows]

    # ------------------------------------------------------------------
    # bootstrap
    # ------------------------------------------------------------------

    def ensure_schema(self) -> None:
        dataset_ref = bigquery.DatasetReference(self._client.project, sql._dataset())
        try:
            self._client.get_dataset(dataset_ref)
        except Exception:
            self._client.create_dataset(dataset_ref, exists_ok=True)

        for table_name, schema in codecs.TABLE_SCHEMAS.items():
            table_ref = dataset_ref.table(table_name)
            bq_schema = [SchemaField(c["name"], c["type"], mode=c.get("mode", "NULLABLE")) for c in schema]
            try:
                self._client.get_table(table_ref)
            except Exception:
                self._client.create_table(bigquery.Table(table_ref, schema=bq_schema), exists_ok=True)

    def seed_defaults(self) -> None:
        # General category if empty
        cats = self._query(sql.SQL_COUNT_CATEGORIES())
        if cats[0]["n"] == 0:
            self.create_category("General", "Default category")
        # Seed queries if empty
        qs = self._query(sql.SQL_COUNT_QUERIES())
        if qs[0]["n"] == 0:
            from .bootstrap import _SEED_QUERIES
            seed_rows = []
            for q in _SEED_QUERIES:
                cat = self._query(sql.SQL_GET_CATEGORY_BY_NAME(), [_string_param("name", q["category"])])
                cat_id = cat[0]["id"] if cat else self.create_category(q["category"])["id"]
                row = {
                    "id": self._next_id(),
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
                seed_rows.append(row)
            if seed_rows:
                self._load_rows("odoo_queries", seed_rows)
        self.seed_destinations_from_schedules()

    # ------------------------------------------------------------------
    # categories
    # ------------------------------------------------------------------

    def list_categories(self) -> list[dict]:
        cached = self._cache.get("categories")
        if cached is not None:
            return cached
        rows = self._query(sql.SQL_LIST_CATEGORIES())
        decoded = [codecs.decode_row("query_categories", r) for r in rows]
        self._cache.set("categories", decoded)
        return decoded

    def create_category(self, name: str, description: str | None = None) -> dict:
        # Uniqueness check
        dup = self._query(sql.SQL_COUNT_CATEGORIES_BY_NAME(), [_string_param("name", name)])
        if dup[0]["n"] > 0:
            raise ConflictError(f"Category name already exists: {name}")
        row = {
            "id": self._next_id(),
            "name": name,
            "description": description,
            "created_at": datetime.now(timezone.utc).replace(tzinfo=None),
        }
        params = _build_params("query_categories", row)
        self._query(sql.SQL_INSERT_CATEGORY(), params)
        self._cache.invalidate_categories()
        return row

    def delete_category(self, category_id: int) -> None:
        # General protection
        cat = self._query(sql.SQL_GET_CATEGORY_BY_ID(), [_int64_param("id", category_id)])
        if cat and cat[0]["name"] == "General":
            raise ConflictError("Cannot delete the General category")
        # Ref-count
        refs = self._query(sql.SQL_COUNT_QUERIES_BY_CATEGORY(), [_int64_param("category_id", category_id)])
        if refs[0]["n"] > 0:
            raise ConflictError("Category is referenced by queries")
        self._query(sql.SQL_DELETE_CATEGORY(), [_int64_param("id", category_id)])
        self._cache.invalidate_categories()

    # ------------------------------------------------------------------
    # queries
    # ------------------------------------------------------------------

    def list_queries(self) -> list[dict]:
        cached = self._cache.get("queries")
        if cached is not None:
            return cached
        rows = self._query(sql.SQL_LIST_QUERIES())
        decoded = [codecs.decode_row("odoo_queries", r) for r in rows]
        cats = {c["id"]: c for c in self.list_categories()}
        for r in decoded:
            r["category"] = cats.get(r.get("category_id"))
        self._cache.set("queries", decoded)
        return decoded

    def get_query(self, name: str) -> dict | None:
        rows = self._query(sql.SQL_GET_QUERY_BY_NAME(), [_string_param("name", name)])
        if not rows:
            return None
        decoded = codecs.decode_row("odoo_queries", rows[0])
        cats = {c["id"]: c for c in self.list_categories()}
        decoded["category"] = cats.get(decoded.get("category_id"))
        return decoded

    def upsert_query(self, row: dict) -> dict:
        name = row["name"]
        cat_id = row.get("category_id")
        if cat_id is not None:
            cats = self._query(sql.SQL_GET_CATEGORY_BY_ID(), [_int64_param("id", cat_id)])
            if not cats:
                raise ValidationError(f"Category id {cat_id} does not exist")
        # Ensure id and created_at are set for BQ MERGE
        if "id" not in row:
            row["id"] = self._next_id()
        if "created_at" not in row:
            row["created_at"] = datetime.now(timezone.utc).replace(tzinfo=None)
        # MERGE upsert
        params = _build_params("odoo_queries", row)
        self._query(sql.SQL_MERGE_QUERY(), params)
        self._cache.invalidate_queries()
        return self.get_query(name)

    def patch_query(self, name: str, patch: dict) -> dict:
        existing = self.get_query(name)
        if existing is None:
            raise NotFoundError(f"Query {name} not found")
        cat_id = patch.get("category_id")
        if cat_id is not None:
            cats = self._query(sql.SQL_GET_CATEGORY_BY_ID(), [_int64_param("id", cat_id)])
            if not cats:
                raise ValidationError(f"Category id {cat_id} does not exist")
        # Update specific fields
        params = [
            _string_param("description", patch.get("description", existing.get("description"))),
            _json_param("domain", patch.get("domain", existing.get("domain"))),
            _json_param("fields", patch.get("fields", existing.get("fields"))),
            _int64_param("limit_val", patch.get("limit_val", existing.get("limit_val"))),
            _int64_param("category_id", patch.get("category_id", existing.get("category_id"))),
            _bool_param("active", patch.get("active", existing.get("active"))),
            _string_param("name", name),
        ]
        self._query(sql.SQL_UPDATE_QUERY(), params)
        self._cache.invalidate_queries()
        return self.get_query(name)

    def deactivate_query(self, name: str) -> None:
        if self.get_query(name) is None:
            raise NotFoundError(f"Query {name} not found")
        self._query(sql.SQL_DEACTIVATE_QUERY(), [_string_param("name", name)])
        # Cascade: delete destinations
        self._query(sql.SQL_DELETE_DESTINATIONS_BY_QUERY(), [_string_param("query_name", name)])
        self._cache.invalidate_queries()
        self._cache.invalidate_destinations()

    def delete_query(self, name: str) -> None:
        if self.get_query(name) is None:
            raise NotFoundError(f"Query {name} not found")
        # Cascade: delete destinations first to avoid orphan rows
        self._query(sql.SQL_DELETE_DESTINATIONS_BY_QUERY(), [_string_param("query_name", name)])
        self._query(sql.SQL_DELETE_QUERY(), [_string_param("name", name)])
        self._cache.invalidate_queries()
        self._cache.invalidate_destinations()

    # ------------------------------------------------------------------
    # schedules
    # ------------------------------------------------------------------

    def list_schedules(self) -> list[dict]:
        cached = self._cache.get("schedules")
        if cached is not None:
            return cached
        rows = self._query(sql.SQL_LIST_SCHEDULES())
        decoded = [codecs.decode_row("query_schedules", r) for r in rows]
        self._cache.set("schedules", decoded)
        return decoded

    def get_schedule(self, schedule_id: int) -> dict | None:
        rows = self._query(sql.SQL_GET_SCHEDULE_BY_ID(), [_int64_param("id", schedule_id)])
        if not rows:
            return None
        return codecs.decode_row("query_schedules", rows[0])

    def create_schedule(self, row: dict) -> dict:
        validators.validate_schedule(row)
        qn = row.get("query_name")
        if qn and self.get_query(qn) is None:
            raise ValidationError(f"Query {qn} does not exist")
        if "id" not in row:
            row["id"] = self._next_id()
        if "created_at" not in row:
            row["created_at"] = datetime.now(timezone.utc).replace(tzinfo=None)
        params = _build_params("query_schedules", row)
        self._query(sql.SQL_INSERT_SCHEDULE(), params)
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
        params = _build_params("query_schedules", updated)
        self._query(sql.SQL_UPDATE_SCHEDULE(), params)
        self._cache.invalidate_schedules(schedule_id)
        return codecs.decode_row("query_schedules", updated)

    def delete_schedule(self, schedule_id: int) -> None:
        if self.get_schedule(schedule_id) is None:
            raise NotFoundError(f"Schedule {schedule_id} not found")
        # Cascade: delete runs
        self._query(sql.SQL_DELETE_RUNS_BY_SCHEDULE(), [_int64_param("schedule_id", schedule_id)])
        self._query(sql.SQL_DELETE_SCHEDULE(), [_int64_param("id", schedule_id)])
        self._cache.invalidate_schedules(schedule_id)

    # ------------------------------------------------------------------
    # runs
    # ------------------------------------------------------------------

    def list_runs(self, schedule_id: int) -> list[dict]:
        key = f"runs:{schedule_id}"
        cached = self._cache.get(key)
        if cached is not None:
            return cached
        rows = self._query(sql.SQL_LIST_RUNS(), [_int64_param("schedule_id", schedule_id)])
        decoded = [codecs.decode_row("query_schedule_runs", r) for r in rows]
        self._cache.set(key, decoded)
        return decoded

    def insert_run(self, run: dict) -> dict:
        if "id" not in run:
            run["id"] = self._next_id()
        if "started_at" not in run:
            run["started_at"] = datetime.now(timezone.utc).replace(tzinfo=None)
        params = _build_params("query_schedule_runs", run)
        self._query(sql.SQL_INSERT_RUN(), params)
        self._cache.invalidate_runs(run["schedule_id"])
        return codecs.decode_row("query_schedule_runs", run)

    def finish_run(self, run_id: int, result: dict) -> None:
        # Fetch run to obtain schedule_id
        rows = self._query(sql.SQL_GET_RUN_BY_ID(), [_int64_param("id", run_id)])
        if not rows:
            raise NotFoundError(f"Run {run_id} not found")
        run = codecs.decode_row("query_schedule_runs", rows[0])
        schedule_id = run["schedule_id"]

        # Update run
        params = [
            _timestamp_param("finished_at", result.get("finished_at", datetime.now(timezone.utc).replace(tzinfo=None))),
            _string_param("status", result["status"]),
            _string_param("message", result.get("message")),
            _int64_param("rows_loaded", result.get("rows_loaded")),
            _int64_param("id", run_id),
        ]
        self._query(sql.SQL_UPDATE_RUN(), params)

        # Update schedule last_run_*
        sched_params = [
            _timestamp_param("last_run_at", result.get("finished_at", datetime.now(timezone.utc).replace(tzinfo=None))),
            _string_param("last_run_status", result["status"]),
            _string_param("last_run_message", result.get("message")),
            _int64_param("id", schedule_id),
        ]
        self._query(sql.SQL_UPDATE_SCHEDULE_LAST_RUN(), sched_params)
        self._cache.invalidate_runs(schedule_id)
        self._cache.invalidate_schedules(schedule_id)

    # ------------------------------------------------------------------
    # destinations
    # ------------------------------------------------------------------

    def list_destinations(self, query_name: str | None = None) -> list[dict]:
        cached = self._cache.get("destinations")
        if cached is not None and query_name is None:
            return cached
        if query_name is not None:
            rows = self._query(sql.SQL_LIST_DESTINATIONS_BY_QUERY(), [_string_param("query_name", query_name)])
        else:
            rows = self._query(sql.SQL_LIST_DESTINATIONS())
        decoded = [codecs.decode_row("query_destinations", r) for r in rows]
        if query_name is None:
            self._cache.set("destinations", decoded)
        return decoded

    def upsert_destination(self, dest: dict) -> dict:
        if "id" not in dest:
            dest["id"] = self._next_id()
        if "created_at" not in dest:
            dest["created_at"] = datetime.now(timezone.utc).replace(tzinfo=None)
        params = _build_params("query_destinations", dest)
        self._query(sql.SQL_MERGE_DESTINATION(), params)
        self._cache.invalidate_destinations()
        return dest

    def mark_destination_stale(self, dest_id: int, error: str | None = None) -> None:
        existing = self._query(sql.SQL_GET_DESTINATION_BY_ID(), [_int64_param("id", dest_id)])
        if not existing:
            return
        row = codecs.decode_row("query_destinations", existing[0])
        row["stale"] = True
        row["last_error"] = error
        row["last_sync_at"] = None
        params = _build_params("query_destinations", row)
        self._query(sql.SQL_MERGE_DESTINATION(), params)
        self._cache.invalidate_destinations()

    def mark_destination_ok(self, dest_id: int, schema: dict | None = None) -> None:
        existing = self._query(sql.SQL_GET_DESTINATION_BY_ID(), [_int64_param("id", dest_id)])
        if not existing:
            return
        row = codecs.decode_row("query_destinations", existing[0])
        row["stale"] = False
        row["last_error"] = None
        row["last_sync_at"] = datetime.now(timezone.utc).replace(tzinfo=None)
        if schema is not None:
            row["last_schema"] = schema
        params = _build_params("query_destinations", row)
        self._query(sql.SQL_MERGE_DESTINATION(), params)
        self._cache.invalidate_destinations()

    def seed_destinations_from_schedules(self) -> int:
        """Seed destinations from distinct (query_name, dataset_id, table_id) in schedules.
        Guard: only seeds when the destinations registry is empty.
        """
        if self.list_destinations():
            return 0
        schedules = self.list_schedules()
        seen = set()
        count = 0
        for s in schedules:
            key = (s["query_name"], s["dataset_id"], s["table_id"])
            if key not in seen:
                seen.add(key)
                self.upsert_destination({
                    "id": self._next_id(),
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

    # ------------------------------------------------------------------
    # Load-job helper (for bulk/seeds/migration, D9)
    # ------------------------------------------------------------------

    def _load_rows(self, table_name: str, rows: list[dict]) -> None:
        """Load rows via BigQuery load job (WRITE_APPEND for bulk)."""
        import json
        from io import BytesIO

        dataset_ref = bigquery.DatasetReference(self._client.project, sql._dataset())
        table_ref = dataset_ref.table(table_name)
        schema = [SchemaField(c["name"], c["type"], mode=c.get("mode", "NULLABLE"))
                  for c in codecs.TABLE_SCHEMAS[table_name]]

        buf = BytesIO()
        for r in rows:
            encoded = codecs.encode_row(table_name, r)
            buf.write((json.dumps(encoded, ensure_ascii=False) + "\n").encode("utf-8"))
        buf.seek(0)

        job_config = bigquery.LoadJobConfig(
            source_format=bigquery.SourceFormat.NEWLINE_DELIMITED_JSON,
            schema=schema,
            write_disposition=bigquery.WriteDisposition.WRITE_APPEND,
        )
        job = self._client.load_table_from_file(buf, table_ref, job_config=job_config)
        job.result()
