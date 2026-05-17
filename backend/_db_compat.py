"""
_db_compat.py — Database connection compatibility shim.

Exports a single _db() context manager that works in both environments:

    MySQL  (production): set DB_HOST in .env
    SQLite (default):    leave DB_HOST unset — uses local data/hf_dash.db

All module db files import _db from here instead of defining their own.
This is the only file that needs to change when switching database backends.
"""
import os

if os.getenv("DB_HOST"):
    # MySQL via connection pool — db_connection.py handles pooling + SQL translation
    from db_connection import _db  # noqa: F401
else:
    # SQLite — zero config, works out of the box for local dev and self-hosting
    import sqlite3
    from pathlib import Path
    from contextlib import contextmanager

    _DB_PATH = Path(os.getenv("DB_PATH", "data/hf_dash.db"))

    def _sqlite_connect() -> sqlite3.Connection:
        _DB_PATH.parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(str(_DB_PATH), check_same_thread=False, timeout=10)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA busy_timeout=10000")
        conn.execute("PRAGMA synchronous=NORMAL")
        return conn

    @contextmanager
    def _db():
        conn = _sqlite_connect()
        try:
            yield conn
            conn.commit()
        finally:
            conn.close()
