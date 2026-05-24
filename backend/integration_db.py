"""
integration_db.py — Toolbox ↔ HF Radar shared integration layer.

Tables (all in Toolbox DB):
  telegram_links      — hf_uid → chat_id mapping
  telegram_link_codes — short-lived link codes generated from dashboard
  integration_accounts — per-user mode (toolbox_only / toolbox_linked_relay / both_linked)
  alert_events        — shared event queue; UNIQUE(hf_uid, type, dedupe_key) prevents doubles
  alert_preferences   — per-user per-type enable/disable

Call init_integration_tables() once at startup (idempotent).
"""

import json
import time
import secrets
import logging

import db
from _db_compat import _db

log = logging.getLogger("integration_db")

LINK_CODE_TTL = 600  # 10 minutes


# ── Schema ────────────────────────────────────────────────────────────────────

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

    # Unique index on alert_events — the dedupe mechanism
    try:
        with _db() as conn:
            conn.execute(
                "CREATE UNIQUE INDEX uq_alert_event ON alert_events (hf_uid, type, dedupe_key)"
            )
    except Exception:
        pass  # already exists

    # Unique index so one chat_id can't link to two HF accounts
    try:
        with _db() as conn:
            conn.execute(
                "CREATE UNIQUE INDEX uq_tg_chat ON telegram_links (chat_id)"
            )
    except Exception:
        pass


# ── Alert events ──────────────────────────────────────────────────────────────

def create_alert_event(
    hf_uid: str,
    type_: str,
    dedupe_key: str,
    title: str = '',
    body: str = '',
    link: str = '',
    source: str = 'toolbox',
    payload: dict | None = None,
    mirror_dashboard: bool = True,
) -> bool:
    """
    Insert a new alert event. Returns True if inserted, False if duplicate.
    If mirror_dashboard=True and inserted, also writes to the dashboard notifications table.
    """
    payload_json = json.dumps(payload) if payload else None
    now = int(time.time())
    inserted = False
    try:
        with _db() as conn:
            conn.execute(
                "INSERT OR IGNORE INTO alert_events "
                "(hf_uid, type, dedupe_key, title, body, link, source, payload, mirror_dashboard, created_at) "
                "VALUES (?,?,?,?,?,?,?,?,?,?)",
                (hf_uid, type_, dedupe_key, title, body, link, source, payload_json,
                 int(mirror_dashboard), now)
            )
            inserted = conn.lastrowid is not None and conn.lastrowid > 0
    except Exception as e:
        log.debug("create_alert_event duplicate or error uid=%s type=%s: %s", hf_uid, type_, e)
        return False

    if inserted and mirror_dashboard:
        try:
            db.add_notification(hf_uid, type_, title, body, link, dedupe_key)
        except Exception as e:
            log.warning("create_alert_event: mirror_dashboard failed uid=%s: %s", hf_uid, e)

    return inserted


def get_pending_alert_events(hf_uid: str, limit: int = 50) -> list[dict]:
    """Return unsent alert events for a given HF uid, ordered oldest-first."""
    with _db() as conn:
        rows = conn.execute(
            "SELECT id, hf_uid, type, dedupe_key, title, body, link, source, payload, created_at "
            "FROM alert_events "
            "WHERE hf_uid=? AND telegram_sent=0 "
            "ORDER BY created_at ASC LIMIT ?",
            (hf_uid, limit)
        ).fetchall()
    result = []
    for r in rows:
        d = dict(r)
        if d.get("payload"):
            try:
                d["payload"] = json.loads(d["payload"])
            except Exception:
                d["payload"] = None
        result.append(d)
    return result


def mark_alert_event_delivered(event_id: int) -> None:
    with _db() as conn:
        conn.execute(
            "UPDATE alert_events SET telegram_sent=1 WHERE id=?", (event_id,)
        )


def mark_dashboard_sent(event_id: int) -> None:
    with _db() as conn:
        conn.execute(
            "UPDATE alert_events SET dashboard_sent=1 WHERE id=?", (event_id,)
        )


