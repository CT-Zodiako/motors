"""Config store errors."""


class ConfigStoreError(Exception):
    """Base error for config store operations."""


class ConflictError(ConfigStoreError):
    """Uniqueness or referential conflict (maps to HTTP 409)."""


class NotFoundError(ConfigStoreError):
    """Resource not found (maps to HTTP 404)."""


class ValidationError(ConfigStoreError):
    """Domain validation failure (maps to HTTP 400/422)."""
