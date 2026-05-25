"""
autobump_db.py — DB layer for the autobump module.
"""

import time
from _db_compat import _db


def init():
    with _db() as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS bump_jobs (
                id           INT          NOT NULL AUTO_INCREMENT,
                uid          VARCHAR(64)  NOT NULL,
                tid          VARCHAR(64)  NOT NULL,
                fid          VARCHAR(64),
                thread_title VARCHAR(512),
                mode         VARCHAR(16)  NOT NULL DEFAULT 'timer',
                interval_h   INT          NOT NULL,
                enabled      TINYINT      NOT NULL DEFAULT 1,
                last_bumped  BIGINT,
                next_bump    BIGINT,
                last_skip    BIGINT,
                bump_count   INT          NOT NULL DEFAULT 0,
                lastpost_ts  BIGINT,
                lastposter   VARCHAR(255),
                created_at   BIGINT       DEFAULT 0,
                bump_until   BIGINT       DEFAULT NULL,
                PRIMARY KEY (id),
                UNIQUE KEY uq_uid_tid (uid, tid),
                INDEX idx_bj_uid (uid)
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS bump_log (
                id         INT          NOT NULL AUTO_INCREMENT,
                job_id     INT          NOT NULL,
                uid        VARCHAR(64)  NOT NULL,
                tid        VARCHAR(64)  NOT NULL,
                action     VARCHAR(64)  NOT NULL,
                reason     TEXT,
                numreplies INT          DEFAULT NULL,
                ts         BIGINT       DEFAULT 0,
                PRIMARY KEY (id),
                INDEX idx_bl_uid (uid),
                INDEX idx_bl_uid_tid (uid, tid)
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS autobump_settings (
                uid            VARCHAR(64) NOT NULL,
                weekly_budget  INT         NOT NULL DEFAULT 0,
                PRIMARY KEY (uid)
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
        """)
    _migrate()


def _migrate():
    with _db() as conn:
        for col, defn in [
            ("lastpost_ts", "BIGINT"),
            ("lastposter",  "VARCHAR(255)"),
            ("bump_until",  "BIGINT DEFAULT NULL"),
            ("mode",        "VARCHAR(16) NOT NULL DEFAULT 'timer'"),
            ("numreplies",  "INT DEFAULT NULL"),  # bump_log column
        ]:
            # bump_jobs migrations
            if col not in ("numreplies",):
                try:
                    conn.execute(f"ALTER TABLE bump_jobs ADD COLUMN {col} {defn}")
                except Exception:
                    pass
            # bump_log numreplies
            if col == "numreplies":
                try:
                    conn.execute(f"ALTER TABLE bump_log ADD COLUMN {col} {defn}")
                except Exception:
                    pass


# ── Settings ───────────────────────────────────────────────────────────────────

def get_settings(uid: str) -> dict:
    with _db() as conn:
        row = conn.execute(
            "SELECT * FROM autobump_settings WHERE uid=%s", (uid,)
        ).fetchone()
        if row:
            return dict(row)
        return {"uid": uid, "weekly_budget": 0}


def set_settings(uid: str, weekly_budget: int) -> None:
    with _db() as conn:
        conn.execute("""
            INSERT INTO autobump_settings (uid, weekly_budget)
            VALUES (%s, %s)
            ON DUPLICATE KEY UPDATE weekly_budget=VALUES(weekly_budget)
        """, (uid, weekly_budget))


def get_weekly_bump_count(uid: str) -> int:
    """Count successful bumps in the last 7 days for this user."""
    since = int(time.time()) - (7 * 86400)
    with _db() as conn:
        row = conn.execute(
            "SELECT COUNT(*) as cnt FROM bump_log WHERE uid=%s AND action='bumped' AND ts >= %s",
            (uid, since)
        ).fetchone()
        return int(row["cnt"]) if row else 0


# ── Jobs ───────────────────────────────────────────────────────────────────────

def add_job(uid: str, tid: str, interval_h: int,
            mode: str = "timer",
            next_bump_override: int | None = None,
            bump_until: int | None = None) -> dict:
    now = int(time.time())
    next_bump = next_bump_override if next_bump_override is not None else now + (interval_h * 3600)
    with _db() as conn:
        conn.execute("""
            INSERT INTO bump_jobs (uid, tid, mode, interval_h, next_bump, bump_until, created_at)
            VALUES (%s, %s, %s, %s, %s, %s, %s)
            ON DUPLICATE KEY UPDATE
                mode=VALUES(mode),
                interval_h=VALUES(interval_h),
                enabled=1,
                next_bump=VALUES(next_bump),
                bump_until=VALUES(bump_until)
        """, (uid, str(tid), mode, interval_h, next_bump, bump_until, now))
    return get_job(uid, str(tid))


def remove_job(uid: str, tid: str) -> None:
    with _db() as conn:
        conn.execute("DELETE FROM bump_jobs WHERE uid=%s AND tid=%s", (uid, str(tid)))


def get_job(uid: str, tid: str) -> dict | None:
    with _db() as conn:
        row = conn.execute(
            "SELECT * FROM bump_jobs WHERE uid=%s AND tid=%s", (uid, str(tid))
        ).fetchone()
        return dict(row) if row else None


def get_jobs_for_user(uid: str) -> list[dict]:
    with _db() as conn:
        rows = conn.execute(
            "SELECT * FROM bump_jobs WHERE uid=%s ORDER BY created_at DESC", (uid,)
        ).fetchall()
        return [dict(r) for r in rows]


def get_due_jobs_for_uid(uid: str) -> list[dict]:
    """Due jobs for a single user — called from poll_autobump per-user."""
    now = int(time.time())
    with _db() as conn:
        rows = conn.execute(
            """SELECT * FROM bump_jobs
               WHERE uid=%s AND enabled=1 AND next_bump <= %s
               AND (bump_until IS NULL OR bump_until > %s)""",
            (uid, now, now)
        ).fetchall()
        return [dict(r) for r in rows]


def get_all_due_jobs() -> list[dict]:
    """All enabled jobs where next_bump <= now and not expired (all users)."""
    now = int(time.time())
    with _db() as conn:
        rows = conn.execute(
            """SELECT * FROM bump_jobs
               WHERE enabled=1 AND next_bump <= %s
               AND (bump_until IS NULL OR bump_until > %s)""",
            (now, now)
        ).fetchall()
        return [dict(r) for r in rows]


def expire_jobs() -> list[str]:
    """Disable jobs whose bump_until has passed."""
    now = int(time.time())
    with _db() as conn:
        rows = conn.execute(
            "SELECT tid, uid FROM bump_jobs WHERE enabled=1 AND bump_until IS NOT NULL AND bump_until <= %s",
            (now,)
        ).fetchall()
        if rows:
            conn.execute(
                "UPDATE bump_jobs SET enabled=0 WHERE enabled=1 AND bump_until IS NOT NULL AND bump_until <= %s",
                (now,)
            )
        return [r["tid"] for r in rows]


def set_job_enabled(uid: str, tid: str, enabled: bool) -> None:
    with _db() as conn:
        conn.execute(
            "UPDATE bump_jobs SET enabled=%s WHERE uid=%s AND tid=%s",
            (int(enabled), uid, str(tid))
        )


def update_after_bump(job_id: int, thread_title: str | None,
                      fid: str | None, lastpost_ts: int | None = None,
                      lastposter: str | None = None) -> None:
    """Update metadata and bump_count after a successful bump.
    NOTE: next_bump is set by update_after_skip BEFORE the bump attempt — not here.
    """
    now = int(time.time())
    with _db() as conn:
        conn.execute("""
            UPDATE bump_jobs SET
                last_bumped=%s,
                bump_count=bump_count+1,
                thread_title=COALESCE(%s, thread_title),
                fid=COALESCE(%s, fid),
                lastpost_ts=COALESCE(%s, lastpost_ts),
                lastposter=COALESCE(%s, lastposter)
            WHERE id=%s
        """, (now, thread_title, fid, lastpost_ts, lastposter, job_id))


def update_after_skip(job_id: int, next_bump: int) -> None:
    now = int(time.time())
    with _db() as conn:
        conn.execute(
            "UPDATE bump_jobs SET last_skip=%s, next_bump=%s WHERE id=%s",
            (now, next_bump, job_id)
        )


def log_action(job_id: int, uid: str, tid: str, action: str,
               reason: str | None = None, numreplies: int | None = None) -> None:
    now = int(time.time())
    with _db() as conn:
        conn.execute(
            "INSERT INTO bump_log (job_id, uid, tid, action, reason, numreplies, ts) VALUES (%s,%s,%s,%s,%s,%s,%s)",
            (job_id, uid, str(tid), action, reason, numreplies, now)
        )


def get_log(uid: str, limit: int = 20) -> list[dict]:
    with _db() as conn:
        rows = conn.execute("""
            SELECT bl.*, bj.thread_title FROM bump_log bl
            LEFT JOIN bump_jobs bj ON bj.id=bl.job_id
            WHERE bl.uid=%s
            ORDER BY bl.ts DESC LIMIT %s
        """, (uid, limit)).fetchall()
        return [dict(r) for r in rows]


def get_job_stats(uid: str, tid: str) -> dict:
    """Full stats for a single job: bump history with numreplies, reply gain calculations."""
    with _db() as conn:
        # All bumps for this thread, oldest first (for reply gain calc)
        bumps = conn.execute("""
            SELECT ts, numreplies, reason FROM bump_log
            WHERE uid=%s AND tid=%s AND action='bumped'
            ORDER BY ts ASC
        """, (uid, str(tid))).fetchall()
        bumps = [dict(r) for r in bumps]

        # Calculate reply gains between consecutive bumps
        gains = []
        for i in range(1, len(bumps)):
            prev_r = bumps[i-1]["numreplies"]
            curr_r = bumps[i]["numreplies"]
            if prev_r is not None and curr_r is not None:
                gains.append(curr_r - prev_r)

        avg_gain = round(sum(gains) / len(gains), 1) if gains else None

        # Skip count
        skip_count = conn.execute(
            "SELECT COUNT(*) as cnt FROM bump_log WHERE uid=%s AND tid=%s AND action='skipped'",
            (uid, str(tid))
        ).fetchone()
        skip_count = int(skip_count["cnt"]) if skip_count else 0

        # First job created_at
        job_row = conn.execute(
            "SELECT created_at, bump_count, mode, interval_h, fid FROM bump_jobs WHERE uid=%s AND tid=%s",
            (uid, str(tid))
        ).fetchone()
        job_info = dict(job_row) if job_row else {}

    return {
        "bump_history":  bumps[-20:],   # last 20 bumps
        "total_bumps":   len(bumps),
        "total_skips":   skip_count,
        "bytes_spent":   None,  # caller should compute using user's group-based fee
        "avg_reply_gain": avg_gain,
        "reply_gains":   gains[-20:],
        "job_info":      job_info,
    }


def get_bumped_since(uid: str, since_ts: int) -> list[dict]:
    """Return bump log entries (action='bumped') since since_ts, with thread title."""
    with _db() as conn:
        rows = conn.execute("""
            SELECT bl.tid, bl.ts, bj.thread_title
            FROM bump_log bl
            LEFT JOIN bump_jobs bj ON bj.id = bl.job_id
            WHERE bl.uid=%s AND bl.action='bumped' AND bl.ts >= %s
            ORDER BY bl.ts DESC
        """, (uid, since_ts)).fetchall()
    return [dict(r) for r in rows]


def get_last_log_ts() -> int | None:
    try:
        with _db() as conn:
            row = conn.execute("SELECT MAX(ts) FROM bump_log").fetchone()
            return list(row.values())[0] if row else None
    except Exception:
        return None


def delete_user_jobs(uid: str) -> None:
    with _db() as conn:
        conn.execute("DELETE FROM bump_jobs WHERE uid=%s", (uid,))
        conn.execute("DELETE FROM bump_log WHERE uid=%s", (uid,))
        conn.execute("DELETE FROM autobump_settings WHERE uid=%s", (uid,))
