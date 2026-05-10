"""
modules/wire/wire_db.py — DB layer for The Wire (curated thread reader).
"""

import time
import sqlite3
from pathlib import Path
from contextlib import contextmanager

DB_PATH = Path("data/hf_dash.db")

def _connect():
    conn = sqlite3.connect(str(DB_PATH), check_same_thread=False, timeout=10)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA busy_timeout=10000")
    return conn

@contextmanager
def _db():
    conn = _connect()
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


VALID_TAGS = {"guide", "tool", "discussion", "resource", "analysis", "classic", "news"}


def init():
    with _db() as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS notable_threads (
                id                  INTEGER PRIMARY KEY AUTOINCREMENT,
                tid                 TEXT NOT NULL UNIQUE,
                fid                 TEXT,
                subject             TEXT,
                author_uid          TEXT,
                author_name         TEXT,
                author_avatar       TEXT,
                author_usertitle    TEXT,
                author_reputation   TEXT  DEFAULT '0',
                author_groups       TEXT,
                firstpost_pid       TEXT,
                firstpost_content   TEXT,
                dateline            INTEGER DEFAULT 0,
                numreplies          INTEGER DEFAULT 0,
                lastpost            INTEGER DEFAULT 0,
                closed              INTEGER DEFAULT 0,
                tag                 TEXT NOT NULL DEFAULT 'discussion',
                curator_uid         TEXT,
                curator_name        TEXT,
                curator_note        TEXT,
                added_at            INTEGER DEFAULT 0,
                last_synced         INTEGER DEFAULT 0
        )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS notable_replies (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                tid         TEXT NOT NULL,
                pid         TEXT NOT NULL UNIQUE,
                uid         TEXT,
                username    TEXT,
                avatar      TEXT,
                dateline    INTEGER DEFAULT 0,
                message     TEXT,
                page_num    INT          DEFAULT 1,
                cached_at   INTEGER DEFAULT 0,
        )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS notable_curators (
                uid         TEXT NOT NULL,
                username    TEXT,
                role        VARCHAR(16)  NOT NULL DEFAULT 'curator',
                added_by    TEXT,
                added_at    INTEGER DEFAULT 0,
                PRIMARY KEY (uid)
        )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS notable_refresh_log (
                id      INTEGER PRIMARY KEY AUTOINCREMENT,
                tid     TEXT NOT NULL,
                uid     TEXT NOT NULL,
                ts      BIGINT      DEFAULT 0,
        )
        """)
    _migrate()


REFRESH_WINDOW   = 3600      # 1 hour window
REFRESH_MAX      = 3         # max refreshes per thread per window


def get_thread_refresh_count(tid: str) -> int:
    """How many refreshes have fired for this thread in the last hour."""
    since = int(time.time()) - REFRESH_WINDOW
    with _db() as conn:
        row = conn.execute(
            "SELECT COUNT(*) as n FROM notable_refresh_log WHERE tid=? AND ts>=?",
            (tid, since)
        ).fetchone()
        return int(row["n"]) if row else 0


def log_thread_refresh(tid: str, uid: str):
    with _db() as conn:
        conn.execute(
            "INSERT INTO notable_refresh_log (tid, uid, ts) VALUES (?,?,?)",
            (tid, uid, int(time.time()))
        )


def set_hf_news_flag(tid: str, value: int) -> None:
    """Set or clear the is_hf_news flag on an existing thread."""
    with _db() as conn:
        conn.execute("UPDATE notable_threads SET is_hf_news=? WHERE tid=?", (int(value), str(tid)))


def update_firstpost_content(tid: str, content: str):
    with _db() as conn:
        conn.execute(
            "UPDATE notable_threads SET firstpost_content=?, last_synced=? WHERE tid=?",
            (content, int(time.time()), tid)
        )


def _migrate():
    """Add columns that didn't exist in the first version of the schema."""
    with _db() as conn:
        for col, defn in [
            ("role VARCHAR(16) NOT NULL DEFAULT 'curator'", "notable_curators"),
            ("is_multipost INTEGER NOT NULL DEFAULT 0", "notable_threads"),
            ("secondpost_content TEXT", "notable_threads"),
            ("secondpost_pid TEXT", "notable_threads"),
            ("is_hf_news INTEGER NOT NULL DEFAULT 0", "notable_threads"),
            ("extra_posts TEXT", "notable_threads"),
            ("post_count TINYINT NOT NULL DEFAULT 1", "notable_threads"),
        ]:
            col_name = col.split()[0]
            table = defn
            try:
                conn.execute(f"ALTER TABLE {table} ADD COLUMN {col}")
            except Exception:
                pass  # already exists


