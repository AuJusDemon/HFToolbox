"""Read-only operator summary endpoints."""

from __future__ import annotations

import os
import time
from typing import Any

from fastapi import APIRouter, Request

from _db_compat import _db
from operator_auth import require_operator

router = APIRouter(prefix="/api/operator", tags=["operator"])


def _now() -> int:
    return int(time.time())


def _value(row: Any, key: str = "v", default: Any = 0) -> Any:
    if not row:
        return default
    try:
        return row[key]
    except Exception:
        try:
            return row[0]
        except Exception:
            return default


def _scalar(conn, sql: str, params: tuple[Any, ...] = (), default: Any = 0) -> Any:
    try:
        return _value(conn.execute(sql, params).fetchone(), default=default)
    except Exception:
        return default


def _row(conn, sql: str, params: tuple[Any, ...] = ()) -> dict[str, Any]:
    try:
        row = conn.execute(sql, params).fetchone()
        return dict(row) if row else {}
    except Exception:
        return {}


def _rows(conn, sql: str, params: tuple[Any, ...] = ()) -> tuple[list[dict[str, Any]], str]:
    try:
        return [dict(row) for row in conn.execute(sql, params).fetchall()], ""
    except Exception as exc:
        return [], f"{type(exc).__name__}: {str(exc)[:180]}"


def _count_map(conn, sql: str, params: tuple[Any, ...] = ()) -> dict[str, int]:
    try:
        rows = conn.execute(sql, params).fetchall()
        return {str(_value(row, "uid", "")): _int(_value(row, "count", 0)) for row in rows}
    except Exception:
        return {}


def _uid_set(conn, sql: str, params: tuple[Any, ...] = ()) -> set[str]:
    try:
        return {str(_value(row, "uid", "")) for row in conn.execute(sql, params).fetchall()}
    except Exception:
        return set()


def _int(value: Any) -> int:
    try:
        return int(value or 0)
    except Exception:
        return 0


def _short(value: Any, limit: int = 140) -> str:
    text = str(value or "").replace("\r", " ").replace("\n", " ").strip()
    while "  " in text:
        text = text.replace("  ", " ")
    if len(text) <= limit:
        return text or "unknown"
    return text[: limit - 1].rstrip() + "..."


def _age(ts: Any, now: int) -> int | None:
    ts_int = _int(ts)
    if ts_int <= 0:
        return None
    return max(0, now - ts_int)


def _flag(name: str) -> bool:
    return os.environ.get(name, "").strip().lower() in {"1", "true", "yes", "on"}


def _status(ok: bool, warn: bool = False) -> str:
    if not ok:
        return "bad"
    if warn:
        return "warn"
    return "good"


def _age_status(age: int | None, warn_after: int, bad_after: int, empty: str = "unknown") -> str:
    if age is None:
        return empty
    if age >= bad_after:
        return "bad"
    if age >= warn_after:
        return "warn"
    return "good"


REAL_USER_WHERE = "uid NOT LIKE 'bot\\_%' AND username NOT LIKE 'Practice Bot%'"
SYNTHETIC_USER_WHERE = "uid LIKE 'bot\\_%' OR username LIKE 'Practice Bot%'"


