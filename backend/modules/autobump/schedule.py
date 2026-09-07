"""Pure schedule calculations shared by the Autobump API and tests."""

import time


PAGE1_RECHECK_SECS = 1800


def calculate_updated_next(job: dict, mode: str, interval_h: int, now: int | None = None) -> int:
    now = int(now or time.time())
    if mode == "page1":
        return now + PAGE1_RECHECK_SECS
    lastpost = int(job.get("lastpost_ts") or 0)
    if not lastpost:
        return now + interval_h * 3600
    eligible_at = lastpost + interval_h * 3600
    return eligible_at if eligible_at > now else now
