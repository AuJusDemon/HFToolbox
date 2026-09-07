import importlib.util
import unittest
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

    def test_page_one_uses_normal_recheck_without_running(self):
        self.assertEqual(schedule.calculate_updated_next({"lastpost_ts": 100}, "page1", 6, 1000), 2800)

    def test_only_supported_intervals_are_accepted(self):
        for value in (6, 8, 12, 16, 24, 48, 72, 120, 168):
            self.assertEqual(schedule.validate_interval(value), value)
        with self.assertRaisesRegex(ValueError, "Interval must be one of"):
            schedule.validate_interval(7)


if __name__ == "__main__":
    unittest.main()
