"""API tests for POST /bigquery/upload-file/load (PR3).

Fully offline: FakeBigQueryClient monkeypatched into routers.file_upload.
Covers decision-validation order (zero BQ calls on failure), the 404/409
gates with zero writes, conversion-before-mutation, WRITE_EMPTY load, and
job-failure cleanup (502).
"""
import io
import json

import pytest
from google.api_core.exceptions import Conflict, NotFound

from test_file_upload_inspect_preview import _csv_bytes, _xlsx_bytes


# ── fakes ────────────────────────────────────────────────────────────

class FakeLoadJob:
    def __init__(self, output_rows, fail_with=None):
        self.output_rows = output_rows
        self.errors = None
        self._fail_with = fail_with

    def result(self):
        if self._fail_with:
            raise self._fail_with


class FakeBigQueryClient:
    def __init__(self, project="test-project"):
        self.project = project
        self.datasets = set()
        self.tables = {}  # ref -> {"schema": [...], "rows": [...]}
        self.created_tables = []
        self.load_jobs = []
        self.deleted_tables = []
        self.calls = []
        self.factory_calls = []
        self.fail_load_with = None
        self.fail_delete_with = None
        self.conflict_on_create = False

    def add_dataset(self, dataset_id):
        """Register a dataset by bare id; the client queries fully-qualified refs."""
        self.datasets.add(f"{self.project}.{dataset_id}")

    def get_dataset(self, ref):
        self.calls.append(("get_dataset", ref))
        if ref not in self.datasets:
            raise NotFound(f"Dataset {ref} not found")
        return ref

    def get_table(self, ref):
        self.calls.append(("get_table", ref))
        if ref not in self.tables:
            raise NotFound(f"Table {ref} not found")
        return self.tables[ref]

    def create_table(self, table):
        self.calls.append(("create_table", table))
        ref = f"{table.reference.project}.{table.reference.dataset_id}.{table.reference.table_id}"
        if self.conflict_on_create or ref in self.tables:
            raise Conflict(f"Table {ref} already exists")
        self.created_tables.append(table)
        self.tables[ref] = {"schema": table.schema, "rows": []}
        return table

    def load_table_from_json(self, rows, ref, job_config=None):
        self.calls.append(("load_table_from_json", ref))
        self.load_jobs.append({"rows": rows, "ref": ref, "job_config": job_config})
        if self.fail_load_with:
            return FakeLoadJob(0, self.fail_load_with)
        self.tables[ref]["rows"].extend(rows)
        return FakeLoadJob(len(rows))

    def delete_table(self, ref, not_found_ok=False):
        self.calls.append(("delete_table", ref))
        self.deleted_tables.append(ref)
        if self.fail_delete_with:
            raise self.fail_delete_with
        self.tables.pop(ref, None)


@pytest.fixture
def fake_bq(monkeypatch):
    fake = FakeBigQueryClient()

    def factory():
        fake.factory_calls.append(True)
        return fake

    monkeypatch.setattr("routers.file_upload.get_bigquery_client", factory, raising=False)
    return fake


# ── helpers ───────────────────────────────────────────────────────────

def _post_load(client, content, filename, source_type, decisions, dataset, table, sheet=None, skip_rows=None):
    data = {
        "sourceType": source_type,
        "decisions": decisions if isinstance(decisions, str) else json.dumps(decisions),
        "dataset": dataset,
        "table": table,
    }
    if sheet is not None:
        data["sheet"] = sheet
    if skip_rows is not None:
        data["skipRows"] = str(skip_rows)
    return client.post(
        "/bigquery/upload-file/load",
        files={"file": (filename, content, "application/octet-stream")},
        data=data,
    )


def _decisions(cols):
    """cols: list of (source, name, type, included)."""
    return [
        {"source": s, "name": n, "type": t, "included": i}
        for s, n, t, i in cols
    ]


_SIMPLE_CSV = _csv_bytes("precio,cant\n10,1\n20,2\n")
_SIMPLE_DECISIONS = _decisions([
    ("precio", "precio", "INT64", True),
    ("cant", "cant", "INT64", True),
])


def _assert_zero_bq(fake):
    assert fake.factory_calls == []
    assert fake.calls == []


# ── decision validation: all failures with ZERO BigQuery calls ───────

