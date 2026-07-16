"""Validators — ex-CHECK constraints from init_db.py DDL, ported to Python (V1)."""
from .errors import ValidationError


_FREQUENCIES = {"hourly", "daily", "weekly", "monthly"}


def validate_schedule(data: dict) -> None:
    """Re-implements CHECK constraints from query_schedules DDL."""
    freq = data.get("frequency")
    if freq is not None and freq not in _FREQUENCIES:
        raise ValidationError(f"frequency must be one of {_FREQUENCIES}, got {freq!r}")

    hour = data.get("hour")
    if hour is not None and not (0 <= hour <= 23):
        raise ValidationError(f"hour must be 0–23, got {hour}")

    minute = data.get("minute")
    if minute is not None and not (0 <= minute <= 59):
        raise ValidationError(f"minute must be 0–59, got {minute}")

    dow = data.get("day_of_week")
    if dow is not None and not (0 <= dow <= 6):
        raise ValidationError(f"day_of_week must be 0–6, got {dow}")

    dom = data.get("day_of_month")
    if dom is not None and not (1 <= dom <= 31):
        raise ValidationError(f"day_of_month must be 1–31, got {dom}")

    ih = data.get("interval_hours")
    if ih is not None and not (1 <= ih <= 24):
        raise ValidationError(f"interval_hours must be 1–24, got {ih}")
