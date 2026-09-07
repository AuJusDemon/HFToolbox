import importlib.util
import unittest
from pathlib import Path

path = Path(__file__).parent / "modules" / "autobump" / "grouping.py"
spec = importlib.util.spec_from_file_location("autobump_grouping", path)
grouping = importlib.util.module_from_spec(spec)
spec.loader.exec_module(grouping)


class AutoBumpPerformanceTests(unittest.TestCase):
    def test_consecutive_quiet_periods_are_grouped(self):
        periods = [
            {"bump_ts": 30, "end_ts": 40, "is_open": False, "period_replies": 0, "contracts_opened": 0, "contracts_completed": 0, "period_skips": []},
            {"bump_ts": 20, "end_ts": 30, "is_open": False, "period_replies": 0, "contracts_opened": 0, "contracts_completed": 0, "period_skips": []},
            {"bump_ts": 10, "end_ts": 20, "is_open": False, "period_replies": 1, "contracts_opened": 0, "contracts_completed": 0, "period_skips": []},
        ]
        result = grouping.quiet_groups(periods)
        self.assertEqual(result[0]["kind"], "quiet_group")
        self.assertEqual(result[0]["count"], 2)
        self.assertEqual(result[1]["kind"], "period")

    def test_scheduler_event_prevents_quiet_grouping(self):
        result = grouping.quiet_groups([{"bump_ts": 10, "is_open": False, "period_replies": 0, "contracts_opened": 0, "contracts_completed": 0, "period_skips": [{"action": "error"}]}])
        self.assertEqual(result[0]["kind"], "period")


if __name__ == "__main__":
    unittest.main()
