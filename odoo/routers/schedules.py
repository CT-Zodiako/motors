from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field, field_validator
from typing import Literal
from datetime import datetime

import db
from routers.runner import _fetch_registered, fetch_query_rows
from routers.bigquery import upload_to_bigquery, BigQueryUploadPayload

router = APIRouter(prefix="/schedules", tags=["schedules"])

ALLOWED_FREQUENCIES = ("hourly", "daily", "weekly", "monthly")


class ScheduleCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=150)
    query_name: str = Field(..., min_length=1, max_length=100)
    dataset_id: str = Field(..., min_length=1, max_length=100)
    table_id: str = Field(..., min_length=1, max_length=100)
    frequency: Literal["hourly", "daily", "weekly", "monthly"]
    hour: int | None = Field(None, ge=0, le=23)
    minute: int | None = Field(None, ge=0, le=59)
    day_of_week: int | None = Field(None, ge=0, le=6)
    day_of_month: int | None = Field(None, ge=1, le=31)
    interval_hours: int | None = Field(None, ge=1, le=24)
    active: bool = True

    @field_validator("hour", "minute", mode="before")
    def default_time(cls, v, info):
        if v is None and info.field_name in ("hour", "minute"):
            return 0 if info.field_name == "hour" else 0
        return v


class ScheduleUpdate(BaseModel):
    name: str | None = Field(None, min_length=1, max_length=150)
    query_name: str | None = Field(None, min_length=1, max_length=100)
    dataset_id: str | None = Field(None, min_length=1, max_length=100)
    table_id: str | None = Field(None, min_length=1, max_length=100)
    frequency: Literal["hourly", "daily", "weekly", "monthly"] | None = None
    hour: int | None = Field(None, ge=0, le=23)
    minute: int | None = Field(None, ge=0, le=59)
    day_of_week: int | None = Field(None, ge=0, le=6)
    day_of_month: int | None = Field(None, ge=1, le=31)
    interval_hours: int | None = Field(None, ge=1, le=24)
    active: bool | None = None


class ScheduleResponse(BaseModel):
    id: int
    name: str
    query_name: str
    dataset_id: str
    table_id: str
    frequency: str
    hour: int | None
    minute: int | None
    day_of_week: int | None
    day_of_month: int | None
    interval_hours: int | None
    active: bool
    last_run_at: datetime | None
    last_run_status: str | None
    last_run_message: str | None
    created_at: datetime


class ScheduleRunResponse(BaseModel):
    id: int
    schedule_id: int
    started_at: datetime
    finished_at: datetime | None
    status: str
    message: str | None
    rows_loaded: int | None


def _row_to_schedule(row: dict) -> dict:
    return {
        "id": row["id"],
        "name": row["name"],
        "query_name": row["query_name"],
        "dataset_id": row["dataset_id"],
        "table_id": row["table_id"],
        "frequency": row["frequency"],
        "hour": row["hour"],
        "minute": row["minute"],
        "day_of_week": row["day_of_week"],
        "day_of_month": row["day_of_month"],
        "interval_hours": row["interval_hours"],
        "active": row["active"],
        "last_run_at": row["last_run_at"],
        "last_run_status": row["last_run_status"],
        "last_run_message": row["last_run_message"],
        "created_at": row["created_at"],
    }


@router.get("", response_model=list[ScheduleResponse])
def list_schedules():
    rows = db.query("SELECT * FROM query_schedules ORDER BY created_at DESC")
    return [_row_to_schedule(r) for r in rows]


@router.get("/{schedule_id}/runs", response_model=list[ScheduleRunResponse])
def list_runs(schedule_id: int):
    rows = db.query(
        "SELECT * FROM query_schedule_runs WHERE schedule_id = %s ORDER BY started_at DESC LIMIT 50",
        (schedule_id,),
    )
    return [dict(r) for r in rows]


