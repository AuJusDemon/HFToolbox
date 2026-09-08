"""Pure scheduling and validation for Auto-Bump jobs."""

from __future__ import annotations

import json
import re
import time
from datetime import date, datetime, time as clock_time, timedelta, timezone
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError


VALID_INTERVALS = frozenset({6, 8, 12, 16, 24, 48, 72, 120, 168})
VALID_MODES = frozenset({"timer", "calendar"})
VALID_END_MODES = frozenset({"unlimited", "date", "duration", "successes", "bytes"})
TIME_RE = re.compile(r"^(?:[01]\d|2[0-3]):[0-5]\d$")


def validate_interval(interval_h: int) -> int:
    interval_h = int(interval_h)
    if interval_h not in VALID_INTERVALS:
        allowed = ", ".join(str(value) for value in sorted(VALID_INTERVALS))
        raise ValueError(f"Interval must be one of: {allowed} hours")
    return interval_h


def validate_timezone(name: str) -> str:
    name = str(name or "UTC").strip()
    try:
        ZoneInfo(name)
    except ZoneInfoNotFoundError as exc:
        raise ValueError("Timezone must be a valid IANA timezone") from exc
    return name


def _minute(value: str) -> int:
    if not TIME_RE.fullmatch(str(value or "")):
        raise ValueError("Times must use HH:MM in 24-hour format")
    hour, minute = map(int, value.split(":"))
    return hour * 60 + minute


def validate_allowed_windows(windows) -> list[dict]:
    if windows in (None, ""):
        return []
    if isinstance(windows, str):
        try:
            windows = json.loads(windows)
        except json.JSONDecodeError as exc:
            raise ValueError("Allowed hours are not valid JSON") from exc
    if not isinstance(windows, list):
        raise ValueError("Allowed hours must be a list")
    normalized = []
    seen = set()
    for row in windows:
        if not isinstance(row, dict):
            raise ValueError("Each allowed-hours row must be an object")
        days = sorted({int(day) for day in row.get("days", [])})
        if not days or any(day < 0 or day > 6 for day in days):
            raise ValueError("Each allowed-hours row needs weekdays from 0 through 6")
        start = str(row.get("start") or "")
        end = str(row.get("end") or "")
        start_minute, end_minute = _minute(start), _minute(end)
        if start_minute == end_minute:
            raise ValueError("Allowed-hours start and end cannot be the same")
        key = (tuple(days), start, end)
        if key in seen:
            raise ValueError("Duplicate allowed-hours rows are not permitted")
        seen.add(key)
        normalized.append({"days": days, "start": start, "end": end})
    return normalized


def validate_calendar_slots(slots) -> list[dict]:
    if slots in (None, ""):
        return []
    if isinstance(slots, str):
        try:
            slots = json.loads(slots)
        except json.JSONDecodeError as exc:
            raise ValueError("Calendar slots are not valid JSON") from exc
    if not isinstance(slots, list):
        raise ValueError("Calendar slots must be a list")
    normalized = []
    seen = set()
    for row in slots:
        if not isinstance(row, dict):
            raise ValueError("Each calendar slot must be an object")
        day = int(row.get("day", -1))
        at = str(row.get("time") or "")
        if day < 0 or day > 6:
            raise ValueError("Calendar weekdays must be from 0 through 6")
        _minute(at)
        key = (day, at)
        if key in seen:
            raise ValueError("Duplicate calendar slots are not permitted")
        seen.add(key)
        normalized.append({"day": day, "time": at})
    return sorted(normalized, key=lambda row: (row["day"], row["time"]))


def end_of_local_date(value: str, timezone_name: str) -> int:
    try:
        selected = date.fromisoformat(str(value or ""))
    except ValueError as exc:
        raise ValueError("End date must use YYYY-MM-DD") from exc
    zone = ZoneInfo(validate_timezone(timezone_name))
    local = datetime.combine(selected, clock_time(23, 59, 59)).replace(tzinfo=zone)
    return int(local.timestamp())


