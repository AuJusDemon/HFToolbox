"""Pure schedule calculations shared by the Autobump API and tests."""

import time


PAGE1_RECHECK_SECS = 1800
VALID_INTERVALS = frozenset({6, 8, 12, 16, 24, 48, 72, 120, 168})


def validate_interval(interval_h: int) -> int:
    interval_h = int(interval_h)
    if interval_h not in VALID_INTERVALS:
        allowed = ", ".join(str(value) for value in sorted(VALID_INTERVALS))
        raise ValueError(f"Interval must be one of: {allowed} hours")
    return interval_h


def calculate_updated_next(job: dict, mode: str, interval_h: int, now: int | None = None) -> int:
    interval_h = validate_interval(interval_h)
    now = int(now or time.time())
    if mode == "page1":
        return now + PAGE1_RECHECK_SECS
    lastpost = int(job.get("lastpost_ts") or 0)
    if not lastpost:
        return now + interval_h * 3600
    eligible_at = lastpost + interval_h * 3600
    return eligible_at if eligible_at > now else now
