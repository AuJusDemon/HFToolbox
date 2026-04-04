"""
modules/posting/posting_db.py — Persistence for thread posting, reply queue, recents.

Tables:
  scheduled_threads — threads queued to post (immediate + scheduled)
  my_threads        — threads created through the tool (tracked for reply queue)
  reply_queue       — unread replies to my threads
  posting_recents   — recently used forums per user (max 5)
"""

import sqlite3
import time
import os
from pathlib import Path

DB_PATH = Path(os.getenv("DB_PATH", "data/hf_dash.db"))


def _conn() -> sqlite3.Connection:
    conn = sqlite3.connect(str(DB_PATH), check_same_thread=False, timeout=10)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA busy_timeout=10000")
    return conn


def init_posting_db() -> None:
    with _conn() as conn:
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS scheduled_threads (
                id              INTEGER PRIMARY KEY AUTOINCREMENT,
                uid             TEXT NOT NULL,
                fid             TEXT NOT NULL,
                forum_name      TEXT NOT NULL,
                subject         TEXT NOT NULL,
                message         TEXT NOT NULL,
                fire_at         INTEGER NOT NULL,
                status          TEXT NOT NULL DEFAULT 'pending',
                sent_at         INTEGER,
                tid             TEXT,
                error           TEXT,
                auto_bump       INTEGER NOT NULL DEFAULT 0,
                bump_interval_h INTEGER NOT NULL DEFAULT 12,
                created_at      INTEGER NOT NULL DEFAULT (strftime('%s','now'))
            );

            CREATE TABLE IF NOT EXISTS my_threads (
                uid          TEXT NOT NULL,
                tid          TEXT NOT NULL,
                fid          TEXT NOT NULL,
                title        TEXT NOT NULL,
                created_at   INTEGER NOT NULL,
                last_pid     TEXT,
                last_checked INTEGER,
                PRIMARY KEY (uid, tid)
            );

            CREATE TABLE IF NOT EXISTS reply_queue (
                id               INTEGER PRIMARY KEY AUTOINCREMENT,
                uid              TEXT NOT NULL,
                tid              TEXT NOT NULL,
                pid              TEXT NOT NULL,
                thread_title     TEXT,
                from_uid         TEXT,
                from_username    TEXT,
                dateline         INTEGER,
                message_preview  TEXT,
                full_message     TEXT,
                status           TEXT NOT NULL DEFAULT 'unread',
                created_at       INTEGER NOT NULL DEFAULT (strftime('%s','now')),
                UNIQUE(uid, pid)
            );

            CREATE TABLE IF NOT EXISTS posting_recents (
                uid           TEXT NOT NULL,
                fid           TEXT NOT NULL,
                forum_name    TEXT NOT NULL,
                category_name TEXT,
                last_used     INTEGER NOT NULL,
                PRIMARY KEY (uid, fid)
            );
        """)
        # Migration-safe: create drafts table separately so it works on existing DBs
        conn.execute("""
            CREATE TABLE IF NOT EXISTS thread_drafts (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                uid         TEXT NOT NULL,
                fid         TEXT NOT NULL,
                forum_name  TEXT NOT NULL,
                subject     TEXT NOT NULL,
                message     TEXT NOT NULL,
                created_at  INTEGER NOT NULL DEFAULT (strftime('%s','now')),
                updated_at  INTEGER NOT NULL DEFAULT (strftime('%s','now'))
            )
        """)


# ── Scheduled threads ──────────────────────────────────────────────────────────

def create_scheduled_thread(uid: str, fid: str, forum_name: str,
                             subject: str, message: str, fire_at: int,
                             auto_bump: bool = False, bump_interval_h: int = 12) -> int:
    """Insert a scheduled (or immediate) thread. Returns the new row id."""
    with _conn() as conn:
        cur = conn.execute(
            """INSERT INTO scheduled_threads
               (uid, fid, forum_name, subject, message, fire_at, auto_bump, bump_interval_h)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            (uid, fid, forum_name, subject, message, fire_at, int(auto_bump), bump_interval_h)
        )
        return cur.lastrowid


def get_due_threads() -> list[dict]:
    """Return all pending threads whose fire_at <= now."""
    now = int(time.time())
    with _conn() as conn:
        rows = conn.execute(
            "SELECT * FROM scheduled_threads WHERE status='pending' AND fire_at <= ? ORDER BY fire_at ASC",
            (now,)
        ).fetchall()
        return [dict(r) for r in rows]


