"""
modules/posting/posting_db.py — Persistence for thread posting, drafts, reply queue.

Tables:
  scheduled_threads   — threads queued to post
  my_threads          — threads tracked for reply queue
  reply_queue         — unread replies
  posting_recents     — recently used forums (max 5)
  thread_drafts       — collaborative drafts with versioning
  draft_collaborators — who can edit each draft
  draft_edit_log      — full edit history
  draft_presence      — who has a draft open right now
"""

import sqlite3
import time
from pathlib import Path
from contextlib import contextmanager

DB_PATH = Path("data/hf_dash.db")


def _conn() -> sqlite3.Connection:
    conn = sqlite3.connect(str(DB_PATH), check_same_thread=False, timeout=10)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA busy_timeout=10000")
    return conn


@contextmanager
def _ctx():
    conn = _conn()
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


def init_posting_db() -> None:
    with _ctx() as conn:
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS scheduled_threads (
                id              INTEGER PRIMARY KEY AUTOINCREMENT,
                uid             TEXT    NOT NULL,
                fid             TEXT    NOT NULL,
                forum_name      TEXT    NOT NULL,
                subject         TEXT    NOT NULL,
                message         TEXT    NOT NULL,
                fire_at         INTEGER NOT NULL,
                status          TEXT    NOT NULL DEFAULT 'pending',
                sent_at         INTEGER,
                tid             TEXT,
                error           TEXT,
                auto_bump       INTEGER NOT NULL DEFAULT 0,
                bump_interval_h INTEGER NOT NULL DEFAULT 12,
                created_at      INTEGER NOT NULL DEFAULT (strftime('%s','now'))
            );

            CREATE TABLE IF NOT EXISTS my_threads (
                uid          TEXT    NOT NULL,
                tid          TEXT    NOT NULL,
                fid          TEXT    NOT NULL,
                title        TEXT    NOT NULL,
                created_at   INTEGER NOT NULL,
                last_pid     TEXT,
                last_checked INTEGER,
                PRIMARY KEY (uid, tid)
            );

            CREATE TABLE IF NOT EXISTS reply_queue (
                id              INTEGER PRIMARY KEY AUTOINCREMENT,
                uid             TEXT    NOT NULL,
                tid             TEXT    NOT NULL,
                pid             TEXT    NOT NULL,
                thread_title    TEXT,
                from_uid        TEXT,
                from_username   TEXT,
                dateline        INTEGER,
                message_preview TEXT,
                full_message    TEXT,
                status          TEXT    NOT NULL DEFAULT 'unread',
                created_at      INTEGER NOT NULL DEFAULT (strftime('%s','now')),
                UNIQUE(uid, pid)
            );

            CREATE TABLE IF NOT EXISTS posting_recents (
                uid           TEXT    NOT NULL,
                fid           TEXT    NOT NULL,
                forum_name    TEXT    NOT NULL,
                category_name TEXT,
                last_used     INTEGER NOT NULL,
                PRIMARY KEY (uid, fid)
            );

            CREATE TABLE IF NOT EXISTS thread_drafts (
                id               INTEGER PRIMARY KEY AUTOINCREMENT,
                uid              TEXT    NOT NULL,
                fid              TEXT    NOT NULL,
                forum_name       TEXT    NOT NULL,
                subject          TEXT    NOT NULL,
                message          TEXT    NOT NULL,
                version          INTEGER NOT NULL DEFAULT 1,
                last_editor_uid  TEXT,
                last_editor_name TEXT,
                created_at       INTEGER NOT NULL DEFAULT (strftime('%s','now')),
                updated_at       INTEGER NOT NULL DEFAULT (strftime('%s','now'))
            );

            CREATE TABLE IF NOT EXISTS draft_collaborators (
                draft_id   INTEGER NOT NULL,
                uid        TEXT    NOT NULL,
                username   TEXT,
                added_at   INTEGER NOT NULL DEFAULT (strftime('%s','now')),
                PRIMARY KEY (draft_id, uid)
            );

            CREATE TABLE IF NOT EXISTS draft_edit_log (
                id           INTEGER PRIMARY KEY AUTOINCREMENT,
                draft_id     INTEGER NOT NULL,
                editor_uid   TEXT    NOT NULL,
                editor_name  TEXT,
                old_subject  TEXT,
                new_subject  TEXT,
                old_message  TEXT,
                new_message  TEXT,
                version      INTEGER NOT NULL DEFAULT 1,
                edited_at    INTEGER NOT NULL DEFAULT (strftime('%s','now')),
                is_rollback  INTEGER NOT NULL DEFAULT 0
            );

            CREATE TABLE IF NOT EXISTS draft_presence (
                draft_id  INTEGER NOT NULL,
                uid       TEXT    NOT NULL,
                username  TEXT,
                last_seen INTEGER NOT NULL DEFAULT (strftime('%s','now')),
                PRIMARY KEY (draft_id, uid)
            );
        """)
        # Migrate existing DBs that predate collab columns
        existing = {r[1] for r in conn.execute("PRAGMA table_info(thread_drafts)").fetchall()}
        for col, defn in [
            ("version",          "INTEGER NOT NULL DEFAULT 1"),
            ("last_editor_uid",  "TEXT"),
            ("last_editor_name", "TEXT"),
        ]:
            if col not in existing:
                try:
                    conn.execute(f"ALTER TABLE thread_drafts ADD COLUMN {col} {defn}")
                except Exception:
                    pass


# ── Scheduled threads ──────────────────────────────────────────────────────────

def create_scheduled_thread(uid: str, fid: str, forum_name: str,
                             subject: str, message: str, fire_at: int,
                             auto_bump: bool = False, bump_interval_h: int = 12) -> int:
    with _conn() as conn:
        cur = conn.execute(
            """INSERT INTO scheduled_threads
               (uid, fid, forum_name, subject, message, fire_at, auto_bump, bump_interval_h)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            (uid, fid, forum_name, subject, message, fire_at, int(auto_bump), bump_interval_h)
        )
        conn.commit()
        return cur.lastrowid


