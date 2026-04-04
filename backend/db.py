"""
db.py — Framework-level persistence only.

Tables:
  users        — authenticated users (uid, token, avatar, username)
  module_prefs — per-user module enabled/disabled state

Modules manage their own data in their own tables.
Call db.init_db() once on startup.
"""

import sqlite3
import json
import asyncio
import os
from pathlib import Path
from contextlib import contextmanager
import crypto

DB_PATH = Path(os.getenv("DB_PATH", "data/hf_dash.db"))


def _connect() -> sqlite3.Connection:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(DB_PATH), check_same_thread=False, timeout=10)  # str() for Windows compat
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA busy_timeout=10000")   # 10s busy wait before error, not infinite hang
    conn.execute("PRAGMA synchronous=NORMAL")   # faster writes, still safe with WAL
    return conn


@contextmanager
def _db():
    conn = _connect()
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


def init_db() -> None:
    with _db() as conn:
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS users (
                uid          TEXT PRIMARY KEY,
                username     TEXT,
                token        TEXT NOT NULL,
                avatar       TEXT,
                groups       TEXT DEFAULT '[]',
                -- Cached HF profile fields (refreshed on login + manual refresh)
                postnum      INTEGER,
                threadnum    INTEGER,
                reputation   INTEGER,
                myps         TEXT,
                usertitle    TEXT,
                timeonline   INTEGER,
                profile_ts   INTEGER,  -- when profile was last fetched
                created_at   INTEGER DEFAULT (strftime('%s','now')),
                last_seen      INTEGER DEFAULT (strftime('%s','now')),
                needs_refresh  INTEGER NOT NULL DEFAULT 0
            );

            CREATE TABLE IF NOT EXISTS module_prefs (
                uid       TEXT NOT NULL,
                module_id TEXT NOT NULL,
                enabled   INTEGER NOT NULL DEFAULT 1,
                PRIMARY KEY (uid, module_id)
            );

        """)

    _init_dash_cache()
    init_bytes_history()
    init_contracts_history()
    # Migrate existing DBs that predate profile columns
    with _db() as conn:
        existing = {r[1] for r in conn.execute("PRAGMA table_info(users)").fetchall()}
        for col, typ in [
            ("postnum",       "INTEGER"),
            ("threadnum",     "INTEGER"),
            ("reputation",    "INTEGER"),
            ("myps",          "TEXT"),
            ("vault",         "TEXT"),
            ("usertitle",     "TEXT"),
            ("timeonline",    "INTEGER"),
            ("profile_ts",    "INTEGER"),
            ("needs_refresh", "INTEGER DEFAULT 0"),
        ]:
            if col not in existing:
                conn.execute(f"ALTER TABLE users ADD COLUMN {col} {typ}")


# ── Users ──────────────────────────────────────────────────────────────────────

def upsert_user(uid: str, username: str, token: str, avatar: str = "", groups: list[str] = []) -> None:
    token = crypto.encrypt_token(token)
    with _db() as conn:
        conn.execute("""
            INSERT INTO users (uid, username, token, avatar, groups, last_seen)
            VALUES (?, ?, ?, ?, ?, strftime('%s','now'))
            ON CONFLICT(uid) DO UPDATE SET
                username=excluded.username, token=excluded.token,
                avatar=excluded.avatar, groups=excluded.groups,
                last_seen=excluded.last_seen
        """, (uid, username, token, avatar, json.dumps(groups)))


def get_user(uid: str) -> dict | None:
    with _db() as conn:
        row = conn.execute("SELECT * FROM users WHERE uid=?", (uid,)).fetchone()
        if not row:
            return None
        d = dict(row)
        d["groups"] = json.loads(d.get("groups") or "[]")
        return d


def get_token(uid: str) -> str | None:
    u = get_user(uid)
    return crypto.decrypt_token(u["token"]) if u else None


# ── Notifications ─────────────────────────────────────────────────────────────

def init_notifications_table() -> None:
    with _db() as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS notifications (
                id         INTEGER PRIMARY KEY AUTOINCREMENT,
                uid        TEXT NOT NULL,
                type       TEXT NOT NULL,
                title      TEXT NOT NULL,
                body       TEXT,
                link       TEXT,
                ref_id     TEXT,
                seen       INTEGER NOT NULL DEFAULT 0,
                created_at INTEGER NOT NULL DEFAULT (strftime('%s','now'))
            )
        """)
        conn.execute("CREATE INDEX IF NOT EXISTS idx_notif_uid ON notifications(uid, seen, created_at)")


