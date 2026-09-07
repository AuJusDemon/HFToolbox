import unittest
import importlib.util
from pathlib import Path

spec = importlib.util.spec_from_file_location("autobump_fees", Path(__file__).parent / "modules" / "autobump" / "fees.py")
fees = importlib.util.module_from_spec(spec)
spec.loader.exec_module(fees)
fee_breakdown = fees.fee_breakdown
hf_fee_for_groups = fees.hf_fee_for_groups
normalize_groups = fees.normalize_groups


class AutoBumpFeeTests(unittest.TestCase):
    def test_regular_and_l33t_use_default_fee(self):
        self.assertEqual(hf_fee_for_groups([]), 100)
        self.assertEqual(hf_fee_for_groups(["9"]), 100)

    def test_uber_and_vendor_fees(self):
        self.assertEqual(hf_fee_for_groups(["28"]), 75)
        self.assertEqual(hf_fee_for_groups(["28", "67"]), 50)

    def test_serialized_groups_are_normalized(self):
        self.assertEqual(normalize_groups('["9", "28"]'), {"9", "28"})
        self.assertEqual(normalize_groups("9,67"), {"9", "67"})

    def test_service_fee_and_owner_exemption(self):
        self.assertEqual(fee_breakdown("42", ["28"], owner_uid="761578"), {"hf_fee": 75, "service_fee": 10, "total_cost": 85})
        self.assertEqual(fee_breakdown("761578", ["67"], owner_uid="761578"), {"hf_fee": 50, "service_fee": 0, "total_cost": 50})


if __name__ == "__main__":
    unittest.main()
