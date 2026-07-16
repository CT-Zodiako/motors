"""Config store package — re-exports + module-level store holder."""
from .errors import ConfigStoreError, ConflictError, NotFoundError, ValidationError
from .protocol import ConfigStore
from .memory_store import InMemoryConfigStore
from .bootstrap import ensure_schema, seed_defaults
from .codecs import TABLE_SCHEMAS, encode_row, decode_row
from .validators import validate_schedule
from .cache import Cache

__all__ = [
    "ConfigStoreError",
    "ConflictError",
    "NotFoundError",
    "ValidationError",
    "ConfigStore",
    "InMemoryConfigStore",
    "ensure_schema",
    "seed_defaults",
    "TABLE_SCHEMAS",
    "encode_row",
    "decode_row",
    "validate_schedule",
    "Cache",
    "set_store",
    "get_store",
]

# Module-level holder for the active ConfigStore instance.
# Injected at startup (main.py) and overridden per-test via set_store(...).
_store: ConfigStore | None = None


def set_store(store: ConfigStore) -> None:
    """Set the active ConfigStore instance (used by routers and tests)."""
    global _store
    _store = store


def get_store() -> ConfigStore:
    """Return the active ConfigStore instance."""
    if _store is None:
        raise RuntimeError("No ConfigStore has been set. Call set_store(...) first.")
    return _store
