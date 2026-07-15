"""Characterization test for upload_to_bigquery behavior (pre-refactor)."""
import pytest
from unittest.mock import MagicMock, patch
from routers.bigquery import upload_to_bigquery, BigQueryUploadPayload


class FakeJob:
    def __init__(self, num_rows):
        self._num_rows = num_rows

    def result(self):
        pass


class FakeTable:
    def __init__(self, num_rows):
        self.num_rows = num_rows


class FakeClient:
    def __init__(self):
        self.project = "test-project"
        self._loads = []
        self._tables = {}

    def load_table_from_json(self, rows, table_ref, job_config=None):
        self._loads.append((rows, table_ref, job_config))
        return FakeJob(len(rows))

    def get_table(self, table_ref):
        return self._tables.get(table_ref, FakeTable(len(self._loads[-1][0])))


@pytest.fixture
def fake_client():
    return FakeClient()


def test_upload_truncates_and_passes_schema(fake_client):
    """After refactor: WRITE_TRUNCATE disposition, schema inferred from union of ALL rows, passed to LoadJobConfig."""
    rows = [{"a": 1, "b": "x"}, {"a": 2, "c": "y"}]
    payload = BigQueryUploadPayload(rows=rows)

    with patch("routers.bigquery.get_bigquery_client", return_value=fake_client):
        result = upload_to_bigquery("ds1", "tbl1", payload)

    assert result.dataset_id == "ds1"
    assert result.table_id == "tbl1"
    assert len(fake_client._loads) == 1
    _rows, table_ref, job_config = fake_client._loads[0]
    assert table_ref == "test-project.ds1.tbl1"
    assert job_config.write_disposition == "WRITE_TRUNCATE"
    # Schema is now union of ALL rows (post-refactor)
    schema_fields = [f.name for f in job_config.schema]
    assert schema_fields == ["a", "b", "c"]  # union includes 'c' from row 1