def serialize_schedule_rows(rows: list[dict]) -> str:
    return json.dumps(rows, separators=(",", ":"), sort_keys=True)


def _local_candidates(day: date, minute: int, zone: ZoneInfo) -> list[datetime]:
    naive = datetime.combine(day, clock_time(minute // 60, minute % 60))
    candidates = []
    for fold in (0, 1):
        local = naive.replace(tzinfo=zone, fold=fold)
        roundtrip = local.astimezone(timezone.utc).astimezone(zone)
        if roundtrip.replace(tzinfo=None) == naive and roundtrip.fold == fold:
            candidates.append(local)
    unique = {int(value.timestamp()): value for value in candidates}
    return [unique[key] for key in sorted(unique)]


def _window_intervals(anchor: date, window: dict, zone: ZoneInfo) -> list[tuple[int, int]]:
    start_minute = _minute(window["start"])
    end_minute = _minute(window["end"])
    end_day = anchor + timedelta(days=1 if end_minute <= start_minute else 0)
    starts = _local_candidates(anchor, start_minute, zone)
    ends = _local_candidates(end_day, end_minute, zone)
    if not starts or not ends:
        return []
    start_ts = min(int(value.timestamp()) for value in starts)
    end_ts = max(int(value.timestamp()) for value in ends)
    return [(start_ts, end_ts)] if end_ts > start_ts else []


def next_allowed_time(candidate_ts: int, timezone_name: str, windows) -> int:
    timezone_name = validate_timezone(timezone_name)
    windows = validate_allowed_windows(windows)
    candidate_ts = int(candidate_ts)
    if not windows:
        return candidate_ts
    zone = ZoneInfo(timezone_name)
    local_day = datetime.fromtimestamp(candidate_ts, zone).date()
    intervals = []
    for offset in range(-1, 9):
        anchor = local_day + timedelta(days=offset)
        for window in windows:
            if anchor.weekday() in window["days"]:
                intervals.extend(_window_intervals(anchor, window, zone))
    for start_ts, end_ts in sorted(intervals):
        if start_ts <= candidate_ts < end_ts:
            return candidate_ts
        if start_ts >= candidate_ts:
            return start_ts
    raise ValueError("Could not find an allowed time in the next week")


def next_calendar_slot(candidate_ts: int, timezone_name: str, slots, windows=None,
                       *, strictly_after: bool = False) -> int:
    timezone_name = validate_timezone(timezone_name)
    slots = validate_calendar_slots(slots)
    windows = validate_allowed_windows(windows)
    if not slots:
        raise ValueError("Calendar Scheduling requires at least one weekly slot")
    zone = ZoneInfo(timezone_name)
    local_day = datetime.fromtimestamp(int(candidate_ts), zone).date()
    choices = []
    for offset in range(0, 15):
        day = local_day + timedelta(days=offset)
        for slot in slots:
            if slot["day"] != day.weekday():
                continue
            for local in _local_candidates(day, _minute(slot["time"]), zone):
                slot_ts = int(local.timestamp())
                if slot_ts < candidate_ts or (strictly_after and slot_ts == candidate_ts):
                    continue
                if windows and next_allowed_time(slot_ts, timezone_name, windows) != slot_ts:
                    continue
                choices.append(slot_ts)
    if not choices:
        raise ValueError("No calendar slot falls inside the allowed hours")
    return min(choices)


def validate_end_condition(end_mode: str, *, end_at=None, end_days=None, end_limit=None,
                           now: int | None = None) -> tuple[str, int | None, int | None]:
    now = int(now or time.time())
    mode = str(end_mode or "unlimited").strip().lower()
    if mode not in VALID_END_MODES:
        raise ValueError("Invalid end condition")
    supplied = sum(value not in (None, "", 0) for value in (end_at, end_days, end_limit))
    if mode == "unlimited":
        if supplied:
            raise ValueError("Unlimited schedules cannot include an end value")
        return mode, None, None
    if mode == "date":
        if end_days not in (None, "", 0) or end_limit not in (None, "", 0):
            raise ValueError("Date schedules accept only an end date")
        end_at = int(end_at or 0)
        if end_at <= now:
            raise ValueError("End date must be in the future")
        return mode, end_at, None
    if mode == "duration":
        if end_limit not in (None, "", 0) or (end_at not in (None, "", 0) and end_days not in (None, "", 0)):
            raise ValueError("Duration schedules accept a day count or their saved end timestamp")
        if end_at not in (None, "", 0):
            end_at = int(end_at)
            if end_at <= now:
                raise ValueError("Duration end timestamp must be in the future")
            return mode, end_at, None
        days = int(end_days or 0)
        if days <= 0:
            raise ValueError("Duration must be a positive number of days")
        return mode, now + days * 86400, days
    if end_at not in (None, "", 0) or end_days not in (None, "", 0):
        raise ValueError("This end condition accepts only a positive limit")
    limit = int(end_limit or 0)
    if limit <= 0:
        raise ValueError("End limit must be greater than zero")
    return mode, None, limit


def normalize_schedule_payload(payload: dict, *, now: int | None = None) -> dict:
    """Normalize the canonical schedule payload used by every entry point."""
    data = dict(payload or {})
    mode = str(data.get("mode") or "timer").strip().lower()
    if mode not in VALID_MODES:
        raise ValueError(f"mode must be one of: {', '.join(sorted(VALID_MODES))}")
    interval_h = validate_interval(int(data.get("interval_h") or 0))
    timezone_name = validate_timezone(data.get("timezone") or "UTC")
    allowed_windows = validate_allowed_windows(data.get("allowed_windows"))
    calendar_slots = validate_calendar_slots(data.get("calendar_slots"))
    if mode == "calendar" and not calendar_slots:
        raise ValueError("Calendar Scheduling requires at least one weekly slot")
    if mode == "calendar" and allowed_windows:
        next_calendar_slot(int(now or time.time()), timezone_name, calendar_slots, allowed_windows)

    end_mode = str(data.get("end_mode") or "unlimited").strip().lower()
    end_at = data.get("end_at")
    end_date = data.get("end_date")
    if end_date:
        if end_at not in (None, "", 0):
            raise ValueError("Conflicting end dates")
        end_at = end_of_local_date(end_date, timezone_name)
    legacy_end = data.get("bump_until")
    if legacy_end and end_mode == "unlimited":
        end_mode, end_at = "date", legacy_end
    if legacy_end and end_at and int(legacy_end) != int(end_at):
        raise ValueError("Conflicting end dates")
    end_mode, end_at, end_limit = validate_end_condition(
        end_mode, end_at=end_at, end_days=data.get("end_days"),
        end_limit=data.get("end_limit"), now=now,
    )
    return {
        "mode": mode,
        "interval_h": interval_h,
        "timezone": timezone_name,
        "allowed_windows": allowed_windows,
        "calendar_slots": calendar_slots,
        "end_mode": end_mode,
        "end_at": end_at,
        "end_limit": end_limit,
    }


def calculate_updated_next(job: dict, mode: str, interval_h: int, now: int | None = None,
                           timezone_name: str | None = None, allowed_windows=None,
                           calendar_slots=None, *, strictly_after: bool = False) -> int:
    interval_h = validate_interval(interval_h)
    if mode not in VALID_MODES:
        raise ValueError("Invalid bump mode")
    now = int(now or time.time())
    lastpost = int(job.get("lastpost_ts") or 0)
    eligible_at = lastpost + interval_h * 3600 if lastpost else now + interval_h * 3600
    candidate = max(now, eligible_at)
    timezone_name = timezone_name or job.get("timezone") or "UTC"
    allowed_windows = allowed_windows if allowed_windows is not None else job.get("allowed_windows")
    calendar_slots = calendar_slots if calendar_slots is not None else job.get("calendar_slots")
    if mode == "calendar":
        return next_calendar_slot(candidate, timezone_name, calendar_slots, allowed_windows,
                                  strictly_after=strictly_after)
    return next_allowed_time(candidate, timezone_name, allowed_windows)
