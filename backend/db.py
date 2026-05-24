"""
db.py — Framework-level persistence only.

Tables:
  users        — authenticated users (uid, token, avatar, username)
  module_prefs — per-user module enabled/disabled state

Modules manage their own data in their own tables.
Call db.init_db() once on startup.
"""

import json
import time
import asyncio
import crypto
from _db_compat import _db


def init_db() -> None:
    # Init hf_cache tables (hf_resource_cache + hf_api_call_log)
    try:
        import hf_cache as _hfc
        _hfc.init_hf_cache_tables()
    except Exception as _e:
        import logging as _log
        _log.getLogger("db").warning("hf_cache table init failed: %s", _e)

    with _db() as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS users (
                uid            VARCHAR(64)  NOT NULL,
                username       VARCHAR(255),
                token          TEXT         NOT NULL,
                avatar         TEXT,
                `groups`       TEXT         DEFAULT '[]',
                postnum        INT          DEFAULT 0,
                threadnum      INT          DEFAULT 0,
                reputation     INT          DEFAULT 0,
                myps           VARCHAR(64)  DEFAULT '0',
                vault          VARCHAR(64)  DEFAULT '0',
                usertitle      VARCHAR(255),
                timeonline     INT          DEFAULT 0,
                profile_ts     BIGINT       DEFAULT 0,
                created_at     BIGINT       DEFAULT 0,
                last_seen      BIGINT       DEFAULT 0,
                needs_refresh  TINYINT      NOT NULL DEFAULT 0,
                last_unreadpms INT          DEFAULT NULL,
                PRIMARY KEY (uid)
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS module_prefs (
                uid       VARCHAR(64) NOT NULL,
                module_id VARCHAR(64) NOT NULL,
                enabled   TINYINT     NOT NULL DEFAULT 1,
                PRIMARY KEY (uid, module_id)
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
        """)
    # Add displaygroup column if missing (safe re-run)
    try:
        with _db() as _c:
            _c.execute("ALTER TABLE users ADD COLUMN displaygroup VARCHAR(32) DEFAULT ''")
    except Exception:
        pass
    # Add token refresh columns if missing (safe re-run)
    for _col, _defn in [
        ("refresh_token", "TEXT DEFAULT ''"),
        ("token_expiry",  "BIGINT DEFAULT 0"),
        ("token_dead",    "TINYINT NOT NULL DEFAULT 0"),
    ]:
        try:
            with _db() as _c:
                _c.execute(f"ALTER TABLE users ADD COLUMN {_col} {_defn}")
        except Exception:
            pass
    _init_dash_cache()
    init_bytes_history()
    init_contracts_history()
    init_uid_usernames()
    init_tid_titles()
    # Column migration is handled at schema level in MySQL — no PRAGMA needed


# ── Users ──────────────────────────────────────────────────────────────────────

def upsert_user(uid: str, username: str, token: str, avatar: str = "", groups: list[str] = []) -> None:
    token = crypto.encrypt_token(token)
    import time as _t
    with _db() as conn:
        conn.execute("""
            INSERT INTO users (uid, username, token, avatar, `groups`, last_seen)
            VALUES (%s, %s, %s, %s, %s, %s)
            ON DUPLICATE KEY UPDATE
                username=VALUES(username), token=VALUES(token),
                avatar=VALUES(avatar), `groups`=VALUES(`groups`),
                last_seen=VALUES(last_seen)
        """, (uid, username, token, avatar, json.dumps(groups), int(_t.time())))


def get_user(uid: str) -> dict | None:
    with _db() as conn:
        row = conn.execute("SELECT * FROM users WHERE uid=%s", (uid,)).fetchone()
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
                id         INT          NOT NULL AUTO_INCREMENT,
                uid        VARCHAR(64)  NOT NULL,
                type       VARCHAR(64)  NOT NULL,
                title      VARCHAR(512) NOT NULL,
                body       TEXT,
                link       TEXT,
                ref_id     VARCHAR(128),
                seen       TINYINT      NOT NULL DEFAULT 0,
                created_at BIGINT       NOT NULL DEFAULT 0,
                PRIMARY KEY (id)
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
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
            "INSERT INTO notifications (uid, type, title, body, link, ref_id, created_at) VALUES (?,?,?,?,?,?,?)",
            (uid, type_, title, body, link, ref_id, int(time.time()))
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
                id         INT          NOT NULL AUTO_INCREMENT,
                uid        VARCHAR(64)  NOT NULL,
                type       VARCHAR(64)  NOT NULL,
                title      VARCHAR(512) NOT NULL,
                body       TEXT,
                link       TEXT,
                ref_id     VARCHAR(128),
                seen       TINYINT      NOT NULL DEFAULT 0,
                created_at BIGINT       NOT NULL DEFAULT 0,
                PRIMARY KEY (id)
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
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
            "INSERT INTO notifications (uid, type, title, body, link, ref_id, created_at) VALUES (?,?,?,?,?,?,?)",
            (uid, type_, title, body, link, ref_id, int(time.time()))
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


def clear_token(uid: str) -> None:
    """Null out a user's stored token (e.g. after HF returns 401). Does NOT delete the user row."""
    with _db() as conn:
        conn.execute("UPDATE users SET token='', token_dead=1 WHERE uid=%s", (uid,))


def update_token(uid: str, new_token: str) -> None:
    """Overwrite the stored access token (e.g. after a successful refresh)."""
    token_enc = crypto.encrypt_token(new_token)
    with _db() as conn:
        conn.execute(
            "UPDATE users SET token=%s, token_dead=0 WHERE uid=%s",
            (token_enc, uid),
        )


def store_refresh_token(uid: str, refresh_token: str, expiry: int = 0) -> None:
    """Store or update the OAuth refresh token and its expiry for a user."""
    with _db() as conn:
        conn.execute(
            "UPDATE users SET refresh_token=%s, token_expiry=%s WHERE uid=%s",
            (refresh_token, int(expiry), uid),
        )


def get_refresh_token(uid: str) -> str | None:
    """Return stored refresh_token for uid, or None if absent."""
    with _db() as conn:
        row = conn.execute(
            "SELECT refresh_token FROM users WHERE uid=%s", (uid,)
        ).fetchone()
        if not row:
            return None
        val = row[0] if isinstance(row, (list, tuple)) else row.get("refresh_token", "")
        return val or None


def mark_token_dead(uid: str, dead: bool = True) -> None:
    """Flag a user's token as dead (expired/revoked, refresh failed)."""
    with _db() as conn:
        conn.execute(
            "UPDATE users SET token_dead=%s WHERE uid=%s",
            (1 if dead else 0, uid),
        )


def is_token_dead(uid: str) -> bool:
    """Return True if token_dead=1 (user needs to re-login)."""
    with _db() as conn:
        row = conn.execute(
            "SELECT token_dead FROM users WHERE uid=%s", (uid,)
        ).fetchone()
        if not row:
            return False
        val = row[0] if isinstance(row, (list, tuple)) else row.get("token_dead", 0)
        return bool(val)


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
            INSERT INTO module_prefs (uid, module_id, enabled) VALUES (%s, %s, %s)
            ON DUPLICATE KEY UPDATE enabled=VALUES(enabled)
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
        "timeonline":    lambda v: int(v or 0),
        "displaygroup":  lambda v: str(v or ""),
    }
    for key, cast in mapping.items():
        if key in profile and profile[key] is not None:
            fields.append(f"{key}=?")
            values.append(cast(profile[key]))
    if not fields:
        return
    import time as _t2
    fields.append('profile_ts=%s')
    values.append(int(_t2.time()))
    values.append(uid)
    with _db() as conn:
        conn.execute(f"UPDATE users SET {', '.join(fields)} WHERE uid=?", values)


def get_cached_profile(uid: str) -> dict | None:
    """Returns cached profile fields or None if never fetched."""
    with _db() as conn:
        row = conn.execute(
            "SELECT postnum, threadnum, reputation, myps, vault, usertitle, timeonline, profile_ts, username, avatar, `groups`, displaygroup FROM users WHERE uid=%s",
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
                uid   VARCHAR(64)  NOT NULL,
                `key` VARCHAR(64)  NOT NULL,
                data  MEDIUMTEXT   NOT NULL,
                ts    BIGINT       NOT NULL,
                PRIMARY KEY (uid, `key`)
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
        """)

def get_dash_cache(uid: str, key: str, max_age: int = 1800) -> dict | None:
    """Return cached data if fresh, else None."""
    import time, json
    with _db() as conn:
        row = conn.execute(
            "SELECT data, ts FROM dash_cache WHERE uid=? AND `key`=?", (uid, key)
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
            conn.execute("DELETE FROM dash_cache WHERE uid=? AND `key`=?", (uid, key))
            return None

def set_dash_cache(uid: str, key: str, data: dict) -> None:
    import time, json
    raw = json.dumps(data)
    stored = raw
    with _db() as conn:
        conn.execute("""
            INSERT INTO dash_cache (uid, `key`, data, ts) VALUES (%s, %s, %s, %s)
            ON DUPLICATE KEY UPDATE data=VALUES(data), ts=VALUES(ts)
        """, (uid, key, stored, int(time.time())))

def clear_dash_cache(uid: str, key: str) -> None:
    with _db() as conn:
        conn.execute("DELETE FROM dash_cache WHERE uid=? AND `key`=?", (uid, key))


def clear_all_dash_cache() -> None:
    with _db() as conn:
        conn.execute("DELETE FROM dash_cache")


# ── Bytes history store ────────────────────────────────────────────────────────

def init_bytes_history():
    with _db() as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS bytes_history (
                uid      VARCHAR(64) NOT NULL,
                id       VARCHAR(64) NOT NULL,
                amount   VARCHAR(32) NOT NULL,
                dateline BIGINT      NOT NULL,
                reason   TEXT,
                sent     TINYINT     NOT NULL,
                type     VARCHAR(16) DEFAULT '',
                post_tid VARCHAR(64) DEFAULT '',
                PRIMARY KEY (uid, id),
                INDEX idx_bh_uid_date (uid, dateline)
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS bytes_crawl_state (
                uid       VARCHAR(64) NOT NULL,
                recv_page INT         NOT NULL DEFAULT 1,
                sent_page INT         NOT NULL DEFAULT 1,
                recv_done TINYINT     NOT NULL DEFAULT 0,
                sent_done TINYINT     NOT NULL DEFAULT 0,
                last_crawl BIGINT,
                PRIMARY KEY (uid)
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
        """)


def upsert_bytes_txns(uid: str, txns: list) -> int:
    """Insert new transactions, skip duplicates. Returns count inserted."""
    if not txns:
        return 0
    rows = []
    for t in txns:
        try:
            rows.append((
                uid, str(t["id"]),
                str(t["amount"]),
                int(t["dateline"]),
                str(t.get("reason") or ""),
                int(t["sent"]),
                str(t.get("type") or ""),
                str(t.get("post_tid") or ""),
            ))
        except Exception:
            pass
    if not rows:
        return 0
    with _db() as conn:
        conn.executemany(
            "INSERT OR IGNORE INTO bytes_history (uid,id,amount,dateline,reason,sent,type,post_tid) VALUES (?,?,?,?,?,?,?,?)",
            rows
        )
    return len(rows)


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
        conn.execute("""
            CREATE TABLE IF NOT EXISTS contracts_history (
                uid       VARCHAR(64) NOT NULL,
                cid       VARCHAR(64) NOT NULL,
                status_n  VARCHAR(8),
                type_n    VARCHAR(8),
                inituid   VARCHAR(64),
                otheruid  VARCHAR(64),
                iprice    VARCHAR(64),
                icurrency VARCHAR(32),
                oprice    VARCHAR(64),
                ocurrency VARCHAR(32),
                iproduct  TEXT,
                oproduct  TEXT,
                dateline  BIGINT,
                tid       VARCHAR(64) DEFAULT '',
                PRIMARY KEY (uid, cid),
                INDEX idx_ch_uid (uid)
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS contracts_crawl_state (
                uid        VARCHAR(64) NOT NULL,
                page       INT         NOT NULL DEFAULT 1,
                done       TINYINT     NOT NULL DEFAULT 0,
                last_crawl BIGINT,
                PRIMARY KEY (uid)
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
        """)
        # MySQL: column already in schema, no migration needed
        try:
            conn.execute("ALTER TABLE contracts_history ADD COLUMN tid TEXT DEFAULT ''")
        except Exception:
            pass  # Column already exists
        try:
            conn.execute("ALTER TABLE contracts_crawl_state ADD COLUMN last_recheck_ts BIGINT DEFAULT 0")
        except Exception:
            pass  # Column already exists


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
                         iprice,icurrency,oprice,ocurrency,iproduct,oproduct,dateline,tid)
                    VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)
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
                        oproduct=excluded.oproduct,
                        tid=excluded.tid
                """, (
                    uid, str(c.get("cid","")),
                    str(c.get("status","")), str(c.get("type","")),
                    e(c.get("inituid","")),  e(c.get("otheruid","")),
                    e(c.get("iprice","0")),  e(c.get("icurrency","")),
                    e(c.get("oprice","0")),  e(c.get("ocurrency","")),
                    e(c.get("iproduct","")), e(c.get("oproduct","")),
                    int(c.get("dateline") or 0),
                    e(c.get("tid","")),
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



def backfill_contract_tids(uid: str, cid_tid_map: dict) -> int:
    """Update tid for contracts that have an empty tid. Only sets non-empty values.
    cid_tid_map: {cid_str: tid_str}. Returns count updated."""
    if not cid_tid_map:
        return 0
    count = 0
    with _db() as conn:
        for cid, tid in cid_tid_map.items():
            if not tid or tid == "0":
                continue
            cur = conn.execute(
                "UPDATE contracts_history SET tid=? WHERE uid=? AND cid=? AND (tid IS NULL OR tid='' OR tid='0')",
                (str(tid), uid, str(cid))
            )
            count += cur.rowcount
    return count


def get_contracts_with_empty_tid(uid: str) -> bool:
    """Returns True if any contracts_history rows for uid have empty tid."""
    with _db() as conn:
        row = conn.execute(
            "SELECT 1 FROM contracts_history WHERE uid=? AND (tid IS NULL OR tid='' OR tid='0') LIMIT 1",
            (uid,)
        ).fetchone()
    return row is not None

def get_open_contract_cids(uid: str) -> list:
    """Return CIDs of contracts still in an open state (Awaiting=1, Active=5).
    These get re-checked every crawl cycle to catch status changes."""
    with _db() as conn:
        rows = conn.execute(
            "SELECT cid FROM contracts_history WHERE uid=? AND status_n IN ('1','5')",
            (uid,)
        ).fetchall()
    return [str(r["cid"]) for r in rows]


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


def get_contracts_export(uid: str, status_n: str | None = None,
                          date_from: int | None = None, date_to: int | None = None) -> list:
    """Return ALL contracts for a user (no limit) for export. Optional filters."""
    conditions = ["uid=?"]
    params: list = [uid]
    if status_n:
        conditions.append("status_n=?")
        params.append(status_n)
    if date_from:
        conditions.append("dateline >= ?")
        params.append(int(date_from))
    if date_to:
        conditions.append("dateline <= ?")
        params.append(int(date_to))
    where = " AND ".join(conditions)
    with _db() as conn:
        rows = conn.execute(
            f"SELECT * FROM contracts_history WHERE {where} ORDER BY dateline DESC",
            params,
        ).fetchall()
        return [dict(r) for r in rows]



def _perspective_type(r, uid: str) -> str:
    TYPE_MAP = {"1":"Selling","2":"Purchasing","3":"Exchanging","4":"Trading","5":"Vouch Copy"}
    type_n = str(r.get("type_n") or "")
    if type_n in ("3","5"):
        return TYPE_MAP.get(type_n, "--")
    trivial = {"","other","n/a","none","null"}
    has_ip  = str(r.get("iproduct") or "").strip().lower() not in trivial
    has_op  = str(r.get("oproduct") or "").strip().lower() not in trivial
    try:    iprice = float(r.get("iprice") or 0)
    except: iprice = 0
    try:    oprice = float(r.get("oprice") or 0)
    except: oprice = 0
    if str(r.get("inituid") or "") == uid:
        if has_ip:     return "Selling"
        if has_op:     return "Purchasing"
        if iprice > 0: return "Purchasing"
        if oprice > 0: return "Selling"
        return "Selling"
    else:
        if has_op:     return "Selling"
        if has_ip:     return "Purchasing"
        if oprice > 0: return "Purchasing"
        if iprice > 0: return "Selling"
        return "Selling"


def get_contracts_preview(uid: str, status_n: str | None = None,
                           date_from: int | None = None, date_to: int | None = None,
                           limit: int = 10) -> dict:
    """Summary stats + first N rows for the export preview panel."""
    conditions = ["uid=?"]
    params: list = [uid]
    if status_n:
        conditions.append("status_n=?")
        params.append(status_n)
    if date_from:
        conditions.append("dateline >= ?")
        params.append(int(date_from))
    if date_to:
        conditions.append("dateline <= ?")
        params.append(int(date_to))
    where = " AND ".join(conditions)

    with _db() as conn:
        total = conn.execute(
            f"SELECT COUNT(*) FROM contracts_history WHERE {where}", params
        ).fetchone()[0]
        date_row = conn.execute(
            f"SELECT MIN(dateline) as mn, MAX(dateline) as mx FROM contracts_history WHERE {where}", params
        ).fetchone()
        status_rows = conn.execute(
            f"SELECT status_n, COUNT(*) as cnt FROM contracts_history WHERE {where} GROUP BY status_n ORDER BY cnt DESC",
            params
        ).fetchall()
        type_rows = conn.execute(
            f"""SELECT CASE
              WHEN type_n IN ('3','5') THEN type_n
              WHEN inituid=? AND iproduct IS NOT NULL AND LOWER(TRIM(iproduct)) NOT IN ('','other','n/a','none','null') THEN '1'
              WHEN inituid=? AND oproduct IS NOT NULL AND LOWER(TRIM(oproduct)) NOT IN ('','other','n/a','none','null') THEN '2'
              WHEN inituid=? AND CAST(COALESCE(iprice,'0') AS DECIMAL(20,4))>0 THEN '2'
              WHEN inituid=? THEN '1'
              WHEN oproduct IS NOT NULL AND LOWER(TRIM(oproduct)) NOT IN ('','other','n/a','none','null') THEN '1'
              WHEN iproduct IS NOT NULL AND LOWER(TRIM(iproduct)) NOT IN ('','other','n/a','none','null') THEN '2'
              WHEN CAST(COALESCE(oprice,'0') AS DECIMAL(20,4))>0 THEN '2'
              ELSE '1'
            END AS type_n, COUNT(*) as cnt FROM contracts_history WHERE {where} GROUP BY 1 ORDER BY cnt DESC""",
            [uid,uid,uid,uid] + params
        ).fetchall()
        preview_rows = conn.execute(
            f"SELECT * FROM contracts_history WHERE {where} ORDER BY dateline DESC LIMIT ?",
            params + [limit]
        ).fetchall()
        # Top SALES threads — counterparty delivering a product, or exchanges
        _sell_cond = "otheruid=? AND (type_n IN ('3','5') OR (oproduct IS NOT NULL AND LOWER(TRIM(oproduct)) NOT IN ('','other','n/a','none','null')))"
        thread_rows = conn.execute(
            f"""SELECT tid, COUNT(*) as cnt FROM contracts_history
                WHERE {where} AND tid IS NOT NULL AND tid != '' AND tid != '0'
                AND {_sell_cond}
                GROUP BY tid ORDER BY cnt DESC LIMIT 10""",
            params + [uid]
        ).fetchall()
        with_thread = conn.execute(
            f"SELECT COUNT(*) FROM contracts_history WHERE {where} AND tid IS NOT NULL AND tid != '' AND tid != '0' AND {_sell_cond}",
            params + [uid]
        ).fetchone()[0]
        # Type breakdown per top thread
        top_tids = [r["tid"] for r in thread_rows]
        thread_type_rows = []
        if top_tids:
            tid_placeholders = ",".join("?" * len(top_tids))
            thread_type_rows = conn.execute(
                f"""SELECT tid, CASE
                        WHEN type_n IN ('3','5') THEN type_n
                        WHEN inituid=? AND iproduct IS NOT NULL AND LOWER(TRIM(iproduct)) NOT IN ('','other','n/a','none','null') THEN '1'
                        WHEN inituid=? AND oproduct IS NOT NULL AND LOWER(TRIM(oproduct)) NOT IN ('','other','n/a','none','null') THEN '2'
                        WHEN inituid=? AND CAST(COALESCE(iprice,'0') AS DECIMAL(20,4))>0 THEN '2'
                        WHEN inituid=? THEN '1'
                        WHEN oproduct IS NOT NULL AND LOWER(TRIM(oproduct)) NOT IN ('','other','n/a','none','null') THEN '1'
                        WHEN iproduct IS NOT NULL AND LOWER(TRIM(iproduct)) NOT IN ('','other','n/a','none','null') THEN '2'
                        WHEN CAST(COALESCE(oprice,'0') AS DECIMAL(20,4))>0 THEN '2'
                        ELSE '1'
                      END AS type_n, COUNT(*) as cnt FROM contracts_history
                    WHERE {where} AND tid IN ({tid_placeholders})
                    GROUP BY tid, 2""",
                [uid,uid,uid,uid] + params + top_tids
            ).fetchall()
        # Most common value (iproduct/oproduct) per top thread
        thread_value_rows = []
        if top_tids:
            thread_value_rows = conn.execute(
                f"""SELECT tid, iproduct, oproduct, iprice, icurrency, oprice, ocurrency, COUNT(*) as cnt
                    FROM contracts_history
                    WHERE {where} AND tid IN ({tid_placeholders})
                    GROUP BY tid, iproduct, oproduct, iprice, icurrency, oprice, ocurrency
                    ORDER BY cnt DESC""",
                params + top_tids
            ).fetchall()

    STATUS_MAP = {"1":"Awaiting Approval","2":"Cancelled","3":"Unknown","4":"Cancelled",
                  "5":"Active Deal","6":"Complete","7":"Disputed","8":"Expired"}
    TYPE_MAP   = {"1":"Selling","2":"Purchasing","3":"Exchanging","4":"Trading","5":"Vouch Copy"}

    counts    = {r["status_n"]: r["cnt"] for r in status_rows}
    complete  = counts.get("6", 0)
    cancelled = counts.get("2", 0)
    non_canc  = total - cancelled
    comp_rate = round(complete / non_canc * 100) if non_canc > 0 else 0

    def _val(r):
        ip, ic = r.get("iprice","0") or "0", r.get("icurrency","other") or "other"
        op, oc = r.get("oprice","0") or "0", r.get("ocurrency","other") or "other"
        ipr, opr = r.get("iproduct","") or "", r.get("oproduct","") or ""
        if ip != "0" and ic.lower() != "other":  return f"{ip} {ic}"
        if op != "0" and oc.lower() != "other":  return f"{op} {oc}"
        if ipr not in ("","other","n/a"):         return ipr
        if opr not in ("","other","n/a"):         return opr
        return ""

    rows = []
    for _r in preview_rows:
        r = dict(_r)  # sqlite3.Row → dict so .get() works
        rows.append({
            "cid":      r["cid"],
            "status":   STATUS_MAP.get(str(r.get("status_n") or ""), "Unknown"),
            "type":     _perspective_type(r, uid),
            "value":    _val(r),
            "inituid":  r.get("inituid") or "",
            "otheruid": r.get("otheruid") or "",
            "tid":      r.get("tid") or "",
            "dateline": r.get("dateline") or 0,
        })

    # Lookup cached thread titles
    all_tids = [r["tid"] for r in thread_rows]
    tid_title_map = get_tid_titles(all_tids)

    # Build per-thread type breakdown
    thread_types: dict = {}
    for r in thread_type_rows:
        tid = r["tid"]
        if tid not in thread_types:
            thread_types[tid] = []
        thread_types[tid].append({
            "type": TYPE_MAP.get(str(r["type_n"] or ""), "--"),
            "count": r["cnt"],
        })

    # Build per-thread most common value
    thread_values: dict = {}
    for r in thread_value_rows:
        tid = r["tid"]
        if tid in thread_values:
            continue  # already have the top one
        # Reuse _val logic inline
        ip = str(r["iprice"] or "0"); ic = str(r["icurrency"] or "other")
        op = str(r["oprice"] or "0"); oc = str(r["ocurrency"] or "other")
        ipr = str(r["iproduct"] or ""); opr = str(r["oproduct"] or "")
        if ip != "0" and ic.lower() != "other": thread_values[tid] = f"{ip} {ic}"
        elif op != "0" and oc.lower() != "other": thread_values[tid] = f"{op} {oc}"
        elif ipr not in ("", "other", "n/a"): thread_values[tid] = ipr
        elif opr not in ("", "other", "n/a"): thread_values[tid] = opr

    return {
        "total":       total,
        "comp_rate":   comp_rate,
        "date_min":    date_row["mn"] if date_row else None,
        "date_max":    date_row["mx"] if date_row else None,
        "by_status":   [{"label": STATUS_MAP.get(str(r["status_n"]),"Unknown"), "count": r["cnt"]} for r in status_rows],
        "by_type":     [{"label": TYPE_MAP.get(str(r["type_n"]),"--"),           "count": r["cnt"]} for r in type_rows],
        "rows":        rows,
        "with_thread": with_thread,
        "top_threads": [{
            "tid":        r["tid"],
            "title":      tid_title_map.get(r["tid"], ""),
            "count":      r["cnt"],
            "types":      sorted(thread_types.get(r["tid"], []), key=lambda x: -x["count"]),
            "top_value":  thread_values.get(r["tid"], ""),
        } for r in thread_rows],
    }


def get_contracts_stats(uid: str) -> dict:
    """Aggregate counts from contracts_history for stats bar."""
    import time as _time
    NINETY_DAYS = 90 * 86400
    cutoff = int(_time.time()) - NINETY_DAYS
    with _db() as conn:
        rows = conn.execute(
            "SELECT status_n, COUNT(*) AS cnt FROM contracts_history WHERE uid=? GROUP BY status_n",
            (uid,)
        ).fetchall()
        # Awaiting contracts older than 90 days that HF never officially expired
        stale_awaiting = conn.execute(
            "SELECT COUNT(*) AS cnt FROM contracts_history "
            "WHERE uid=? AND status_n='1' AND dateline > 0 AND dateline < ?",
            (uid, cutoff)
        ).fetchone()["cnt"]

    counts    = {r["status_n"]: r["cnt"] for r in rows}
    total     = sum(counts.values())
    active    = counts.get("5", 0)
    complete  = counts.get("6", 0)
    disputed  = counts.get("7", 0)
    expired   = counts.get("8", 0) + stale_awaiting
    awaiting  = max(0, counts.get("1", 0) - stale_awaiting)
    # status 2 and 4 are both cancelled (4 = counterparty-denied)
    cancelled = counts.get("2", 0) + counts.get("4", 0)
    non_canc  = total - cancelled
    comp_rate = round(complete / non_canc * 100) if non_canc > 0 else 0
    return {
        "total": total, "active": active, "complete": complete,
        "disputed": disputed, "expired": expired, "awaiting": awaiting,
        "cancelled": cancelled, "completion_rate": comp_rate,
    }


def get_contracts_analytics(uid: str, status_n: str | None = None,
                              date_from: int | None = None, date_to: int | None = None) -> dict:
    """Rich aggregate analytics for the contracts preview panel."""
    conditions = ["uid=?"]
    params: list = [uid]
    if status_n:
        conditions.append("status_n=?")
        params.append(status_n)
    if date_from:
        conditions.append("dateline >= ?")
        params.append(int(date_from))
    if date_to:
        conditions.append("dateline <= ?")
        params.append(int(date_to))
    where = " AND ".join(conditions)

    STATUS_MAP = {"1":"Awaiting Approval","2":"Cancelled","3":"Unknown","4":"Cancelled",
                  "5":"Active Deal","6":"Complete","7":"Disputed","8":"Expired"}
    TYPE_MAP   = {"1":"Selling","2":"Purchasing","3":"Exchanging","4":"Trading","5":"Vouch Copy"}

    with _db() as conn:
        total = conn.execute(
            f"SELECT COUNT(*) FROM contracts_history WHERE {where}", params
        ).fetchone()[0]

        date_row = conn.execute(
            f"SELECT MIN(dateline) as mn, MAX(dateline) as mx FROM contracts_history WHERE {where}", params
        ).fetchone()

        by_status_rows = conn.execute(
            f"SELECT status_n, COUNT(*) as cnt FROM contracts_history WHERE {where} GROUP BY status_n ORDER BY cnt DESC",
            params
        ).fetchall()

        by_type_rows = conn.execute(
            f"""SELECT CASE
              WHEN type_n IN ('3','5') THEN type_n
              WHEN inituid=? AND iproduct IS NOT NULL AND LOWER(TRIM(iproduct)) NOT IN ('','other','n/a','none','null') THEN '1'
              WHEN inituid=? AND oproduct IS NOT NULL AND LOWER(TRIM(oproduct)) NOT IN ('','other','n/a','none','null') THEN '2'
              WHEN inituid=? AND CAST(COALESCE(iprice,'0') AS DECIMAL(20,4))>0 THEN '2'
              WHEN inituid=? THEN '1'
              WHEN oproduct IS NOT NULL AND LOWER(TRIM(oproduct)) NOT IN ('','other','n/a','none','null') THEN '1'
              WHEN iproduct IS NOT NULL AND LOWER(TRIM(iproduct)) NOT IN ('','other','n/a','none','null') THEN '2'
              WHEN CAST(COALESCE(oprice,'0') AS DECIMAL(20,4))>0 THEN '2'
              ELSE '1'
            END AS type_n, COUNT(*) as cnt FROM contracts_history WHERE {where} GROUP BY 1 ORDER BY cnt DESC""",
            [uid,uid,uid,uid] + params
        ).fetchall()

        # Counterparty = the other party (not the session user)
        cp_rows = conn.execute(
            f"""SELECT
                    CASE WHEN inituid=uid THEN otheruid ELSE inituid END AS cp,
                    COUNT(*) AS cnt
                FROM contracts_history
                WHERE {where} AND (inituid != '' OR otheruid != '')
                GROUP BY cp
                ORDER BY cnt DESC
                LIMIT 8""",
            params
        ).fetchall()

        monthly_rows = conn.execute(
            f"""SELECT
                    DATE_FORMAT(FROM_UNIXTIME(dateline), '%Y-%m') AS month,
                    COUNT(*) AS cnt
                FROM contracts_history
                WHERE {where} AND dateline > 0
                GROUP BY month
                ORDER BY month DESC
                LIMIT 24""",
            params
        ).fetchall()

        # Simple value stats: count how many have a non-trivial price vs product description
        val_row = conn.execute(
            f"""SELECT
                    SUM(CASE WHEN icurrency NOT IN ('','other') AND iprice NOT IN ('','0') THEN 1 ELSE 0 END) AS has_price,
                    SUM(CASE WHEN iproduct NOT IN ('','other','n/a','None') AND iproduct IS NOT NULL AND LENGTH(iproduct)>1 THEN 1 ELSE 0 END) AS has_product
                FROM contracts_history WHERE {where}""",
            params
        ).fetchone()

    counts = {r["status_n"]: r["cnt"] for r in by_status_rows}
    complete  = counts.get("6", 0)
    cancelled = counts.get("2", 0)
    non_canc  = total - cancelled
    comp_rate = round(complete / non_canc * 100) if non_canc > 0 else 0

    return {
        "total":     total,
        "comp_rate": comp_rate,
        "date_min":  date_row["mn"] if date_row else None,
        "date_max":  date_row["mx"] if date_row else None,
        "by_status": [{"label": STATUS_MAP.get(str(r["status_n"]),"Unknown"), "count": r["cnt"]} for r in by_status_rows],
        "by_type":   [{"label": TYPE_MAP.get(str(r["type_n"]),"--"),           "count": r["cnt"]} for r in by_type_rows],
        "top_counterparties": [{"uid": r["cp"], "count": r["cnt"]} for r in cp_rows if r["cp"]],
        "monthly":   [{"month": r["month"], "count": r["cnt"]} for r in monthly_rows],
        "has_price":   val_row["has_price"]   or 0,
        "has_product": val_row["has_product"] or 0,
    }


def init_uid_usernames() -> None:
    """Create uid_usernames table with full profile fields."""
    with _db() as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS uid_usernames (
                uid            VARCHAR(64)  NOT NULL,
                username       VARCHAR(255) NOT NULL DEFAULT '',
                avatar         TEXT         DEFAULT '',
                usertitle      VARCHAR(255) DEFAULT '',
                reputation     INT          DEFAULT 0,
                displaygroup   VARCHAR(32)  DEFAULT '',
                additionalgroups TEXT       DEFAULT '',
                cached_at      BIGINT,
                PRIMARY KEY (uid)
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
        """)
        # Migrate existing table — add columns if missing
        for col, defn in [
            ("avatar",           "TEXT DEFAULT ''"),
            ("usertitle",        "VARCHAR(255) DEFAULT ''"),
            ("reputation",       "INT DEFAULT 0"),
            ("displaygroup",     "VARCHAR(32) DEFAULT ''"),
            ("additionalgroups", "TEXT DEFAULT ''"),
        ]:
            try:
                conn.execute(f"ALTER TABLE uid_usernames ADD COLUMN {col} {defn}")
            except Exception:
                pass  # already exists


