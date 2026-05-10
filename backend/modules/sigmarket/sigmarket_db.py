"""
modules/sigmarket/sigmarket_db.py — persistence for sigmarket auto-rotate.

Table: sigmarket_rotations
  uid          TEXT
  sigs         TEXT  — JSON array of BBCode strings (ordered)
  interval_h   INTEGER — minimum hours between rotations
  enabled      INTEGER — 0/1
  last_rotated INTEGER — unix timestamp of last changesig call
  current_idx  INTEGER — index of currently active sig
"""

import sqlite3
import json
import os
from pathlib import Path
from contextlib import contextmanager

DB_PATH = Path(os.getenv("DB_PATH", "data/hf_dash.db"))


def _connect() -> sqlite3.Connection:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(DB_PATH), check_same_thread=False, timeout=10)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA busy_timeout=10000")
    conn.execute("PRAGMA synchronous=NORMAL")
    return conn


@contextmanager
def _db():
    conn = _connect()
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


def init_sigmarket_db() -> None:
    with _db() as conn:
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS sigmarket_rotations (
                uid          TEXT PRIMARY KEY,
                sigs         TEXT    NOT NULL DEFAULT '[]',
                interval_h   INTEGER NOT NULL DEFAULT 6,
                enabled      INTEGER NOT NULL DEFAULT 0,
                last_rotated INTEGER NOT NULL DEFAULT 0,
                current_idx  INTEGER NOT NULL DEFAULT 0
            );
        """)


def get_rotation(uid: str) -> dict | None:
    with _db() as conn:
        row = conn.execute(
            "SELECT * FROM sigmarket_rotations WHERE uid = ?", (uid,)
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
            VALUES (?, ?, ?, ?, 0, 0)
            ON CONFLICT(uid) DO UPDATE SET
                sigs       = excluded.sigs,
                interval_h = excluded.interval_h,
                enabled    = excluded.enabled
        """, (uid, json.dumps(sigs), int(interval_h), int(enabled)))


def set_rotation_enabled(uid: str, enabled: bool) -> None:
    with _db() as conn:
        conn.execute(
            "UPDATE sigmarket_rotations SET enabled = ? WHERE uid = ?",
            (int(enabled), uid)
        )


def advance_rotation(uid: str, new_idx: int, now: int) -> None:
    with _db() as conn:
        conn.execute("""
            UPDATE sigmarket_rotations
            SET current_idx = ?, last_rotated = ?
            WHERE uid = ?
        """, (new_idx, now, uid))


def get_all_rotation_uids() -> list[str]:
    with _db() as conn:
        rows = conn.execute(
            "SELECT uid FROM sigmarket_rotations WHERE enabled = 1"
        ).fetchall()
    return [r["uid"] for r in rows]
