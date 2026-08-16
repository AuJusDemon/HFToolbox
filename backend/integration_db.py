"""
Shared integration storage for Telegram links, alert events, and alert delivery
preferences.

Alert delivery is guarded by per-user baselines:
- linking Telegram marks all existing alerts as seen
- re-enabling an alert type marks old rows for that type as seen
- the delivery loop only returns events created after the effective baseline
"""

import json
import time
import secrets
import logging

import db
from _db_compat import _db

log = logging.getLogger("integration_db")

LINK_CODE_TTL = 600
GLOBAL_BASELINE_TYPE = ""


def _now() -> int:
    return int(time.time())


def init_integration_tables() -> None:
    with _db() as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS telegram_links (
                hf_uid    VARCHAR(64) NOT NULL,
                chat_id   BIGINT      NOT NULL,
                linked_at BIGINT      NOT NULL DEFAULT 0,
                PRIMARY KEY (hf_uid)
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS telegram_link_codes (
                code       VARCHAR(64) NOT NULL,
                hf_uid     VARCHAR(64) NOT NULL,
                created_at BIGINT      NOT NULL DEFAULT 0,
                PRIMARY KEY (code)
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS integration_accounts (
                hf_uid     VARCHAR(64) NOT NULL,
                mode       VARCHAR(32) NOT NULL DEFAULT 'toolbox_only',
                updated_at BIGINT      NOT NULL DEFAULT 0,
                PRIMARY KEY (hf_uid)
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS alert_events (
                id               INT          NOT NULL AUTO_INCREMENT,
                hf_uid           VARCHAR(64)  NOT NULL,
                type             VARCHAR(64)  NOT NULL,
                dedupe_key       VARCHAR(255) NOT NULL,
                title            VARCHAR(512) NOT NULL DEFAULT '',
                body             TEXT,
                link             TEXT,
                source           VARCHAR(32)  NOT NULL DEFAULT 'toolbox',
                payload          TEXT,
                mirror_dashboard TINYINT      NOT NULL DEFAULT 1,
                telegram_sent    TINYINT      NOT NULL DEFAULT 0,
                dashboard_sent   TINYINT      NOT NULL DEFAULT 0,
                created_at       BIGINT       NOT NULL DEFAULT 0,
                PRIMARY KEY (id)
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS alert_preferences (
                hf_uid     VARCHAR(64) NOT NULL,
                event_type VARCHAR(64) NOT NULL,
                enabled    TINYINT     NOT NULL DEFAULT 1,
                PRIMARY KEY (hf_uid, event_type)
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS alert_baselines (
                hf_uid      VARCHAR(64) NOT NULL,
                event_type  VARCHAR(64) NOT NULL DEFAULT '',
                baseline_at BIGINT      NOT NULL DEFAULT 0,
                PRIMARY KEY (hf_uid, event_type)
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
        """)

    for column, ddl in (
        ("telegram_status", "ALTER TABLE alert_events ADD COLUMN telegram_status VARCHAR(32) NOT NULL DEFAULT 'pending'"),
        ("telegram_delivered_at", "ALTER TABLE alert_events ADD COLUMN telegram_delivered_at BIGINT NOT NULL DEFAULT 0"),
        ("telegram_skipped_at", "ALTER TABLE alert_events ADD COLUMN telegram_skipped_at BIGINT NOT NULL DEFAULT 0"),
        ("telegram_error", "ALTER TABLE alert_events ADD COLUMN telegram_error TEXT"),
    ):
        try:
            with _db() as conn:
                conn.execute(ddl)
        except Exception:
            pass

    try:
        with _db() as conn:
            conn.execute(
                "CREATE UNIQUE INDEX uq_alert_event ON alert_events (hf_uid, type, dedupe_key)"
            )
    except Exception:
        pass

    try:
        with _db() as conn:
            conn.execute("CREATE UNIQUE INDEX uq_tg_chat ON telegram_links (chat_id)")
    except Exception:
        pass


def _decode_payload(row: dict) -> dict:
    if row.get("payload"):
        try:
            row["payload"] = json.loads(row["payload"])
        except Exception:
            row["payload"] = None
    return row


def create_alert_event(
    hf_uid: str,
    type_: str,
    dedupe_key: str,
    title: str = "",
    body: str = "",
    link: str = "",
    source: str = "toolbox",
    payload: dict | None = None,
    mirror_dashboard: bool = True,
    telegram_deliverable: bool = True,
) -> bool:
    payload_json = json.dumps(payload) if payload else None
    now = _now()
    inserted = False
    telegram_status = "pending" if telegram_deliverable else "skipped_imported"
    telegram_sent = 0 if telegram_deliverable else 1
    try:
        with _db() as conn:
            conn.execute(
                "INSERT OR IGNORE INTO alert_events "
                "(hf_uid, type, dedupe_key, title, body, link, source, payload, "
                "mirror_dashboard, telegram_sent, telegram_status, created_at) "
                "VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
                (
                    hf_uid,
                    type_,
                    dedupe_key,
                    title,
                    body,
                    link,
                    source,
                    payload_json,
                    int(mirror_dashboard),
                    telegram_sent,
                    telegram_status,
                    now,
                ),
            )
            inserted = conn.lastrowid is not None and conn.lastrowid > 0
    except Exception as e:
        log.debug("create_alert_event skipped uid=%s type=%s: %s", hf_uid, type_, e)
        return False

    if inserted and mirror_dashboard:
        try:
            db.add_notification(hf_uid, type_, title, body, link, dedupe_key)
        except Exception as e:
            log.warning("create_alert_event: dashboard mirror failed uid=%s: %s", hf_uid, e)

    return inserted


def get_pending_alert_events(hf_uid: str, limit: int = 50) -> list[dict]:
    with _db() as conn:
        rows = conn.execute(
            "SELECT id, hf_uid, type, dedupe_key, title, body, link, source, payload, created_at "
            "FROM alert_events "
            "WHERE hf_uid=? AND telegram_sent=0 "
            "ORDER BY created_at ASC LIMIT ?",
            (hf_uid, limit),
        ).fetchall()
    return [_decode_payload(dict(r)) for r in rows]


def mark_alert_event_delivered(event_id: int) -> None:
    now = _now()
    with _db() as conn:
        conn.execute(
            "UPDATE alert_events SET telegram_sent=1, telegram_status='sent', "
            "telegram_delivered_at=?, telegram_error='' WHERE id=?",
            (now, event_id),
        )


def mark_alert_event_skipped(event_id: int, reason: str) -> None:
    now = _now()
    with _db() as conn:
        conn.execute(
            "UPDATE alert_events SET telegram_sent=1, telegram_status=?, "
            "telegram_skipped_at=? WHERE id=?",
            (f"skipped_{reason}"[:32], now, event_id),
        )


def mark_alert_event_failed(event_id: int, error: str) -> None:
    with _db() as conn:
        conn.execute(
            "UPDATE alert_events SET telegram_status='failed', telegram_error=? WHERE id=?",
            (str(error)[:500], event_id),
        )


def set_alert_baseline(hf_uid: str, event_type: str = GLOBAL_BASELINE_TYPE,
                       baseline_at: int | None = None) -> int:
    baseline = int(baseline_at or _now())
    with _db() as conn:
        conn.execute(
            "INSERT INTO alert_baselines (hf_uid, event_type, baseline_at) VALUES (?,?,?) "
            "ON CONFLICT (hf_uid, event_type) DO UPDATE SET baseline_at=excluded.baseline_at",
            (hf_uid, event_type or GLOBAL_BASELINE_TYPE, baseline),
        )
    return baseline


def get_alert_baselines(hf_uid: str) -> dict[str, int]:
    with _db() as conn:
        rows = conn.execute(
            "SELECT event_type, baseline_at FROM alert_baselines WHERE hf_uid=?",
            (hf_uid,),
        ).fetchall()
    return {str(r["event_type"] or GLOBAL_BASELINE_TYPE): int(r["baseline_at"] or 0) for r in rows}


def get_effective_alert_baseline(hf_uid: str, event_type: str) -> int:
    baselines = get_alert_baselines(hf_uid)
    return max(
        int(baselines.get(GLOBAL_BASELINE_TYPE, 0) or 0),
        int(baselines.get(event_type, 0) or 0),
    )


def mark_existing_alerts_seen(hf_uid: str, event_type: str = GLOBAL_BASELINE_TYPE) -> dict:
    baseline = set_alert_baseline(hf_uid, event_type)
    if event_type:
        sql = (
            "UPDATE alert_events SET telegram_sent=1, telegram_status=?, telegram_skipped_at=? "
            "WHERE hf_uid=? AND telegram_sent=0 AND type=? AND created_at < ?"
        )
        params = ("skipped_seen_baseline", baseline, hf_uid, event_type, baseline)
    else:
        sql = (
            "UPDATE alert_events SET telegram_sent=1, telegram_status=?, telegram_skipped_at=? "
            "WHERE hf_uid=? AND telegram_sent=0 AND created_at < ?"
        )
        params = ("skipped_seen_baseline", baseline, hf_uid, baseline)
    with _db() as conn:
        cur = conn.execute(sql, params)
        skipped = int(getattr(cur, "rowcount", 0) or 0)
    return {"baseline_at": baseline, "skipped": skipped}


def get_all_undelivered_events(limit: int = 100) -> list[dict]:
    with _db() as conn:
        rows = conn.execute(
            "SELECT ae.id, ae.hf_uid, ae.type, ae.dedupe_key, ae.title, ae.body, "
            "       ae.link, ae.source, ae.payload, ae.created_at, tl.chat_id "
            "FROM alert_events ae "
            "INNER JOIN telegram_links tl ON tl.hf_uid = ae.hf_uid "
            "WHERE ae.telegram_sent = 0 "
            "ORDER BY ae.created_at ASC LIMIT ?",
            (limit,),
        ).fetchall()

    result = []
    for r in rows:
        d = dict(r)
        event_id = int(d["id"])
        hf_uid = str(d["hf_uid"])
        event_type = str(d["type"])
        if not is_alert_enabled(hf_uid, event_type):
            mark_alert_event_skipped(event_id, "disabled")
            continue
        baseline = get_effective_alert_baseline(hf_uid, event_type)
        if int(d.get("created_at") or 0) < baseline:
            mark_alert_event_skipped(event_id, "before_baseline")
            continue
        result.append(_decode_payload(d))
    return result


def mark_dashboard_sent(event_id: int) -> None:
    with _db() as conn:
        conn.execute("UPDATE alert_events SET dashboard_sent=1 WHERE id=?", (event_id,))


def get_pending_events_for_chat(chat_id: int, limit: int = 50) -> list[dict]:
    with _db() as conn:
        row = conn.execute(
            "SELECT hf_uid FROM telegram_links WHERE chat_id=?", (chat_id,)
        ).fetchone()
    if not row:
        return []
    return get_pending_alert_events(str(row["hf_uid"]), limit=limit)


def generate_link_code(hf_uid: str) -> str:
    code = secrets.token_urlsafe(16)
    now = _now()
    with _db() as conn:
        conn.execute("DELETE FROM telegram_link_codes WHERE hf_uid=?", (hf_uid,))
        conn.execute(
            "INSERT INTO telegram_link_codes (code, hf_uid, created_at) VALUES (?,?,?)",
            (code, hf_uid, now),
        )
    return code


def consume_link_code(code: str) -> str | None:
    now = _now()
    with _db() as conn:
        row = conn.execute(
            "SELECT hf_uid, created_at FROM telegram_link_codes WHERE code=?", (code,)
        ).fetchone()
        if not row:
            return None
        age = now - int(row["created_at"])
        conn.execute("DELETE FROM telegram_link_codes WHERE code=?", (code,))
        if age > LINK_CODE_TTL:
            return None
        return str(row["hf_uid"])


def link_telegram(hf_uid: str, chat_id: int) -> None:
    now = _now()
    with _db() as conn:
        conn.execute("DELETE FROM telegram_links WHERE chat_id=?", (chat_id,))
        conn.execute(
            "INSERT INTO telegram_links (hf_uid, chat_id, linked_at) VALUES (?,?,?) "
            "ON CONFLICT (hf_uid) DO UPDATE SET chat_id=excluded.chat_id, linked_at=excluded.linked_at",
            (hf_uid, chat_id, now),
        )
    mark_existing_alerts_seen(hf_uid)


def unlink_telegram(hf_uid: str) -> None:
    with _db() as conn:
        conn.execute("DELETE FROM telegram_links WHERE hf_uid=?", (hf_uid,))


def get_telegram_link(hf_uid: str) -> dict | None:
    with _db() as conn:
        row = conn.execute(
            "SELECT hf_uid, chat_id, linked_at FROM telegram_links WHERE hf_uid=?", (hf_uid,)
        ).fetchone()
    return dict(row) if row else None


def get_hf_uid_for_chat(chat_id: int) -> str | None:
    with _db() as conn:
        row = conn.execute(
            "SELECT hf_uid FROM telegram_links WHERE chat_id=?", (chat_id,)
        ).fetchone()
    return str(row["hf_uid"]) if row else None


def get_chat_id_for_uid(hf_uid: str) -> int | None:
    with _db() as conn:
        row = conn.execute(
            "SELECT chat_id FROM telegram_links WHERE hf_uid=?", (hf_uid,)
        ).fetchone()
    return int(row["chat_id"]) if row else None


def upsert_integration_account(hf_uid: str, mode: str = "toolbox_only") -> None:
    now = _now()
    with _db() as conn:
        conn.execute(
            "INSERT INTO integration_accounts (hf_uid, mode, updated_at) VALUES (?,?,?) "
            "ON CONFLICT (hf_uid) DO UPDATE SET updated_at=excluded.updated_at",
            (hf_uid, mode, now),
        )


def set_integration_mode(hf_uid: str, mode: str) -> None:
    now = _now()
    with _db() as conn:
        conn.execute(
            "INSERT INTO integration_accounts (hf_uid, mode, updated_at) VALUES (?,?,?) "
            "ON CONFLICT (hf_uid) DO UPDATE SET mode=excluded.mode, updated_at=excluded.updated_at",
            (hf_uid, mode, now),
        )


def get_integration_mode(hf_uid: str) -> str:
    with _db() as conn:
        row = conn.execute(
            "SELECT mode FROM integration_accounts WHERE hf_uid=?", (hf_uid,)
        ).fetchone()
    return str(row["mode"]) if row else "toolbox_only"


def get_alert_preferences(hf_uid: str) -> dict[str, bool]:
    with _db() as conn:
        rows = conn.execute(
            "SELECT event_type, enabled FROM alert_preferences WHERE hf_uid=?", (hf_uid,)
        ).fetchall()
    return {str(r["event_type"]): bool(r["enabled"]) for r in rows}


def set_alert_preference(hf_uid: str, event_type: str, enabled: bool) -> None:
    with _db() as conn:
        conn.execute(
            "INSERT INTO alert_preferences (hf_uid, event_type, enabled) VALUES (?,?,?) "
            "ON CONFLICT (hf_uid, event_type) DO UPDATE SET enabled=excluded.enabled",
            (hf_uid, event_type, int(enabled)),
        )
        if not enabled:
            conn.execute(
                "UPDATE alert_events SET telegram_sent=1, telegram_status='skipped_disabled', "
                "telegram_skipped_at=? WHERE hf_uid=? AND type=? AND telegram_sent=0",
                (_now(), hf_uid, event_type),
            )
    if enabled:
        mark_existing_alerts_seen(hf_uid, event_type)


def is_alert_enabled(hf_uid: str, event_type: str) -> bool:
    with _db() as conn:
        row = conn.execute(
            "SELECT enabled FROM alert_preferences WHERE hf_uid=? AND event_type=?",
            (hf_uid, event_type),
        ).fetchone()
    return bool(row["enabled"]) if row else True


def get_alert_delivery_status(hf_uid: str) -> dict:
    baseline = get_effective_alert_baseline(hf_uid, GLOBAL_BASELINE_TYPE)
    baselines = get_alert_baselines(hf_uid)
    with _db() as conn:
        pending = conn.execute(
            "SELECT COUNT(*) AS c FROM alert_events "
            "WHERE hf_uid=? AND telegram_sent=0 AND created_at >= ?",
            (hf_uid, baseline),
        ).fetchone()
        disabled = conn.execute(
            "SELECT COUNT(*) AS c FROM alert_preferences WHERE hf_uid=? AND enabled=0",
            (hf_uid,),
        ).fetchone()
        last_sent = conn.execute(
            "SELECT type, title, telegram_delivered_at FROM alert_events "
            "WHERE hf_uid=? AND telegram_status='sent' "
            "ORDER BY telegram_delivered_at DESC LIMIT 1",
            (hf_uid,),
        ).fetchone()
        last_failed = conn.execute(
            "SELECT type, title, telegram_error, created_at FROM alert_events "
            "WHERE hf_uid=? AND telegram_status='failed' "
            "ORDER BY created_at DESC LIMIT 1",
            (hf_uid,),
        ).fetchone()
    return {
        "baseline_at": baseline,
        "baselines": baselines,
        "pending_after_baseline": int((pending or {}).get("c", 0) if isinstance(pending, dict) else (pending[0] if pending else 0)),
        "disabled_count": int((disabled or {}).get("c", 0) if isinstance(disabled, dict) else (disabled[0] if disabled else 0)),
        "last_sent": dict(last_sent) if last_sent else None,
        "last_failed": dict(last_failed) if last_failed else None,
    }