def add_notification(uid: str, type_: str, title: str, body: str = '', link: str = '', ref_id: str = '') -> None:
    with _db() as conn:
        existing = conn.execute(
            "SELECT id FROM notifications WHERE uid=? AND type=? AND ref_id=? AND seen=0",
            (uid, type_, ref_id)
        ).fetchone()
        if existing:
            return
        conn.execute(
            "INSERT INTO notifications (uid, type, title, body, link, ref_id) VALUES (?,?,?,?,?,?)",
            (uid, type_, title, body, link, ref_id)
        )


def get_notifications(uid: str, limit: int = 30) -> list:
    with _db() as conn:
        rows = conn.execute(
            "SELECT id,type,title,body,link,ref_id,seen,created_at FROM notifications "
            "WHERE uid=? ORDER BY created_at DESC LIMIT ?",
            (uid, limit)
        ).fetchall()
        return [dict(r) for r in rows]


def get_unseen_count(uid: str) -> int:
    with _db() as conn:
        row = conn.execute(
            "SELECT COUNT(*) FROM notifications WHERE uid=? AND seen=0", (uid,)
        ).fetchone()
        return row[0] if row else 0


def mark_notifications_seen(uid: str) -> None:
    with _db() as conn:
        conn.execute("UPDATE notifications SET seen=1 WHERE uid=? AND seen=0", (uid,))


def get_last_pm_count(uid: str) -> int | None:
    with _db() as conn:
        row = conn.execute("SELECT last_unreadpms FROM users WHERE uid=?", (uid,)).fetchone()
        return int(row[0]) if row and row[0] is not None else None


def set_last_pm_count(uid: str, count: int) -> None:
    with _db() as conn:
        try:
            conn.execute("ALTER TABLE users ADD COLUMN last_unreadpms INTEGER")
        except Exception:
            pass
        conn.execute("UPDATE users SET last_unreadpms=? WHERE uid=?", (count, uid))


# ── Notifications ─────────────────────────────────────────────────────────────