def _build_summary(operator_uid: str) -> dict[str, Any]:
    now = _now()
    day_ago = now - 86400
    week_ago = now - (7 * 86400)
    hour_ago = now - 3600

    with _db() as conn:
        users = {
            "total": _int(_scalar(conn, f"SELECT COUNT(*) AS v FROM users WHERE {REAL_USER_WHERE}")),
            "synthetic_hidden": _int(_scalar(conn, f"SELECT COUNT(*) AS v FROM users WHERE {SYNTHETIC_USER_WHERE}")),
            "active_24h": _int(_scalar(conn, f"SELECT COUNT(*) AS v FROM users WHERE {REAL_USER_WHERE} AND last_seen >= ?", (day_ago,))),
            "active_7d": _int(_scalar(conn, f"SELECT COUNT(*) AS v FROM users WHERE {REAL_USER_WHERE} AND last_seen >= ?", (week_ago,))),
            "token_ready": _int(_scalar(
                conn,
                f"SELECT COUNT(*) AS v FROM users WHERE {REAL_USER_WHERE} AND COALESCE(token_dead,0)=0 AND COALESCE(token,'')<>''",
            )),
            "token_dead": _int(_scalar(conn, f"SELECT COUNT(*) AS v FROM users WHERE {REAL_USER_WHERE} AND COALESCE(token_dead,0)=1")),
            "token_expiring_24h": _int(_scalar(
                conn,
                f"SELECT COUNT(*) AS v FROM users WHERE {REAL_USER_WHERE} AND token_expiry > ? AND token_expiry <= ?",
                (now, now + 86400),
            )),
            "telegram_linked": _int(_scalar(conn, "SELECT COUNT(*) AS v FROM telegram_links")),
        }

        bump_fail_reason = _row(
            conn,
            """
            SELECT COALESCE(NULLIF(reason,''),'unknown') AS reason, COUNT(*) AS count
            FROM bump_log
            WHERE ts >= ? AND action NOT IN ('bumped','skip')
            GROUP BY COALESCE(NULLIF(reason,''),'unknown')
            ORDER BY count DESC
            LIMIT 1
            """,
            (day_ago,),
        )
        bump = {
            "jobs_total": _int(_scalar(conn, "SELECT COUNT(*) AS v FROM bump_jobs")),
            "jobs_active": _int(_scalar(conn, "SELECT COUNT(*) AS v FROM bump_jobs WHERE enabled=1")),
            "jobs_due": _int(_scalar(
                conn,
                "SELECT COUNT(*) AS v FROM bump_jobs WHERE enabled=1 AND COALESCE(next_bump,0) <= ?",
                (now,),
            )),
            "jobs_expired": _int(_scalar(
                conn,
                "SELECT COUNT(*) AS v FROM bump_jobs WHERE bump_until IS NOT NULL AND bump_until > 0 AND bump_until <= ?",
                (now,),
            )),
            "blocked_dead_token": 0,
            "bumps_24h": _int(_scalar(
                conn,
                "SELECT COUNT(*) AS v FROM bump_log WHERE ts >= ? AND action='bumped'",
                (day_ago,),
            )),
            "non_success_24h": _int(_scalar(
                conn,
                "SELECT COUNT(*) AS v FROM bump_log WHERE ts >= ? AND action NOT IN ('bumped','skip')",
                (day_ago,),
            )),
            "top_non_success_reason": {
                "reason": str(bump_fail_reason.get("reason") or ""),
                "count": _int(bump_fail_reason.get("count")),
            } if bump_fail_reason else None,
        }

        last_run = _row(
            conn,
            """
            SELECT started_at, finished_at, source, calls_used, threads_seen,
                   new_threads, contracts_seen, remaining, status
            FROM market_collection_runs
            ORDER BY started_at DESC
            LIMIT 1
            """,
        )
        market = {
            "threads": _int(_scalar(conn, "SELECT COUNT(*) AS v FROM market_threads")),
            "contracts": _int(_scalar(conn, "SELECT COUNT(*) AS v FROM market_contracts")),
            "watches_enabled": _int(_scalar(conn, "SELECT COUNT(*) AS v FROM market_watches WHERE enabled=1")),
            "watch_matches_24h": _int(_scalar(
                conn,
                "SELECT COUNT(*) AS v FROM market_watch_matches WHERE matched_at >= ?",
                (day_ago,),
            )),
            "refresh_queue": _int(_scalar(conn, "SELECT COUNT(*) AS v FROM market_thread_refresh_queue")),
            "contract_queue": _int(_scalar(conn, "SELECT COUNT(*) AS v FROM market_contract_thread_queue")),
            "last_thread_seen_age": _age(_scalar(conn, "SELECT MAX(last_seen_at) AS v FROM market_threads"), now),
            "last_contract_seen_age": _age(_scalar(conn, "SELECT MAX(last_seen_at) AS v FROM market_contracts"), now),
            "last_forum_scan_age": _age(_scalar(conn, "SELECT MAX(last_scanned_at) AS v FROM market_forums"), now),
            "last_run": last_run,
        }

        alerts = {
            "events_24h": _int(_scalar(conn, "SELECT COUNT(*) AS v FROM alert_events WHERE created_at >= ?", (day_ago,))),
            "telegram_sent_24h": _int(_scalar(
                conn,
                "SELECT COUNT(*) AS v FROM alert_events WHERE created_at >= ? AND telegram_status='sent'",
                (day_ago,),
            )),
            "telegram_failed_24h": _int(_scalar(
                conn,
                "SELECT COUNT(*) AS v FROM alert_events WHERE created_at >= ? AND telegram_status='failed'",
                (day_ago,),
            )),
            "pending_older_1h": _int(_scalar(
                conn,
                "SELECT COUNT(*) AS v FROM alert_events WHERE telegram_sent=0 AND created_at < ?",
                (hour_ago,),
            )),
        }

        queues = {
            "posting_pending": _int(_scalar(conn, "SELECT COUNT(*) AS v FROM scheduled_threads WHERE status='pending'")),
            "posting_due": _int(_scalar(
                conn,
                "SELECT COUNT(*) AS v FROM scheduled_threads WHERE status='pending' AND fire_at <= ?",
                (now,),
            )),
            "posting_sending": _int(_scalar(conn, "SELECT COUNT(*) AS v FROM scheduled_threads WHERE status='sending'")),
            "posting_failed": _int(_scalar(conn, "SELECT COUNT(*) AS v FROM scheduled_threads WHERE status='failed'")),
            "reply_unread": _int(_scalar(conn, "SELECT COUNT(*) AS v FROM reply_queue WHERE status='unread'")),
            "reply_checks_pending": _int(_scalar(conn, "SELECT COUNT(*) AS v FROM owned_reply_checks WHERE status='pending'")),
            "reply_checks_due": _int(_scalar(
                conn,
                "SELECT COUNT(*) AS v FROM owned_reply_checks WHERE status='pending' AND COALESCE(next_attempt_at,0) <= ?",
                (now,),
            )),
            "reply_checks_running": _int(_scalar(conn, "SELECT COUNT(*) AS v FROM owned_reply_checks WHERE status='running'")),
            "reply_checks_stuck": _int(_scalar(
                conn,
                "SELECT COUNT(*) AS v FROM owned_reply_checks WHERE status='running' AND COALESCE(updated_at,0) <= ?",
                (now - 300,),
            )),
            "market_thread_refresh": market["refresh_queue"],
            "market_thread_refresh_due": _int(_scalar(
                conn,
                "SELECT COUNT(*) AS v FROM market_thread_refresh_queue WHERE COALESCE(next_attempt_at,0) <= ?",
                (now,),
            )),
            "market_reply_verify": _int(_scalar(conn, "SELECT COUNT(*) AS v FROM market_reply_verify_queue")),
            "market_reply_verify_due": _int(_scalar(
                conn,
                "SELECT COUNT(*) AS v FROM market_reply_verify_queue WHERE COALESCE(next_attempt_at,0) <= ?",
                (now,),
            )),
            "market_contract_lookup": market["contract_queue"],
            "market_contract_lookup_due": _int(_scalar(
                conn,
                "SELECT COUNT(*) AS v FROM market_contract_thread_queue WHERE COALESCE(next_attempt_at,0) <= ?",
                (now,),
            )),
            "telegram_pending": _int(_scalar(conn, "SELECT COUNT(*) AS v FROM alert_events WHERE telegram_sent=0")),
            "telegram_pending_old": alerts["pending_older_1h"],
        }

        freshness = {
            "bytes_crawl_age": _age(_scalar(conn, "SELECT MAX(last_crawl) AS v FROM bytes_crawl_state"), now),
            "contracts_crawl_age": _age(_scalar(conn, "SELECT MAX(last_crawl) AS v FROM contracts_crawl_state"), now),
            "contracts_recheck_age": _age(_scalar(conn, "SELECT MAX(last_recheck_ts) AS v FROM contracts_crawl_state"), now),
            "last_bump_attempt_age": _age(_scalar(conn, "SELECT MAX(ts) AS v FROM bump_log"), now),
            "last_bump_success_age": _age(_scalar(conn, "SELECT MAX(ts) AS v FROM bump_log WHERE action='bumped'"), now),
            "last_post_sent_age": _age(_scalar(conn, "SELECT MAX(sent_at) AS v FROM scheduled_threads WHERE status='sent'"), now),
            "last_reply_seen_age": _age(_scalar(conn, "SELECT MAX(created_at) AS v FROM reply_queue"), now),
            "last_alert_created_age": _age(_scalar(conn, "SELECT MAX(created_at) AS v FROM alert_events"), now),
            "last_alert_sent_age": _age(_scalar(conn, "SELECT MAX(telegram_delivered_at) AS v FROM alert_events"), now),
        }

        recent_failures: list[dict[str, Any]] = []
        for row in _rows(
            conn,
            """
            SELECT COALESCE(NULLIF(telegram_error,''),'unknown') AS message,
                   COUNT(*) AS count, MAX(created_at) AS last_seen
            FROM alert_events
            WHERE created_at >= ? AND telegram_status='failed'
            GROUP BY COALESCE(NULLIF(telegram_error,''),'unknown')
            ORDER BY count DESC, last_seen DESC
            LIMIT 5
            """,
            (week_ago,),
        )[0]:
            recent_failures.append({
                "area": "Telegram delivery",
                "message": _short(row.get("message")),
                "count": _int(row.get("count")),
                "last_seen": _int(row.get("last_seen")),
            })
        for row in _rows(
            conn,
            """
            SELECT COALESCE(NULLIF(error,''),'unknown') AS message,
                   COUNT(*) AS count, MAX(COALESCE(sent_at,created_at,fire_at,0)) AS last_seen
            FROM scheduled_threads
            WHERE status='failed'
            GROUP BY COALESCE(NULLIF(error,''),'unknown')
            ORDER BY count DESC, last_seen DESC
            LIMIT 5
            """,
        )[0]:
            recent_failures.append({
                "area": "Scheduled posting",
                "message": _short(row.get("message")),
                "count": _int(row.get("count")),
                "last_seen": _int(row.get("last_seen")),
            })
        for row in _rows(
            conn,
            """
            SELECT COALESCE(NULLIF(last_error,''),'unknown') AS message,
                   COUNT(*) AS count, MAX(updated_at) AS last_seen
            FROM owned_reply_checks
            WHERE COALESCE(last_error,'') <> ''
            GROUP BY COALESCE(NULLIF(last_error,''),'unknown')
            ORDER BY count DESC, last_seen DESC
            LIMIT 5
            """,
        )[0]:
            recent_failures.append({
                "area": "Reply monitor",
                "message": _short(row.get("message")),
                "count": _int(row.get("count")),
                "last_seen": _int(row.get("last_seen")),
            })
        for row in _rows(
            conn,
            """
            SELECT COALESCE(NULLIF(reason,''),'unknown') AS message,
                   COUNT(*) AS count, MAX(ts) AS last_seen
            FROM bump_log
            WHERE ts >= ? AND action NOT IN ('bumped','skip')
            GROUP BY COALESCE(NULLIF(reason,''),'unknown')
            ORDER BY count DESC, last_seen DESC
            LIMIT 5
            """,
            (week_ago,),
        )[0]:
            recent_failures.append({
                "area": "Auto bumper",
                "message": _short(row.get("message")),
                "count": _int(row.get("count")),
                "last_seen": _int(row.get("last_seen")),
            })
        for row in _rows(
            conn,
            """
            SELECT source, status, COALESCE(NULLIF(error,''),'') AS error,
                   COUNT(*) AS count, MAX(started_at) AS last_seen
            FROM market_collection_runs
            WHERE started_at >= ?
              AND status NOT IN ('ok','success','complete','completed')
              AND (COALESCE(error,'') <> '' OR status NOT IN ('running'))
            GROUP BY source, status, COALESCE(NULLIF(error,''),'')
            ORDER BY count DESC, last_seen DESC
            LIMIT 5
            """,
            (week_ago,),
        )[0]:
            source = _short(row.get("source"), 40)
            detail = row.get("error") or row.get("status") or "unknown"
            recent_failures.append({
                "area": "Marketplace collector",
                "message": _short(f"{source}: {detail}"),
                "count": _int(row.get("count")),
                "last_seen": _int(row.get("last_seen")),
            })
        recent_failures.sort(key=lambda item: (_int(item.get("last_seen")), _int(item.get("count"))), reverse=True)
        recent_failures = recent_failures[:12]

        dead_uids = _uid_set(conn, f"SELECT uid FROM users WHERE {REAL_USER_WHERE} AND COALESCE(token_dead,0)=1")
        active_bump_uids = _uid_set(conn, "SELECT uid FROM bump_jobs WHERE enabled=1")
        bump["blocked_dead_token"] = len(active_bump_uids.intersection(dead_uids))

        authed_users, authed_users_error = _rows(
            conn,
            """
            SELECT
                uid,
                COALESCE(NULLIF(username,''),'unknown') AS username,
                COALESCE(last_seen,0) AS last_seen,
                COALESCE(created_at,0) AS created_at,
                COALESCE(token_dead,0) AS token_dead,
                COALESCE(token_expiry,0) AS token_expiry,
                CASE WHEN COALESCE(token,'')='' THEN 0 ELSE 1 END AS has_token
            FROM users
            WHERE uid NOT LIKE 'bot\\_%' AND username NOT LIKE 'Practice Bot%'
            ORDER BY COALESCE(last_seen,0) DESC, COALESCE(created_at,0) DESC
            LIMIT 100
            """,
        )
        telegram_uids = _uid_set(conn, "SELECT hf_uid AS uid FROM telegram_links")
        bump_counts = _count_map(conn, "SELECT uid, COUNT(*) AS count FROM bump_jobs GROUP BY uid")
        posting_counts = _count_map(conn, "SELECT uid, COUNT(*) AS count FROM scheduled_threads WHERE status='pending' GROUP BY uid")
        reply_counts = _count_map(conn, "SELECT uid, COUNT(*) AS count FROM reply_queue WHERE status='unread' GROUP BY uid")
        watch_counts = _count_map(
            conn,
            "SELECT uid, COUNT(*) AS count FROM market_watches WHERE enabled=1 GROUP BY uid",
        )
        alert_counts = _count_map(
            conn,
            "SELECT hf_uid AS uid, COUNT(*) AS count FROM alert_events WHERE created_at >= ? GROUP BY hf_uid",
            (week_ago,),
        )
        for user in authed_users:
            uid = str(user.get("uid") or "")
            user["telegram_linked"] = 1 if uid in telegram_uids else 0
            user["bump_jobs"] = bump_counts.get(uid, 0)
            user["scheduled_posts"] = posting_counts.get(uid, 0)
            user["open_replies"] = reply_counts.get(uid, 0)
            user["market_watches"] = watch_counts.get(uid, 0)
            user["alerts_7d"] = alert_counts.get(uid, 0)
        operator_user = _row(
            conn,
            """
            SELECT uid, COALESCE(NULLIF(username,''),'unknown') AS username,
                   COALESCE(last_seen,0) AS last_seen, COALESCE(created_at,0) AS created_at,
                   COALESCE(token_dead,0) AS token_dead, COALESCE(token_expiry,0) AS token_expiry,
                   CASE WHEN COALESCE(token,'')='' THEN 0 ELSE 1 END AS has_token
            FROM users
            WHERE uid=?
            LIMIT 1
            """,
            (operator_uid,),
        )

    background_disabled = _flag("DEV_DISABLE_CRAWL")
    telegram_disabled = _flag("DEV_DISABLE_TELEGRAM")
    controller_configured = bool(os.environ.get("HF_CONTROL_PLANE_URL", "").strip())
    db_host = os.environ.get("DB_HOST", "sqlite").strip() or "sqlite"
    db_name = os.environ.get("DB_NAME", os.environ.get("DB_PATH", "data/hf_dash.db")).strip()

    attention = []
    if users["token_dead"]:
        attention.append({"level": "warn", "label": "Dead tokens", "value": users["token_dead"]})
    if bump["blocked_dead_token"]:
        attention.append({"level": "warn", "label": "Bump jobs blocked by auth", "value": bump["blocked_dead_token"]})
    if bump["non_success_24h"]:
        attention.append({"level": "warn", "label": "Bump non-success in 24h", "value": bump["non_success_24h"]})
    if alerts["telegram_failed_24h"]:
        attention.append({"level": "bad", "label": "Telegram failures in 24h", "value": alerts["telegram_failed_24h"]})
    if market["last_contract_seen_age"] is None or market["last_contract_seen_age"] > 21600:
        attention.append({"level": "warn", "label": "Contract index stale", "value": "over 6h"})
    if queues["posting_failed"]:
        attention.append({"level": "bad", "label": "Failed scheduled posts", "value": queues["posting_failed"]})
    if queues["reply_checks_stuck"]:
        attention.append({"level": "bad", "label": "Stuck reply checks", "value": queues["reply_checks_stuck"]})
    if queues["market_contract_lookup_due"]:
        attention.append({"level": "warn", "label": "Contract lookups due", "value": queues["market_contract_lookup_due"]})

    workers = [
        {
            "name": "HF Controller",
            "state": "configured" if controller_configured else "missing",
            "status": "good" if controller_configured else "bad",
            "last_seen_age": None,
            "backlog": 0,
            "note": "backend uses controller URL" if controller_configured else "no controller URL in env",
        },
        {
            "name": "Background Scheduler",
            "state": "disabled" if background_disabled else "enabled",
            "status": "warn" if background_disabled else "good",
            "last_seen_age": None,
            "backlog": queues["posting_due"] + bump["jobs_due"] + queues["reply_checks_due"],
            "note": "dev crawl flag is on" if background_disabled else "jobs may run",
        },
        {
            "name": "Auto Bumper",
            "state": "active" if bump["jobs_active"] else "idle",
            "status": "bad" if bump["non_success_24h"] else ("warn" if bump["jobs_due"] else "good"),
            "last_seen_age": freshness["last_bump_attempt_age"],
            "backlog": bump["jobs_due"],
            "note": "last success shown separately",
        },
        {
            "name": "Scheduled Posting",
            "state": "queued" if queues["posting_pending"] else "idle",
            "status": "bad" if queues["posting_failed"] else ("warn" if queues["posting_due"] else "good"),
            "last_seen_age": freshness["last_post_sent_age"],
            "backlog": queues["posting_due"],
            "note": f"{queues['posting_pending']} pending, {queues['posting_failed']} failed",
        },
        {
            "name": "Reply Monitor",
            "state": "queued" if queues["reply_checks_pending"] else "idle",
            "status": "bad" if queues["reply_checks_stuck"] else ("warn" if queues["reply_checks_due"] else "good"),
            "last_seen_age": freshness["last_reply_seen_age"],
            "backlog": queues["reply_checks_due"],
            "note": f"{queues['reply_unread']} unread replies",
        },
        {
            "name": "Marketplace Collector",
            "state": str((last_run or {}).get("status") or "unknown"),
            "status": _age_status(market["last_forum_scan_age"], 3600, 21600),
            "last_seen_age": market["last_forum_scan_age"],
            "backlog": queues["market_thread_refresh_due"] + queues["market_reply_verify_due"] + queues["market_contract_lookup_due"],
            "note": f"{market['threads']} threads, {market['contracts']} contracts",
        },
        {
            "name": "Bytes Crawl",
            "state": "known" if freshness["bytes_crawl_age"] is not None else "no rows",
            "status": _age_status(freshness["bytes_crawl_age"], 86400, 604800, "warn"),
            "last_seen_age": freshness["bytes_crawl_age"],
            "backlog": 0,
            "note": "per-user crawl state",
        },
        {
            "name": "Contracts Crawl",
            "state": "known" if freshness["contracts_crawl_age"] is not None else "no rows",
            "status": _age_status(freshness["contracts_crawl_age"], 86400, 604800, "warn"),
            "last_seen_age": freshness["contracts_crawl_age"],
            "backlog": queues["market_contract_lookup_due"],
            "note": "HF contract history crawl state",
        },
        {
            "name": "Telegram Delivery",
            "state": "disabled" if telegram_disabled else "enabled",
            "status": "warn" if telegram_disabled else ("bad" if alerts["telegram_failed_24h"] else "good"),
            "last_seen_age": freshness["last_alert_sent_age"],
            "backlog": queues["telegram_pending_old"],
            "note": f"{alerts['telegram_sent_24h']} sent in 24h",
        },
    ]

    return {
        "generated_at": now,
        "operator_uid": operator_uid,
        "environment": os.environ.get("ENV", "development"),
        "runtime": {
            "background_crawl": "disabled" if background_disabled else "enabled",
            "telegram_delivery": "disabled" if telegram_disabled else "enabled",
            "controller": "configured" if controller_configured else "not configured",
            "database": f"{db_host}/{db_name}" if db_name else db_host,
            "status": _status(controller_configured, background_disabled),
        },
        "users": users,
        "authed_users": authed_users,
        "authed_users_error": authed_users_error,
        "operator_user": operator_user,
        "bump_service": bump,
        "marketplace": market,
        "alerts": alerts,
        "queues": queues,
        "freshness": freshness,
        "workers": workers,
        "recent_failures": recent_failures,
        "attention": attention,
    }


@router.get("/summary")
async def summary(request: Request):
    operator_uid = require_operator(request)
    return _build_summary(operator_uid)
