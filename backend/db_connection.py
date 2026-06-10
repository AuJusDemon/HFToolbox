"""
db_connection.py — MySQL connection pool with SQLite-compatible interface.

Drop-in replacement for the SQLite _db() context manager.
Handles SQL translation automatically:
  ? → %s
  INSERT OR IGNORE → INSERT IGNORE
  INSERT OR REPLACE → REPLACE INTO
  ON CONFLICT(...) DO UPDATE SET x=excluded.x → ON DUPLICATE KEY UPDATE x=VALUES(x)
  strftime('%s','now') → UNIX_TIMESTAMP()
  PRAGMA table_info(t) → INFORMATION_SCHEMA query
  executescript(sql) → split on ; and execute individually
"""

import os
import re
import threading
import logging
from contextlib import contextmanager

import pymysql
import pymysql.cursors

log = logging.getLogger("hftoolbox.db")

# ── Config ─────────────────────────────────────────────────────────────────────

_DB_CONFIG = {
    "host":        os.environ["DB_HOST"],
    "port":        int(os.getenv("DB_PORT", "3306")),
    "user":        os.environ["DB_USER"],
    "password":    os.environ["DB_PASSWORD"],
    "database":    os.environ["DB_NAME"],
    "charset":     "utf8mb4",
    "autocommit":  False,
    "connect_timeout": 5,
    "read_timeout":    8,
    "write_timeout":   8,
    "cursorclass": pymysql.cursors.DictCursor,
}

# ── Connection pool ────────────────────────────────────────────────────────────
# The old threading.local() approach stored one persistent connection per thread.
# With max_workers=64, that meant up to 64 open MySQL connections — exceeding
# shared hosting max_user_connections limits and causing (1203) errors.
#
# New approach: create a fresh connection per _db() call and close it on exit.
# A semaphore caps concurrent connections to MAX_POOL_CONNS regardless of how
# many threads the pool contains. pymysql.connect() is ~1-5ms on LAN — negligible.

import queue as _queue

MAX_POOL_CONNS = 8          # hard ceiling: never more than N simultaneous connections
_pool: _queue.Queue = _queue.Queue(maxsize=MAX_POOL_CONNS)
_pool_size_lock = threading.Lock()
_pool_size = 0              # total connections ever created (live + in pool)


def _create_conn():
    return pymysql.connect(**_DB_CONFIG)


def _acquire_conn():
    """Get a connection from the pool, or create one if under the cap."""
    global _pool_size
    # Fast path: reuse a pooled connection
    try:
        conn = _pool.get_nowait()
        try:
            conn.ping(reconnect=False)
            return conn
        except Exception:
            # Stale connection — discard and fall through to create a new one
            try:
                conn.close()
            except Exception:
                pass
            with _pool_size_lock:
                _pool_size -= 1
    except _queue.Empty:
        pass

    # Create a new connection if we haven't hit the cap
    with _pool_size_lock:
        if _pool_size < MAX_POOL_CONNS:
            _pool_size += 1
            create = True
        else:
            create = False

    if create:
        return _create_conn()

    # At the cap — wait up to 15 s for a connection to free up
    try:
        conn = _pool.get(timeout=15)
        try:
            conn.ping(reconnect=False)
            return conn
        except Exception:
            try:
                conn.close()
            except Exception:
                pass
            with _pool_size_lock:
                _pool_size -= 1
            return _create_conn()
    except _queue.Empty:
        # Timeout — create anyway and let MySQL reject if truly overloaded
        with _pool_size_lock:
            _pool_size += 1
        return _create_conn()


def _release_conn(conn):
    """Return a connection to the pool, or close it if the pool is full."""
    try:
        _pool.put_nowait(conn)
    except _queue.Full:
        # Pool is full (shouldn't happen normally) — just close
        try:
            conn.close()
        except Exception:
            pass
        with _pool_size_lock:
            global _pool_size
            _pool_size -= 1


# ── Row dict — supports both r["col"] and r[0] access ─────────────────────────

class RowDict(dict):
    """dict that also supports integer index access like sqlite3.Row."""
    def __getitem__(self, key):
        if isinstance(key, int):
            return list(self.values())[key]
        return super().__getitem__(key)


# ── SQL translation ────────────────────────────────────────────────────────────

_RE_PLACEHOLDER     = re.compile(r'\?')
_RE_INSERT_IGNORE   = re.compile(r'\bINSERT\s+OR\s+IGNORE\b', re.IGNORECASE)
_RE_INSERT_REPLACE  = re.compile(r'\bINSERT\s+OR\s+REPLACE\s+INTO\b', re.IGNORECASE)
_RE_STRFTIME        = re.compile(r"strftime\('%s',\s*'now'\)", re.IGNORECASE)
_RE_ON_CONFLICT     = re.compile(
    r'ON\s+CONFLICT\s*\([^)]*\)\s+DO\s+UPDATE\s+SET\b',
    re.IGNORECASE,
)
_RE_EXCLUDED        = re.compile(r'\bexcluded\.(\w+)', re.IGNORECASE)
_RE_PRAGMA_INFO     = re.compile(r'^\s*PRAGMA\s+table_info\((\w+)\)', re.IGNORECASE)
_RE_PRAGMA          = re.compile(r'^\s*PRAGMA\b', re.IGNORECASE)


