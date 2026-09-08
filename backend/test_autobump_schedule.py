import importlib.util
import unittest
from datetime import datetime, timezone
from pathlib import Path


ROOT = Path(__file__).parent / "modules" / "autobump"


def load(name):
    spec = importlib.util.spec_from_file_location(name, ROOT / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


schedule = load("schedule")


class AutoBumpScheduleTests(unittest.TestCase):
    def test_timer_uses_future_eligibility(self):
        self.assertEqual(schedule.calculate_updated_next({"lastpost_ts": 900}, "timer", 6, 1000), 22500)

    def test_timer_marks_already_eligible_job_due(self):
        self.assertEqual(schedule.calculate_updated_next({"lastpost_ts": 100}, "timer", 6, 50000), 50000)

    def test_timer_without_observation_schedules_from_now(self):
        self.assertEqual(schedule.calculate_updated_next({}, "timer", 6, 1000), 22600)

    def test_page_one_is_rejected(self):
        with self.assertRaisesRegex(ValueError, "Invalid bump mode"):
            schedule.calculate_updated_next({"lastpost_ts": 100}, "page1", 6, 1000)
        with self.assertRaisesRegex(ValueError, "mode must be one of"):
            schedule.normalize_schedule_payload({"mode": "page1", "interval_h": 12})

    def test_only_supported_intervals_are_accepted(self):
        for value in (6, 8, 12, 16, 24, 48, 72, 120, 168):
            self.assertEqual(schedule.validate_interval(value), value)
        with self.assertRaisesRegex(ValueError, "Interval must be one of"):
            schedule.validate_interval(7)

    def test_multiple_allowed_windows_choose_the_next_opening(self):
        monday_8 = int(datetime(2026, 9, 7, 12, tzinfo=timezone.utc).timestamp())
        windows = [
            {"days": [0], "start": "09:00", "end": "11:00"},
            {"days": [0], "start": "14:00", "end": "16:00"},
        ]
        # New York is UTC-4 on this date: candidate is Monday 08:00 local.
        self.assertEqual(
            schedule.next_allowed_time(monday_8, "America/New_York", windows),
            int(datetime(2026, 9, 7, 13, tzinfo=timezone.utc).timestamp()),
        )

    def test_overnight_window_includes_the_following_day(self):
        candidate = int(datetime(2026, 9, 8, 5, tzinfo=timezone.utc).timestamp())
        windows = [{"days": [0], "start": "22:00", "end": "02:00"}]
        self.assertEqual(schedule.next_allowed_time(candidate, "America/New_York", windows), candidate)

    def test_dst_gap_advances_past_nonexistent_window(self):
        candidate = int(datetime(2026, 3, 8, 6, 0, tzinfo=timezone.utc).timestamp())
        windows = [{"days": [6], "start": "02:30", "end": "04:00"}]
        result = schedule.next_allowed_time(candidate, "America/New_York", windows)
        self.assertEqual(datetime.fromtimestamp(result, timezone.utc), datetime(2026, 3, 15, 6, 30, tzinfo=timezone.utc))

    def test_dst_fold_uses_first_future_calendar_occurrence(self):
        candidate = int(datetime(2026, 11, 1, 4, 0, tzinfo=timezone.utc).timestamp())
        slots = [{"day": 6, "time": "01:30"}]
        result = schedule.next_calendar_slot(candidate, "America/New_York", slots)
        self.assertEqual(datetime.fromtimestamp(result, timezone.utc), datetime(2026, 11, 1, 5, 30, tzinfo=timezone.utc))

    def test_missed_calendar_slot_advances_without_catch_up(self):
        after_slot = int(datetime(2026, 9, 7, 15, 1, tzinfo=timezone.utc).timestamp())
        slots = [{"day": 0, "time": "11:00"}]
        result = schedule.next_calendar_slot(after_slot, "UTC", slots)
        self.assertEqual(datetime.fromtimestamp(result, timezone.utc), datetime(2026, 9, 14, 11, 0, tzinfo=timezone.utc))

    def test_recent_activity_defers_calendar_to_a_future_slot(self):
        now = int(datetime(2026, 9, 7, 8, 0, tzinfo=timezone.utc).timestamp())
        lastpost = int(datetime(2026, 9, 7, 7, 0, tzinfo=timezone.utc).timestamp())
        slots = [{"day": 0, "time": "10:00"}, {"day": 1, "time": "10:00"}]
        result = schedule.calculate_updated_next(
            {"lastpost_ts": lastpost}, "calendar", 6, now,
            "UTC", [], slots,
        )
        self.assertEqual(datetime.fromtimestamp(result, timezone.utc), datetime(2026, 9, 8, 10, 0, tzinfo=timezone.utc))

    def test_end_conditions_normalize(self):
        self.assertEqual(schedule.validate_end_condition("unlimited", now=100), ("unlimited", None, None))
        self.assertEqual(schedule.validate_end_condition("date", end_at=200, now=100), ("date", 200, None))
        self.assertEqual(schedule.validate_end_condition("duration", end_days=2, now=100), ("duration", 172900, 2))
        self.assertEqual(schedule.validate_end_condition("duration", end_at=500, now=100), ("duration", 500, None))
        self.assertEqual(schedule.validate_end_condition("successes", end_limit=4, now=100), ("successes", None, 4))
        self.assertEqual(schedule.validate_end_condition("bytes", end_limit=500, now=100), ("bytes", None, 500))
        self.assertEqual(
            schedule.end_of_local_date("2026-03-08", "America/New_York"),
            int(datetime(2026, 3, 9, 3, 59, 59, tzinfo=timezone.utc).timestamp()),
        )

    def test_validation_rejects_duplicates_and_conflicting_end_values(self):
        with self.assertRaisesRegex(ValueError, "Duplicate calendar"):
            schedule.validate_calendar_slots([{"day": 0, "time": "10:00"}, {"day": 0, "time": "10:00"}])
        with self.assertRaisesRegex(ValueError, "only an end date"):
            schedule.validate_end_condition("date", end_at=200, end_limit=3, now=100)
        with self.assertRaisesRegex(ValueError, "greater than zero"):
            schedule.validate_end_condition("bytes", end_limit=0, now=100)

    def test_canonical_api_payload_validation(self):
        valid = schedule.normalize_schedule_payload({
            "mode": "calendar", "interval_h": 12, "timezone": "America/New_York",
            "allowed_windows": [{"days": [0, 2], "start": "09:00", "end": "23:00"}],
            "calendar_slots": [{"day": 0, "time": "10:00"}],
            "end_mode": "successes", "end_limit": 20,
        }, now=100)
        self.assertEqual(valid["mode"], "calendar")
        self.assertEqual(valid["end_limit"], 20)
        dated = schedule.normalize_schedule_payload({
            "mode":"timer", "interval_h":12, "timezone":"America/New_York",
            "end_mode":"date", "end_date":"2026-09-30",
        }, now=100)
        self.assertEqual(datetime.fromtimestamp(dated["end_at"], timezone.utc), datetime(2026, 10, 1, 3, 59, 59, tzinfo=timezone.utc))
        with self.assertRaisesRegex(ValueError, "IANA"):
            schedule.normalize_schedule_payload({"mode": "timer", "interval_h": 12, "timezone": "Eastern-ish"})
        with self.assertRaisesRegex(ValueError, "weekdays"):
            schedule.normalize_schedule_payload({"mode": "timer", "interval_h": 12, "allowed_windows": [{"days": [7], "start": "09:00", "end": "17:00"}]})
        with self.assertRaisesRegex(ValueError, "HH:MM"):
            schedule.normalize_schedule_payload({"mode": "calendar", "interval_h": 12, "calendar_slots": [{"day": 0, "time": "9am"}]})
        with self.assertRaisesRegex(ValueError, "requires at least one"):
            schedule.normalize_schedule_payload({"mode": "calendar", "interval_h": 12})


if __name__ == "__main__":
    unittest.main()