def upsert_uid_usernames(uid_map: dict) -> None:
    """Store user profile data keyed by UID.

    uid_map values can be either:
      - a plain string  → stored as username only (legacy callers)
      - a dict          → full profile: {username, avatar, usertitle,
                          reputation, displaygroup, additionalgroups}
    """
    if not uid_map:
        return
    import time as _t
    now = int(_t.time())
    with _db() as conn:
        for u, val in uid_map.items():
            uid = str(u)
            if isinstance(val, str):
                # Legacy: just a username string
                conn.execute("""
                    INSERT INTO uid_usernames (uid, username, cached_at)
                    VALUES (%s, %s, %s)
                    ON DUPLICATE KEY UPDATE username=VALUES(username), cached_at=VALUES(cached_at)
                """, (uid, val, now))
            elif isinstance(val, dict):
                username       = str(val.get("username", "") or "")
                avatar         = str(val.get("avatar", "") or "")
                usertitle      = str(val.get("usertitle", "") or "")
                reputation     = int(val.get("reputation") or 0)
                displaygroup   = str(val.get("displaygroup", "") or val.get("usergroup", "") or "")
                additionalgroups = str(val.get("additionalgroups", "") or "")
                # displaygroup "0" means same as usergroup
                if displaygroup == "0":
                    displaygroup = str(val.get("usergroup", "") or "")
                conn.execute("""
                    INSERT INTO uid_usernames
                        (uid, username, avatar, usertitle, reputation,
                         displaygroup, additionalgroups, cached_at)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                    ON DUPLICATE KEY UPDATE
                        username=VALUES(username),
                        avatar=IF(VALUES(avatar)!='', VALUES(avatar), avatar),
                        usertitle=IF(VALUES(usertitle)!='', VALUES(usertitle), usertitle),
                        reputation=IF(VALUES(reputation)!=0, VALUES(reputation), reputation),
                        displaygroup=IF(VALUES(displaygroup)!='', VALUES(displaygroup), displaygroup),
                        additionalgroups=IF(VALUES(additionalgroups)!='', VALUES(additionalgroups), additionalgroups),
                        cached_at=VALUES(cached_at)
                """, (uid, username, avatar, usertitle, reputation,
                      displaygroup, additionalgroups, now))


