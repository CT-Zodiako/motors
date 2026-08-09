"""Server-side validation and execution of native dashboard definitions.

Validation is pure (`validate_definition`) for TDD; `fetch_and_validate`
crosses the Odoo boundary (ir.model + fields_get) before validating.
`_execute_definition` is the single query-construction path shared by the
stored-data endpoint and the admin preview endpoint so they can never diverge.

No string from a definition is ever concatenated into SQL or used as an Odoo
method name: the only boundary crossings are ir.model.search_read, fields_get,
and read_group with structured args.
"""
from __future__ import annotations

from odoo_client import execute as odoo_execute

NUMERIC_TYPES = {"integer", "float", "monetary"}
AGGREGATIONS = {"sum", "avg", "count"}
DOMAIN_OPERATORS = {
    "=", "!=", ">", ">=", "<", "<=",
    "in", "not in", "like", "ilike", "child_of", "parent_of",
}
DOMAIN_CONNECTORS = {"&", "|", "!"}


class DefinitionError(ValueError):
    """Invalid dashboard definition, carrying model/field context for 422 details."""

    def __init__(self, message: str, model: str | None = None, field: str | None = None):
        super().__init__(message)
        self.message = message
        self.model = model
        self.field = field


def _validate_domain(domain: list, fields_meta: dict, model: str | None) -> None:
    for item in domain:
        if isinstance(item, str):
            if item in DOMAIN_CONNECTORS:
                continue
            raise DefinitionError(
                f"Invalid domain token '{item}': only {sorted(DOMAIN_CONNECTORS)} connectors are allowed",
                model=model,
            )
        if not isinstance(item, (list, tuple)) or len(item) != 3:
            raise DefinitionError(
                f"Invalid domain clause {item!r}: expected a [field, operator, value] triplet",
                model=model,
            )
        field, operator, _value = item
        if not isinstance(field, str) or field not in fields_meta:
            raise DefinitionError(
                f"Field '{field}' in domain does not exist on model '{model}'",
                model=model,
                field=field if isinstance(field, str) else None,
            )
        if operator not in DOMAIN_OPERATORS:
            raise DefinitionError(
                f"Operator '{operator}' is not allowed in dashboard domains",
                model=model,
                field=field,
            )


def validate_definition(defn: dict, fields_meta: dict[str, dict]) -> None:
    """Pure: validate a definition against fields_get metadata.

    Raises DefinitionError. Model existence is the caller's concern
    (checked via ir.model before fields_get).
    """
    model = defn.get("model")
    fields = defn.get("fields") or []
    group_by = defn.get("group_by") or []
    domain = defn.get("domain") or []
    aggregations = defn.get("aggregations") or {}

    if not fields:
        raise DefinitionError(
            f"Dashboard definition on model '{model}' requires at least one field",
            model=model,
        )

    for name in fields + group_by:
        if name not in fields_meta:
            raise DefinitionError(
                f"Field '{name}' does not exist on model '{model}'",
                model=model,
                field=name,
            )

    for field in fields:
        if field not in aggregations:
            raise DefinitionError(
                f"Missing aggregation function for field '{field}'",
                model=model,
                field=field,
            )

    for field, agg in aggregations.items():
        if agg not in AGGREGATIONS:
            raise DefinitionError(
                f"Unknown aggregation function '{agg}' for field '{field}'",
                model=model,
                field=field,
            )
        if field not in fields_meta:
            raise DefinitionError(
                f"Aggregated field '{field}' does not exist on model '{model}'",
                model=model,
                field=field,
            )
        field_type = fields_meta[field].get("type")
        if agg in ("sum", "avg") and field_type not in NUMERIC_TYPES:
            raise DefinitionError(
                f"Aggregation '{agg}' is not applicable to field '{field}' of type '{field_type}'",
                model=model,
                field=field,
            )

    _validate_domain(domain, fields_meta, model)


def fetch_and_validate(defn: dict) -> dict[str, dict]:
    """Cross the Odoo boundary: model existence (ir.model), fields_get, then validate.

    Returns the fields_get metadata (used for column labels downstream).
    Raises DefinitionError with model/field context.
    """
    model = defn.get("model")
    found = odoo_execute(
        "ir.model",
        "search_read",
        [[["model", "=", model]]],
        {"fields": ["model"], "limit": 1},
    )
    if not found:
        raise DefinitionError(
            f"Model '{model}' does not exist in Odoo",
            model=model,
        )
    fields_meta = odoo_execute(
        model,
        "fields_get",
        [],
        {"attributes": ["string", "type"]},
    )
    validate_definition(defn, fields_meta)
    return fields_meta


def _execute_definition(defn: dict, fields_meta: dict[str, dict]) -> dict:
    """Build and run the read_group call from a validated definition and normalize rows.

    Shared by the stored-data endpoint and the admin preview endpoint.
    Strips `__domain` from Odoo rows, keeps `__count`. Column labels come from
    the fields_get metadata (falling back to the field name).
    """
    aggregations = defn.get("aggregations") or {}
    rows = odoo_execute(
        defn["model"],
        "read_group",
        [defn.get("domain") or []],
        {
            "fields": [f"{field}:{agg}" for field, agg in aggregations.items()],
            "groupby": defn.get("group_by") or [],
            "lazy": False,
        },
    )
    columns = []
    for field in defn.get("group_by") or []:
        columns.append({
            "key": field,
            "label": fields_meta.get(field, {}).get("string", field),
            "kind": "group",
        })
    for field, agg in aggregations.items():
        label = fields_meta.get(field, {}).get("string", field)
        columns.append({
            "key": field,
            "label": f"{label} ({agg})",
            "kind": "aggregate",
            "function": agg,
        })
    normalized = [
        {key: value for key, value in row.items() if key != "__domain"}
        for row in rows
    ]
    return {"model": defn["model"], "columns": columns, "rows": normalized}
