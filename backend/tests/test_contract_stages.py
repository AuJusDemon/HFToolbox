"""
tests/test_contract_stages.py

Focused tests for contract stage classification and bucketing.
Run with: python -m pytest backend/tests/ -v
      or: python backend/tests/test_contract_stages.py
"""
import sys
import os
import time
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from modules.merchant.metrics import (
    contract_bucket,
    classify_contract_stage,
    _AGE_EXPIRED_S,
)

INIT_UID  = '111'
OTHER_UID = '999'
MY_UID    = OTHER_UID  # current user is the counterparty in most tests
NOW       = int(time.time())
RECENT    = NOW - 3600
STALE     = NOW - _AGE_EXPIRED_S - 86400


class TestContractBucket(unittest.TestCase):

    def test_status0_recent_is_awaiting(self):
        self.assertEqual(contract_bucket('0', RECENT), 'awaiting_approval')

    def test_status1_recent_is_awaiting(self):
        self.assertEqual(contract_bucket('1', RECENT), 'awaiting_approval')

    def test_status0_stale_is_expired(self):
        self.assertEqual(contract_bucket('0', STALE), 'expired')

    def test_status1_stale_is_expired(self):
        self.assertEqual(contract_bucket('1', STALE), 'expired')

    def test_status5_is_active(self):
        self.assertEqual(contract_bucket('5', RECENT), 'active_fulfillment')

    def test_status6_is_completed(self):
        self.assertEqual(contract_bucket('6', RECENT), 'completed')

    def test_status7_is_disputed(self):
        self.assertEqual(contract_bucket('7', RECENT), 'disputed')

    def test_status8_is_expired(self):
        self.assertEqual(contract_bucket('8', RECENT), 'expired')


class TestClassifyContractStage(unittest.TestCase):

    # ── status "0" cases ─────────────────────────────────────────────────────

    def test_status0_other_is_me_ostatus0_needs_review(self):
        # Incoming contract: I am otheruid, my ostatus=0 means I haven't approved
        stage = classify_contract_stage(
            '0', RECENT, INIT_UID, MY_UID, MY_UID,
            False, NOW, istatus='1', ostatus='0',
        )
        self.assertEqual(stage, 'needs_review')

    def test_status0_init_is_me_istatus1_ostatus0_waiting(self):
        # I created it, they haven't approved yet
        stage = classify_contract_stage(
            '0', RECENT, MY_UID, OTHER_UID, MY_UID,
            False, NOW, istatus='1', ostatus='0',
        )
        self.assertEqual(stage, 'waiting_on_approval')

    def test_status0_stale_is_problem(self):
        stage = classify_contract_stage(
            '0', STALE, INIT_UID, MY_UID, MY_UID,
            False, NOW, istatus='1', ostatus='0',
        )
        self.assertEqual(stage, 'problem')

    # ── status "1" legacy (no side flags) ────────────────────────────────────

    def test_status1_no_flags_other_is_me_needs_review(self):
        stage = classify_contract_stage(
            '1', RECENT, INIT_UID, MY_UID, MY_UID,
            False, NOW, istatus='', ostatus='',
        )
        self.assertEqual(stage, 'needs_review')

    def test_status1_no_flags_init_is_me_waiting(self):
        # I created the contract; the other party ('222') hasn't approved yet
        stage = classify_contract_stage(
            '1', RECENT, MY_UID, '222', MY_UID,
            False, NOW, istatus='', ostatus='',
        )
        self.assertEqual(stage, 'waiting_on_approval')

    def test_status1_stale_no_flags_is_problem(self):
        stage = classify_contract_stage(
            '1', STALE, INIT_UID, MY_UID, MY_UID,
            False, NOW, istatus='', ostatus='',
        )
        self.assertEqual(stage, 'problem')

    # ── status "5" active / waiting ──────────────────────────────────────────

    def test_status5_no_completion_is_active(self):
        stage = classify_contract_stage(
            '5', RECENT, INIT_UID, MY_UID, MY_UID,
            False, NOW,
        )
        self.assertEqual(stage, 'active')

    def test_status5_with_completion_is_waiting_on_counterparty(self):
        stage = classify_contract_stage(
            '5', RECENT, INIT_UID, MY_UID, MY_UID,
            True, NOW,
        )
        self.assertEqual(stage, 'waiting_on_counterparty')

    # ── terminal statuses ────────────────────────────────────────────────────

    def test_status6_is_completed(self):
        stage = classify_contract_stage(
            '6', RECENT, INIT_UID, MY_UID, MY_UID,
            False, NOW,
        )
        self.assertEqual(stage, 'completed')

    def test_status7_is_problem(self):
        stage = classify_contract_stage(
            '7', RECENT, INIT_UID, MY_UID, MY_UID,
            False, NOW,
        )
        self.assertEqual(stage, 'problem')

    def test_status2_is_problem(self):
        stage = classify_contract_stage(
            '2', RECENT, INIT_UID, MY_UID, MY_UID,
            False, NOW,
        )
        self.assertEqual(stage, 'problem')


if __name__ == '__main__':
    unittest.main()
