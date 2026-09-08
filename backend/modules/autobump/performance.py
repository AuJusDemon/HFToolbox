"""Shared, bounded bump-performance contract for Bump Service and My Business."""

import math
import time

from _db_compat import _db
from modules.merchant.merchant_db import latest_thread_snapshot
from modules.merchant.service import get_promotion_detail
from .grouping import quiet_groups


RANGES = {"7d": 7 * 86400, "30d": 30 * 86400, "all": None}


def _metric(value, source: str, available: bool = True) -> dict:
    return {"value": value if available else None, "source": source, "available": available}


def _logs(uid: str, tid: str) -> list[dict]:
    with _db() as conn:
        rows = conn.execute(
            "SELECT id,job_id,uid,tid,action,reason,numreplies,hf_fee,service_fee,total_cost,ts "
            "FROM bump_log WHERE uid=? AND tid=? ORDER BY ts DESC, id DESC",
            (uid, str(tid)),
        ).fetchall()
    return [dict(row) for row in rows]


def build_performance(uid: str, tid: str, range_key: str = "30d", page: int = 1,
                      page_size: int = 5, fees: dict | None = None) -> dict | None:
    if range_key not in RANGES:
        raise ValueError("range must be 7d, 30d, or all")
    page = max(1, int(page))
    page_size = min(20, max(1, int(page_size)))
    now = int(time.time())
    since = now - RANGES[range_key] if RANGES[range_key] else 0
    detail = get_promotion_detail(uid, str(tid))
    if not detail:
        return None

    logs = _logs(uid, str(tid))
    ranged_logs = [row for row in logs if int(row.get("ts") or 0) >= since]
    all_periods = detail.get("periods", [])
    periods = [row for row in all_periods if int(row.get("bump_ts") or 0) >= since]
    grouped = quiet_groups(periods)
    offset = (page - 1) * page_size
    page_items = grouped[offset:offset + page_size]

    successful_logs = [row for row in ranged_logs if row.get("action") == "bumped"]
    successful = len(successful_logs)
    skips = sum(1 for row in ranged_logs if row.get("action") == "skipped")
    failures = sum(1 for row in ranged_logs if row.get("action") == "error")
    replies = sum(int(row.get("period_replies") or 0) for row in periods)
    contracts = sum(int(row.get("contracts_opened") or 0) for row in periods)
    completed = sum(int(row.get("contracts_completed") or 0) for row in periods)
    gains = [int(row["reply_gain"]) for row in periods if row.get("reply_gain") is not None and not row.get("is_open")]
    reply_periods = sum(1 for row in periods if not row.get("is_open") and int(row.get("reply_gain") or 0) > 0)
    current = next((row for row in all_periods if row.get("is_open")), None)

    try:
        snapshot = latest_thread_snapshot(uid, str(tid))
    except Exception:
        snapshot = None
    latest_bump = next((row for row in logs if row.get("action") == "bumped"), None)
    current_gain = None
    current_observed_at = None
    if snapshot and snapshot.get("replies") is not None and latest_bump and latest_bump.get("numreplies") is not None:
        current_observed_at = int(snapshot.get("observed_at") or 0) or None
        if current_observed_at and current_observed_at >= int(latest_bump.get("ts") or 0):
            current_gain = int(snapshot["replies"]) - int(latest_bump["numreplies"])

    fees = fees or {"hf_fee": 0, "service_fee": 10, "total_cost": 10}
    observed_spend = sum(
        int(row["total_cost"]) if row.get("total_cost") is not None
        else int(fees.get("total_cost") or 0)
        for row in successful_logs
    )
    attempts = ranged_logs[:5]
    return {
        "tid": str(tid),
        "title": detail.get("title") or f"Thread {tid}",
        "range": {"key": range_key, "since": since or None, "through": now},
        "freshness": {
            "thread_observed_at": current_observed_at,
            "contracts_observed_at": detail.get("freshness", {}).get("contracts_last_crawl"),
        },
        "current_period": {
            "started_at": current.get("bump_ts") if current else None,
            "replies_since_latest_bump": _metric(current_gain, "observed", current_gain is not None),
            "tracked_replies": _metric((detail.get("since_last_bump") or {}).get("tracked_replies", 0), "observed"),
            "contracts_opened": _metric((detail.get("since_last_bump") or {}).get("contracts_opened"), "observed", current is not None),
            "contracts_completed": _metric((detail.get("since_last_bump") or {}).get("contracts_completed"), "observed", current is not None),
        },
        "metrics": {
            "successful_bumps": _metric(successful, "observed"),
            "skips": _metric(skips, "observed"),
            "failures": _metric(failures, "observed"),
            "tracked_replies": _metric(replies, "observed"),
            "contracts_opened": _metric(contracts, "observed"),
            "contracts_completed": _metric(completed, "observed"),
            "contracts_per_bump": _metric(round(contracts / successful, 2) if successful else None, "derived", bool(successful)),
            "average_reply_gain": _metric(round(sum(gains) / len(gains), 1) if gains else None, "derived", bool(gains)),
            "bumps_with_replies": _metric(reply_periods, "derived"),
            "reply_period_rate": _metric(round(reply_periods * 100 / len(gains), 1) if gains else None, "derived", bool(gains)),
            "estimated_bytes_spent": _metric(observed_spend, "recorded"),
        },
        "fees": {**fees, "source": "estimated"},
        "activity": page_items,
        "attempts": attempts,
        "pagination": {
            "page": page,
            "page_size": page_size,
            "total_items": len(grouped),
            "total_pages": max(1, math.ceil(len(grouped) / page_size)),
            "has_previous": page > 1,
            "has_next": offset + page_size < len(grouped),
        },
    }
