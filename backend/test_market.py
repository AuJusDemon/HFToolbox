"""Local database and classification tests for Market Pulse."""

from __future__ import annotations

import os
import asyncio
import tempfile
import unittest
import importlib
from unittest.mock import AsyncMock, patch

_tmp = tempfile.NamedTemporaryFile(prefix="hft-market-", suffix=".db", delete=False)
_tmp.close()
os.environ.pop("DB_HOST", None)
os.environ["DB_PATH"] = _tmp.name

try:
    from modules.market import collector  # noqa: E402
    from modules.market.collector import _classify  # noqa: E402
    from modules.market.collector import _reply_count_from_final_page  # noqa: E402
except ImportError:
    collector = None
    _classify = None
    _reply_count_from_final_page = None
from modules.market import market_db  # noqa: E402
from modules.market import topics  # noqa: E402
market_router = importlib.import_module("modules.market.router")  # noqa: E402
from modules.merchant import merchant_db  # noqa: E402
import importlib.util  # noqa: E402
_posting_spec = importlib.util.spec_from_file_location(
    "posting_db_under_test", os.path.join(os.path.dirname(__file__), "modules", "posting", "posting_db.py")
)
posting_db = importlib.util.module_from_spec(_posting_spec)
_posting_spec.loader.exec_module(posting_db)
from types import SimpleNamespace  # noqa: E402


class MarketTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        market_db.init_market_db()
        from _db_compat import _db
        with _db() as conn:
            conn.execute("CREATE TABLE IF NOT EXISTS merchant_followups (id TEXT PRIMARY KEY,uid TEXT,cid TEXT,tid TEXT,counterparty_uid TEXT,template_id TEXT,subject_snapshot TEXT,body_snapshot TEXT,note TEXT,marked_sent_at INTEGER,corrected_at INTEGER,correction_note TEXT,created_at INTEGER)")
            conn.execute("CREATE TABLE IF NOT EXISTS merchant_contract_workflow (uid TEXT,cid TEXT,completed_side_at INTEGER,last_followup_at INTEGER,updated_at INTEGER,PRIMARY KEY(uid,cid))")

    @classmethod
    def tearDownClass(cls):
        try:
            os.unlink(_tmp.name)
        except FileNotFoundError:
            pass

    def test_classification(self):
        if _classify is None:
            self.skipTest("private market collector is not present in this checkout")
        self.assertEqual(_classify("Looking for IPTV reseller", "", 308)[0], "wtb")
        self.assertEqual(_classify("Managed VPS hosting", "", 145)[1], "hosting")
        self.assertEqual(_classify("Logo design service", "", 219)[1], "design")
        self.assertEqual(
            _classify("Member has disputed a contract", "looking for resolution", 111)[0],
            "dispute",
        )

    def test_disputes_are_retained_but_excluded_from_market_demand(self):
        market_db.upsert_thread({
            "tid": "900003", "fid": "111", "uid": "12345",
            "subject": "Member has Disputed a Contract with Seller",
            "dateline": "100", "lastpost": "100", "views": "48",
            "numreplies": "0", "closed": "0", "firstpost": {"pid": "800003"},
        }, "dispute", "other")
        market_db.update_opening_post(900003, "Dispute details", "dispute-hash")
        self.assertEqual(market_db.list_threads(1, 25)["total"], 0)
        disputes = market_db.list_disputes()
        self.assertEqual(disputes["total"], 1)
        self.assertEqual(disputes["disputes"][0]["tid"], 900003)
        self.assertEqual(topics.assign_unclassified()["assigned"], 0)
        market_db.remove_thread(900003)

    def test_topic_normalization_preserves_modifiers(self):
        self.assertEqual(topics.normalize("[WTB] Claude Max API accounts"),
                         ["claude", "max", "api"])

    def test_owner_free_preview_is_disabled(self):
        request = SimpleNamespace(session={"market_access_preview": "free"})
        with patch.object(market_router, "ACCESS_PREVIEW_ENABLED", True):
            self.assertFalse(market_router._previewing_free("761578", request))
            self.assertFalse(market_router._previewing_free("12345", request))
        with patch.object(market_router, "ACCESS_PREVIEW_ENABLED", False):
            self.assertFalse(market_router._previewing_free("761578", request))

    def test_followup_requires_explicit_record_and_can_be_corrected(self):
        event = merchant_db.create_followup("761578", "99001", "88001", "42",
                                            "template-a", "Checking in", "Body")
        rows = merchant_db.list_followups("761578", "99001")
        self.assertEqual(len(rows), 1)
        self.assertIsNone(rows[0]["corrected_at"])
        self.assertTrue(merchant_db.correct_followup("761578", event["id"], "not sent"))
        self.assertIsNotNone(merchant_db.list_followups("761578", "99001")[0]["corrected_at"])

    def test_market_pass_default_price_is_five_hundred_bytes(self):
        self.assertEqual(market_router.PASS_PRICE, 500)
        self.assertTrue(market_router.PASS_PERMANENT)
        paths = {route.path for route in market_router.router.routes}
        self.assertFalse(any("/bulk/" in path for path in paths))
        self.assertNotIn("/contracts", paths)

    def test_owned_reply_checks_are_durable_and_recoverable(self):
        from _db_compat import _db
        with _db() as conn:
            conn.execute("CREATE TABLE IF NOT EXISTS my_threads (uid TEXT,tid TEXT,fid TEXT,title TEXT,created_at INTEGER,last_pid TEXT,last_checked INTEGER,lastpost INTEGER,lastposteruid TEXT,numreplies INTEGER,closed INTEGER DEFAULT 0,firstpost TEXT DEFAULT '0',PRIMARY KEY(uid,tid))")
            conn.execute("CREATE TABLE IF NOT EXISTS owned_reply_checks (uid TEXT,tid TEXT,thread_title TEXT,numreplies_hint INTEGER,seed_only INTEGER,target_lastpost INTEGER,status TEXT,attempts INTEGER,next_attempt_at INTEGER,last_error TEXT,queued_at INTEGER,updated_at INTEGER,PRIMARY KEY(uid,tid))")
        posting_db.add_my_thread("761578", "88001", "107", "Test sales thread", 100, "42", 31)
        posting_db.enqueue_owned_reply_check(
            "761578", "88001", "Test sales thread", 31, False, 100
        )
        claimed = posting_db.claim_owned_reply_checks({"761578"}, 10)
        self.assertEqual([row["tid"] for row in claimed], ["88001"])
        posting_db.retry_owned_reply_check("761578", "88001", "temporary")
        with _db() as conn:
            conn.execute("UPDATE owned_reply_checks SET next_attempt_at=0 WHERE uid='761578'")
        self.assertEqual(len(posting_db.claim_owned_reply_checks({"761578"}, 10)), 1)
        posting_db.finish_owned_reply_check("761578", "88001")
        self.assertEqual(posting_db.claim_owned_reply_checks({"761578"}, 10), [])

    def test_products_only_group_owned_marketplace_threads(self):
        from _db_compat import _db
        with _db() as conn:
            conn.execute("CREATE TABLE IF NOT EXISTS my_threads (uid TEXT,tid TEXT,fid TEXT,title TEXT,created_at INTEGER,last_pid TEXT,last_checked INTEGER,lastpost INTEGER,lastposteruid TEXT,numreplies INTEGER,closed INTEGER DEFAULT 0,firstpost TEXT DEFAULT '0',PRIMARY KEY(uid,tid))")
            conn.execute("CREATE TABLE IF NOT EXISTS merchant_offers (uid TEXT,tid TEXT,label TEXT,category TEXT,status TEXT,goal_json TEXT,hidden INTEGER,created_at INTEGER,updated_at INTEGER,PRIMARY KEY(uid,tid))")
            conn.execute("CREATE TABLE IF NOT EXISTS contracts_history (uid TEXT,tid TEXT,cid TEXT,status_n TEXT,dateline INTEGER DEFAULT 0,PRIMARY KEY(uid,cid))")
            conn.execute("CREATE TABLE IF NOT EXISTS merchant_products (id TEXT PRIMARY KEY,uid TEXT,name TEXT,slug TEXT,status TEXT DEFAULT 'active',source TEXT,confidence REAL,created_at INTEGER,updated_at INTEGER,UNIQUE(uid,slug))")
            conn.execute("CREATE TABLE IF NOT EXISTS merchant_product_threads (uid TEXT,product_id TEXT,tid TEXT,confidence REAL,source TEXT,excluded INTEGER DEFAULT 0,created_at INTEGER,updated_at INTEGER,PRIMARY KEY(uid,tid))")
            conn.execute("INSERT OR REPLACE INTO my_threads (uid,tid,fid,title,created_at,lastpost,lastposteruid,numreplies) VALUES ('puser','99001','107','Managed VPS Hosting',1,1,'2',0)")
            conn.execute("INSERT OR REPLACE INTO my_threads (uid,tid,fid,title,created_at,lastpost,lastposteruid,numreplies) VALUES ('puser','99002','1','Unrelated discussion',1,1,'2',0)")
            conn.execute("INSERT OR REPLACE INTO contracts_history (uid,tid,cid,status_n,dateline) VALUES ('puser','99001','1','5',?)", (int(__import__("time").time()),))
        merchant_db.sync_seller_products("puser")
        products = merchant_db.list_seller_products("puser")
        tids = {thread["tid"] for product in products for thread in product["threads"]}
        self.assertEqual(tids, {"99001"})

    def test_reply_count_page_boundaries(self):
        if _reply_count_from_final_page is None:
            self.skipTest("private market collector is not present in this checkout")
        self.assertEqual(_reply_count_from_final_page(1, 1), 0)
        self.assertEqual(_reply_count_from_final_page(1, 30), 29)
        self.assertEqual(_reply_count_from_final_page(2, 1), 30)
        self.assertEqual(_reply_count_from_final_page(2, 2), 31)
        self.assertEqual(_reply_count_from_final_page(4, 8), 97)

    def test_market_reads_are_submitted_as_background_work(self):
        if collector is None:
            self.skipTest("private market collector is not present in this checkout")
        worker = collector.Collector("scheduler", [], 1)
        worker.client = AsyncMock()
        worker.client.token = "test-token"
        worker.client.read.return_value = {"threads": []}
        asyncio.run(worker._read("threads:107:1", {}))
        options = worker.client.read.await_args.kwargs
        self.assertTrue(options["background"])
        self.assertEqual("public", options["privacy_scope"])
        self.assertEqual(6, options["priority"])

    def test_empty_hf_response_fails_collection_instead_of_advancing(self):
        if collector is None:
            self.skipTest("private market collector is not present in this checkout")
        worker = collector.Collector("scheduler", [], 1)
        worker.client = AsyncMock()
        worker.client.token = "test-token"
        worker.client.read.return_value = None
        worker.remaining = 100
        with patch.object(collector, "get_circuit_status", return_value={
                 "available": True, "retry_after_seconds": 0, "reason": "",
             }):
            with self.assertRaisesRegex(RuntimeError, "HF market read failed"):
                asyncio.run(worker._read("empty", {}))
        self.assertEqual(worker.calls, 1)

    def test_deleted_threads_are_removed(self):
        thread = {
            "tid": "900002", "fid": "107", "uid": "12345",
            "subject": "Unavailable listing", "dateline": "100",
            "lastpost": "100", "views": "2", "closed": "0",
            "sticky": "0", "firstpost": {"pid": "800002"},
        }
        market_db.upsert_thread(thread, "wts", "other")
        market_db.update_opening_post(900002, "[deleted]", "deleted-hash")
        self.assertEqual(market_db.list_threads(1, 25)["total"], 0)
        self.assertIsNone(market_db.thread_detail(900002))
        market_db.remove_thread(900002)
        self.assertIsNone(market_db.get_thread(900002))

    def test_unqueried_sellers_come_before_deep_pagination(self):
        for seller in market_db.due_sellers(100):
            market_db.mark_seller_checked(seller["uid"], 0, 1)
        market_db.upsert_thread({
            "tid": "900010", "fid": "107", "uid": "30001",
            "subject": "First seller", "dateline": "100", "lastpost": "100",
            "views": "500", "numreplies": "0", "firstpost": {"pid": "800010"},
        }, "wts", "other")
        market_db.mark_seller_checked(30001, 30, 1)
        market_db.upsert_thread({
            "tid": "900011", "fid": "107", "uid": "30002",
            "subject": "Unqueried seller", "dateline": "100", "lastpost": "100",
            "views": "1", "numreplies": "0", "firstpost": {"pid": "800011"},
        }, "wts", "other")
        self.assertEqual(market_db.due_sellers(1)[0]["uid"], 30002)

    def test_failed_zero_call_run_does_not_pin_allowance(self):
        run_id = market_db.begin_run("scheduler", [107])
        market_db.finish_run(
            run_id, calls_used=0, remaining=9, status="failed",
            error="HF allowance below market safety floor",
        )
        self.assertIsNone(market_db.latest_remaining())

    def test_forward_contract_frontier_keeps_overlap_and_backs_off(self):
        if collector is None:
            self.skipTest("private market collector is not present in this checkout")
        before = market_db.get_contract_cursor("forward")
        requested_start = int(before["next_cid"])

        async def fake_read(worker, _label, asks):
            worker.calls += 1
            worker.remaining = 119
            cid = asks["contracts"]["_cid"][0]
            return {"contracts": {
                "cid": str(cid), "tid": "999997", "status": "5", "type": "1",
                "public": "0", "dateline": "200", "otherdateline": "0",
                "inituid": "12345", "otheruid": "54321",
            }}

        with (
            patch.object(collector.db, "get_token", return_value="token"),
            patch.object(collector, "HFClient", return_value=object()),
            patch.object(
                collector, "_safe_remaining",
                new=AsyncMock(return_value=120),
            ),
            patch.object(collector.Collector, "_read", new=fake_read),
        ):
            result = asyncio.run(
                collector.scan_contract_frontier("forward", 1)
            )

        self.assertEqual(result["calls_used"], 1)
        self.assertEqual(result["contracts_seen"], 1)
        after = market_db.get_contract_cursor("forward")
        self.assertLessEqual(int(after["next_cid"]), requested_start + 1)
        self.assertEqual(int(after["confirmed_cid"]), requested_start)
        self.assertGreater(int(after["next_probe_at"]), 0)

        market_db.update_forward_frontier(int(after["next_cid"]), [])
        empty = market_db.get_contract_cursor("forward")
        self.assertEqual(int(empty["empty_streak"]), 1)
        first_retry = int(empty["next_probe_at"])
        market_db.update_forward_frontier(int(empty["next_cid"]), [])
        second_empty = market_db.get_contract_cursor("forward")
        self.assertEqual(int(second_empty["empty_streak"]), 2)
        self.assertGreater(int(second_empty["next_probe_at"]), first_retry)

        market_db.update_forward_frontier(
            int(second_empty["next_cid"]), [requested_start + 1]
        )
        recovered = market_db.get_contract_cursor("forward")
        self.assertEqual(int(recovered["empty_streak"]), 0)
        self.assertEqual(int(recovered["confirmed_cid"]), requested_start + 1)

    def test_priority_and_reply_queues_are_durable(self):
        thread = {
            "tid": "900020", "fid": "107", "uid": "40001",
            "subject": "Active hosting service", "dateline": "100",
            "lastpost": "100", "views": "10", "firstpost": {"pid": "800020"},
        }
        market_db.upsert_thread(thread, "wts", "hosting")
        job = market_db.due_reply_verification()
        self.assertEqual(int(job["tid"]), 900020)
        market_db.finish_reply_verification(900020, 31)
        stored = market_db.get_thread(900020)
        self.assertEqual(stored["replies"], 31)
        self.assertEqual(stored["reply_confidence"], "verified")

        changed = dict(thread, lastpost="200", views="100")
        state = market_db.upsert_thread(changed, "wts", "hosting")
        self.assertTrue(state["lastpost_changed"])
        self.assertEqual(market_db.get_thread(900020)["priority_tier"], "hot")
        self.assertIn(900020, market_db.due_thread_refreshes(30))
        market_db.remove_thread(900020)

    def test_contract_promotes_known_thread(self):
        thread = {
            "tid": "900030", "fid": "107", "uid": "50001",
            "subject": "Contract listing", "dateline": "100",
            "lastpost": "100", "views": "1", "numreplies": "0",
            "firstpost": {"pid": "800030"},
        }
        market_db.upsert_thread(thread, "wts", "other")
        market_db.finish_thread_refreshes([900030])
        market_db.upsert_contract(50001, {
            "cid": "700030", "tid": "900030", "status": "5", "type": "1",
            "public": "0", "dateline": "110", "inituid": "50001",
            "otheruid": "50002",
        })
        self.assertIn(900030, market_db.due_thread_refreshes(30))
        market_db.remove_thread(900030)

    def test_thread_contract_and_watch_flow(self):
        thread = {
            "tid": "900001", "fid": "107", "uid": "12345",
            "subject": "Managed VPS hosting", "dateline": "100",
            "lastpost": "100", "views": "42", "numreplies": "3", "closed": "0",
            "sticky": "0", "firstpost": {"pid": "800001"},
        }
        state = market_db.upsert_thread(thread, "wts", "hosting")
        self.assertTrue(state["new"])
        market_db.update_opening_post(
            900001, "Managed hosting with daily backups", "hash-one"
        )
        market_db.upsert_contract(12345, {
            "cid": "700001", "tid": "900001", "status": "6", "type": "1",
            "public": "0", "dateline": "110", "otherdateline": "120",
            "inituid": "12345", "otheruid": "54321",
        })
        market_db.upsert_contract(12345, {
            "cid": "700002", "tid": "900001", "status": "8", "type": "1",
            "public": "0", "dateline": "115", "otherdateline": "125",
        })
        result = market_db.list_threads(1, 25, contract_only=True)
        self.assertEqual(result["total"], 1)
        self.assertEqual(result["threads"][0]["complete_contracts"], 1)
        self.assertEqual(result["threads"][0]["expired_contracts"], 1)
        self.assertEqual(
            market_db.list_threads(
                1, 25, sort="expired_contracts", sort_dir="asc"
            )["threads"][0]["tid"],
            900001,
        )
        detail = market_db.thread_detail(900001)
        self.assertEqual(detail["replies"], 3)
        self.assertEqual(
            {row["status"] for row in detail["contract_counts"]}, {"6", "8"}
        )
        contracts = market_db.list_contracts(
            1, 25, status="expired", query="900001"
        )
        self.assertEqual(contracts["total"], 1)
        self.assertEqual(contracts["contracts"][0]["cid"], 700002)
        hosting = next(
            row for row in market_db.pulse()["categories"]
            if row["category"] == "hosting"
        )
        self.assertEqual(int(hosting["threads"]), 1)
        self.assertEqual(int(hosting["contracts"]), 2)
        self.assertEqual(int(hosting["complete_contracts"]), 1)
        stored = market_db.list_contracts(
            1, 25, query="700001"
        )["contracts"][0]
        self.assertEqual(stored["initiator_uid"], 12345)
        self.assertEqual(stored["counterparty_uid"], 54321)
        self.assertEqual(stored["scope"], "market")
        market_db.upsert_contract(12345, {
            "cid": "700003", "tid": "999999", "status": "5", "type": "1",
            "public": "0", "dateline": "130", "otherdateline": "140",
        })
        self.assertIn(999999, market_db.due_contract_threads())

        forward = market_db.get_contract_cursor("forward")
        market_db.advance_contract_cursor(
            "forward", int(forward["next_cid"]) + 30, 30
        )
        advanced = market_db.get_contract_cursor("forward")
        self.assertEqual(
            int(advanced["next_cid"]), int(forward["next_cid"]) + 30
        )
        self.assertEqual(int(advanced["empty_streak"]), 0)
        market_db.advance_contract_cursor(
            "forward", int(advanced["next_cid"]), 0
        )
        self.assertEqual(
            int(market_db.get_contract_cursor("forward")["empty_streak"]), 1
        )

        payment_id = "a" * 32
        market_db.create_payment(payment_id, "555", 5000, 30)
        expires = market_db.complete_payment(payment_id, "555", 30, permanent=True)
        self.assertEqual(expires, 4102444800)
        self.assertTrue(market_db.access_status("555")["paid"])
        expiring_payment = "b" * 32
        market_db.create_payment(expiring_payment, "556", 5000, 5)
        market_db.complete_payment(expiring_payment, "556", 5)
        self.assertIn("556", {str(row["uid"]) for row in market_db.expiring_passes(7)})

        watch_id = market_db.create_watch("555", {
            "name": "Hosting watch",
            "required_phrase": "daily backups",
            "optional_terms": [],
            "excluded_terms": [],
            "fids": [107],
            "market_type": "wts",
            "seller_uid": "",
            "telegram_enabled": True,
        })
        self.assertGreater(watch_id, 0)
        self.assertEqual(market_db.match_watches_for_thread(900001), 1)
        self.assertEqual(market_db.match_watches_for_thread(900001), 0)
        self.assertEqual(len(market_db.pending_matches()), 1)
        self.assertEqual(len(market_db.list_watch_matches("555")), 1)
        self.assertEqual(market_db.list_watches("555")[0]["telegram_enabled"], 1)


if __name__ == "__main__":
    unittest.main()