def init_notifications_table() -> None:
    with _db() as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS notifications (
                id         INTEGER PRIMARY KEY AUTOINCREMENT,
                uid        TEXT NOT NULL,
                type       TEXT NOT NULL,
                title      TEXT NOT NULL,
                body       TEXT,
                link       TEXT,
                ref_id     TEXT,
                seen       INTEGER NOT NULL DEFAULT 0,
                created_at INTEGER NOT NULL DEFAULT (strftime('%s','now'))
            )
        """)
        conn.execute("CREATE INDEX IF NOT EXISTS idx_notif_uid ON notifications(uid, seen, created_at)")


def add_notification(uid: str, type_: str, title: str, body: str = '', link: str = '', ref_id: str = '') -> None:
    with _db() as conn:
        existing = conn.execute(
            "SELECT id FROM notifications WHERE uid=? AND type=? AND ref_id=? AND seen=0",
            (uid, type_, ref_id)
        ).fetchone()
        if existing:
            return
        conn.execute(
            "INSERT INTO notifications (uid, type, title, body, link, ref_id) VALUES (?,?,?,?,?,?)",
            (uid, type_, title, body, link, ref_id)
        )


def get_notifications(uid: str, limit: int = 30) -> list:
    with _db() as conn:
        rows = conn.execute(
            "SELECT id,type,title,body,link,ref_id,seen,created_at FROM notifications "
            "WHERE uid=? ORDER BY created_at DESC LIMIT ?",
            (uid, limit)
        ).fetchall()
        return [dict(r) for r in rows]


def get_unseen_count(uid: str) -> int:
    with _db() as conn:
        row = conn.execute(
            "SELECT COUNT(*) FROM notifications WHERE uid=? AND seen=0", (uid,)
        ).fetchone()
        return row[0] if row else 0


def mark_notifications_seen(uid: str) -> None:
    with _db() as conn:
        conn.execute("UPDATE notifications SET seen=1 WHERE uid=? AND seen=0", (uid,))


def get_existing_contract_cids(uid: str, cids: list) -> set:
    """Return set of CIDs already in contracts_history for this user."""
    if not cids:
        return set()
    with _db() as conn:
        placeholders = ",".join("?" * len(cids))
        rows = conn.execute(
            f"SELECT cid FROM contracts_history WHERE uid=? AND cid IN ({placeholders})",
            (uid, *cids)
        ).fetchall()
        return {row[0] for row in rows}


def get_last_pm_count(uid: str) -> int | None:
    with _db() as conn:
        row = conn.execute("SELECT last_unreadpms FROM users WHERE uid=?", (uid,)).fetchone()
        return int(row[0]) if row and row[0] is not None else None


def set_last_pm_count(uid: str, count: int) -> None:
    with _db() as conn:
        try:
            conn.execute("ALTER TABLE users ADD COLUMN last_unreadpms INTEGER")
        except Exception:
            pass
        conn.execute("UPDATE users SET last_unreadpms=? WHERE uid=?", (count, uid))


def update_user_groups(uid: str, groups: list) -> None:
    """Update stored group list for a user. Called by crawl when groups change."""
    import json
    with _db() as conn:
        conn.execute(
            "UPDATE users SET groups=? WHERE uid=?",
            (json.dumps(groups), uid)
        )


def get_all_uids() -> list[str]:
    with _db() as conn:
        return [r[0] for r in conn.execute("SELECT uid FROM users").fetchall()]


def touch_last_active(uid: str) -> None:
    """Update last_seen to now. Called on every authenticated endpoint hit."""
    import time as _t
    with _db() as conn:
        conn.execute(
            "UPDATE users SET last_seen=? WHERE uid=?",
            (int(_t.time()), uid)
        )


def get_last_active(uid: str) -> int | None:
    """Return last_seen unix timestamp for a user, or None."""
    with _db() as conn:
        row = conn.execute("SELECT last_seen FROM users WHERE uid=?", (uid,)).fetchone()
        return row[0] if row else None


def set_needs_refresh(uid: str, flag: int) -> None:
    """Mark user as needing a crawl on next activity."""
    with _db() as conn:
        conn.execute("UPDATE users SET needs_refresh=? WHERE uid=?", (flag, uid))


def get_needs_refresh(uid: str) -> bool:
    with _db() as conn:
        row = conn.execute("SELECT needs_refresh FROM users WHERE uid=?", (uid,)).fetchone()
        return bool(row[0]) if row else False



# ── Module prefs ───────────────────────────────────────────────────────────────

def set_module_enabled(uid: str, module_id: str, enabled: bool) -> None:
    with _db() as conn:
        conn.execute("""
            INSERT INTO module_prefs (uid, module_id, enabled) VALUES (?,?,?)
            ON CONFLICT(uid, module_id) DO UPDATE SET enabled=excluded.enabled
        """, (uid, module_id, int(enabled)))


def get_module_prefs(uid: str) -> dict[str, bool]:
    with _db() as conn:
        rows = conn.execute(
            "SELECT module_id, enabled FROM module_prefs WHERE uid=?", (uid,)
        ).fetchall()
        return {r["module_id"]: bool(r["enabled"]) for r in rows}


def is_module_enabled(uid: str, module_id: str, default: bool = True) -> bool:
    with _db() as conn:
        row = conn.execute(
            "SELECT enabled FROM module_prefs WHERE uid=? AND module_id=?", (uid, module_id)
        ).fetchone()
        return bool(row["enabled"]) if row else default


# ── Profile cache ─────────────────────────────────────────────────────────────

def update_profile_cache(uid: str, profile: dict) -> None:
    """Cache extended HF profile data. Only updates fields that are provided."""
    fields = []
    values = []
    mapping = {
        "postnum":    lambda v: int(v or 0),
        "threadnum":  lambda v: int(v or 0),
        "reputation": lambda v: int(float(v or 0)),
        "myps":       lambda v: str(v or "0"),
        "vault":      lambda v: str(v or "0"),
        "usertitle":  lambda v: str(v or ""),
        "timeonline": lambda v: int(v or 0),
    }
    for key, cast in mapping.items():
        if key in profile and profile[key] is not None:
            fields.append(f"{key}=?")
            values.append(cast(profile[key]))
    if not fields:
        return
    fields.append("profile_ts=strftime('%s','now')")
    values.append(uid)
    with _db() as conn:
        conn.execute(f"UPDATE users SET {', '.join(fields)} WHERE uid=?", values)


def get_cached_profile(uid: str) -> dict | None:
    """Returns cached profile fields or None if never fetched."""
    with _db() as conn:
        row = conn.execute(
            "SELECT postnum, threadnum, reputation, myps, vault, usertitle, timeonline, profile_ts, username, avatar, groups FROM users WHERE uid=?",
            (uid,)
        ).fetchone()
        if not row:
            return None
        d = dict(row)
        d["groups"] = json.loads(d.get("groups") or "[]")
        return d


# ── Dash cache ─────────────────────────────────────────────────────────────────

def _init_dash_cache():
    with _db() as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS dash_cache (
                uid  TEXT NOT NULL,
                key  TEXT NOT NULL,
                data TEXT NOT NULL,
                ts   INTEGER NOT NULL,
                PRIMARY KEY (uid, key)
            )
        """)

