import importlib.util
import sys
import types
import unittest
from contextlib import contextmanager
from pathlib import Path
from unittest.mock import patch


ROOT = Path(__file__).parent / "modules" / "autobump" / "autobump_db.py"


class Cursor:
    rowcount = 1
    lastrowid = 1


class FakeConnection:
    def __init__(self):
        self.calls = []
        self.page1_pending = True

    def execute(self, sql, params=()):
        normalized = " ".join(sql.split())
        self.calls.append((normalized, params))
        if normalized.startswith("SELECT id,uid,tid FROM bump_jobs"):
            return Rows([{"id": 7, "uid": "42", "tid": "99"}] if self.page1_pending else [])
        if normalized.startswith("UPDATE bump_jobs SET enabled=0,retired_reason"):
            self.page1_pending = False
        return Cursor()


class Rows:
    def __init__(self, rows):
        self.rows = rows

    def fetchall(self):
        return self.rows


def load_with(connection):
    @contextmanager
    def fake_db():
        yield connection

    compat = types.ModuleType("_db_compat")
    compat._db = fake_db
    spec = importlib.util.spec_from_file_location("autobump_db_under_test", ROOT)
    module = importlib.util.module_from_spec(spec)
    with patch.dict(sys.modules, {"_db_compat": compat}):
        spec.loader.exec_module(module)
    return module


class AutoBumpDatabaseTests(unittest.TestCase):
    def test_page1_retirement_is_idempotent_and_preserves_mode(self):
        connection = FakeConnection()
        module = load_with(connection)
        module._migrate()
        module._migrate()
        retirement_updates = [sql for sql, _ in connection.calls if sql.startswith("UPDATE bump_jobs SET enabled=0,retired_reason")]
        audit_rows = [sql for sql, _ in connection.calls if "INSERT INTO bump_log" in sql]
        self.assertEqual(len(retirement_updates), 1)
        self.assertEqual(len(audit_rows), 1)
        self.assertNotIn("mode=", retirement_updates[0].split("WHERE", 1)[0])

    def test_skips_do_not_advance_success_or_spending_counters(self):
        connection = FakeConnection()
        module = load_with(connection)
        module.update_after_skip(3, 5000)
        sql, params = connection.calls[-1]
        self.assertNotIn("bump_count", sql)
        self.assertNotIn("spent_bytes", sql)
        self.assertEqual(params[1:], (5000, 3))

    def test_confirmed_bump_advances_both_counters_with_snapshot_total(self):
        connection = FakeConnection()
        module = load_with(connection)
        module.update_after_bump(3, "Thread", "107", 4000, "Stanley", 85)
        sql, params = connection.calls[-1]
        self.assertIn("bump_count=bump_count+1", sql)
        self.assertIn("spent_bytes=spent_bytes+%s", sql)
        self.assertEqual(params[1], 85)

    def test_new_page1_jobs_are_rejected_before_database_access(self):
        connection = FakeConnection()
        module = load_with(connection)
        with self.assertRaisesRegex(ValueError, "Activity Interval or Calendar"):
            module.add_job("42", "99", 12, mode="page1")
        self.assertEqual(connection.calls, [])


if __name__ == "__main__":
    unittest.main()