def get_scheduled_threads(uid: str) -> list[dict]:
    """All non-sent, non-cancelled threads for a user (their queue)."""
    with _conn() as conn:
        rows = conn.execute(
            "SELECT * FROM scheduled_threads WHERE uid=? AND status IN ('pending','failed') ORDER BY fire_at ASC",
            (uid,)
        ).fetchall()
        return [dict(r) for r in rows]


def get_sent_threads(uid: str, limit: int = 30) -> list[dict]:
    """Recently sent threads for a user."""
    with _conn() as conn:
        rows = conn.execute(
            "SELECT * FROM scheduled_threads WHERE uid=? AND status='sent' ORDER BY sent_at DESC LIMIT ?",
            (uid, limit)
        ).fetchall()
        return [dict(r) for r in rows]


def mark_thread_sending(row_id: int) -> None:
    """Mark as 'sending' before API call to prevent double-fire."""
    with _conn() as conn:
        conn.execute("UPDATE scheduled_threads SET status='sending' WHERE id=? AND status='pending'", (row_id,))


def mark_thread_sent(row_id: int, tid: str) -> None:
    with _conn() as conn:
        conn.execute(
            "UPDATE scheduled_threads SET status='sent', sent_at=?, tid=? WHERE id=?",
            (int(time.time()), tid, row_id)
        )


def mark_thread_failed(row_id: int, error: str) -> None:
    with _conn() as conn:
        conn.execute(
            "UPDATE scheduled_threads SET status='failed', error=? WHERE id=?",
            (error[:500], row_id)
        )


def cancel_scheduled_thread(row_id: int, uid: str) -> bool:
    """Cancel a pending thread. Returns True if cancelled, False if not found/not pending."""
    with _conn() as conn:
        cur = conn.execute(
            "UPDATE scheduled_threads SET status='cancelled' WHERE id=? AND uid=? AND status='pending'",
            (row_id, uid)
        )
        return cur.rowcount > 0


# ── My threads ─────────────────────────────────────────────────────────────────

def add_my_thread(uid: str, tid: str, fid: str, title: str) -> None:
    with _conn() as conn:
        conn.execute(
            """INSERT INTO my_threads (uid, tid, fid, title, created_at)
               VALUES (?, ?, ?, ?, ?)
               ON CONFLICT(uid, tid) DO NOTHING""",
            (uid, tid, fid, title, int(time.time()))
        )


def get_my_threads(uid: str) -> list[dict]:
    with _conn() as conn:
        rows = conn.execute(
            "SELECT * FROM my_threads WHERE uid=? ORDER BY created_at DESC",
            (uid,)
        ).fetchall()
        return [dict(r) for r in rows]



def save_draft(uid: str, fid: str, forum_name: str, subject: str, message: str) -> int:
    import time as _t
    with _conn() as conn:
        cur = conn.execute(
            "INSERT INTO thread_drafts (uid,fid,forum_name,subject,message,created_at,updated_at) VALUES (?,?,?,?,?,?,?)",
            (uid, fid, forum_name, subject, message, int(_t.time()), int(_t.time()))
        )
        return cur.lastrowid


def update_draft(draft_id: int, uid: str, fid: str, forum_name: str, subject: str, message: str) -> bool:
    import time as _t
    with _conn() as conn:
        cur = conn.execute(
            "UPDATE thread_drafts SET fid=?,forum_name=?,subject=?,message=?,updated_at=? WHERE id=? AND uid=?",
            (fid, forum_name, subject, message, int(_t.time()), draft_id, uid)
        )
        return cur.rowcount > 0


def get_drafts(uid: str) -> list:
    with _conn() as conn:
        rows = conn.execute(
            "SELECT * FROM thread_drafts WHERE uid=? ORDER BY updated_at DESC", (uid,)
        ).fetchall()
        return [dict(r) for r in rows]


def delete_draft(draft_id: int, uid: str) -> bool:
    with _conn() as conn:
        cur = conn.execute("DELETE FROM thread_drafts WHERE id=? AND uid=?", (draft_id, uid))
        return cur.rowcount > 0


def cancel_to_draft(row_id: int, uid: str) -> dict | None:
    """Cancel a scheduled thread and return its data for saving as draft."""
    with _conn() as conn:
        row = conn.execute(
            "SELECT * FROM scheduled_threads WHERE id=? AND uid=? AND status='pending'", (row_id, uid)
        ).fetchone()
        if not row:
            return None
        conn.execute(
            "UPDATE scheduled_threads SET status='cancelled' WHERE id=?", (row_id,)
        )
        return dict(row)