class TestDecisionValidation:
    def test_unparseable_decisions_400(self, client, fake_bq):
        r = _post_load(client, _SIMPLE_CSV, "d.csv", "csv", "not-json{{{", "ds", "t")
        assert r.status_code == 400
        _assert_zero_bq(fake_bq)

    def test_decisions_length_mismatch_400(self, client, fake_bq):
        r = _post_load(client, _SIMPLE_CSV, "d.csv", "csv",
                       _decisions([("precio", "precio", "INT64", True)]), "ds", "t")
        assert r.status_code == 400
        assert "out of sync" in r.json()["detail"]
        _assert_zero_bq(fake_bq)

    def test_decisions_source_mismatch_400(self, client, fake_bq):
        r = _post_load(client, _SIMPLE_CSV, "d.csv", "csv",
                       _decisions([("precio", "precio", "INT64", True),
                                   ("OTRO", "cant", "INT64", True)]), "ds", "t")
        assert r.status_code == 400
        assert "out of sync" in r.json()["detail"]
        _assert_zero_bq(fake_bq)

    def test_type_outside_closed_set_400(self, client, fake_bq):
        r = _post_load(client, _SIMPLE_CSV, "d.csv", "csv",
                       _decisions([("precio", "precio", "NUMERIC", True),
                                   ("cant", "cant", "INT64", True)]), "ds", "t")
        assert r.status_code == 400
        assert "NUMERIC" in r.json()["detail"]
        _assert_zero_bq(fake_bq)

    def test_zero_included_400(self, client, fake_bq):
        r = _post_load(client, _SIMPLE_CSV, "d.csv", "csv",
                       _decisions([("precio", "precio", "INT64", False),
                                   ("cant", "cant", "INT64", False)]), "ds", "t")
        assert r.status_code == 400
        assert "at least one" in r.json()["detail"].lower()
        _assert_zero_bq(fake_bq)

    def test_invalid_included_name_400(self, client, fake_bq):
        r = _post_load(client, _SIMPLE_CSV, "d.csv", "csv",
                       _decisions([("precio", "con espacio", "INT64", True),
                                   ("cant", "cant", "INT64", True)]), "ds", "t")
        assert r.status_code == 400
        _assert_zero_bq(fake_bq)

    def test_case_insensitive_duplicate_names_400(self, client, fake_bq):
        r = _post_load(client, _SIMPLE_CSV, "d.csv", "csv",
                       _decisions([("precio", "fecha", "INT64", True),
                                   ("cant", "FECHA", "INT64", True)]), "ds", "t")
        assert r.status_code == 400
        assert "uplicate" in r.json()["detail"]
        _assert_zero_bq(fake_bq)

    def test_invalid_dataset_identifier_400(self, client, fake_bq):
        r = _post_load(client, _SIMPLE_CSV, "d.csv", "csv", _SIMPLE_DECISIONS, "bad-name", "t")
        assert r.status_code == 400
        _assert_zero_bq(fake_bq)

    def test_invalid_table_identifier_400(self, client, fake_bq):
        r = _post_load(client, _SIMPLE_CSV, "d.csv", "csv", _SIMPLE_DECISIONS, "ds", "9table")
        assert r.status_code == 400
        _assert_zero_bq(fake_bq)

    def test_header_only_file_400(self, client, fake_bq):
        r = _post_load(client, _csv_bytes("a,b\n"), "d.csv", "csv",
                       _decisions([("a", "a", "INT64", True), ("b", "b", "INT64", True)]),
                       "ds", "t")
        assert r.status_code == 400
        assert "no data" in r.json()["detail"].lower()
        _assert_zero_bq(fake_bq)


# ── BigQuery flow ─────────────────────────────────────────────────────