@router.post("", response_model=ScheduleResponse)
def create_schedule(payload: ScheduleCreate):
    _validate_schedule_fields(payload.frequency, payload)
    _ensure_query_exists(payload.query_name)
    payload_dict = payload.model_dump()

    row = db.query(
        """
        INSERT INTO query_schedules
        (name, query_name, dataset_id, table_id, frequency, hour, minute, day_of_week, day_of_month, interval_hours, active)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        RETURNING *
        """,
        (
            payload_dict["name"],
            payload_dict["query_name"],
            payload_dict["dataset_id"],
            payload_dict["table_id"],
            payload_dict["frequency"],
            payload_dict["hour"],
            payload_dict["minute"],
            payload_dict["day_of_week"],
            payload_dict["day_of_month"],
            payload_dict["interval_hours"],
            payload_dict["active"],
        ),
    )[0]
    schedule = _row_to_schedule(row)
    _register_job(schedule)
    return schedule


@router.patch("/{schedule_id}", response_model=ScheduleResponse)
def update_schedule(schedule_id: int, payload: ScheduleUpdate):
    existing = db.query("SELECT * FROM query_schedules WHERE id = %s", (schedule_id,))
    if not existing:
        raise HTTPException(status_code=404, detail="Schedule not found")

    current = existing[0]
    merged = {
        "name": payload.name if payload.name is not None else current["name"],
        "query_name": payload.query_name if payload.query_name is not None else current["query_name"],
        "dataset_id": payload.dataset_id if payload.dataset_id is not None else current["dataset_id"],
        "table_id": payload.table_id if payload.table_id is not None else current["table_id"],
        "frequency": payload.frequency if payload.frequency is not None else current["frequency"],
        "hour": payload.hour if payload.hour is not None else current["hour"],
        "minute": payload.minute if payload.minute is not None else current["minute"],
        "day_of_week": payload.day_of_week if payload.day_of_week is not None else current["day_of_week"],
        "day_of_month": payload.day_of_month if payload.day_of_month is not None else current["day_of_month"],
        "interval_hours": payload.interval_hours if payload.interval_hours is not None else current["interval_hours"],
        "active": payload.active if payload.active is not None else current["active"],
    }

    _validate_schedule_fields(merged["frequency"], merged)
    _ensure_query_exists(merged["query_name"])

    row = db.query(
        """
        UPDATE query_schedules
        SET name = %s, query_name = %s, dataset_id = %s, table_id = %s,
            frequency = %s, hour = %s, minute = %s, day_of_week = %s,
            day_of_month = %s, interval_hours = %s, active = %s
        WHERE id = %s
        RETURNING *
        """,
        (
            merged["name"],
            merged["query_name"],
            merged["dataset_id"],
            merged["table_id"],
            merged["frequency"],
            merged["hour"],
            merged["minute"],
            merged["day_of_week"],
            merged["day_of_month"],
            merged["interval_hours"],
            merged["active"],
            schedule_id,
        ),
    )[0]
    schedule = _row_to_schedule(row)
    _register_job(schedule)
    return schedule


@router.delete("/{schedule_id}")
def delete_schedule(schedule_id: int):
    existing = db.query("SELECT * FROM query_schedules WHERE id = %s", (schedule_id,))
    if not existing:
        raise HTTPException(status_code=404, detail="Schedule not found")
    _unregister_job(schedule_id)
    db.execute("DELETE FROM query_schedules WHERE id = %s", (schedule_id,))
    return {"deleted": schedule_id}


@router.post("/{schedule_id}/run")
def run_schedule_now(schedule_id: int):
    existing = db.query("SELECT * FROM query_schedules WHERE id = %s", (schedule_id,))
    if not existing:
        raise HTTPException(status_code=404, detail="Schedule not found")
    return _execute_schedule(existing[0])


def _validate_schedule_fields(frequency: str, fields):
    def get(key):
        if isinstance(fields, dict):
            return fields.get(key)
        return getattr(fields, key, None)

    if frequency == "hourly":
        if get("interval_hours") is None:
            raise HTTPException(status_code=400, detail="interval_hours is required for hourly frequency")
    elif frequency in ("daily", "weekly", "monthly"):
        if get("hour") is None or get("minute") is None:
            raise HTTPException(status_code=400, detail="hour and minute are required for daily/weekly/monthly frequency")
        if frequency == "weekly" and get("day_of_week") is None:
            raise HTTPException(status_code=400, detail="day_of_week is required for weekly frequency")
        if frequency == "monthly" and get("day_of_month") is None:
            raise HTTPException(status_code=400, detail="day_of_month is required for monthly frequency")


