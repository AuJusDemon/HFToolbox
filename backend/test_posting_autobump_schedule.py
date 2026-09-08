import importlib.util
import json
import sys
import types
import unittest
from contextlib import contextmanager
from pathlib import Path
from unittest.mock import patch


POSTING_DB = Path(__file__).parent / "modules" / "posting" / "posting_db.py"
SCHEDULE = Path(__file__).parent / "modules" / "autobump" / "schedule.py"


class Cursor:
    lastrowid = 12


class FakeConnection:
    def __init__(self):
        self.calls = []

    def execute(self, sql, params=()):
        self.calls.append((" ".join(sql.split()), params))
        return Cursor()


def load_module(path, name, connection=None):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    if connection is None:
        spec.loader.exec_module(module)
        return module

    @contextmanager
    def fake_db():
        yield connection

    compat = types.ModuleType("_db_compat")
    compat._db = fake_db
    with patch.dict(sys.modules, {"_db_compat": compat}):
        spec.loader.exec_module(module)
    return module


class PostingAutoBumpScheduleTests(unittest.TestCase):
    def test_posting_persists_the_canonical_schedule_without_translation(self):
        schedule = load_module(SCHEDULE, "posting_schedule_under_test")
        canonical = schedule.normalize_schedule_payload({
            "mode": "calendar", "interval_h": 12, "timezone": "America/New_York",
            "allowed_windows": [{"days": [0, 2, 4], "start": "09:00", "end": "22:00"}],
            "calendar_slots": [{"day": 0, "time": "10:00"}, {"day": 2, "time": "18:00"}],
            "end_mode": "bytes", "end_limit": 1000,
        })
        connection = FakeConnection()
        posting_db = load_module(POSTING_DB, "posting_db_schedule_under_test", connection)
        row_id = posting_db.create_scheduled_thread(
            "42", "107", "Marketplace", "Subject", "Body", 2000000000,
            auto_bump=True, bump_interval_h=canonical["interval_h"],
            bump_mode=canonical["mode"], bump_until=canonical["end_at"],
            bump_timezone=canonical["timezone"],
            bump_allowed_windows=canonical["allowed_windows"],
            bump_calendar_slots=canonical["calendar_slots"],
            bump_end_mode=canonical["end_mode"], bump_end_limit=canonical["end_limit"],
        )
        self.assertEqual(row_id, 12)
        _, params = connection.calls[-1]
        self.assertEqual(params[8], canonical["mode"])
        self.assertEqual(params[10], canonical["timezone"])
        self.assertEqual(json.loads(params[11]), canonical["allowed_windows"])
        self.assertEqual(json.loads(params[12]), canonical["calendar_slots"])
        self.assertEqual(params[13:15], ("bytes", 1000))


if __name__ == "__main__":
    unittest.main()
