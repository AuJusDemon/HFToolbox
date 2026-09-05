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


def _rows(conn, sql: str, params: tuple[Any, ...] = ()) -> list[dict[str, Any]]:
    try:
        return [dict(row) for row in conn.execute(sql, params).fetchall()]
    except Exception:
        return []


def _int(value: Any) -> int:
    try:
        return int(value or 0)
    except Exception:
        return 0


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


def _build_summary() -> dict[str, Any]:
    now = _now()
    day_ago = now - 86400
    week_ago = now - (7 * 86400)
    hour_ago = now - 3600

    with _db() as conn:
        users = {
            "total": _int(_scalar(conn, "SELECT COUNT(*) AS v FROM users")),
            "active_24h": _int(_scalar(conn, "SELECT COUNT(*) AS v FROM users WHERE last_seen >= ?", (day_ago,))),
            "active_7d": _int(_scalar(conn, "SELECT COUNT(*) AS v FROM users WHERE last_seen >= ?", (week_ago,))),
            "token_ready": _int(_scalar(
                conn,
                "SELECT COUNT(*) AS v FROM users WHERE COALESCE(token_dead,0)=0 AND COALESCE(token,'')<>''",
            )),
            "token_dead": _int(_scalar(conn, "SELECT COUNT(*) AS v FROM users WHERE COALESCE(token_dead,0)=1")),
            "token_expiring_24h": _int(_scalar(
                conn,
                "SELECT COUNT(*) AS v FROM users WHERE token_expiry > ? AND token_expiry <= ?",
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
            "blocked_dead_token": _int(_scalar(
                conn,
                """
                SELECT COUNT(*) AS v
                FROM bump_jobs j
                JOIN users u ON u.uid = j.uid
                WHERE j.enabled=1 AND COALESCE(u.token_dead,0)=1
                """,
            )),
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

        authed_users = _rows(
            conn,
            """
            SELECT
                u.uid,
                COALESCE(NULLIF(u.username,''),'unknown') AS username,
                COALESCE(u.last_seen,0) AS last_seen,
                COALESCE(u.created_at,0) AS created_at,
                COALESCE(u.token_dead,0) AS token_dead,
                COALESCE(u.token_expiry,0) AS token_expiry,
                CASE WHEN tl.hf_uid IS NULL THEN 0 ELSE 1 END AS telegram_linked,
                (SELECT COUNT(*) FROM bump_jobs bj WHERE bj.uid=u.uid) AS bump_jobs,
                (SELECT COUNT(*) FROM market_watches mw WHERE mw.uid=u.uid AND mw.enabled=1) AS market_watches,
                (SELECT COUNT(*) FROM alert_events ae WHERE ae.hf_uid=u.uid AND ae.created_at >= ?) AS alerts_7d
            FROM users u
            LEFT JOIN telegram_links tl ON tl.hf_uid=u.uid
            WHERE COALESCE(u.token,'')<>''
            ORDER BY COALESCE(u.last_seen,0) DESC, COALESCE(u.created_at,0) DESC
            LIMIT 100
            """,
            (week_ago,),
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

    return {
        "generated_at": now,
        "operator_uid": "761578",
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
        "bump_service": bump,
        "marketplace": market,
        "alerts": alerts,
        "attention": attention,
    }


@router.get("/summary")
async def summary(request: Request):
    require_operator(request)
    return _build_summary()