def _translate(sql: str) -> str:
    sql = _RE_INSERT_IGNORE.sub('INSERT IGNORE', sql)
    sql = _RE_INSERT_REPLACE.sub('REPLACE INTO', sql)
    sql = _RE_STRFTIME.sub('UNIX_TIMESTAMP()', sql)
    sql = _RE_ON_CONFLICT.sub('ON DUPLICATE KEY UPDATE', sql)
    sql = _RE_EXCLUDED.sub(lambda m: f'VALUES({m.group(1)})', sql)
    sql = re.sub(r'(?<![`\w])key(?![`\w])(?=\s*[=,)])', '`key`', sql)
    sql = _RE_PLACEHOLDER.sub('%s', sql)
    return sql


# ── Cursor wrapper ─────────────────────────────────────────────────────────────

class _CursorWrapper:
    def __init__(self, cursor, db_name: str):
        self._cur    = cursor
        self._db     = db_name
        self._pragma = None   # holds PRAGMA results when applicable

    # expose lastrowid so code like `cur.lastrowid` works
    @property
    def lastrowid(self):
        return self._cur.lastrowid

    @property
    def rowcount(self):
        return self._cur.rowcount

    def _wrap_rows(self, rows):
        if rows is None:
            return None
        if isinstance(rows, list):
            return [RowDict(r) if isinstance(r, dict) else r for r in rows]
        return RowDict(rows) if isinstance(rows, dict) else rows

    def execute(self, sql: str, params=None):
        self._pragma = None
        sql = sql.strip()

        # PRAGMA table_info(table) → INFORMATION_SCHEMA
        m = _RE_PRAGMA_INFO.match(sql)
        if m:
            table = m.group(1)
            self._cur.execute(
                "SELECT COLUMN_NAME AS name FROM INFORMATION_SCHEMA.COLUMNS "
                "WHERE TABLE_NAME=%s AND TABLE_SCHEMA=%s ORDER BY ORDINAL_POSITION",
                (table, self._db)
            )
            # Return in format compatible with SQLite PRAGMA (index 1 = name)
            rows = self._cur.fetchall()
            self._pragma = [RowDict({"cid": i, "name": r["name"]}) for i, r in enumerate(rows)]
            return self

        # Ignore all other PRAGMAs silently
        if _RE_PRAGMA.match(sql):
            self._pragma = []
            return self

        sql = _translate(sql)
        if params:
            self._cur.execute(sql, params)
        else:
            self._cur.execute(sql)
        return self

    def executemany(self, sql: str, params):
        sql = _translate(sql.strip())
        self._cur.executemany(sql, params)
        return self

    def executescript(self, sql: str):
        """Split on ; and execute each statement (mirrors sqlite3.executescript)."""
        for stmt in sql.split(";"):
            stmt = stmt.strip()
            if stmt and not stmt.startswith("--"):
                try:
                    self.execute(stmt)
                except Exception as e:
                    # Ignore "already exists" and similar DDL no-ops
                    msg = str(e).lower()
                    if "already exists" in msg or "duplicate column" in msg:
                        pass
                    else:
                        log.debug("executescript stmt failed: %s — %s", stmt[:80], e)
        return self

    def fetchone(self):
        if self._pragma is not None:
            return self._pragma[0] if self._pragma else None
        row = self._cur.fetchone()
        return RowDict(row) if isinstance(row, dict) else row

    def fetchall(self):
        if self._pragma is not None:
            return self._pragma
        rows = self._cur.fetchall()
        return [RowDict(r) if isinstance(r, dict) else r for r in rows]

    def __iter__(self):
        return iter(self.fetchall())


# ── Connection wrapper ─────────────────────────────────────────────────────────

class _ConnWrapper:
    """Wraps a pymysql connection to expose a sqlite3-like interface."""

    def __init__(self, conn):
        self._conn   = conn
        self._cursor = conn.cursor()
        self._cw     = _CursorWrapper(self._cursor, _DB_CONFIG["database"])

    # Delegate execute/executemany/executescript to cursor wrapper
    def execute(self, sql: str, params=None):
        return self._cw.execute(sql, params)

    def executemany(self, sql: str, params):
        return self._cw.executemany(sql, params)

    def executescript(self, sql: str):
        return self._cw.executescript(sql)

    @property
    def lastrowid(self):
        return self._cw.lastrowid

    def commit(self):
        self._conn.commit()

    def rollback(self):
        self._conn.rollback()

    def close(self):
        try:
            self._cursor.close()
        except Exception:
            pass


# ── Public context manager ─────────────────────────────────────────────────────

@contextmanager
def _db():
    """Context manager yielding a MySQL connection from the pool.
    Caps concurrent connections at MAX_POOL_CONNS — prevents max_user_connections errors."""
    conn = _acquire_conn()
    wrap = _ConnWrapper(conn)
    try:
        yield wrap
        conn.commit()
    except Exception:
        try:
            conn.rollback()
        except Exception:
            pass
        raise
    finally:
        try:
            wrap._cursor.close()
        except Exception:
            pass
        _release_conn(conn)
