"""Unit tests for dashboard definition validation (pure functions + Odoo-boundary fetch)."""
import pytest

from dashboard_validation import (
    DefinitionError,
    fetch_and_validate,
    validate_definition,
)
import dashboard_validation


FIELDS_META = {
    "name": {"type": "char", "string": "Name"},
    "amount_total": {"type": "monetary", "string": "Total"},
    "quantity": {"type": "integer", "string": "Qty"},
    "weight": {"type": "float", "string": "Weight"},
    "user_id": {"type": "many2one", "string": "Salesperson"},
    "state": {"type": "selection", "string": "Status"},
}


def _definition(**overrides):
    defn = {
        "model": "sale.order",
        "fields": ["amount_total"],
        "group_by": ["user_id"],
        "domain": [],
        "aggregations": {"amount_total": "sum"},
    }
    defn.update(overrides)
    return defn


class TestAggregationApplicability:
    @pytest.mark.parametrize("field", ["amount_total", "quantity", "weight"])
    def test_sum_avg_allowed_on_numeric_types(self, field):
        for agg in ("sum", "avg"):
            defn = _definition(fields=[field], aggregations={field: agg})
            validate_definition(defn, FIELDS_META)  # must not raise

    def test_count_allowed_on_any_type(self):
        for field in FIELDS_META:
            defn = _definition(fields=[field], aggregations={field: "count"})
            validate_definition(defn, FIELDS_META)  # must not raise

    @pytest.mark.parametrize("field", ["name", "user_id", "state"])
    def test_sum_avg_rejected_on_non_numeric_types(self, field):
        for agg in ("sum", "avg"):
            defn = _definition(fields=[field], aggregations={field: agg})
            with pytest.raises(DefinitionError) as exc:
                validate_definition(defn, FIELDS_META)
            assert exc.value.field == field
            assert exc.value.model == "sale.order"

    def test_unknown_aggregation_function_rejected(self):
        defn = _definition(aggregations={"amount_total": "median"})
        with pytest.raises(DefinitionError) as exc:
            validate_definition(defn, FIELDS_META)
        assert "median" in str(exc.value)

    def test_missing_aggregation_entry_rejected(self):
        defn = _definition(
            fields=["amount_total", "quantity"],
            aggregations={"amount_total": "sum"},
        )
        with pytest.raises(DefinitionError) as exc:
            validate_definition(defn, FIELDS_META)
        assert exc.value.field == "quantity"

    def test_empty_fields_rejected(self):
        with pytest.raises(DefinitionError):
            validate_definition(_definition(fields=[], aggregations={}), FIELDS_META)


class TestFieldExistence:
    def test_unknown_field_in_fields_rejected(self):
        defn = _definition(fields=["x_ghost"], aggregations={"x_ghost": "count"})
        with pytest.raises(DefinitionError) as exc:
            validate_definition(defn, FIELDS_META)
        assert exc.value.field == "x_ghost"

    def test_unknown_field_in_group_by_rejected(self):
        defn = _definition(group_by=["x_ghost"])
        with pytest.raises(DefinitionError) as exc:
            validate_definition(defn, FIELDS_META)
        assert exc.value.field == "x_ghost"


class TestDomainStructure:
    def test_empty_domain_ok(self):
        validate_definition(_definition(domain=[]), FIELDS_META)

    def test_valid_triplets_and_connectors_ok(self):
        domain = [
            "&",
            ["state", "=", "sale"],
            "|",
            ["amount_total", ">=", 1000],
            ["name", "ilike", "acme"],
        ]
        validate_definition(_definition(domain=domain), FIELDS_META)

    def test_unknown_field_in_domain_rejected(self):
        defn = _definition(domain=[["x_ghost", "=", 1]])
        with pytest.raises(DefinitionError) as exc:
            validate_definition(defn, FIELDS_META)
        assert exc.value.field == "x_ghost"

    @pytest.mark.parametrize("op", ["=!", "like lower", "@@", "><"])
    def test_operator_outside_allowlist_rejected(self, op):
        defn = _definition(domain=[["state", op, "sale"]])
        with pytest.raises(DefinitionError) as exc:
            validate_definition(defn, FIELDS_META)
        assert op in str(exc.value)

    @pytest.mark.parametrize("bad", [["state", "="], ["state"], "state", 42, ["state", "=", "sale", "extra"]])
    def test_malformed_triplet_rejected(self, bad):
        defn = _definition(domain=[bad])
        with pytest.raises(DefinitionError):
            validate_definition(defn, FIELDS_META)

    @pytest.mark.parametrize("op", ["=", "!=", ">", ">=", "<", "<=", "in", "not in", "like", "ilike", "child_of", "parent_of"])
    def test_full_operator_allowlist_accepted(self, op):
        value = [1, 2] if op in ("in", "not in", "child_of", "parent_of") else "x"
        validate_definition(_definition(domain=[["name", op, value]]), FIELDS_META)


class TestFetchAndValidate:
    def test_unknown_model_rejected(self, monkeypatch):
        def fake_execute(model, method, args, kwargs=None):
            if model == "ir.model":
                return []  # model not found
            raise AssertionError(f"unexpected call {model}.{method}")

        monkeypatch.setattr(dashboard_validation, "odoo_execute", fake_execute)
        with pytest.raises(DefinitionError) as exc:
            fetch_and_validate(_definition(model="ghost.model"))
        assert exc.value.model == "ghost.model"
        assert exc.value.field is None

    def test_known_model_fetches_fields_and_validates(self, monkeypatch):
        calls = []

        def fake_execute(model, method, args, kwargs=None):
            calls.append((model, method))
            if model == "ir.model":
                return [{"model": "sale.order"}]
            if method == "fields_get":
                return FIELDS_META
            raise AssertionError(f"unexpected call {model}.{method}")

        monkeypatch.setattr(dashboard_validation, "odoo_execute", fake_execute)
        meta = fetch_and_validate(_definition())
        assert meta == FIELDS_META
        assert ("ir.model", "search_read") in calls
        assert ("sale.order", "fields_get") in calls

    def test_stale_field_rejected_with_context(self, monkeypatch):
        def fake_execute(model, method, args, kwargs=None):
            if model == "ir.model":
                return [{"model": "sale.order"}]
            if method == "fields_get":
                return {k: v for k, v in FIELDS_META.items() if k != "amount_total"}
            raise AssertionError(f"unexpected call {model}.{method}")

        monkeypatch.setattr(dashboard_validation, "odoo_execute", fake_execute)
        with pytest.raises(DefinitionError) as exc:
            fetch_and_validate(_definition())
        assert exc.value.field == "amount_total"
        assert exc.value.model == "sale.order"