def get_dash_cache(uid: str, key: str, max_age: int = 1800) -> dict | None:
    """Return cached data if fresh, else None."""
    import time, json
    with _db() as conn:
        row = conn.execute(
            "SELECT data, ts FROM dash_cache WHERE uid=? AND key=?", (uid, key)
        ).fetchone()
        if not row:
            return None
        if time.time() - row[1] > max_age:
            return None
        raw = row[0]
        try:
            return json.loads(raw)
        except Exception:
            # Corrupt / wrong-key cache entry — nuke it so it regenerates fresh
            conn.execute("DELETE FROM dash_cache WHERE uid=? AND key=?", (uid, key))
            return None

def set_dash_cache(uid: str, key: str, data: dict) -> None:
    import time, json
    raw = json.dumps(data)
    stored = raw
    with _db() as conn:
        conn.execute("""
            INSERT INTO dash_cache (uid, key, data, ts) VALUES (?,?,?,?)
            ON CONFLICT(uid,key) DO UPDATE SET data=excluded.data, ts=excluded.ts
        """, (uid, key, stored, int(time.time())))

def clear_dash_cache(uid: str, key: str) -> None:
    with _db() as conn:
        conn.execute("DELETE FROM dash_cache WHERE uid=? AND key=?", (uid, key))


def clear_all_dash_cache() -> None:
    with _db() as conn:
        conn.execute("DELETE FROM dash_cache")


# ── Bytes history store ────────────────────────────────────────────────────────