def get_due_threads() -> list[dict]:
    now = int(time.time())
    with _conn() as conn:
        rows = conn.execute(
            "SELECT * FROM scheduled_threads WHERE status='pending' AND fire_at <= ? ORDER BY fire_at ASC",
            (now,)
        ).fetchall()
        return [dict(r) for r in rows]


def get_scheduled_threads(uid: str) -> list[dict]:
    with _conn() as conn:
        rows = conn.execute(
            "SELECT * FROM scheduled_threads WHERE uid=? AND status IN ('pending','failed') ORDER BY fire_at ASC",
            (uid,)
        ).fetchall()
        return [dict(r) for r in rows]


def get_sent_threads(uid: str, limit: int = 30) -> list[dict]:
    with _conn() as conn:
        rows = conn.execute(
            "SELECT * FROM scheduled_threads WHERE uid=? AND status='sent' ORDER BY sent_at DESC LIMIT ?",
            (uid, limit)
        ).fetchall()
        return [dict(r) for r in rows]


def mark_thread_sending(row_id: int) -> None:
    with _conn() as conn:
        conn.execute("UPDATE scheduled_threads SET status='sending' WHERE id=? AND status='pending'", (row_id,))
        conn.commit()


def mark_thread_sent(row_id: int, tid: str) -> None:
    with _conn() as conn:
        conn.execute(
            "UPDATE scheduled_threads SET status='sent', sent_at=?, tid=? WHERE id=?",
            (int(time.time()), tid, row_id)
        )
        conn.commit()


def mark_thread_failed(row_id: int, error: str) -> None:
    with _conn() as conn:
        conn.execute(
            "UPDATE scheduled_threads SET status='failed', error=? WHERE id=?",
            (error[:500], row_id)
        )
        conn.commit()