class TestBigQueryFlow:
    def test_dataset_not_found_404(self, client, fake_bq):
        r = _post_load(client, _SIMPLE_CSV, "d.csv", "csv", _SIMPLE_DECISIONS, "ds", "t")
        assert r.status_code == 404
        assert "ds" in r.json()["detail"]

    def test_table_exists_409_zero_writes(self, client, fake_bq):
        fake_bq.add_dataset("ds")
        fake_bq.tables["test-project.ds.t"] = {"schema": [], "rows": [{"x": 1}]}
        r = _post_load(client, _SIMPLE_CSV, "d.csv", "csv", _SIMPLE_DECISIONS, "ds", "t")
        assert r.status_code == 409
        assert "test-project.ds.t" in r.json()["detail"]
        assert fake_bq.created_tables == []
        assert fake_bq.load_jobs == []
        assert fake_bq.tables["test-project.ds.t"]["rows"] == [{"x": 1}]

    def test_create_table_conflict_409(self, client, fake_bq):
        fake_bq.add_dataset("ds")
        fake_bq.conflict_on_create = True
        r = _post_load(client, _SIMPLE_CSV, "d.csv", "csv", _SIMPLE_DECISIONS, "ds", "t")
        assert r.status_code == 409
        assert fake_bq.load_jobs == []

    def test_success_creates_and_loads_all_rows(self, client, fake_bq):
        fake_bq.add_dataset("ds")
        r = _post_load(client, _SIMPLE_CSV, "d.csv", "csv", _SIMPLE_DECISIONS, "ds", "nueva")
        assert r.status_code == 200
        body = r.json()
        assert body == {"table": "test-project.ds.nueva", "rows": 2}

        created = fake_bq.created_tables[0]
        assert [(f.name, f.field_type, f.mode) for f in created.schema] == [
            ("precio", "INT64", "NULLABLE"),
            ("cant", "INT64", "NULLABLE"),
        ]
        job = fake_bq.load_jobs[0]
        assert job["job_config"].write_disposition == "WRITE_EMPTY"
        assert job["rows"] == [{"precio": 10, "cant": 1}, {"precio": 20, "cant": 2}]

    def test_loads_all_rows_not_just_sample(self, client, fake_bq):
        fake_bq.add_dataset("ds")
        content = _csv_bytes("n\n" + "".join(f"{i}\n" for i in range(150)))
        r = _post_load(client, content, "d.csv", "csv",
                       _decisions([("n", "n", "INT64", True)]), "ds", "t")
        assert r.status_code == 200
        assert r.json()["rows"] == 150
        assert len(fake_bq.load_jobs[0]["rows"]) == 150

    def test_column_subset_and_rename_in_order(self, client, fake_bq):
        fake_bq.add_dataset("ds")
        content = _csv_bytes("a,b,c\n1,2,3\n")
        r = _post_load(client, content, "d.csv", "csv",
                       _decisions([("a", "alpha", "INT64", True),
                                   ("b", "b", "INT64", False),
                                   ("c", "gamma", "INT64", True)]), "ds", "t")
        assert r.status_code == 200
        created = fake_bq.created_tables[0]
        assert [f.name for f in created.schema] == ["alpha", "gamma"]
        assert fake_bq.load_jobs[0]["rows"] == [{"alpha": 1, "gamma": 3}]

    def test_type_override_honored_exactly(self, client, fake_bq):
        fake_bq.add_dataset("ds")
        r = _post_load(client, _SIMPLE_CSV, "d.csv", "csv",
                       _decisions([("precio", "precio", "STRING", True),
                                   ("cant", "cant", "INT64", True)]), "ds", "t")
        assert r.status_code == 200
        created = fake_bq.created_tables[0]
        assert created.schema[0].field_type == "STRING"
        assert fake_bq.load_jobs[0]["rows"][0]["precio"] == "10"

    def test_conversion_error_exact_detail_and_zero_bq(self, client, fake_bq):
        rows = "".join(f"{i}\n" for i in range(1, 17)) + "abc\n"
        content = _csv_bytes("precio\n" + rows)
        r = _post_load(client, content, "d.csv", "csv",
                       _decisions([("precio", "precio", "INT64", True)]), "ds", "t")
        assert r.status_code == 400
        assert r.json()["detail"] == "Column 'precio' row 17: string 'abc' is not an integer"
        _assert_zero_bq(fake_bq)

    def test_job_failure_502_with_cleanup(self, client, fake_bq):
        fake_bq.add_dataset("ds")
        fake_bq.fail_load_with = Exception("boom")
        r = _post_load(client, _SIMPLE_CSV, "d.csv", "csv", _SIMPLE_DECISIONS, "ds", "t")
        assert r.status_code == 502
        detail = r.json()["detail"]
        assert "boom" in detail
        assert "partial table dropped" in detail
        assert fake_bq.deleted_tables == ["test-project.ds.t"]

    def test_job_failure_cleanup_failure_still_502(self, client, fake_bq):
        fake_bq.add_dataset("ds")
        fake_bq.fail_load_with = Exception("boom")
        fake_bq.fail_delete_with = Exception("cannot delete")
        r = _post_load(client, _SIMPLE_CSV, "d.csv", "csv", _SIMPLE_DECISIONS, "ds", "t")
        assert r.status_code == 502
        detail = r.json()["detail"]
        assert "boom" in detail
        assert "manually" in detail


