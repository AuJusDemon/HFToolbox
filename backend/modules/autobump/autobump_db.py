"""
autobump_db.py — DB layer for the autobump module.

Separate file so it doesn't pollute the framework db.py.
Call autobump_db.init() once on module startup.
"""

import sqlite3
import json
import time
from pathlib import Path
from contextlib import contextmanager

DB_PATH = Path("data/hf_dash.db")

def _connect():
    conn = sqlite3.connect(str(DB_PATH), check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    return conn

@contextmanager
def _db():
    conn = _connect()
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()

def init():
    with _db() as conn:
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS bump_jobs (
                id           INTEGER PRIMARY KEY AUTOINCREMENT,
                uid          TEXT NOT NULL,          -- owner
                tid          TEXT NOT NULL,
                fid          TEXT,                   -- cached forum ID
                thread_title TEXT,                   -- cached title
                interval_h   INTEGER NOT NULL,       -- hours between bumps (min 6)
                enabled      INTEGER NOT NULL DEFAULT 1,
                last_bumped  INTEGER,                -- unix timestamp
                next_bump    INTEGER,                -- unix timestamp
                last_skip    INTEGER,                -- last time we skipped (post was fresh)
                bump_count   INTEGER NOT NULL DEFAULT 0,
                lastpost_ts  INTEGER,
                lastposter   TEXT,
                created_at   INTEGER DEFAULT (strftime('%s','now')),
                UNIQUE(uid, tid)
            );

            CREATE TABLE IF NOT EXISTS bump_log (
                id        INTEGER PRIMARY KEY AUTOINCREMENT,
                job_id    INTEGER NOT NULL,
                uid       TEXT NOT NULL,
                tid       TEXT NOT NULL,
                action    TEXT NOT NULL,  -- 'bumped' | 'skipped' | 'error'
                reason    TEXT,
                ts        INTEGER DEFAULT (strftime('%s','now'))
            );
        """)


# ── Jobs ───────────────────────────────────────────────────────────────────────


    _migrate()
def _migrate():
    with _db() as conn:
        existing = {r[1] for r in conn.execute("PRAGMA table_info(bump_jobs)").fetchall()}
        for col, typ in [("lastpost_ts","INTEGER"),("lastposter","TEXT")]:
            if col not in existing:
                conn.execute(f"ALTER TABLE bump_jobs ADD COLUMN {col} {typ}")


def add_job(uid: str, tid: str, interval_h: int, next_bump_override: int | None = None) -> dict:
    now = int(time.time())
    next_bump = next_bump_override if next_bump_override is not None else now + (interval_h * 3600)
    with _db() as conn:
        conn.execute("""
            INSERT INTO bump_jobs (uid, tid, interval_h, next_bump)
            VALUES (?, ?, ?, ?)
            ON CONFLICT(uid, tid) DO UPDATE SET
                interval_h=excluded.interval_h,
                enabled=1,
                next_bump=excluded.next_bump
        """, (uid, str(tid), interval_h, next_bump))
    return get_job(uid, str(tid))


def remove_job(uid: str, tid: str) -> None:
    with _db() as conn:
        conn.execute("DELETE FROM bump_jobs WHERE uid=? AND tid=?", (uid, str(tid)))


def get_job(uid: str, tid: str) -> dict | None:
    with _db() as conn:
        row = conn.execute(
            "SELECT * FROM bump_jobs WHERE uid=? AND tid=?", (uid, str(tid))
        ).fetchone()
        return dict(row) if row else None


def get_jobs_for_user(uid: str) -> list[dict]:
    with _db() as conn:
        rows = conn.execute(
            "SELECT * FROM bump_jobs WHERE uid=? ORDER BY created_at DESC", (uid,)
        ).fetchall()
        return [dict(r) for r in rows]


def get_all_due_jobs() -> list[dict]:
    """All enabled jobs where next_bump <= now."""
    now = int(time.time())
    with _db() as conn:
        rows = conn.execute(
            "SELECT * FROM bump_jobs WHERE enabled=1 AND next_bump <= ?", (now,)
        ).fetchall()
        return [dict(r) for r in rows]


def set_job_enabled(uid: str, tid: str, enabled: bool) -> None:
    with _db() as conn:
        conn.execute(
            "UPDATE bump_jobs SET enabled=? WHERE uid=? AND tid=?",
            (int(enabled), uid, str(tid))
        )


def update_after_bump(job_id: int, interval_h: int, thread_title: str | None, fid: str | None, lastpost_ts: int | None = None, lastposter: str | None = None) -> None:
    now = int(time.time())
    next_bump = now + (interval_h * 3600)
    with _db() as conn:
        conn.execute("""
            UPDATE bump_jobs SET
                last_bumped=?, next_bump=?,
                bump_count=bump_count+1,
                thread_title=COALESCE(?, thread_title),
                fid=COALESCE(?, fid),
                lastpost_ts=COALESCE(?, lastpost_ts),
                lastposter=COALESCE(?, lastposter)
            WHERE id=?
        """, (now, next_bump, thread_title, fid, lastpost_ts, lastposter, job_id))


def update_after_skip(job_id: int, next_bump: int) -> None:
    now = int(time.time())
    with _db() as conn:
        conn.execute(
            "UPDATE bump_jobs SET last_skip=?, next_bump=? WHERE id=?",
            (now, next_bump, job_id)
        )


def log_action(job_id: int, uid: str, tid: str, action: str, reason: str | None = None) -> None:
    with _db() as conn:
        conn.execute(
            "INSERT INTO bump_log (job_id, uid, tid, action, reason) VALUES (?,?,?,?,?)",
            (job_id, uid, str(tid), action, reason)
        )


def get_log(uid: str, limit: int = 20) -> list[dict]:
    with _db() as conn:
        rows = conn.execute("""
            SELECT bl.*, bj.thread_title FROM bump_log bl
            LEFT JOIN bump_jobs bj ON bj.id=bl.job_id
            WHERE bl.uid=?
            ORDER BY bl.ts DESC LIMIT ?
        """, (uid, limit)).fetchall()
        return [dict(r) for r in rows]


def get_last_log_ts() -> int | None:
    """Returns the timestamp of the most recent bump log entry, or None."""
    try:
        with _db() as conn:
            row = conn.execute("SELECT MAX(ts) FROM bump_log").fetchone()
            return row[0] if row and row[0] else None
    except Exception:
        return None


def delete_user_jobs(uid: str) -> None:
    """Delete all bump jobs and log entries for a user."""
    with _db() as conn:
        conn.execute("DELETE FROM bump_jobs WHERE uid=?", (uid,))
        conn.execute("DELETE FROM bump_log WHERE uid=?", (uid,))