def get_pending_events_for_chat(chat_id: int, limit: int = 50) -> list[dict]:
    """Look up hf_uid from chat_id, then return pending events. Used by Radar's bridge."""
    with _db() as conn:
        row = conn.execute(
            "SELECT hf_uid FROM telegram_links WHERE chat_id=?", (chat_id,)
        ).fetchone()
    if not row:
        return []
    return get_pending_alert_events(str(row["hf_uid"]), limit=limit)


# ── Telegram link codes ───────────────────────────────────────────────────────

def generate_link_code(hf_uid: str) -> str:
    """Generate a short-lived link code for this user. Replaces any existing code."""
    code = secrets.token_urlsafe(16)
    now = int(time.time())
    with _db() as conn:
        conn.execute(
            "DELETE FROM telegram_link_codes WHERE hf_uid=?", (hf_uid,)
        )
        conn.execute(
            "INSERT INTO telegram_link_codes (code, hf_uid, created_at) VALUES (?,?,?)",
            (code, hf_uid, now)
        )
    return code


def consume_link_code(code: str) -> str | None:
    """Validate and consume a link code. Returns hf_uid if valid, None if expired/missing."""
    now = int(time.time())
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


# ── Telegram links ────────────────────────────────────────────────────────────

def link_telegram(hf_uid: str, chat_id: int) -> None:
    """Associate a Telegram chat_id with an HF uid. Replaces any prior link for this uid."""
    now = int(time.time())
    with _db() as conn:
        # Remove any existing link for this chat_id (another HF account)
        conn.execute("DELETE FROM telegram_links WHERE chat_id=?", (chat_id,))
        conn.execute(
            "INSERT INTO telegram_links (hf_uid, chat_id, linked_at) VALUES (?,?,?) "
            "ON CONFLICT (hf_uid) DO UPDATE SET chat_id=excluded.chat_id, linked_at=excluded.linked_at",
            (hf_uid, chat_id, now)
        )


def unlink_telegram(hf_uid: str) -> None:
    with _db() as conn:
        conn.execute("DELETE FROM telegram_links WHERE hf_uid=?", (hf_uid,))


def get_telegram_link(hf_uid: str) -> dict | None:
    """Returns {hf_uid, chat_id, linked_at} or None."""
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


# ── Integration mode ──────────────────────────────────────────────────────────

def upsert_integration_account(hf_uid: str, mode: str = 'toolbox_only') -> None:
    now = int(time.time())
    with _db() as conn:
        conn.execute(
            "INSERT INTO integration_accounts (hf_uid, mode, updated_at) VALUES (?,?,?) "
            "ON CONFLICT (hf_uid) DO UPDATE SET updated_at=excluded.updated_at",
            (hf_uid, mode, now)
        )


def set_integration_mode(hf_uid: str, mode: str) -> None:
    now = int(time.time())
    with _db() as conn:
        conn.execute(
            "INSERT INTO integration_accounts (hf_uid, mode, updated_at) VALUES (?,?,?) "
            "ON CONFLICT (hf_uid) DO UPDATE SET mode=excluded.mode, updated_at=excluded.updated_at",
            (hf_uid, mode, now)
        )


def get_integration_mode(hf_uid: str) -> str:
    """Returns the mode string, defaulting to 'toolbox_only' if no record."""
    with _db() as conn:
        row = conn.execute(
            "SELECT mode FROM integration_accounts WHERE hf_uid=?", (hf_uid,)
        ).fetchone()
    return str(row["mode"]) if row else "toolbox_only"


# ── Alert preferences ─────────────────────────────────────────────────────────

def get_alert_preferences(hf_uid: str) -> dict[str, bool]:
    """Returns {event_type: enabled} dict. Types not in table default to True."""
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
            (hf_uid, event_type, int(enabled))
        )


def is_alert_enabled(hf_uid: str, event_type: str) -> bool:
    """Returns True unless explicitly disabled. Defaults to True for unknown types."""
    with _db() as conn:
        row = conn.execute(
            "SELECT enabled FROM alert_preferences WHERE hf_uid=? AND event_type=?",
            (hf_uid, event_type)
        ).fetchone()
    return bool(row["enabled"]) if row else True