def get_uid_usernames(uids: list) -> dict:
    """Lookup full user profiles from cache.
    Returns {uid: {username, avatar, usertitle, reputation, displaygroup, additionalgroups}}.
    Falls back to username-only if new columns don't exist yet.
    """
    if not uids:
        return {}
    uids = [str(u) for u in uids if u]
    placeholders = ",".join(["%s"] * len(uids))
    with _db() as conn:
        try:
            rows = conn.execute(
                f"SELECT uid, username, avatar, usertitle, reputation, displaygroup, additionalgroups "
                f"FROM uid_usernames WHERE uid IN ({placeholders})", uids
            ).fetchall()
        except Exception:
            # Fallback if new columns don't exist yet (pre-migration)
            rows = conn.execute(
                f"SELECT uid, username FROM uid_usernames WHERE uid IN ({placeholders})", uids
            ).fetchall()
    result = {}
    for r in rows:
        result[str(r["uid"])] = {
            "username":         r.get("username", ""),
            "avatar":           r.get("avatar", ""),
            "usertitle":        r.get("usertitle", ""),
            "reputation":       r.get("reputation", 0),
            "displaygroup":     r.get("displaygroup", ""),
            "additionalgroups": r.get("additionalgroups", ""),
        }
    return result


def get_unknown_uids_from_contracts(uid: str, limit: int = 60) -> list:
    """Return counterparty UIDs from contracts_history not yet in uid_usernames.
    Used by crawl to know which UIDs still need resolving."""
    with _db() as conn:
        rows = conn.execute("""
            SELECT DISTINCT cp FROM (
                SELECT inituid AS cp FROM contracts_history WHERE uid=? AND inituid != '' AND inituid != ?
                UNION
                SELECT otheruid AS cp FROM contracts_history WHERE uid=? AND otheruid != '' AND otheruid != ?
            )
            WHERE cp NOT IN (SELECT uid FROM uid_usernames)
            LIMIT ?
        """, (uid, uid, uid, uid, limit)).fetchall()
    return [r["cp"] for r in rows if r["cp"]]