def cancel_scheduled_thread(row_id: int, uid: str) -> bool:
    with _conn() as conn:
        cur = conn.execute(
            "UPDATE scheduled_threads SET status='cancelled' WHERE id=? AND uid=? AND status='pending'",
            (row_id, uid)
        )
        conn.commit()
        return cur.rowcount > 0


def update_fire_at(row_id: int, uid: str, fire_at: int) -> bool:
    with _conn() as conn:
        cur = conn.execute(
            "UPDATE scheduled_threads SET fire_at=? WHERE id=? AND uid=? AND status='pending'",
            (fire_at, row_id, uid)
        )
        conn.commit()
        return cur.rowcount > 0


def cancel_to_draft(row_id: int, uid: str) -> dict | None:
    with _conn() as conn:
        row = conn.execute(
            "SELECT * FROM scheduled_threads WHERE id=? AND uid=? AND status='pending'", (row_id, uid)
        ).fetchone()
        if not row:
            return None
        conn.execute("UPDATE scheduled_threads SET status='cancelled' WHERE id=?", (row_id,))
        conn.commit()
        return dict(row)


# ── My threads ─────────────────────────────────────────────────────────────────

def add_my_thread(uid: str, tid: str, fid: str, title: str) -> None:
    with _conn() as conn:
        conn.execute(
            """INSERT INTO my_threads (uid, tid, fid, title, created_at)
               VALUES (?, ?, ?, ?, ?)
               ON CONFLICT(uid, tid) DO NOTHING""",
            (uid, tid, fid, title, int(time.time()))
        )
        conn.commit()


def get_my_threads(uid: str) -> list[dict]:
    with _conn() as conn:
        rows = conn.execute(
            "SELECT * FROM my_threads WHERE uid=? ORDER BY created_at DESC", (uid,)
        ).fetchall()
        return [dict(r) for r in rows]


def get_all_tracked_threads() -> list[dict]:
    with _conn() as conn:
        rows = conn.execute("SELECT * FROM my_threads ORDER BY uid, tid").fetchall()
        return [dict(r) for r in rows]


def update_thread_last_checked(uid: str, tid: str, last_pid: str, last_checked: int) -> None:
    with _conn() as conn:
        conn.execute(
            "UPDATE my_threads SET last_pid=?, last_checked=? WHERE uid=? AND tid=?",
            (last_pid, last_checked, uid, tid)
        )
        conn.commit()


# ── Reply queue ────────────────────────────────────────────────────────────────

