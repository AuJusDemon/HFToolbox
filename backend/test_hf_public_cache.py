from __future__ import annotations

import unittest
from unittest.mock import patch

import hf_public_cache


class PublicCacheTests(unittest.TestCase):
    def test_seed_from_users_and_threads(self):
        calls = {"users": None, "threads": None}

        def users(value):
            calls["users"] = {**(calls["users"] or {}), **value}

        def threads(value):
            calls["threads"] = value

        payload = {
            "users": [{"uid": 10, "username": "alice", "avatar": "./avatar.png"}],
            "threads": [{"tid": 55, "subject": "Thread title", "lastposteruid": 11, "lastposter": "bob"}],
        }
        with patch("hf_public_cache.db.upsert_uid_usernames", users), \
             patch("hf_public_cache.db.upsert_tid_titles", threads):
            seeded = hf_public_cache.seed_from_response(payload)

        self.assertEqual(1, seeded["users"])
        self.assertEqual(1, seeded["threads"])
        self.assertEqual("alice", calls["users"]["10"]["username"])
        self.assertEqual("https://hackforums.net/avatar.png", calls["users"]["10"]["avatar"])
        self.assertEqual("Thread title", calls["threads"]["55"])


if __name__ == "__main__":
    unittest.main()
