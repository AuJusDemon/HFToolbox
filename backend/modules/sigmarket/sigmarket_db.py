"""
modules/sigmarket/sigmarket_db.py — persistence for sigmarket auto-rotate.

Table: sigmarket_rotations
  uid          VARCHAR — primary key
  sigs         TEXT    — JSON array of BBCode strings (ordered)
  interval_h   INT     — minimum hours between rotations
  enabled      TINYINT — 0/1
  last_rotated BIGINT  — unix timestamp of last changesig call
  current_idx  INT     — index of currently active sig
"""

import json
from _db_compat import _db


def init_sigmarket_db() -> None:
    with _db() as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS sigmarket_rotations (
                uid          VARCHAR(64)  NOT NULL,
                sigs         TEXT         NOT NULL DEFAULT '[]',
                interval_h   INT          NOT NULL DEFAULT 6,
                enabled      TINYINT      NOT NULL DEFAULT 0,
                last_rotated BIGINT       NOT NULL DEFAULT 0,
                current_idx  INT          NOT NULL DEFAULT 0,
                PRIMARY KEY (uid)
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
        """)


# ── Rotation config ────────────────────────────────────────────────────────────

def get_rotation(uid: str) -> dict | None:
    with _db() as conn:
        row = conn.execute(
            "SELECT * FROM sigmarket_rotations WHERE uid = %s", (uid,)
        ).fetchone()
    if not row:
        return None
    r = dict(row)
    r["sigs"] = json.loads(r["sigs"] or "[]")
    return r


def upsert_rotation(uid: str, sigs: list, interval_h: int, enabled: bool) -> None:
    with _db() as conn:
        conn.execute("""
            INSERT INTO sigmarket_rotations (uid, sigs, interval_h, enabled, last_rotated, current_idx)
            VALUES (%s, %s, %s, %s, 0, 0)
            ON DUPLICATE KEY UPDATE
                sigs       = VALUES(sigs),
                interval_h = VALUES(interval_h),
                enabled    = VALUES(enabled)
        """, (uid, json.dumps(sigs), int(interval_h), int(enabled)))


def set_rotation_enabled(uid: str, enabled: bool) -> None:
    with _db() as conn:
        conn.execute(
            "UPDATE sigmarket_rotations SET enabled = %s WHERE uid = %s",
            (int(enabled), uid)
        )


def advance_rotation(uid: str, new_idx: int, now: int) -> None:
    """Called after a successful changesig — record the new index and timestamp."""
    with _db() as conn:
        conn.execute("""
            UPDATE sigmarket_rotations
            SET current_idx = %s, last_rotated = %s
            WHERE uid = %s
        """, (new_idx, now, uid))


def get_all_rotation_uids() -> list[str]:
    """All UIDs with rotation enabled."""
    with _db() as conn:
        rows = conn.execute("""
            SELECT uid FROM sigmarket_rotations
            WHERE enabled = 1
        """).fetchall()
    return [r["uid"] for r in rows]