def update_fire_at(row_id: int, uid: str, fire_at: int) -> bool:
    """Update the fire_at timestamp for a pending scheduled thread."""
    with _conn() as conn:
        cur = conn.execute(
            "UPDATE scheduled_threads SET fire_at=? WHERE id=? AND uid=? AND status='pending'",
            (fire_at, row_id, uid)
        )
        return cur.rowcount > 0


def get_all_tracked_threads() -> list[dict]:
    """All my_threads across all users — used by reply queue poller."""
    with _conn() as conn:
        rows = conn.execute("SELECT * FROM my_threads ORDER BY uid, tid").fetchall()
        return [dict(r) for r in rows]


def update_thread_last_checked(uid: str, tid: str, last_pid: str, last_checked: int) -> None:
    with _conn() as conn:
        conn.execute(
            "UPDATE my_threads SET last_pid=?, last_checked=? WHERE uid=? AND tid=?",
            (last_pid, last_checked, uid, tid)
        )


# ── Reply queue ────────────────────────────────────────────────────────────────

def upsert_reply(uid: str, tid: str, pid: str, thread_title: str,
                 from_uid: str, from_username: str, dateline: int,
                 message_preview: str, full_message: str) -> None:
    """Insert new reply into queue. Ignores if pid already exists."""
    with _conn() as conn:
        conn.execute(
            """INSERT OR IGNORE INTO reply_queue
               (uid, tid, pid, thread_title, from_uid, from_username, dateline,
                message_preview, full_message)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (uid, tid, pid, thread_title, from_uid, from_username, dateline,
             message_preview[:200], full_message)
        )


def auto_dismiss_by_pid(uid: str, quoted_pid: str) -> None:
    """Mark a queued reply as dismissed when user quotes it in their reply."""
    with _conn() as conn:
        conn.execute(
            "UPDATE reply_queue SET status='dismissed' WHERE uid=? AND pid=? AND status='unread'",
            (uid, quoted_pid)
        )


def auto_dismiss_by_thread_before(uid: str, tid: str, before_dateline: int) -> int:
    """Dismiss all unread replies in a thread posted before our reply dateline.
    Catches replies-without-quoting from both dashboard and HF website replies.
    Returns count of dismissed rows.
    """
    with _conn() as conn:
        cur = conn.execute(
            """UPDATE reply_queue SET status='dismissed'
               WHERE uid=? AND tid=? AND status='unread' AND dateline <= ?""",
            (uid, tid, before_dateline)
        )
        return cur.rowcount


def dismiss_reply(reply_id: int, uid: str) -> bool:
    with _conn() as conn:
        cur = conn.execute(
            "UPDATE reply_queue SET status='dismissed' WHERE id=? AND uid=?",
            (reply_id, uid)
        )
        return cur.rowcount > 0


def get_reply_queue(uid: str, status: str = 'unread') -> list[dict]:
    with _conn() as conn:
        rows = conn.execute(
            """SELECT * FROM reply_queue WHERE uid=? AND status=?
               ORDER BY dateline DESC""",
            (uid, status)
        ).fetchall()
        return [dict(r) for r in rows]


def get_unread_count(uid: str) -> int:
    with _conn() as conn:
        return conn.execute(
            "SELECT COUNT(*) FROM reply_queue WHERE uid=? AND status='unread'", (uid,)
        ).fetchone()[0]


# ── Posting recents ────────────────────────────────────────────────────────────

def touch_recent(uid: str, fid: str, forum_name: str, category_name: str) -> None:
    """Upsert a forum into recents. Prunes to 5 most recent."""
    now = int(time.time())
    with _conn() as conn:
        conn.execute(
            """INSERT INTO posting_recents (uid, fid, forum_name, category_name, last_used)
               VALUES (?, ?, ?, ?, ?)
               ON CONFLICT(uid, fid) DO UPDATE SET
                 forum_name=excluded.forum_name,
                 category_name=excluded.category_name,
                 last_used=excluded.last_used""",
            (uid, fid, forum_name, category_name, now)
        )
        # Keep only 5 most recent per user
        conn.execute(
            """DELETE FROM posting_recents WHERE uid=? AND fid NOT IN (
               SELECT fid FROM posting_recents WHERE uid=? ORDER BY last_used DESC LIMIT 5
            )""",
            (uid, uid)
        )


def get_recents(uid: str) -> list[dict]:
    with _conn() as conn:
        rows = conn.execute(
            "SELECT * FROM posting_recents WHERE uid=? ORDER BY last_used DESC LIMIT 5",
            (uid,)
        ).fetchall()
        return [dict(r) for r in rows]