def init_bytes_history():
    with _db() as conn:
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS bytes_history (
                uid      TEXT NOT NULL,
                id       TEXT NOT NULL,
                amount   TEXT NOT NULL,
                dateline INTEGER NOT NULL,
                reason   TEXT,
                sent     INTEGER NOT NULL,
                type     TEXT DEFAULT '',
                post_tid TEXT DEFAULT '',
                PRIMARY KEY (uid, id)
            );
            CREATE TABLE IF NOT EXISTS bytes_crawl_state (
                uid           TEXT PRIMARY KEY,
                recv_page     INTEGER NOT NULL DEFAULT 1,
                sent_page     INTEGER NOT NULL DEFAULT 1,
                recv_done     INTEGER NOT NULL DEFAULT 0,
                sent_done     INTEGER NOT NULL DEFAULT 0,
                last_crawl    INTEGER
            );
        """)
        for _col, _def in [("type", "TEXT DEFAULT ''"), ("post_tid", "TEXT DEFAULT ''")]:
            try:
                conn.execute(f"ALTER TABLE bytes_history ADD COLUMN {_col} {_def}")
            except Exception:
                pass


def upsert_bytes_txns(uid: str, txns: list) -> int:
    """Insert new transactions, skip duplicates. Returns count inserted."""
    count = 0
    with _db() as conn:
        for t in txns:
            try:
                conn.execute(
                    "INSERT OR IGNORE INTO bytes_history (uid,id,amount,dateline,reason,sent,type,post_tid) VALUES (?,?,?,?,?,?,?,?)",
                    (
                        uid, str(t["id"]),
                        str(t["amount"]),
                        int(t["dateline"]),
                        str(t.get("reason") or ""),
                        int(t["sent"]),
                        str(t.get("type") or ""),
                        str(t.get("post_tid") or ""),
                    )
                )
                count += 1
            except Exception:
                pass
    return count


def get_bytes_history(uid: str, limit: int = 50, offset: int = 0,
                       direction: str = "all", type_filter: str = "", q: str = "") -> list:
    """Filtered bytes history. direction=all|sent|received. type_filter=comma-sep codes. q=reason search."""
    wheres, params = ["uid=?"], [uid]
    if direction == "sent":
        wheres.append("sent=1")
    elif direction == "received":
        wheres.append("sent=0")
    if type_filter:
        codes = [c.strip() for c in type_filter.split(",") if c.strip()]
        if codes:
            wheres.append(f"type IN ({','.join('?'*len(codes))})")
            params.extend(codes)
    with _db() as conn:
        rows = conn.execute(
            f"SELECT id,amount,dateline,reason,sent,type,post_tid FROM bytes_history WHERE {' AND '.join(wheres)} ORDER BY dateline DESC",
            params
        ).fetchall()
        result = []
        for r in rows:
            reason = r["reason"]
            if q and q.lower() not in (reason or "").lower():
                continue
            result.append({"id": r["id"], "amount": r["amount"],
                           "dateline": r["dateline"], "reason": reason, "sent": r["sent"],
                           "type": r["type"] or "", "post_tid": r["post_tid"] or ""})
        return result[offset:offset+limit], len(result)


def get_bytes_history_all(uid: str) -> list:
    with _db() as conn:
        rows = conn.execute(
            "SELECT id,amount,dateline,reason,sent,type,post_tid FROM bytes_history WHERE uid=? ORDER BY dateline DESC",
            (uid,)
        ).fetchall()
        return [{"id": r["id"], "amount": r["amount"],
                 "dateline": r["dateline"], "reason": r["reason"],
                 "sent": r["sent"], "type": r["type"] or "", "post_tid": r["post_tid"] or ""}
                for r in rows]


def get_bytes_history_count(uid: str) -> int:
    with _db() as conn:
        return conn.execute("SELECT COUNT(*) FROM bytes_history WHERE uid=?", (uid,)).fetchone()[0]


def get_crawl_state(uid: str) -> dict:
    import time as _t
    with _db() as conn:
        row = conn.execute("SELECT * FROM bytes_crawl_state WHERE uid=?", (uid,)).fetchone()
        if not row:
            conn.execute("INSERT OR IGNORE INTO bytes_crawl_state (uid) VALUES (?)", (uid,))
            return {"uid": uid, "recv_page": 1, "sent_page": 1,
                    "recv_done": 0, "sent_done": 0, "last_crawl": None}
        return dict(row)


def update_crawl_state(uid: str, **kwargs) -> None:
    import time as _t
    fields = ", ".join(f"{k}=?" for k in kwargs)
    values = list(kwargs.values()) + [uid]
    with _db() as conn:
        conn.execute(f"UPDATE bytes_crawl_state SET {fields} WHERE uid=?", values)


# ── Contracts history store ────────────────────────────────────────────────────

def init_contracts_history():
    with _db() as conn:
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS contracts_history (
                uid        TEXT NOT NULL,
                cid        TEXT NOT NULL,
                status_n   TEXT,
                type_n     TEXT,
                inituid    TEXT,
                otheruid   TEXT,
                iprice     TEXT,
                icurrency  TEXT,
                oprice     TEXT,
                ocurrency  TEXT,
                iproduct   TEXT,
                oproduct   TEXT,
                dateline   INTEGER,
                PRIMARY KEY (uid, cid)
            );
            CREATE TABLE IF NOT EXISTS contracts_crawl_state (
                uid        TEXT PRIMARY KEY,
                page       INTEGER NOT NULL DEFAULT 1,
                done       INTEGER NOT NULL DEFAULT 0,
                last_crawl INTEGER
            );
        """)