def _ensure_query_exists(query_name: str):
    registered = _fetch_registered(query_name)
    if registered is None:
        raise HTTPException(status_code=404, detail=f"Query '{query_name}' not found or inactive")


# ─── Scheduler integration ──────────────────────────────────────────────────

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.interval import IntervalTrigger

_scheduler: BackgroundScheduler | None = None


def get_scheduler() -> BackgroundScheduler:
    global _scheduler
    if _scheduler is None:
        _scheduler = BackgroundScheduler(timezone="UTC")
    return _scheduler


def start_scheduler():
    scheduler = get_scheduler()
    if scheduler.running:
        return
    schedules = db.query("SELECT * FROM query_schedules WHERE active = TRUE")
    for s in schedules:
        _register_job(_row_to_schedule(s))
    scheduler.start()


def _job_id(schedule_id: int) -> str:
    return f"schedule_{schedule_id}"


def _register_job(schedule: dict):
    scheduler = get_scheduler()
    _unregister_job(schedule["id"])
    if not schedule["active"]:
        return
    trigger = _build_trigger(schedule)
    scheduler.add_job(
        _execute_schedule_job,
        trigger=trigger,
        id=_job_id(schedule["id"]),
        replace_existing=True,
        args=[schedule["id"]],
    )


def _unregister_job(schedule_id: int):
    scheduler = get_scheduler()
    job_id = _job_id(schedule_id)
    try:
        scheduler.remove_job(job_id)
    except Exception:
        pass


def _build_trigger(schedule: dict):
    freq = schedule["frequency"]
    if freq == "hourly":
        return IntervalTrigger(hours=schedule.get("interval_hours") or 1)
    kwargs = {"hour": schedule["hour"], "minute": schedule["minute"]}
    if freq == "weekly":
        kwargs["day_of_week"] = str(schedule["day_of_week"])
    elif freq == "monthly":
        kwargs["day"] = str(schedule["day_of_month"])
    return CronTrigger(**kwargs)


def _execute_schedule_job(schedule_id: int):
    rows = db.query("SELECT * FROM query_schedules WHERE id = %s", (schedule_id,))
    if not rows:
        return
    _execute_schedule(rows[0])


def _execute_schedule(schedule: dict):

    run_id = db.query(
        "INSERT INTO query_schedule_runs (schedule_id, status) VALUES (%s, %s) RETURNING id",
        (schedule["id"], "running"),
    )[0]["id"]

    try:
        registered = _fetch_registered(schedule["query_name"])
        data = fetch_query_rows(registered)

        # Exportable value normalization (same as frontend)
        def _exportable_value(val):
            if val is None:
                return None
            if isinstance(val, (list, dict)):
                import json
                return json.dumps(val, ensure_ascii=False)
            return val

        rows = [{k: _exportable_value(v) for k, v in row.items()} for row in data]

        result = upload_to_bigquery(
            schedule["dataset_id"],
            schedule["table_id"],
            BigQueryUploadPayload(rows=rows),
            query_name=schedule["query_name"],
            origin="schedule",
        )

        db.execute(
            """
            UPDATE query_schedule_runs
            SET finished_at = NOW(), status = %s, message = %s, rows_loaded = %s
            WHERE id = %s
            """,
            (
                "success",
                f"Loaded {result.rows_loaded} rows into {schedule['dataset_id']}.{schedule['table_id']}",
                result.rows_loaded,
                run_id,
            ),
        )
        db.execute(
            """
            UPDATE query_schedules
            SET last_run_at = NOW(), last_run_status = %s, last_run_message = %s
            WHERE id = %s
            """,
            ("success", f"Loaded {result.rows_loaded} rows", schedule["id"]),
        )
        return {"status": "success", "rows_loaded": result.rows_loaded}

    except Exception as e:
        db.execute(
            "UPDATE query_schedule_runs SET finished_at = NOW(), status = %s, message = %s WHERE id = %s",
            ("error", str(e), run_id),
        )
        db.execute(
            "UPDATE query_schedules SET last_run_at = NOW(), last_run_status = %s, last_run_message = %s WHERE id = %s",
            ("error", str(e), schedule["id"]),
        )
        return {"status": "error", "message": str(e)}
