"""
token_manager.py - OAuth token refresh logic.

Handles refreshing expired HF tokens using stored refresh_tokens.
Called by background tasks before marking a user as dead and giving up.

Flow:
  1. Look up stored refresh_token for uid
  2. Ask the HF controller to refresh with grant_type=refresh_token
  3. On success: update users.token + refresh_token in DB, return new token
  4. On failure: mark token_dead=1, return None

Callers should then skip that uid and wait for the user to re-login.
"""

import os
import time
import logging
import asyncio

import db
from HFClient import refresh_access_token

log = logging.getLogger("token_manager")

CLIENT_ID = os.environ.get("HF_CLIENT_ID", "")
CLIENT_SECRET = os.environ.get("HF_CLIENT_SECRET", "")


async def _notify_token_dead(uid: str, title: str) -> None:
    try:
        await asyncio.to_thread(
            db.add_notification,
            uid,
            "token_dead",
            title,
            "Autobump and background sync are paused. Log in again to resume.",
            "/dashboard/settings",
            "token_dead",
        )
    except Exception:
        pass
    try:
        import time as _t, integration_db as _idb
        day = str(int(_t.time()) // 86400)
        await asyncio.to_thread(
            _idb.create_alert_event,
            uid,
            "token_dead",
            f"token_dead:{day}",
            title,
            "Log back in to HFToolbox to resume autobump and alerts.",
            "/dashboard/settings",
            "toolbox",
            None,
            True,
        )
    except Exception:
        pass


async def try_refresh_token(uid: str) -> str | None:
    """
    Attempt to refresh the HF OAuth token for uid using the stored refresh_token.

    Returns the new access_token string on success, None on failure.
    On failure, marks token_dead=1 in the DB so poll loops can skip this user
    immediately without wasting API calls.
    """
    refresh_token = await asyncio.to_thread(db.get_refresh_token, uid)
    if not refresh_token:
        log.warning("token_manager: uid=%s has no stored refresh_token - marking dead", uid)
        await asyncio.to_thread(db.mark_token_dead, uid)
        await _notify_token_dead(uid, "Token expired - re-authentication required")
        return None

    log.info("token_manager: attempting token refresh for uid=%s", uid)
    try:
        new_token, expires_in, new_refresh = await refresh_access_token(refresh_token, {
            "hf_client_id": CLIENT_ID,
            "hf_client_secret": CLIENT_SECRET,
        })
    except Exception as e:
        log.warning("token_manager: controller error refreshing uid=%s: %s", uid, e)
        return None

    if not new_token:
        log.warning("token_manager: refresh failed for uid=%s - no access_token in response", uid)
        await asyncio.to_thread(db.mark_token_dead, uid)
        await _notify_token_dead(uid, "Token refresh failed - re-authentication required")
        return None

    expires_in_int = int(expires_in or 0)
    new_expiry = int(time.time()) + expires_in_int if expires_in_int else 0
    stored_refresh = new_refresh or refresh_token

    await asyncio.to_thread(db.update_token, uid, new_token)
    await asyncio.to_thread(db.store_refresh_token, uid, stored_refresh, new_expiry)
    await asyncio.to_thread(db.mark_token_dead, uid, False)

    log.info("token_manager: token refreshed successfully for uid=%s", uid)
    return new_token