def upsert_reply(uid: str, tid: str, pid: str, thread_title: str,
                 from_uid: str, from_username: str, dateline: int,
                 message_preview: str, full_message: str) -> None:
    with _conn() as conn:
        conn.execute(
            """INSERT OR IGNORE INTO reply_queue
               (uid, tid, pid, thread_title, from_uid, from_username, dateline,
                message_preview, full_message)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (uid, tid, pid, thread_title, from_uid, from_username, dateline,
             message_preview[:200], full_message)
        )
        conn.commit()


def auto_dismiss_by_pid(uid: str, quoted_pid: str) -> None:
    with _conn() as conn:
        conn.execute(
            "UPDATE reply_queue SET status='dismissed' WHERE uid=? AND pid=? AND status='unread'",
            (uid, quoted_pid)
        )
        conn.commit()


def auto_dismiss_by_thread_before(uid: str, tid: str, before_dateline: int) -> int:
    with _conn() as conn:
        cur = conn.execute(
            """UPDATE reply_queue SET status='dismissed'
               WHERE uid=? AND tid=? AND status='unread' AND dateline <= ?""",
            (uid, tid, before_dateline)
        )
        conn.commit()
        return cur.rowcount


def dismiss_reply(reply_id: int, uid: str) -> bool:
    with _conn() as conn:
        cur = conn.execute(
            "UPDATE reply_queue SET status='dismissed' WHERE id=? AND uid=?",
            (reply_id, uid)
        )
        conn.commit()
        return cur.rowcount > 0


def get_reply_queue(uid: str, status: str = "unread") -> list[dict]:
    with _conn() as conn:
        rows = conn.execute(
            "SELECT * FROM reply_queue WHERE uid=? AND status=? ORDER BY dateline DESC",
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
        conn.execute(
            """DELETE FROM posting_recents WHERE uid=? AND fid NOT IN (
               SELECT fid FROM posting_recents WHERE uid=? ORDER BY last_used DESC LIMIT 5
            )""",
            (uid, uid)
        )
        conn.commit()


def get_recents(uid: str) -> list[dict]:
    with _conn() as conn:
        rows = conn.execute(
            "SELECT * FROM posting_recents WHERE uid=? ORDER BY last_used DESC LIMIT 5",
            (uid,)
        ).fetchall()
        return [dict(r) for r in rows]


# ── Simple draft helpers ───────────────────────────────────────────────────────

def save_draft(uid: str, fid: str, forum_name: str, subject: str, message: str) -> int:
    now = int(time.time())
    with _conn() as conn:
        cur = conn.execute(
            """INSERT INTO thread_drafts (uid,fid,forum_name,subject,message,version,created_at,updated_at)
               VALUES (?,?,?,?,?,1,?,?)""",
            (uid, fid, forum_name, subject, message, now, now)
        )
        conn.commit()
        return cur.lastrowid


def delete_draft(draft_id: int, uid: str) -> bool:
    """Delete a draft. Only the owner can delete."""
    with _conn() as conn:
        row = conn.execute("SELECT uid FROM thread_drafts WHERE id=?", (draft_id,)).fetchone()
        if not row or row["uid"] != uid:
            return False
        conn.execute("DELETE FROM thread_drafts WHERE id=?", (draft_id,))
        conn.execute("DELETE FROM draft_collaborators WHERE draft_id=?", (draft_id,))
        conn.execute("DELETE FROM draft_edit_log WHERE draft_id=?", (draft_id,))
        conn.execute("DELETE FROM draft_presence WHERE draft_id=?", (draft_id,))
        conn.commit()
        return True


def cancel_to_draft_save(row: dict) -> int:
    """Save a cancelled scheduled thread as a draft. Returns new draft ID."""
    return save_draft(row["uid"], row["fid"], row["forum_name"], row["subject"], row["message"])


# ── Collaborative draft helpers ────────────────────────────────────────────────

def _draft_accessible(conn, draft_id: int, uid: str) -> tuple[bool, bool]:
    """Returns (accessible, is_owner)."""
    row = conn.execute("SELECT uid FROM thread_drafts WHERE id=?", (draft_id,)).fetchone()
    if not row:
        return False, False
    if row["uid"] == uid:
        return True, True
    # Check collaborator
    collab = conn.execute(
        "SELECT 1 FROM draft_collaborators WHERE draft_id=? AND uid=?", (draft_id, uid)
    ).fetchone()
    return (collab is not None), False


def get_draft(draft_id: int, uid: str) -> dict | None:
    """Get a single draft if the user is owner or collaborator."""
    with _conn() as conn:
        accessible, is_owner = _draft_accessible(conn, draft_id, uid)
        if not accessible:
            return None
        row = conn.execute("SELECT * FROM thread_drafts WHERE id=?", (draft_id,)).fetchone()
        if not row:
            return None
        d = dict(row)
        d["is_owner"] = is_owner
        return d


def get_drafts_with_collab_info(uid: str) -> list[dict]:
    """Owner's drafts with version + collaborator count."""
    with _conn() as conn:
        rows = conn.execute(
            "SELECT * FROM thread_drafts WHERE uid=? ORDER BY updated_at DESC", (uid,)
        ).fetchall()
        result = []
        for r in rows:
            d = dict(r)
            d["is_owner"] = True
            cnt = conn.execute(
                "SELECT COUNT(*) FROM draft_collaborators WHERE draft_id=?", (r["id"],)
            ).fetchone()[0]
            d["collab_count"] = cnt
            result.append(d)
        return result


def get_shared_drafts(uid: str) -> list[dict]:
    """Drafts where the user is a collaborator (not owner)."""
    with _conn() as conn:
        rows = conn.execute(
            """SELECT td.* FROM thread_drafts td
               JOIN draft_collaborators dc ON dc.draft_id=td.id
               WHERE dc.uid=? AND td.uid != ?
               ORDER BY td.updated_at DESC""",
            (uid, uid)
        ).fetchall()
        result = []
        for r in rows:
            d = dict(r)
            d["is_owner"] = False
            cnt = conn.execute(
                "SELECT COUNT(*) FROM draft_collaborators WHERE draft_id=?", (r["id"],)
            ).fetchone()[0]
            d["collab_count"] = cnt
            result.append(d)
        return result


def save_draft_collab(draft_id: int, uid: str, fid: str, forum_name: str,
                      subject: str, message: str,
                      base_version: int,
                      editor_name: str) -> tuple[str, dict]:
    """
    Versioned save with optimistic locking.
    Returns ("ok", draft_dict) | ("conflict", current_dict) | ("notfound", {})
    """
    now = int(time.time())
    with _ctx() as conn:
        accessible, _ = _draft_accessible(conn, draft_id, uid)
        if not accessible:
            return "notfound", {}

        row = conn.execute(
            "SELECT * FROM thread_drafts WHERE id=?", (draft_id,)
        ).fetchone()
        if not row:
            return "notfound", {}

        current_version = int(row["version"] or 1)
        if current_version != base_version:
            return "conflict", {
                "version":          current_version,
                "subject":          row["subject"],
                "message":          row["message"],
                "last_editor_name": row["last_editor_name"] or "",
            }

        new_version = current_version + 1

        # Log the edit
        conn.execute(
            """INSERT INTO draft_edit_log
               (draft_id, editor_uid, editor_name, old_subject, new_subject,
                old_message, new_message, version, edited_at)
               VALUES (?,?,?,?,?,?,?,?,?)""",
            (draft_id, uid, editor_name,
             row["subject"], subject,
             row["message"], message,
             new_version, now)
        )

        conn.execute(
            """UPDATE thread_drafts SET
               fid=?, forum_name=?, subject=?, message=?,
               version=?, last_editor_uid=?, last_editor_name=?, updated_at=?
               WHERE id=?""",
            (fid, forum_name, subject, message,
             new_version, uid, editor_name, now,
             draft_id)
        )

        updated = dict(conn.execute(
            "SELECT * FROM thread_drafts WHERE id=?", (draft_id,)
        ).fetchone())
        return "ok", updated


def get_draft_version_info(draft_id: int, uid: str) -> dict | None:
    """Lightweight poll — returns version, last_editor_name, presence list."""
    with _conn() as conn:
        accessible, _ = _draft_accessible(conn, draft_id, uid)
        if not accessible:
            return None
        row = conn.execute(
            "SELECT version, last_editor_name FROM thread_drafts WHERE id=?", (draft_id,)
        ).fetchone()
        if not row:
            return None
        # Presence: anyone who pinged in the last 60 seconds
        cutoff = int(time.time()) - 60
        presence_rows = conn.execute(
            "SELECT uid, username FROM draft_presence WHERE draft_id=? AND last_seen >= ?",
            (draft_id, cutoff)
        ).fetchall()
        return {
            "version":          int(row["version"] or 1),
            "last_editor_name": row["last_editor_name"] or "",
            "presence":         [dict(p) for p in presence_rows],
        }


# ── Collaborators ──────────────────────────────────────────────────────────────

def add_collaborator(draft_id: int, owner_uid: str, collab_uid: str,
                     collab_name: str) -> bool:
    """Add a collaborator. Owner only. Returns False if forbidden."""
    if collab_uid == owner_uid:
        return False
    with _conn() as conn:
        row = conn.execute("SELECT uid FROM thread_drafts WHERE id=?", (draft_id,)).fetchone()
        if not row or row["uid"] != owner_uid:
            return False
        conn.execute(
            """INSERT OR REPLACE INTO draft_collaborators (draft_id, uid, username, added_at)
               VALUES (?,?,?,?)""",
            (draft_id, collab_uid, collab_name, int(time.time()))
        )
        conn.commit()
        return True


def remove_collaborator(draft_id: int, owner_uid: str, collab_uid: str) -> bool:
    with _conn() as conn:
        row = conn.execute("SELECT uid FROM thread_drafts WHERE id=?", (draft_id,)).fetchone()
        if not row or row["uid"] != owner_uid:
            return False
        conn.execute(
            "DELETE FROM draft_collaborators WHERE draft_id=? AND uid=?",
            (draft_id, collab_uid)
        )
        conn.commit()
        return True


def get_collaborators(draft_id: int) -> list[dict]:
    with _conn() as conn:
        rows = conn.execute(
            "SELECT uid, username, added_at FROM draft_collaborators WHERE draft_id=? ORDER BY added_at ASC",
            (draft_id,)
        ).fetchall()
        return [dict(r) for r in rows]


# ── Edit log ───────────────────────────────────────────────────────────────────

def get_edit_log(draft_id: int, limit: int = 50) -> list[dict]:
    with _conn() as conn:
        rows = conn.execute(
            """SELECT * FROM draft_edit_log WHERE draft_id=?
               ORDER BY edited_at DESC LIMIT ?""",
            (draft_id, limit)
        ).fetchall()
        return [dict(r) for r in rows]


def rollback_to_log_entry(draft_id: int, log_id: int,
                           uid: str, owner_name: str) -> tuple[str, int]:
    """
    Restore draft to the content saved in a log entry. Owner only.
    Returns ("ok", new_version) | ("forbidden", 0) | ("notfound", 0)
    """
    now = int(time.time())
    with _ctx() as conn:
        # Only owner may rollback
        draft_row = conn.execute("SELECT uid, version FROM thread_drafts WHERE id=?", (draft_id,)).fetchone()
        if not draft_row:
            return "notfound", 0
        if draft_row["uid"] != uid:
            return "forbidden", 0

        log_row = conn.execute(
            "SELECT * FROM draft_edit_log WHERE id=? AND draft_id=?", (log_id, draft_id)
        ).fetchone()
        if not log_row:
            return "notfound", 0

        current_version = int(draft_row["version"] or 1)
        new_version = current_version + 1

        conn.execute(
            """INSERT INTO draft_edit_log
               (draft_id, editor_uid, editor_name, old_subject, new_subject,
                old_message, new_message, version, edited_at, is_rollback)
               VALUES (?,?,?,?,?,?,?,?,?,1)""",
            (draft_id, uid, owner_name,
             conn.execute("SELECT subject FROM thread_drafts WHERE id=?", (draft_id,)).fetchone()["subject"],
             log_row["old_subject"],
             conn.execute("SELECT message FROM thread_drafts WHERE id=?", (draft_id,)).fetchone()["message"],
             log_row["old_message"],
             new_version, now)
        )

        conn.execute(
            """UPDATE thread_drafts SET
               subject=?, message=?, version=?, last_editor_uid=?, last_editor_name=?, updated_at=?
               WHERE id=?""",
            (log_row["old_subject"], log_row["old_message"],
             new_version, uid, owner_name, now,
             draft_id)
        )
        return "ok", new_version


# ── Presence ───────────────────────────────────────────────────────────────────

def touch_presence(draft_id: int, uid: str, username: str) -> None:
    with _conn() as conn:
        conn.execute(
            """INSERT OR REPLACE INTO draft_presence (draft_id, uid, username, last_seen)
               VALUES (?,?,?,?)""",
            (draft_id, uid, username, int(time.time()))
        )
        conn.commit()


def clear_presence(draft_id: int, uid: str) -> None:
    with _conn() as conn:
        conn.execute(
            "DELETE FROM draft_presence WHERE draft_id=? AND uid=?",
            (draft_id, uid)
        )
        conn.commit()