def upsert_contracts(uid: str, contracts: list) -> int:
    """Insert/update contracts. Returns count upserted."""
    e = lambda v: str(v) if v is not None else ""
    count = 0
    with _db() as conn:
        for c in contracts:
            try:
                conn.execute("""
                    INSERT INTO contracts_history
                        (uid,cid,status_n,type_n,inituid,otheruid,
                         iprice,icurrency,oprice,ocurrency,iproduct,oproduct,dateline)
                    VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)
                    ON CONFLICT(uid,cid) DO UPDATE SET
                        status_n=excluded.status_n,
                        dateline=excluded.dateline,
                        inituid=excluded.inituid,
                        otheruid=excluded.otheruid,
                        iprice=excluded.iprice,
                        icurrency=excluded.icurrency,
                        oprice=excluded.oprice,
                        ocurrency=excluded.ocurrency,
                        iproduct=excluded.iproduct,
                        oproduct=excluded.oproduct
                """, (
                    uid, str(c.get("cid","")),
                    str(c.get("status","")), str(c.get("type","")),
                    e(c.get("inituid","")),  e(c.get("otheruid","")),
                    e(c.get("iprice","0")),  e(c.get("icurrency","")),
                    e(c.get("oprice","0")),  e(c.get("ocurrency","")),
                    e(c.get("iproduct","")), e(c.get("oproduct","")),
                    int(c.get("dateline") or 0),
                ))
                count += 1
            except Exception:
                pass
    return count


def get_contracts_history(uid: str, limit: int = 10, offset: int = 0,
                           status_n: str | None = None,
                           sort_col: str = "dateline", sort_dir: str = "desc",
) -> list:
    # Whitelist columns to prevent SQL injection
    allowed_cols = {"cid", "status_n", "type_n", "dateline"}
    col = sort_col if sort_col in allowed_cols else "dateline"
    # For cid sort we cast to int for numeric ordering
    order_expr = f"CAST(cid AS INTEGER)" if col == "cid" else col
    direction  = "ASC" if sort_dir.lower() == "asc" else "DESC"
    order      = f"{order_expr} {direction}"
    with _db() as conn:
        if status_n:
            rows = conn.execute(
                f"""SELECT * FROM contracts_history WHERE uid=? AND status_n=?
                   ORDER BY {order} LIMIT ? OFFSET ?""",
                (uid, status_n, limit, offset)
            ).fetchall()
        else:
            rows = conn.execute(
                f"""SELECT * FROM contracts_history WHERE uid=?
                   ORDER BY {order} LIMIT ? OFFSET ?""",
                (uid, limit, offset)
            ).fetchall()
        d = lambda v: v
        return [{
            "uid":       r["uid"],
            "cid":       r["cid"],
            "status_n":  r["status_n"],
            "type_n":    r["type_n"],
            "dateline":  r["dateline"],
            "inituid":   d(r["inituid"]),
            "otheruid":  d(r["otheruid"]),
            "iprice":    d(r["iprice"]),
            "icurrency": d(r["icurrency"]),
            "oprice":    d(r["oprice"]),
            "ocurrency": d(r["ocurrency"]),
            "iproduct":  d(r["iproduct"]),
            "oproduct":  d(r["oproduct"]),
        } for r in rows]


