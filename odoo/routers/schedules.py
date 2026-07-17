from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field, field_validator
from typing import Literal
from datetime import datetime

from auth import require_permission
from config_store import get_store
from query_registry import mark_other_destinations_stale, upsert_destination
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
    last_run_at: datetime | None = None
    last_run_status: str | None = None
    last_run_message: str | None = None
    created_at: datetime


class ScheduleRunResponse(BaseModel):
    id: int
    schedule_id: int
    started_at: datetime
    finished_at: datetime | None
    status: str
    message: str | None
    rows_loaded: int | None


@router.get("", response_model=list[ScheduleResponse])
def list_schedules(user: dict = Depends(require_permission("menu.consultar.programar"))):
    return get_store().list_schedules()


@router.get("/{schedule_id}/runs", response_model=list[ScheduleRunResponse])
def list_runs(schedule_id: int, user: dict = Depends(require_permission("menu.consultar.programar"))):
    return get_store().list_runs(schedule_id)


@router.post("", response_model=ScheduleResponse)
def create_schedule(payload: ScheduleCreate, user: dict = Depends(require_permission("menu.consultar.programar"))):
    _validate_schedule_fields(payload.frequency, payload)
    _ensure_query_exists(payload.query_name)
    payload_dict = payload.model_dump()

    schedule = get_store().create_schedule(payload_dict)
    mark_other_destinations_stale(schedule["query_name"], schedule["dataset_id"], schedule["table_id"])
    upsert_destination(schedule["query_name"], schedule["dataset_id"], schedule["table_id"], origin="schedule")
    _register_job(schedule)
    return schedule


@router.patch("/{schedule_id}", response_model=ScheduleResponse)
def update_schedule(schedule_id: int, payload: ScheduleUpdate, user: dict = Depends(require_permission("menu.consultar.programar"))):
    current = get_store().get_schedule(schedule_id)
    if current is None:
        raise HTTPException(status_code=404, detail="Schedule not found")

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

    schedule = get_store().update_schedule(schedule_id, merged)
    mark_other_destinations_stale(schedule["query_name"], schedule["dataset_id"], schedule["table_id"])
    upsert_destination(schedule["query_name"], schedule["dataset_id"], schedule["table_id"], origin="schedule")
    _register_job(schedule)
    return schedule


@router.delete("/{schedule_id}")
def delete_schedule(schedule_id: int, user: dict = Depends(require_permission("menu.consultar.programar"))):
    if get_store().get_schedule(schedule_id) is None:
        raise HTTPException(status_code=404, detail="Schedule not found")
    _unregister_job(schedule_id)
    get_store().delete_schedule(schedule_id)
    return {"deleted": schedule_id}


@router.post("/{schedule_id}/run")
def run_schedule_now(schedule_id: int, user: dict = Depends(require_permission("menu.consultar.programar"))):
    existing = get_store().get_schedule(schedule_id)
    if existing is None:
        raise HTTPException(status_code=404, detail="Schedule not found")
    return _execute_schedule(existing)


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
    schedules = [s for s in get_store().list_schedules() if s.get("active", True)]
    for s in schedules:
        _register_job(s)
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
    schedule = get_store().get_schedule(schedule_id)
    if schedule is None:
        return
    _execute_schedule(schedule)


def _execute_schedule(schedule: dict):
    store = get_store()
    run = store.insert_run({
        "schedule_id": schedule["id"],
        "status": "running",
    })
    run_id = run["id"]

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

        store.finish_run(run_id, {
            "status": "success",
            "message": f"Loaded {result.rows_loaded} rows into {schedule['dataset_id']}.{schedule['table_id']}",
            "rows_loaded": result.rows_loaded,
        })
        return {"status": "success", "rows_loaded": result.rows_loaded}

    except Exception as e:
        store.finish_run(run_id, {
            "status": "error",
            "message": str(e),
        })
        return {"status": "error", "message": str(e)}