# ── Role helpers ───────────────────────────────────────────────────────────────

def is_admin(uid: str) -> bool:
    return uid == WIRE_ADMIN_UID


def is_lead_curator(uid: str) -> bool:
    if uid == WIRE_ADMIN_UID:
        return True
    with _db() as conn:
        cur = conn.execute("SELECT role FROM notable_curators WHERE uid=?", (uid,))
        row = cur.fetchone()
        return row is not None and row["role"] == "lead"


def is_curator(uid: str) -> bool:
    if uid == WIRE_ADMIN_UID:
        return True
    with _db() as conn:
        cur = conn.execute("SELECT 1 FROM notable_curators WHERE uid=?", (uid,))
        return cur.fetchone() is not None


def get_my_role(uid: str) -> str:
    if uid == WIRE_ADMIN_UID:
        return "admin"
    with _db() as conn:
        cur = conn.execute("SELECT role FROM notable_curators WHERE uid=?", (uid,))
        row = cur.fetchone()
        return row["role"] if row else "none"


# ── Curator management ─────────────────────────────────────────────────────────

def get_curators() -> list[dict]:
    with _db() as conn:
        cur = conn.execute(
            "SELECT uid, username, role, added_by, added_at FROM notable_curators ORDER BY role DESC, added_at ASC"
        )
        return list(cur.fetchall())


def add_curator(uid: str, username: str, added_by: str, role: str = "curator"):
    with _db() as conn:
        conn.execute("""
            INSERT OR IGNORE INTO notable_curators (uid, username, role, added_by, added_at)
            VALUES (?, ?, ?, ?, ?)
        """, (uid, username, role, added_by, int(time.time())))


def remove_curator(uid: str):
    with _db() as conn:
        conn.execute("DELETE FROM notable_curators WHERE uid=?", (uid,))


def set_curator_role(uid: str, role: str):
    with _db() as conn:
        conn.execute("UPDATE notable_curators SET role=? WHERE uid=?", (role, uid))


# ── Threads ────────────────────────────────────────────────────────────────────

def add_thread(
    tid, fid, subject,
    author_uid, author_name, author_avatar,
    author_usertitle, author_reputation, author_groups,
    firstpost_pid, firstpost_content,
    dateline, numreplies, lastpost, closed,
    tag, curator_uid, curator_name, curator_note,
    is_multipost=0, secondpost_content="", secondpost_pid="",
    is_hf_news=0, extra_posts="", post_count=1,
):
    with _db() as conn:
        conn.execute("""
            INSERT INTO notable_threads (
                tid, fid, subject,
                author_uid, author_name, author_avatar,
                author_usertitle, author_reputation, author_groups,
                firstpost_pid, firstpost_content,
                dateline, numreplies, lastpost, closed,
                tag, curator_uid, curator_name, curator_note,
                added_at, last_synced, is_multipost, secondpost_content, secondpost_pid,
                is_hf_news, extra_posts, post_count
            ) VALUES (
                ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?,
                ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?,
                ?, ?, ?
            )
            ON CONFLICT(tid) DO UPDATE SET
                subject=excluded.subject,
                numreplies=excluded.numreplies,
                lastpost=excluded.lastpost,
                closed=excluded.closed,
                last_synced=excluded.last_synced
        """, (
            tid, fid, subject,
            author_uid, author_name, author_avatar,
            author_usertitle, author_reputation, author_groups,
            firstpost_pid, firstpost_content,
            dateline, numreplies, lastpost, closed,
            tag, curator_uid, curator_name, curator_note,
            int(time.time()), int(time.time()), is_multipost, secondpost_content, secondpost_pid,
            int(is_hf_news), extra_posts, int(post_count),
        ))