def init_tid_titles() -> None:
    with _db() as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS tid_titles (
                tid       VARCHAR(64)  NOT NULL,
                title     VARCHAR(512) NOT NULL,
                cached_at BIGINT,
                PRIMARY KEY (tid)
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
        """)


def upsert_tid_titles(tid_map: dict) -> None:
    """Store tid→title. {tid: title}"""
    if not tid_map:
        return
    import time as _t
    now = int(_t.time())
    with _db() as conn:
        for tid, title in tid_map.items():
            conn.execute(
                "INSERT OR REPLACE INTO tid_titles (tid, title, cached_at) VALUES (?,?,?)",
                (str(tid), str(title), now)
            )


def get_tid_titles(tids: list) -> dict:
    """Lookup thread titles from cache. Returns {tid: title}."""
    if not tids:
        return {}
    tids = [str(t) for t in tids if t]
    placeholders = ",".join("?" * len(tids))
    with _db() as conn:
        rows = conn.execute(
            f"SELECT tid, title FROM tid_titles WHERE tid IN ({placeholders})", tids
        ).fetchall()
    return {r["tid"]: r["title"] for r in rows}


def get_unknown_tids_from_contracts(uid: str, limit: int = 30) -> list:
    """Return TIDs from contracts_history (for this user) not yet in tid_titles."""
    with _db() as conn:
        rows = conn.execute("""
            SELECT DISTINCT tid FROM contracts_history
            WHERE uid=? AND tid IS NOT NULL AND tid != ''
            AND tid NOT IN (SELECT tid FROM tid_titles)
            LIMIT ?
        """, (uid, limit)).fetchall()
    return [r["tid"] for r in rows]


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
                uid      VARCHAR(64) NOT NULL,
                settings TEXT        NOT NULL DEFAULT '{}',
                PRIMARY KEY (uid)
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
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
            "INSERT INTO user_settings (uid, settings) VALUES (%s, %s) "
            "ON DUPLICATE KEY UPDATE settings=VALUES(settings)",
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
            "notifications",
            "scheduled_threads", "my_threads", "reply_queue",
            "posting_recents", "thread_drafts",
            "draft_collaborators", "draft_edit_log", "draft_presence",
            "sigmarket_rotations",
        ]:
            try:
                conn.execute(f"DELETE FROM {tbl} WHERE uid=?", (uid,))
            except Exception:
                pass
    # Autobump tables
    try:
        from modules.autobump.autobump_db import delete_user_jobs
        delete_user_jobs(uid)
    except Exception:
        pass
    # hf_resource_cache and hf_api_call_log (different column names — handled separately)
    try:
        with _db() as conn:
            conn.execute("DELETE FROM hf_resource_cache WHERE owner_uid=?", (uid,))
            for pattern in [
                f"me:{uid}", f"bytes:{uid}:", f"contracts:{uid}:",
                f"user:{uid}:", f"sigmarket:status:{uid}",
                f"sigmarket:analytics:{uid}", f"threads:uid:{uid}:",
            ]:
                conn.execute(
                    "DELETE FROM hf_resource_cache WHERE cache_key LIKE ?",
                    (pattern + "%",),
                )
            conn.execute("DELETE FROM hf_api_call_log WHERE uid=?", (uid,))
    except Exception:
        pass