def get_contracts_history_count(uid: str, status_n: str | None = None) -> int:
    with _db() as conn:
        if status_n:
            return conn.execute(
                "SELECT COUNT(*) FROM contracts_history WHERE uid=? AND status_n=?",
                (uid, status_n)
            ).fetchone()[0]
        return conn.execute(
            "SELECT COUNT(*) FROM contracts_history WHERE uid=?", (uid,)
        ).fetchone()[0]


def get_contracts_stats(uid: str) -> dict:
    """Aggregate counts from contracts_history for stats bar."""
    with _db() as conn:
        rows = conn.execute(
            "SELECT status_n, COUNT(*) AS cnt FROM contracts_history WHERE uid=? GROUP BY status_n",
            (uid,)
        ).fetchall()
    counts = {r["status_n"]: r["cnt"] for r in rows}
    total      = sum(counts.values())
    active     = counts.get("5", 0)
    complete   = counts.get("6", 0)
    disputed   = counts.get("7", 0)
    expired    = counts.get("8", 0)
    awaiting   = counts.get("1", 0)
    cancelled  = counts.get("2", 0)
    non_canc   = total - cancelled
    comp_rate  = round(complete / non_canc * 100) if non_canc > 0 else 0
    return {
        "total": total, "active": active, "complete": complete,
        "disputed": disputed, "expired": expired, "awaiting": awaiting,
        "cancelled": cancelled, "completion_rate": comp_rate,
    }


def get_contracts_crawl_state(uid: str) -> dict:
    with _db() as conn:
        row = conn.execute(
            "SELECT * FROM contracts_crawl_state WHERE uid=?", (uid,)
        ).fetchone()
        if not row:
            conn.execute(
                "INSERT OR IGNORE INTO contracts_crawl_state (uid) VALUES (?)", (uid,)
            )
            return {"uid": uid, "page": 1, "done": 0, "last_crawl": None}
        return dict(row)


def update_contracts_crawl_state(uid: str, **kwargs) -> None:
    fields = ", ".join(f"{k}=?" for k in kwargs)
    values = list(kwargs.values()) + [uid]
    with _db() as conn:
        conn.execute(
            f"UPDATE contracts_crawl_state SET {fields} WHERE uid=?", values
        )


# ── Async helper ───────────────────────────────────────────────────────────────

async def run(fn, *args):
    """Run a sync DB function in the thread pool. Uses get_running_loop() — Python 3.10+ safe."""
    loop = asyncio.get_running_loop()
    return await loop.run_in_executor(None, fn, *args)

# ── User settings (polling intervals, API floor, etc.) ─────────────────────────

def init_user_settings() -> None:
    with _db() as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS user_settings (
                uid      TEXT PRIMARY KEY,
                settings TEXT NOT NULL DEFAULT '{}'
            )
        """)


def get_user_settings(uid: str) -> dict:
    import json
    with _db() as conn:
        row = conn.execute("SELECT settings FROM user_settings WHERE uid=?", (uid,)).fetchone()
        if not row:
            return {}
        try:
            return json.loads(row[0]) or {}
        except Exception:
            return {}


def save_user_settings(uid: str, settings: dict) -> None:
    import json
    with _db() as conn:
        conn.execute(
            "INSERT INTO user_settings (uid, settings) VALUES (?,?) "
            "ON CONFLICT(uid) DO UPDATE SET settings=excluded.settings",
            (uid, json.dumps(settings))
        )


# ── Account deletion ────────────────────────────────────────────────────────────


def delete_user_data(uid: str) -> None:
    """Hard delete all stored data for a user. Irreversible."""
    with _db() as conn:
        for tbl in [
            "users", "module_prefs", "user_settings",
            "dash_cache", "bytes_history", "bytes_crawl_state",
            "contracts_history", "contracts_crawl_state",
        ]:
            try:
                conn.execute(f"DELETE FROM {tbl} WHERE uid=?", (uid,))
            except Exception:
                pass
    # Autobump tables live in main DB too
    try:
        from modules.autobump.autobump_db import delete_user_jobs
        delete_user_jobs(uid)
    except Exception:
        pass