def get_threads(tag: str = "all", page: int = 1, per_page: int = 10, search: str = "", sort: str = "recent") -> dict:
    offset        = (page - 1) * per_page
    search_clause = " AND (subject LIKE ? OR curator_note LIKE ?)" if search else ""
    search_param  = (f"%{search}%", f"%{search}%") if search else ()
    tag_clause    = "" if tag == "all" else " AND tag=?"
    tag_param     = () if tag == "all" else (tag,)
    # Exclude news and hf_news from the default 'all' view — they have their own section
    news_exclude  = " AND tag != 'news' AND is_hf_news = 0" if tag == "all" and not search else ""
    where         = "WHERE 1=1" + tag_clause + search_clause + news_exclude
    params        = tag_param + search_param
    order         = "lastpost DESC" if sort == "active" else "added_at DESC"

    with _db() as conn:
        cur = conn.execute(
            f"SELECT COUNT(*) as n FROM notable_threads {where}", params
        )
        total = (cur.fetchone() or {}).get("n", 0)

        cur = conn.execute(f"""
            SELECT tid, fid, subject, author_name, author_avatar,
                   author_usertitle, author_reputation, author_groups,
                   dateline, numreplies, lastpost, closed,
                   tag, curator_uid, curator_name, curator_note, added_at,
                   is_multipost, secondpost_content, secondpost_pid,
                   is_hf_news, extra_posts, post_count
            FROM notable_threads
            {where}
            ORDER BY {order}
            LIMIT ? OFFSET ?
        """, params + (per_page, offset))
        rows = list(cur.fetchall())

    pages = max(1, (total + per_page - 1) // per_page)
    return {"threads": rows, "total": total, "page": page, "pages": pages}

def get_latest_hf_news() -> dict | None:
    """Return the single most recent HF News thread (is_hf_news=1)."""
    with _db() as conn:
        cur = conn.execute("""
            SELECT tid, fid, subject, author_name, author_avatar,
                   author_usertitle, author_reputation, author_groups,
                   dateline, numreplies, lastpost, closed,
                   tag, curator_uid, curator_name, curator_note, added_at,
                   is_multipost, secondpost_content, secondpost_pid,
                   is_hf_news, extra_posts, post_count
            FROM notable_threads
            WHERE is_hf_news=1
            ORDER BY added_at DESC
            LIMIT 1
        """)
        row = cur.fetchone()
        return dict(row) if row else None


def get_thread(tid: str) -> dict | None:
    with _db() as conn:
        cur = conn.execute("SELECT * FROM notable_threads WHERE tid=?", (tid,))
        return cur.fetchone()


def get_my_submissions(curator_uid: str) -> list[dict]:
    with _db() as conn:
        cur = conn.execute("""
            SELECT tid, fid, subject, tag, dateline, numreplies, added_at, closed
            FROM notable_threads
            WHERE curator_uid=?
            ORDER BY added_at DESC
        """, (curator_uid,))
        return list(cur.fetchall())


def remove_thread(tid: str):
    with _db() as conn:
        conn.execute("DELETE FROM notable_threads WHERE tid=?", (tid,))
        conn.execute("DELETE FROM notable_replies WHERE tid=?", (tid,))


def update_thread_stats(tid: str, numreplies: int, lastpost: int, closed: int):
    with _db() as conn:
        conn.execute("""
            UPDATE notable_threads
            SET numreplies=?, lastpost=?, closed=?, last_synced=?
            WHERE tid=?
        """, (numreplies, lastpost, closed, int(time.time()), tid))


def get_all_tids() -> list[str]:
    with _db() as conn:
        cur = conn.execute("SELECT tid FROM notable_threads")
        return [r["tid"] for r in cur.fetchall()]


# ── Replies ────────────────────────────────────────────────────────────────────

def get_cached_replies(tid: str, page: int) -> list[dict]:
    with _db() as conn:
        cur = conn.execute("""
            SELECT * FROM notable_replies
            WHERE tid=? AND page_num=?
            ORDER BY dateline ASC
        """, (tid, page))
        return list(cur.fetchall())


def get_reply_cache_ts(tid: str) -> int | None:
    with _db() as conn:
        cur = conn.execute(
            "SELECT MAX(cached_at) as ts FROM notable_replies WHERE tid=?", (tid,)
        )
        row = cur.fetchone()
        return row["ts"] if row and row["ts"] else None


def upsert_replies(replies: list[dict], tid: str, page_num: int):
    now = int(time.time())
    with _db() as conn:
        for r in replies:
            conn.execute("""
                INSERT INTO notable_replies
                    (tid, pid, uid, username, avatar, dateline, message, page_num, cached_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(pid) DO UPDATE SET
                    username=excluded.username, avatar=excluded.avatar,
                    message=excluded.message, cached_at=excluded.cached_at
            """, (
                tid,
                str(r.get("pid", "")),
                str(r.get("uid", "")),
                r.get("username", ""),
                r.get("avatar", ""),
                int(r.get("dateline", 0)),
                r.get("message", ""),
                page_num,
                now,
            ))


def clear_reply_cache(tid: str):
    with _db() as conn:
        conn.execute("DELETE FROM notable_replies WHERE tid=?", (tid,))