"""
autobump_db.py — DB layer for the autobump module.
"""

import sqlite3
import time
from pathlib import Path
from contextlib import contextmanager

DB_PATH = Path("data/hf_dash.db")


def _connect() -> sqlite3.Connection:
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


def init() -> None:
    with _db() as conn:
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS bump_jobs (
                id           INTEGER PRIMARY KEY AUTOINCREMENT,
                uid          TEXT    NOT NULL,
                tid          TEXT    NOT NULL,
                fid          TEXT,
                thread_title TEXT,
                mode         TEXT    NOT NULL DEFAULT 'timer',
                interval_h   INTEGER NOT NULL,
                enabled      INTEGER NOT NULL DEFAULT 1,
                last_bumped  INTEGER,
                next_bump    INTEGER,
                last_skip    INTEGER,
                bump_count   INTEGER NOT NULL DEFAULT 0,
                lastpost_ts  INTEGER,
                lastposter   TEXT,
                created_at   INTEGER DEFAULT (strftime('%s','now')),
                bump_until   INTEGER DEFAULT NULL,
                UNIQUE(uid, tid)
            );

            CREATE TABLE IF NOT EXISTS bump_log (
                id         INTEGER PRIMARY KEY AUTOINCREMENT,
                job_id     INTEGER NOT NULL,
                uid        TEXT    NOT NULL,
                tid        TEXT    NOT NULL,
                action     TEXT    NOT NULL,
                reason     TEXT,
                numreplies INTEGER DEFAULT NULL,
                ts         INTEGER DEFAULT (strftime('%s','now'))
            );

            CREATE TABLE IF NOT EXISTS autobump_settings (
                uid           TEXT    PRIMARY KEY,
                weekly_budget INTEGER NOT NULL DEFAULT 0
            );
        """)
    _migrate()


def _migrate() -> None:
    """Add columns to existing DBs that predate this schema."""
    with _db() as conn:
        existing_jobs = {r[1] for r in conn.execute("PRAGMA table_info(bump_jobs)").fetchall()}
        for col, defn in [
            ("lastpost_ts", "INTEGER"),
            ("lastposter",  "TEXT"),
            ("bump_until",  "INTEGER DEFAULT NULL"),
            ("mode",        "TEXT NOT NULL DEFAULT 'timer'"),
        ]:
            if col not in existing_jobs:
                try:
                    conn.execute(f"ALTER TABLE bump_jobs ADD COLUMN {col} {defn}")
                except Exception:
                    pass

        existing_log = {r[1] for r in conn.execute("PRAGMA table_info(bump_log)").fetchall()}
        if "numreplies" not in existing_log:
            try:
                conn.execute("ALTER TABLE bump_log ADD COLUMN numreplies INTEGER DEFAULT NULL")
            except Exception:
                pass


# ── Settings ──────────────────────────────────────────────────────────────────

def get_settings(uid: str) -> dict:
    with _db() as conn:
        row = conn.execute(
            "SELECT * FROM autobump_settings WHERE uid=?", (uid,)
        ).fetchone()
        return dict(row) if row else {"uid": uid, "weekly_budget": 0}


def set_settings(uid: str, weekly_budget: int) -> None:
    with _db() as conn:
        conn.execute("""
            INSERT INTO autobump_settings (uid, weekly_budget) VALUES (?, ?)
            ON CONFLICT(uid) DO UPDATE SET weekly_budget=excluded.weekly_budget
        """, (uid, weekly_budget))


def get_weekly_bump_count(uid: str) -> int:
    """Count successful bumps in the last 7 days for this user."""
    since = int(time.time()) - (7 * 86400)
    with _db() as conn:
        row = conn.execute(
            "SELECT COUNT(*) FROM bump_log WHERE uid=? AND action='bumped' AND ts >= ?",
            (uid, since)
        ).fetchone()
        return int(row[0]) if row else 0


# ── Jobs ──────────────────────────────────────────────────────────────────────

def add_job(uid: str, tid: str, interval_h: int,
            mode: str = "timer",
            next_bump_override: int | None = None,
            bump_until: int | None = None) -> dict:
    now = int(time.time())
    next_bump = next_bump_override if next_bump_override is not None else now + (interval_h * 3600)
    with _db() as conn:
        conn.execute("""
            INSERT INTO bump_jobs (uid, tid, mode, interval_h, next_bump, bump_until, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(uid, tid) DO UPDATE SET
                mode=excluded.mode,
                interval_h=excluded.interval_h,
                enabled=1,
                next_bump=excluded.next_bump,
                bump_until=excluded.bump_until
        """, (uid, str(tid), mode, interval_h, next_bump, bump_until, now))
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
    """All enabled jobs where next_bump <= now and not expired."""
    now = int(time.time())
    with _db() as conn:
        rows = conn.execute(
            """SELECT * FROM bump_jobs
               WHERE enabled=1 AND next_bump <= ?
               AND (bump_until IS NULL OR bump_until > ?)""",
            (now, now)
        ).fetchall()
        return [dict(r) for r in rows]


def expire_jobs() -> list[str]:
    """Disable jobs whose bump_until has passed. Returns list of disabled TIDs."""
    now = int(time.time())
    with _db() as conn:
        rows = conn.execute(
            "SELECT tid FROM bump_jobs WHERE enabled=1 AND bump_until IS NOT NULL AND bump_until <= ?",
            (now,)
        ).fetchall()
        if rows:
            conn.execute(
                "UPDATE bump_jobs SET enabled=0 WHERE enabled=1 AND bump_until IS NOT NULL AND bump_until <= ?",
                (now,)
            )
        return [r["tid"] for r in rows]


def set_job_enabled(uid: str, tid: str, enabled: bool) -> None:
    with _db() as conn:
        conn.execute(
            "UPDATE bump_jobs SET enabled=? WHERE uid=? AND tid=?",
            (int(enabled), uid, str(tid))
        )


def update_after_bump(job_id: int, interval_h: int, thread_title: str | None,
                      fid: str | None, lastpost_ts: int | None = None,
                      lastposter: str | None = None,
                      mode: str = "timer") -> None:
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


def log_action(job_id: int, uid: str, tid: str, action: str,
               reason: str | None = None, numreplies: int | None = None) -> None:
    now = int(time.time())
    with _db() as conn:
        conn.execute(
            "INSERT INTO bump_log (job_id, uid, tid, action, reason, numreplies, ts) VALUES (?,?,?,?,?,?,?)",
            (job_id, uid, str(tid), action, reason, numreplies, now)
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


def get_job_stats(uid: str, tid: str) -> dict:
    """Full stats for a single job: bump history with reply gain calculations."""
    with _db() as conn:
        bumps = conn.execute("""
            SELECT ts, numreplies, reason FROM bump_log
            WHERE uid=? AND tid=? AND action='bumped'
            ORDER BY ts ASC
        """, (uid, str(tid))).fetchall()
        bumps = [dict(r) for r in bumps]

        gains = []
        for i in range(1, len(bumps)):
            prev_r = bumps[i-1]["numreplies"]
            curr_r = bumps[i]["numreplies"]
            if prev_r is not None and curr_r is not None:
                gains.append(curr_r - prev_r)

        avg_gain = round(sum(gains) / len(gains), 1) if gains else None

        skip_row = conn.execute(
            "SELECT COUNT(*) FROM bump_log WHERE uid=? AND tid=? AND action='skipped'",
            (uid, str(tid))
        ).fetchone()
        skip_count = int(skip_row[0]) if skip_row else 0

        job_row = conn.execute(
            "SELECT created_at, bump_count, mode, interval_h, fid FROM bump_jobs WHERE uid=? AND tid=?",
            (uid, str(tid))
        ).fetchone()
        job_info = dict(job_row) if job_row else {}

    return {
        "bump_history":   bumps[-20:],
        "total_bumps":    len(bumps),
        "total_skips":    skip_count,
        "bytes_spent":    len(bumps) * 50,
        "avg_reply_gain": avg_gain,
        "reply_gains":    gains[-20:],
        "job_info":       job_info,
    }


def get_last_log_ts() -> int | None:
    try:
        with _db() as conn:
            row = conn.execute("SELECT MAX(ts) FROM bump_log").fetchone()
            return row[0] if row and row[0] else None
    except Exception:
        return None


def delete_user_jobs(uid: str) -> None:
    with _db() as conn:
        conn.execute("DELETE FROM bump_jobs WHERE uid=?", (uid,))
        conn.execute("DELETE FROM bump_log WHERE uid=?", (uid,))
        conn.execute("DELETE FROM autobump_settings WHERE uid=?", (uid,))
