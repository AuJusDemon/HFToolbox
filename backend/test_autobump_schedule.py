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
        self.assertEqual(schedule.calculate_updated_next({"lastpost_ts": 900}, "timer", 1, 1000), 4500)

    def test_timer_marks_already_eligible_job_due(self):
        self.assertEqual(schedule.calculate_updated_next({"lastpost_ts": 100}, "timer", 1, 5000), 5000)

    def test_timer_without_observation_schedules_from_now(self):
        self.assertEqual(schedule.calculate_updated_next({}, "timer", 6, 1000), 22600)

    def test_page_one_uses_normal_recheck_without_running(self):
        self.assertEqual(schedule.calculate_updated_next({"lastpost_ts": 100}, "page1", 6, 1000), 2800)


if __name__ == "__main__":
    unittest.main()
