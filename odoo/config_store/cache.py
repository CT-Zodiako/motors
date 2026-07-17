"""Cache: hybrid TTL + write-through invalidation inside the BQ store (D10).

- TTL 30 s default, env CONFIG_CACHE_TTL_SECONDS, 0=off (kill-switch).
  NOTE: CONFIG_CACHE_TTL_SECONDS is resolved at import time; changing the env
  after the module is loaded has no effect on the default Cache().
- Cached: list_categories, list_queries (incl. app-side category resolution),
  list_schedules, list_destinations, list_runs(schedule_id) per schedule.
- Point lookups derive from cached lists.
- Invalidation matrix per write type (write-through after successful mutation).
"""
from __future__ import annotations

import os
import time
from typing import Any

_DEFAULT_TTL = int(os.getenv("CONFIG_CACHE_TTL_SECONDS", "30"))


class Cache:
    """Simple in-process TTL cache with explicit invalidation."""

    def __init__(self, ttl_seconds: int | None = None) -> None:
        self._ttl = _DEFAULT_TTL if ttl_seconds is None else ttl_seconds
        self._store: dict[str, tuple[Any, float]] = {}

    # ------------------------------------------------------------------
    # Core ops
    # ------------------------------------------------------------------

    def get(self, key: str) -> Any | None:
        if self._ttl == 0:
            return None
        entry = self._store.get(key)
        if entry is None:
            return None
        value, ts = entry
        if time.monotonic() - ts > self._ttl:
            del self._store[key]
            return None
        return value

    def set(self, key: str, value: Any) -> None:
        if self._ttl == 0:
            return
        self._store[key] = (value, time.monotonic())

    def delete(self, key: str) -> None:
        self._store.pop(key, None)

    def clear(self) -> None:
        self._store.clear()

    # ------------------------------------------------------------------
    # Invalidation helpers (write-through matrix from D10)
    # ------------------------------------------------------------------

    def invalidate_categories(self) -> None:
        self.delete("categories")
        self.delete("queries")  # list embeds category name

    def invalidate_queries(self) -> None:
        self.delete("queries")
        self.delete("destinations")

    def invalidate_schedules(self, schedule_id: int | None = None) -> None:
        self.delete("schedules")
        if schedule_id is not None:
            self.delete(f"runs:{schedule_id}")

    def invalidate_runs(self, schedule_id: int) -> None:
        self.delete(f"runs:{schedule_id}")
        self.delete("schedules")  # last_run_* fields

    def invalidate_destinations(self) -> None:
        self.delete("destinations")

    def invalidate_permissions(self) -> None:
        self.delete("permissions")
        # Best-effort: clear all user permission caches. Avoids stale data when
        # the permission catalog is reseeded.
        for key in list(self._store.keys()):
            if key.startswith("user_permissions:"):
                self.delete(key)