# ── triangulation ─────────────────────────────────────────────────────

class TestLoadTriangulation:
    def test_xlsx_loads_chosen_sheet(self, client, fake_bq):
        fake_bq.add_dataset("ds")
        content = _xlsx_bytes({
            "Primera": [["skip"], ["no va"]],
            "Segunda": [["precio"], [10], [20]],
        })
        r = _post_load(client, content, "d.xlsx", "xlsx",
                       _decisions([("precio", "precio", "INT64", True)]),
                       "ds", "t", sheet="Segunda")
        assert r.status_code == 200
        assert fake_bq.load_jobs[0]["rows"] == [{"precio": 10}, {"precio": 20}]

    def test_defaults_applied_when_name_and_type_omitted(self, client, fake_bq):
        fake_bq.add_dataset("ds")
        content = _csv_bytes("Fecha de Venta,unidades\n2024-01-15,3\n")
        decisions = [
            {"source": "Fecha de Venta", "name": None, "type": None, "included": True},
            {"source": "unidades", "name": None, "type": None, "included": True},
        ]
        r = _post_load(client, content, "d.csv", "csv", decisions, "ds", "t")
        assert r.status_code == 200
        created = fake_bq.created_tables[0]
        assert [(f.name, f.field_type) for f in created.schema] == [
            ("Fecha_de_Venta", "DATE"),
            ("unidades", "INT64"),
        ]
        assert fake_bq.load_jobs[0]["rows"] == [{"Fecha_de_Venta": "2024-01-15", "unidades": 3}]

    def test_int64_accepts_integer_valued_float(self, client, fake_bq):
        fake_bq.add_dataset("ds")
        content = _xlsx_bytes({"H": [["valor"], [3.0]]})
        r = _post_load(client, content, "d.xlsx", "xlsx",
                       _decisions([("valor", "valor", "INT64", True)]), "ds", "t")
        assert r.status_code == 200
        assert fake_bq.load_jobs[0]["rows"] == [{"valor": 3}]

    def test_int64_rejects_decimal_float_with_column_and_row(self, client, fake_bq):
        content = _xlsx_bytes({"H": [["valor"], [3.5]]})
        r = _post_load(client, content, "d.xlsx", "xlsx",
                       _decisions([("valor", "valor", "INT64", True)]), "ds", "t")
        assert r.status_code == 400
        detail = r.json()["detail"]
        assert "Column 'valor' row 1" in detail
        _assert_zero_bq(fake_bq)

    def test_timestamp_z_suffix_and_naive(self, client, fake_bq):
        fake_bq.add_dataset("ds")
        content = _csv_bytes("ts\n2024-01-15T10:30:00Z\n2024-01-16T08:00:00\n")
        r = _post_load(client, content, "d.csv", "csv",
                       _decisions([("ts", "ts", "TIMESTAMP", True)]), "ds", "t")
        assert r.status_code == 200
        rows = fake_bq.load_jobs[0]["rows"]
        assert rows[0]["ts"].startswith("2024-01-15T10:30:00")
        assert rows[1]["ts"].startswith("2024-01-16T08:00:00")


def test_load_with_skip_rows_uses_shifted_headers(client, fake_bq):
    fake_bq.add_dataset("ds")
    content = b"title junk\n,params\nname,price\nana,10\nluis,20\n"
    decisions = _decisions([("name", "name", "STRING", True), ("price", "price", "INT64", True)])
    resp = _post_load(client, content, "d.csv", "csv", decisions, "ds", "t1", skip_rows=2)
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["rows"] == 2
    fields = fake_bq.created_tables[0].schema
    assert [f.name for f in fields] == ["name", "price"]
    assert fake_bq.tables["test-project.ds.t1"]["rows"] == [{"name": "ana", "price": 10}, {"name": "luis", "price": 20}]


def test_load_skip_rows_negative_400(client, fake_bq):
    decisions = _decisions([("a", "a", "STRING", True)])
    resp = _post_load(client, b"a\n1\n", "d.csv", "csv", decisions, "ds", "t1", skip_rows=-1)
    assert resp.status_code == 400
    assert fake_bq.created_tables == []
