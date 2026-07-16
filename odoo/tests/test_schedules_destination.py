"""Tests for schedule destination binding (PR-1)."""
import uuid


def _uid():
    return uuid.uuid4().hex[:8]


def _mk_query(client, name: str):
    return client.post("/queries/", json={"name": name, "model": "res.partner"})


def test_schedule_create_creates_destination(client):
    name = f"t_q_{_uid()}"
    _mk_query(client, name)
    res = client.post("/schedules/", json={
        "name": "s1",
        "query_name": name,
        "dataset_id": "ds1",
        "table_id": "tbl1",
        "frequency": "daily",
        "hour": 0,
        "minute": 0,
        "active": True,
    })
    assert res.status_code == 200
    dest = client.get(f"/queries/{name}/destination").json()
    assert dest["dataset_id"] == "ds1"
    assert dest["table_id"] == "tbl1"
    assert dest["origin"] == "schedule"
    assert dest["stale"] is False


def test_schedule_update_marks_old_destination_stale(client):
    from config_store import get_store

    name = f"t_q_{_uid()}"
    _mk_query(client, name)
    client.post("/schedules/", json={
        "name": "s1", "query_name": name, "dataset_id": "ds1", "table_id": "tbl1",
        "frequency": "daily", "hour": 0, "minute": 0, "active": True,
    })
    schedule = client.get("/schedules/").json()[0]
    res = client.patch(f"/schedules/{schedule['id']}", json={"dataset_id": "ds2", "table_id": "tbl2"})
    assert res.status_code == 200

    dest = client.get(f"/queries/{name}/destination").json()
    assert dest["dataset_id"] == "ds2"
    assert dest["table_id"] == "tbl2"

    rows = [d for d in get_store().list_destinations(name) if d["dataset_id"] == "ds1" and d["table_id"] == "tbl1"]
    assert len(rows) == 1
    assert rows[0]["stale"] is True


def test_query_destination_404_when_no_destination(client):
    name = f"t_q_{_uid()}"
    _mk_query(client, name)
    res = client.get(f"/queries/{name}/destination")
    assert res.status_code == 404


def test_query_destination_404_when_query_unknown(client):
    res = client.get("/queries/t_missing/destination")
    assert res.status_code == 404


def test_schedule_update_unchanged_destination_stays_active(client):
    from config_store import get_store

    name = f"t_q_{_uid()}"
    _mk_query(client, name)
    client.post("/schedules/", json={
        "name": "s1", "query_name": name, "dataset_id": "ds1", "table_id": "tbl1",
        "frequency": "daily", "hour": 0, "minute": 0, "active": True,
    })
    schedule = client.get("/schedules/").json()[0]
    res = client.patch(f"/schedules/{schedule['id']}", json={"active": False})
    assert res.status_code == 200

    dest = client.get(f"/queries/{name}/destination").json()
    assert dest["dataset_id"] == "ds1"
    assert dest["table_id"] == "tbl1"
    assert dest["stale"] is False

    rows = [d for d in get_store().list_destinations(name) if d["dataset_id"] == "ds1" and d["table_id"] == "tbl1"]
    assert len(rows) == 1
    assert rows[0]["stale"] is False
