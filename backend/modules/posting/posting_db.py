"""
modules/posting/posting_db.py — Persistence for thread posting, reply queue, recents,
and collaborative drafts. Uses MySQL via db_connection._db().
"""

import secrets
import time
from _db_compat import _db


def init_posting_db() -> None:
    with _db() as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS scheduled_threads (
                id              INT          NOT NULL AUTO_INCREMENT,
                uid             VARCHAR(64)  NOT NULL,
                fid             VARCHAR(64)  NOT NULL,
                forum_name      VARCHAR(255) NOT NULL,
                subject         VARCHAR(512) NOT NULL,
                message         MEDIUMTEXT   NOT NULL,
                fire_at         BIGINT       NOT NULL,
                status          VARCHAR(32)  NOT NULL DEFAULT 'pending',
                sent_at         BIGINT,
                tid             VARCHAR(64),
                error           TEXT,
                auto_bump       TINYINT      NOT NULL DEFAULT 0,
                bump_interval_h INT          NOT NULL DEFAULT 12,
                overflow_message MEDIUMTEXT,
                overflow_message_2 MEDIUMTEXT,
                created_at      BIGINT       NOT NULL DEFAULT 0,
                PRIMARY KEY (id),
                INDEX idx_st_uid (uid)
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS my_threads (
                uid           VARCHAR(64)  NOT NULL,
                tid           VARCHAR(64)  NOT NULL,
                fid           VARCHAR(64)  NOT NULL,
                title         VARCHAR(512) NOT NULL,
                created_at    BIGINT       NOT NULL,
                last_pid      VARCHAR(64),
                last_checked  BIGINT,
                lastpost      BIGINT       NOT NULL DEFAULT 0,
                lastposteruid VARCHAR(64)  NOT NULL DEFAULT '',
                numreplies    INT          NOT NULL DEFAULT 0,
                PRIMARY KEY (uid, tid),
                INDEX idx_mt_uid_lastpost (uid, lastpost)
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
        """)
        # Add overflow_message column if not present (migration-safe)
        try:
            conn.execute("ALTER TABLE scheduled_threads ADD COLUMN overflow_message MEDIUMTEXT")
        except Exception:
            pass
        try:
            conn.execute("ALTER TABLE scheduled_threads ADD COLUMN overflow_message_2 MEDIUMTEXT")
        except Exception:
            pass
        try:
            conn.execute("ALTER TABLE thread_drafts ADD COLUMN reply1 MEDIUMTEXT")
        except Exception:
            pass
        try:
            conn.execute("ALTER TABLE thread_drafts ADD COLUMN reply2 MEDIUMTEXT")
        except Exception:
            pass
        # Add closed column if not present (migration-safe)
        try:
            conn.execute("ALTER TABLE my_threads ADD COLUMN closed TINYINT NOT NULL DEFAULT 0")
        except Exception:
            pass
        # Add firstpost column if not present (migration-safe)
        # Stores the PID of the thread's first post so the reply poller can
        # calculate which page new replies are on without numreplies (not in API).
        try:
            conn.execute("ALTER TABLE my_threads ADD COLUMN firstpost VARCHAR(64) NOT NULL DEFAULT '0'")
        except Exception:
            pass

        conn.execute("""
            CREATE TABLE IF NOT EXISTS reply_queue (
                id               INT          NOT NULL AUTO_INCREMENT,
                uid              VARCHAR(64)  NOT NULL,
                tid              VARCHAR(64)  NOT NULL,
                pid              VARCHAR(64)  NOT NULL,
                thread_title     VARCHAR(512),
                from_uid         VARCHAR(64),
                from_username    VARCHAR(255),
                dateline         BIGINT,
                message_preview  TEXT,
                full_message     MEDIUMTEXT,
                status           VARCHAR(32)  NOT NULL DEFAULT 'unread',
                created_at       BIGINT       NOT NULL DEFAULT 0,
                PRIMARY KEY (id),
                UNIQUE KEY uq_rq_uid_pid (uid, pid),
                INDEX idx_rq_uid (uid)
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS posting_recents (
                uid           VARCHAR(64)  NOT NULL,
                fid           VARCHAR(64)  NOT NULL,
                forum_name    VARCHAR(255) NOT NULL,
                category_name VARCHAR(255),
                last_used     BIGINT       NOT NULL,
                PRIMARY KEY (uid, fid)
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS thread_drafts (
                id               INT          NOT NULL AUTO_INCREMENT,
                uid              VARCHAR(64)  NOT NULL,
                fid              VARCHAR(64)  NOT NULL,
                forum_name       VARCHAR(255) NOT NULL,
                subject          VARCHAR(512) NOT NULL,
                message          MEDIUMTEXT   NOT NULL,
                reply1           MEDIUMTEXT,
                reply2           MEDIUMTEXT,
                version          INT          NOT NULL DEFAULT 1,
                last_editor_uid  VARCHAR(64)  NOT NULL DEFAULT '',
                last_editor_name VARCHAR(255) NOT NULL DEFAULT '',
                created_at       BIGINT       NOT NULL DEFAULT 0,
                updated_at       BIGINT       NOT NULL DEFAULT 0,
                PRIMARY KEY (id),
                INDEX idx_td_uid (uid)
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS draft_collaborators (
                draft_id   INT          NOT NULL,
                uid        VARCHAR(64)  NOT NULL,
                username   VARCHAR(255) NOT NULL DEFAULT '',
                invited_by VARCHAR(64)  NOT NULL,
                added_at   BIGINT       NOT NULL DEFAULT 0,
                PRIMARY KEY (draft_id, uid)
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS draft_edit_log (
                id          INT          NOT NULL AUTO_INCREMENT,
                draft_id    INT          NOT NULL,
                editor_uid  VARCHAR(64)  NOT NULL,
                editor_name VARCHAR(255) NOT NULL DEFAULT '',
                old_subject VARCHAR(512) NOT NULL DEFAULT '',
                new_subject VARCHAR(512) NOT NULL DEFAULT '',
                old_message MEDIUMTEXT   NOT NULL,
                new_message MEDIUMTEXT   NOT NULL,
                version     INT          NOT NULL,
                is_rollback TINYINT      NOT NULL DEFAULT 0,
                edited_at   BIGINT       NOT NULL DEFAULT 0,
                PRIMARY KEY (id),
                INDEX idx_del_draft (draft_id)
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS draft_invite_tokens (
                token       VARCHAR(64)  NOT NULL,
                draft_id    INT          NOT NULL,
                created_by  VARCHAR(64)  NOT NULL,
                created_at  BIGINT       NOT NULL,
                PRIMARY KEY (token),
                INDEX idx_dit_draft (draft_id)
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS draft_presence (
                draft_id    INT          NOT NULL,
                uid         VARCHAR(64)  NOT NULL,
                username    VARCHAR(255) NOT NULL DEFAULT '',
                last_active BIGINT       NOT NULL,
                PRIMARY KEY (draft_id, uid)
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
        """)


# ─────────────────────────────────────────────────────────────────────────────
# Scheduled threads
# ─────────────────────────────────────────────────────────────────────────────

def create_scheduled_thread(uid: str, fid: str, forum_name: str,
                             subject: str, message: str, fire_at: int,
                             auto_bump: bool = False, bump_interval_h: int = 12,
                             overflow_message: str = "",
                             overflow_message_2: str = "") -> int:
    with _db() as conn:
        cur = conn.execute(
            """INSERT INTO scheduled_threads
               (uid, fid, forum_name, subject, message, fire_at, auto_bump, bump_interval_h, overflow_message, overflow_message_2)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (uid, fid, forum_name, subject, message, fire_at, int(auto_bump), bump_interval_h,
             overflow_message or "", overflow_message_2 or "")
        )
        return cur.lastrowid


def get_due_threads() -> list[dict]:
    now = int(time.time())
    with _db() as conn:
        rows = conn.execute(
            "SELECT * FROM scheduled_threads WHERE status='pending' AND fire_at <= ? ORDER BY fire_at ASC",
            (now,)
        ).fetchall()
        return [dict(r) for r in rows]


def get_scheduled_threads(uid: str) -> list[dict]:
    with _db() as conn:
        rows = conn.execute(
            "SELECT * FROM scheduled_threads WHERE uid=? AND status IN ('pending','failed') ORDER BY fire_at ASC",
            (uid,)
        ).fetchall()
        return [dict(r) for r in rows]


def get_sent_threads(uid: str, limit: int = 30) -> list[dict]:
    with _db() as conn:
        rows = conn.execute(
            "SELECT * FROM scheduled_threads WHERE uid=? AND status='sent' ORDER BY sent_at DESC LIMIT ?",
            (uid, limit)
        ).fetchall()
        return [dict(r) for r in rows]


def mark_thread_sending(row_id: int) -> None:
    with _db() as conn:
        conn.execute("UPDATE scheduled_threads SET status='sending' WHERE id=? AND status='pending'", (row_id,))


def mark_thread_sent(row_id: int, tid: str) -> None:
    with _db() as conn:
        conn.execute(
            "UPDATE scheduled_threads SET status='sent', sent_at=?, tid=? WHERE id=?",
            (int(time.time()), tid, row_id)
        )


def mark_thread_failed(row_id: int, error: str) -> None:
    with _db() as conn:
        conn.execute(
            "UPDATE scheduled_threads SET status='failed', error=? WHERE id=?",
            (error[:500], row_id)
        )


def cancel_scheduled_thread(row_id: int, uid: str) -> bool:
    with _db() as conn:
        cur = conn.execute(
            "UPDATE scheduled_threads SET status='cancelled' WHERE id=? AND uid=? AND status='pending'",
            (row_id, uid)
        )
        return cur.rowcount > 0


def update_fire_at(row_id: int, uid: str, fire_at: int) -> bool:
    with _db() as conn:
        cur = conn.execute(
            "UPDATE scheduled_threads SET fire_at=? WHERE id=? AND uid=? AND status='pending'",
            (fire_at, row_id, uid)
        )
        return cur.rowcount > 0


# ─────────────────────────────────────────────────────────────────────────────
# My tracked threads
# ─────────────────────────────────────────────────────────────────────────────

def add_my_thread(uid: str, tid: str, fid: str, title: str,
                  lastpost: int = 0, lastposteruid: str = "", numreplies: int = 0,
                  closed: int = 0, firstpost: str = "0") -> None:
    with _db() as conn:
        conn.execute(
            """INSERT INTO my_threads (uid, tid, fid, title, created_at, lastpost, lastposteruid, numreplies, closed, firstpost)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
               ON CONFLICT(uid, tid) DO UPDATE SET
                   lastpost      = excluded.lastpost,
                   lastposteruid = excluded.lastposteruid,
                   numreplies    = excluded.numreplies,
                   closed        = excluded.closed,
                   firstpost     = CASE WHEN my_threads.firstpost = '0' OR my_threads.firstpost IS NULL
                                        THEN excluded.firstpost ELSE my_threads.firstpost END""",
            (uid, tid, fid, title, int(time.time()), lastpost, lastposteruid, numreplies, closed, firstpost)
        )


def get_my_threads(uid: str) -> list[dict]:
    with _db() as conn:
        rows = conn.execute(
            """SELECT m.*, u.username AS lastposter_username
               FROM my_threads m
               LEFT JOIN uid_usernames u ON u.uid = m.lastposteruid
               WHERE m.uid=?
               ORDER BY CASE WHEN m.lastpost > 0 THEN m.lastpost ELSE m.created_at END DESC""",
            (uid,)
        ).fetchall()
        return [dict(r) for r in rows]


def get_all_tracked_threads() -> list[dict]:
    with _db() as conn:
        rows = conn.execute("SELECT * FROM my_threads ORDER BY uid, tid").fetchall()
        return [dict(r) for r in rows]


def update_thread_last_checked(uid: str, tid: str, last_pid: str, last_checked: int) -> None:
    with _db() as conn:
        conn.execute(
            "UPDATE my_threads SET last_pid=?, last_checked=? WHERE uid=? AND tid=?",
            (last_pid, last_checked, uid, tid)
        )


def update_thread_numreplies(uid: str, tid: str, numreplies: int) -> None:
    """Store fresh numreplies from a _tid API fetch so the poller can use it for page calculation."""
    with _db() as conn:
        conn.execute(
            "UPDATE my_threads SET numreplies=? WHERE uid=? AND tid=?",
            (numreplies, uid, tid)
        )


# ─────────────────────────────────────────────────────────────────────────────
# Reply queue
# ─────────────────────────────────────────────────────────────────────────────

def upsert_reply(uid: str, tid: str, pid: str, thread_title: str,
                 from_uid: str, from_username: str, dateline: int,
                 message_preview: str, full_message: str) -> None:
    with _db() as conn:
        conn.execute(
            """INSERT OR IGNORE INTO reply_queue
               (uid, tid, pid, thread_title, from_uid, from_username, dateline,
                message_preview, full_message)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (uid, tid, pid, thread_title, from_uid, from_username, dateline,
             message_preview[:200], full_message)
        )


def auto_dismiss_by_pid(uid: str, quoted_pid: str) -> None:
    with _db() as conn:
        conn.execute(
            "UPDATE reply_queue SET status='dismissed' WHERE uid=? AND pid=? AND status='unread'",
            (uid, quoted_pid)
        )


def auto_dismiss_by_thread_before(uid: str, tid: str, before_dateline: int) -> int:
    with _db() as conn:
        cur = conn.execute(
            """UPDATE reply_queue SET status='dismissed'
               WHERE uid=? AND tid=? AND status='unread' AND dateline <= ?""",
            (uid, tid, before_dateline)
        )
        return cur.rowcount


def dismiss_reply(reply_id: int, uid: str) -> bool:
    with _db() as conn:
        cur = conn.execute(
            "UPDATE reply_queue SET status='dismissed' WHERE id=? AND uid=?",
            (reply_id, uid)
        )
        return cur.rowcount > 0


def get_reply_queue(uid: str, status: str = 'unread') -> list[dict]:
    with _db() as conn:
        rows = conn.execute(
            "SELECT * FROM reply_queue WHERE uid=? AND status=? ORDER BY dateline DESC",
            (uid, status)
        ).fetchall()
        return [dict(r) for r in rows]


def get_unread_count(uid: str) -> int:
    with _db() as conn:
        return conn.execute(
            "SELECT COUNT(*) AS cnt FROM reply_queue WHERE uid=? AND status='unread'", (uid,)
        ).fetchone()["cnt"]


# ─────────────────────────────────────────────────────────────────────────────
# Posting recents
# ─────────────────────────────────────────────────────────────────────────────

def touch_recent(uid: str, fid: str, forum_name: str, category_name: str) -> None:
    now = int(time.time())
    with _db() as conn:
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
               SELECT fid FROM (
                   SELECT fid FROM posting_recents WHERE uid=? ORDER BY last_used DESC LIMIT 5
               ) AS keep
            )""",
            (uid, uid)
        )


def get_recents(uid: str) -> list[dict]:
    with _db() as conn:
        rows = conn.execute(
            "SELECT * FROM posting_recents WHERE uid=? ORDER BY last_used DESC",
            (uid,)
        ).fetchall()
        return [dict(r) for r in rows]


def delete_recent(uid: str, fid: str) -> None:
    with _db() as conn:
        conn.execute("DELETE FROM posting_recents WHERE uid=? AND fid=?", (uid, fid))


# ─────────────────────────────────────────────────────────────────────────────
# Drafts — simple
# ─────────────────────────────────────────────────────────────────────────────

def save_draft(uid: str, fid: str, forum_name: str, subject: str, message: str) -> int:
    """Create a new draft at version 1."""
    now = int(time.time())
    with _db() as conn:
        cur = conn.execute(
            """INSERT INTO thread_drafts
               (uid, fid, forum_name, subject, message, version, created_at, updated_at)
               VALUES (?,?,?,?,?,1,?,?)""",
            (uid, fid, forum_name, subject, message, now, now)
        )
        return cur.lastrowid


def delete_draft(draft_id: int, uid: str) -> bool:
    """Owner-only hard delete."""
    with _db() as conn:
        conn.execute("DELETE FROM draft_collaborators WHERE draft_id=?", (draft_id,))
        conn.execute("DELETE FROM draft_edit_log WHERE draft_id=?", (draft_id,))
        conn.execute("DELETE FROM draft_presence WHERE draft_id=?", (draft_id,))
        cur = conn.execute("DELETE FROM thread_drafts WHERE id=? AND uid=?", (draft_id, uid))
        return cur.rowcount > 0


def cancel_to_draft(row_id: int, uid: str) -> dict | None:
    with _db() as conn:
        row = conn.execute(
            "SELECT * FROM scheduled_threads WHERE id=? AND uid=? AND status='pending'", (row_id, uid)
        ).fetchone()
        if not row:
            return None
        conn.execute("UPDATE scheduled_threads SET status='cancelled' WHERE id=?", (row_id,))
        return dict(row)


# ─────────────────────────────────────────────────────────────────────────────
# Drafts — collaborative (versioned access)
# ─────────────────────────────────────────────────────────────────────────────

def _draft_accessible(conn, draft_id: int, uid: str) -> tuple[bool, bool]:
    """Returns (accessible, is_owner). conn is already open."""
    row = conn.execute("SELECT uid FROM thread_drafts WHERE id=?", (draft_id,)).fetchone()
    if not row:
        return False, False
    is_owner = row["uid"] == uid
    if is_owner:
        return True, True
    collab = conn.execute(
        "SELECT 1 FROM draft_collaborators WHERE draft_id=? AND uid=?", (draft_id, uid)
    ).fetchone()
    return bool(collab), False


def create_draft(uid: str, fid: str, forum_name: str, subject: str, message: str,
                   reply1: str = "", reply2: str = "") -> int:
    now = int(time.time())
    with _db() as conn:
        cur = conn.execute(
            """INSERT INTO thread_drafts (uid, fid, forum_name, subject, message, reply1, reply2, created_at, updated_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (uid, fid, forum_name, subject, message, reply1 or "", reply2 or "", now, now)
        )
        return cur.lastrowid


def get_drafts_with_collab_info(uid: str) -> list[dict]:
    """Owner's drafts enriched with collab count + version."""
    with _db() as conn:
        rows = conn.execute(
            "SELECT * FROM thread_drafts WHERE uid=? ORDER BY updated_at DESC", (uid,)
        ).fetchall()
        result = []
        for r in rows:
            d = dict(r)
            d["is_owner"] = True
            d["version"]  = d.get("version") or 1
            cc = conn.execute(
                "SELECT COUNT(*) AS cnt FROM draft_collaborators WHERE draft_id=?", (d["id"],)
            ).fetchone()["cnt"]
            d["collab_count"] = cc
            result.append(d)
        return result


def get_shared_drafts(uid: str) -> list[dict]:
    """Drafts where uid is a collaborator (not the owner)."""
    with _db() as conn:
        rows = conn.execute(
            """SELECT d.* FROM thread_drafts d
               JOIN draft_collaborators dc ON dc.draft_id = d.id
               WHERE dc.uid=?
               ORDER BY d.updated_at DESC""",
            (uid,)
        ).fetchall()
        result = []
        for r in rows:
            d = dict(r)
            d["is_owner"] = False
            d["version"]  = d.get("version") or 1
            cc = conn.execute(
                "SELECT COUNT(*) AS cnt FROM draft_collaborators WHERE draft_id=?", (d["id"],)
            ).fetchone()["cnt"]
            d["collab_count"] = cc
            result.append(d)
        return result


def get_draft(draft_id: int, uid: str) -> dict | None:
    with _db() as conn:
        row = conn.execute("SELECT * FROM thread_drafts WHERE id=?", (draft_id,)).fetchone()
        if not row:
            return None
        accessible, is_owner = _draft_accessible(conn, draft_id, uid)
        if not accessible:
            return None
        d = dict(row)
        d["is_owner"] = is_owner
        d["version"]  = d.get("version") or 1
        return d


def save_draft_collab(draft_id: int, uid: str, fid: str, forum_name: str,
                       subject: str, message: str, base_version: int,
                       editor_name: str = "",
                       reply1: str = "", reply2: str = "") -> tuple:
    now = int(time.time())
    with _db() as conn:
        row = conn.execute("SELECT * FROM thread_drafts WHERE id=?", (draft_id,)).fetchone()
        if not row:
            return ("notfound", None)

        accessible, is_owner = _draft_accessible(conn, draft_id, uid)
        if not accessible:
            return ("notfound", None)

        d               = dict(row)
        current_version = d.get("version") or 1

        if current_version != base_version:
            current         = dict(row)
            current["is_owner"] = is_owner
            return ("conflict", current)

        new_version = current_version + 1

        conn.execute(
            """INSERT INTO draft_edit_log
               (draft_id, editor_uid, editor_name,
                old_subject, new_subject, old_message, new_message,
                version, edited_at)
               VALUES (?,?,?,?,?,?,?,?,?)""",
            (draft_id, uid, editor_name,
             d["subject"], subject, d["message"], message,
             new_version, now)
        )

        conn.execute(
            """UPDATE thread_drafts
               SET fid=?, forum_name=?, subject=?, message=?, reply1=?, reply2=?,
                   version=?, last_editor_uid=?, last_editor_name=?, updated_at=?
               WHERE id=?""",
            (fid, forum_name, subject, message, reply1 or "", reply2 or "",
             new_version, uid, editor_name, now, draft_id)
        )

        updated             = dict(conn.execute("SELECT * FROM thread_drafts WHERE id=?", (draft_id,)).fetchone())
        updated["is_owner"] = is_owner
        return ("ok", updated)


def get_draft_version_info(draft_id: int, uid: str) -> dict | None:
    with _db() as conn:
        row = conn.execute(
            "SELECT id, uid, version, last_editor_uid, last_editor_name FROM thread_drafts WHERE id=?",
            (draft_id,)
        ).fetchone()
        if not row:
            return None
        accessible, _ = _draft_accessible(conn, draft_id, uid)
        if not accessible:
            return None
        now = int(time.time())
        presence = conn.execute(
            "SELECT uid, username, last_active FROM draft_presence WHERE draft_id=? AND last_active > ?",
            (draft_id, now - 60)
        ).fetchall()
        return {
            "version":          row["version"] or 1,
            "last_editor_uid":  row["last_editor_uid"]  or "",
            "last_editor_name": row["last_editor_name"] or "",
            "presence":         [dict(p) for p in presence],
        }


# ─────────────────────────────────────────────────────────────────────────────
# Collaborators
# ─────────────────────────────────────────────────────────────────────────────

def add_collaborator(draft_id: int, owner_uid: str, collab_uid: str,
                     collab_username: str) -> bool:
    with _db() as conn:
        row = conn.execute("SELECT uid FROM thread_drafts WHERE id=?", (draft_id,)).fetchone()
        if not row or row["uid"] != owner_uid:
            return False
        if collab_uid == owner_uid:
            return False
        conn.execute(
            """INSERT OR IGNORE INTO draft_collaborators (draft_id, uid, username, invited_by)
               VALUES (?,?,?,?)""",
            (draft_id, collab_uid, collab_username, owner_uid)
        )
        return True


def remove_collaborator(draft_id: int, owner_uid: str, collab_uid: str) -> bool:
    with _db() as conn:
        row = conn.execute("SELECT uid FROM thread_drafts WHERE id=?", (draft_id,)).fetchone()
        if not row or row["uid"] != owner_uid:
            return False
        conn.execute(
            "DELETE FROM draft_collaborators WHERE draft_id=? AND uid=?",
            (draft_id, collab_uid)
        )
        return True


def get_collaborators(draft_id: int) -> list[dict]:
    with _db() as conn:
        rows = conn.execute(
            "SELECT uid, username, invited_by, added_at FROM draft_collaborators WHERE draft_id=? ORDER BY added_at",
            (draft_id,)
        ).fetchall()
        return [dict(r) for r in rows]


# ─────────────────────────────────────────────────────────────────────────────
# Edit log
# ─────────────────────────────────────────────────────────────────────────────

def get_edit_log(draft_id: int, limit: int = 50) -> list[dict]:
    with _db() as conn:
        rows = conn.execute(
            """SELECT id, editor_uid, editor_name,
                      old_subject, new_subject, old_message, new_message,
                      version, is_rollback, edited_at
               FROM draft_edit_log WHERE draft_id=?
               ORDER BY edited_at DESC LIMIT ?""",
            (draft_id, limit)
        ).fetchall()
        return [dict(r) for r in rows]


def rollback_to_log_entry(draft_id: int, log_id: int,
                            owner_uid: str, owner_name: str) -> tuple:
    now = int(time.time())
    with _db() as conn:
        draft = conn.execute("SELECT * FROM thread_drafts WHERE id=?", (draft_id,)).fetchone()
        if not draft or dict(draft)["uid"] != owner_uid:
            return ("forbidden", None)

        log_entry = conn.execute(
            "SELECT * FROM draft_edit_log WHERE id=? AND draft_id=?", (log_id, draft_id)
        ).fetchone()
        if not log_entry:
            return ("notfound", None)

        d           = dict(draft)
        le          = dict(log_entry)
        new_version = (d.get("version") or 1) + 1

        conn.execute(
            """INSERT INTO draft_edit_log
               (draft_id, editor_uid, editor_name,
                old_subject, new_subject, old_message, new_message,
                version, is_rollback, edited_at)
               VALUES (?,?,?,?,?,?,?,?,1,?)""",
            (draft_id, owner_uid, owner_name,
             d["subject"], le["new_subject"],
             d["message"],  le["new_message"],
             new_version, now)
        )

        conn.execute(
            """UPDATE thread_drafts
               SET subject=?, message=?, version=?,
                   last_editor_uid=?, last_editor_name=?, updated_at=?
               WHERE id=?""",
            (le["new_subject"], le["new_message"], new_version,
             owner_uid, owner_name, now, draft_id)
        )

        return ("ok", new_version)


# ─────────────────────────────────────────────────────────────────────────────
# Presence
# ─────────────────────────────────────────────────────────────────────────────

def touch_presence(draft_id: int, uid: str, username: str) -> None:
    now = int(time.time())
    with _db() as conn:
        conn.execute(
            """INSERT INTO draft_presence (draft_id, uid, username, last_active)
               VALUES (?,?,?,?)
               ON CONFLICT(draft_id, uid)
               DO UPDATE SET username=excluded.username, last_active=excluded.last_active""",
            (draft_id, uid, username, now)
        )


def clear_presence(draft_id: int, uid: str) -> None:
    with _db() as conn:
        conn.execute("DELETE FROM draft_presence WHERE draft_id=? AND uid=?", (draft_id, uid))


# ─────────────────────────────────────────────────────────────────────────────
# Invite tokens
# ─────────────────────────────────────────────────────────────────────────────

def get_or_create_invite_token(draft_id: int, owner_uid: str) -> str | None:
    """Owner only. Returns existing token or creates a new one. Returns None if not owner."""
    with _db() as conn:
        row = conn.execute("SELECT uid FROM thread_drafts WHERE id=?", (draft_id,)).fetchone()
        if not row or row["uid"] != owner_uid:
            return None
        existing = conn.execute(
            "SELECT token FROM draft_invite_tokens WHERE draft_id=?", (draft_id,)
        ).fetchone()
        if existing:
            return existing["token"]
        token = secrets.token_urlsafe(16)
        conn.execute(
            "INSERT OR IGNORE INTO draft_invite_tokens (token, draft_id, created_by, created_at) VALUES (?,?,?,?)",
            (token, draft_id, owner_uid, int(time.time()))
        )
        return token


def resolve_invite_token(token: str) -> int | None:
    """Returns draft_id for a valid token, or None."""
    with _db() as conn:
        row = conn.execute(
            "SELECT draft_id FROM draft_invite_tokens WHERE token=?", (token,)
        ).fetchone()
        return row["draft_id"] if row else None


def check_draft_access(draft_id: int, uid: str) -> bool:
    """Returns True if uid is the owner OR a listed collaborator. Direct check, no side effects."""
    with _db() as conn:
        row = conn.execute("SELECT uid FROM thread_drafts WHERE id=?", (draft_id,)).fetchone()
        if not row:
            return False
        if row["uid"] == uid:          # owner
            return True
        collab = conn.execute(
            "SELECT 1 FROM draft_collaborators WHERE draft_id=? AND uid=?", (draft_id, uid)
        ).fetchone()
        return bool(collab)
