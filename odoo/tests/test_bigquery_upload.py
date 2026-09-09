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


def test_load_query_chunks_over_100k_truncate_then_append_and_preserves_schema(fake_client, monkeypatch):
    from routers import bigquery

    total_rows = 100_001
    def fetch_chunk(_query, offset, limit):
        if offset >= total_rows:
            return []
        count = min(limit, total_rows - offset)
        return [{"id": offset + i, "name": "row"} for i in range(count)]

    monkeypatch.setattr(bigquery, "get_bigquery_client", lambda: fake_client)
    from routers import runner
    monkeypatch.setattr(runner, "fetch_query_rows", fetch_chunk)

    loaded = bigquery.load_query_to_bigquery({"model": "x", "method": "search_read"}, "ds", "tbl", chunk_size=5000)

    assert loaded == total_rows
    assert len(fake_client._loads) == 21
    assert fake_client._loads[0][2].write_disposition == "WRITE_TRUNCATE"
    assert all(c[2].write_disposition == "WRITE_APPEND" for c in fake_client._loads[1:])
    assert all([f.name for f in c[2].schema] == ["id", "name"] for c in fake_client._loads)


def test_load_query_rejects_incompatible_types_in_later_chunk(fake_client, monkeypatch):
    from routers import bigquery

    chunks = iter([[{"id": 1}], [{"id": "not-an-integer"}]])
    monkeypatch.setattr(bigquery, "get_bigquery_client", lambda: fake_client)
    from routers import runner
    monkeypatch.setattr(runner, "fetch_query_rows", lambda *args, **kwargs: next(chunks))

    with pytest.raises(ValueError, match="schema changed.*id.*INTEGER.*STRING"):
        bigquery.load_query_to_bigquery({"model": "x", "method": "search_read"}, "ds", "tbl", chunk_size=1)
    assert len(fake_client._loads) == 1


def test_load_query_rejects_new_columns_in_later_chunk(fake_client, monkeypatch):
    from routers import bigquery

    chunks = iter([[{"id": 1}], [{"id": 2, "new_column": "not dropped"}]])
    monkeypatch.setattr(bigquery, "get_bigquery_client", lambda: fake_client)
    from routers import runner
    monkeypatch.setattr(runner, "fetch_query_rows", lambda *args, **kwargs: next(chunks))

    with pytest.raises(ValueError, match="schema changed.*new_column"):
        bigquery.load_query_to_bigquery({"model": "x", "method": "search_read"}, "ds", "tbl", chunk_size=1)
    assert len(fake_client._loads) == 1


def test_load_query_serializes_later_heterogeneous_values_for_string_schema(fake_client, monkeypatch):
    from routers import bigquery

    chunks = iter([
        [{"analytic_distribution": "initial"}],
        [{"analytic_distribution": True}],
    ])
    monkeypatch.setattr(bigquery, "get_bigquery_client", lambda: fake_client)
    from routers import runner
    monkeypatch.setattr(runner, "fetch_query_rows", lambda *args, **kwargs: next(chunks))

    loaded = bigquery.load_query_to_bigquery(
        {"model": "x", "method": "search_read"}, "ds", "tbl", chunk_size=1
    )

    assert loaded == 2
    assert fake_client._loads[1][0] == [{"analytic_distribution": "True"}]
    assert fake_client._loads[1][2].schema[0].field_type == "STRING"
