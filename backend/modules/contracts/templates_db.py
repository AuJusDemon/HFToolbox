"""
modules/contracts/templates_db.py — contract template persistence.

Table: contract_templates
  id            INT PRIMARY KEY AUTO_INCREMENT
  uid           VARCHAR — owner
  name          VARCHAR — display name
  position      VARCHAR — selling/buying/exchanging/trading/vouchcopy
  terms         TEXT    — full terms BBCode
  yourproduct   VARCHAR
  yourcurrency  VARCHAR
  youramount    VARCHAR
  theirproduct  VARCHAR
  theircurrency VARCHAR
  theiramount   VARCHAR
  address       VARCHAR
  middleman_uid VARCHAR
  timeout_days  INT     — default 14
  is_public     TINYINT — 0=private, 1=public
  created_at    BIGINT
  updated_at    BIGINT
"""

import time
from db_connection import _db

TEMPLATE_FIELDS = [
    "id", "uid", "name", "position", "terms",
    "yourproduct", "yourcurrency", "youramount",
    "theirproduct", "theircurrency", "theiramount",
    "address", "middleman_uid",
    "timeout_days", "is_public", "created_at", "updated_at",
]


def init_templates_db() -> None:
    with _db() as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS contract_templates (
                id            INT          NOT NULL AUTO_INCREMENT,
                uid           VARCHAR(64)  NOT NULL,
                name          VARCHAR(255) NOT NULL DEFAULT 'Untitled',
                position      VARCHAR(64)  NOT NULL DEFAULT 'selling',
                terms         TEXT         NOT NULL,
                yourproduct   VARCHAR(512) NOT NULL DEFAULT '',
                yourcurrency  VARCHAR(64)  NOT NULL DEFAULT 'other',
                youramount    VARCHAR(64)  NOT NULL DEFAULT '0',
                theirproduct  VARCHAR(512) NOT NULL DEFAULT '',
                theircurrency VARCHAR(64)  NOT NULL DEFAULT 'other',
                theiramount   VARCHAR(64)  NOT NULL DEFAULT '0',
                address       VARCHAR(512) NOT NULL DEFAULT '',
                middleman_uid VARCHAR(64)  NOT NULL DEFAULT '',
                timeout_days  INT          NOT NULL DEFAULT 14,
                is_public     TINYINT      NOT NULL DEFAULT 0,
                created_at    BIGINT       NOT NULL DEFAULT 0,
                updated_at    BIGINT       NOT NULL DEFAULT 0,
                PRIMARY KEY (id),
                INDEX idx_ct_uid (uid)
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
        """)
        # Migration-safe column additions
        for col, defn in [
            ("address",       "VARCHAR(512) NOT NULL DEFAULT ''"),
            ("middleman_uid", "VARCHAR(64)  NOT NULL DEFAULT ''"),
        ]:
            try:
                conn.execute(f"ALTER TABLE contract_templates ADD COLUMN {col} {defn}")
            except Exception:
                pass


def _row_to_dict(row) -> dict:
    d = dict(row)
    d["is_public"] = bool(d["is_public"])
    return d


def list_templates(uid: str) -> list[dict]:
    """Return own templates + all public templates from others."""
    with _db() as conn:
        rows = conn.execute("""
            SELECT * FROM contract_templates
            WHERE uid = %s OR is_public = 1
            ORDER BY (uid = %s) DESC, updated_at DESC
        """, (uid, uid)).fetchall()
    return [_row_to_dict(r) for r in rows]


def get_template(tid: int, uid: str) -> dict | None:
    """Get a single template — must be owned or public."""
    with _db() as conn:
        row = conn.execute("""
            SELECT * FROM contract_templates
            WHERE id = %s AND (uid = %s OR is_public = 1)
        """, (tid, uid)).fetchone()
    return _row_to_dict(row) if row else None


def create_template(uid: str, data: dict) -> int:
    now = int(time.time())
    with _db() as conn:
        cur = conn.execute("""
            INSERT INTO contract_templates
              (uid, name, position, terms, yourproduct, yourcurrency, youramount,
               theirproduct, theircurrency, theiramount,
               address, middleman_uid, timeout_days, is_public,
               created_at, updated_at)
            VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
        """, (
            uid,
            data.get("name", "Untitled")[:100],
            data.get("position", "selling"),
            data.get("terms", ""),
            data.get("yourproduct", ""),
            data.get("yourcurrency", "other"),
            str(data.get("youramount", "0")),
            data.get("theirproduct", ""),
            data.get("theircurrency", "other"),
            str(data.get("theiramount", "0")),
            data.get("address", ""),
            data.get("middleman_uid", ""),
            int(data.get("timeout_days", 14)),
            int(bool(data.get("is_public", False))),
            now, now,
        ))
    return cur.lastrowid


def update_template(tid: int, uid: str, data: dict) -> bool:
    now = int(time.time())
    with _db() as conn:
        cur = conn.execute("""
            UPDATE contract_templates SET
              name=%s, position=%s, terms=%s,
              yourproduct=%s, yourcurrency=%s, youramount=%s,
              theirproduct=%s, theircurrency=%s, theiramount=%s,
              address=%s, middleman_uid=%s,
              timeout_days=%s, is_public=%s, updated_at=%s
            WHERE id = %s AND uid = %s
        """, (
            data.get("name", "Untitled")[:100],
            data.get("position", "selling"),
            data.get("terms", ""),
            data.get("yourproduct", ""),
            data.get("yourcurrency", "other"),
            str(data.get("youramount", "0")),
            data.get("theirproduct", ""),
            data.get("theircurrency", "other"),
            str(data.get("theiramount", "0")),
            data.get("address", ""),
            data.get("middleman_uid", ""),
            int(data.get("timeout_days", 14)),
            int(bool(data.get("is_public", False))),
            now, tid, uid,
        ))
    return cur.rowcount > 0


def delete_template(tid: int, uid: str) -> bool:
    with _db() as conn:
        cur = conn.execute(
            "DELETE FROM contract_templates WHERE id = %s AND uid = %s",
            (tid, uid)
        )
    return cur.rowcount > 0
