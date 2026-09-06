"""Regression tests for browser-session and OAuth entry behavior."""

from __future__ import annotations

import asyncio
import os
import unittest
from types import SimpleNamespace
from unittest.mock import patch

os.environ.setdefault("HF_CLIENT_ID", "test-client")
os.environ.setdefault("HF_CLIENT_SECRET", "test-secret")
os.environ.setdefault("HF_REDIRECT_URI", "https://dev.example/auth/callback")
os.environ.setdefault("FRONTEND_URL", "https://dev.example")
os.environ.setdefault("SESSION_SECRET", "test-session-secret")

import auth  # noqa: E402


class AuthSessionTests(unittest.TestCase):
    def test_logout_clears_only_the_browser_session(self):
        request = SimpleNamespace(session={"uid": "761578"})
        with patch.object(auth.db, "mark_token_dead") as mark_dead:
            response = asyncio.run(auth.logout(request))

        self.assertEqual({}, request.session)
        mark_dead.assert_not_called()
        self.assertEqual(200, response.status_code)
        cookie = response.headers.get("set-cookie", "").lower()
        self.assertIn("max-age=0", cookie)
        self.assertIn("secure", cookie)

    def test_existing_valid_session_skips_provider_oauth(self):
        request = SimpleNamespace(session={"uid": "761578"})
        with patch.object(auth.db, "get_user", return_value={"uid": "761578", "token_dead": 0}):
            response = asyncio.run(auth.login(request, next="/dashboard/market"))

        self.assertEqual(307, response.status_code)
        self.assertEqual("https://dev.example/dashboard/market", response.headers["location"])
        self.assertNotIn("oauth_state", request.session)

    def test_new_oauth_attempt_gets_one_trace_reference(self):
        request = SimpleNamespace(session={})
        response = asyncio.run(auth.login(request, next="/dashboard/bytes"))

        self.assertEqual(307, response.status_code)
        self.assertIn("hackforums.net/" + "api/v2/authorize", response.headers["location"])
        self.assertTrue(request.session.get("oauth_state"))
        self.assertTrue(request.session.get("oauth_ref"))
        self.assertEqual("/dashboard/bytes", request.session.get("oauth_next"))


if __name__ == "__main__":
    unittest.main()
