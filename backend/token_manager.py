"""
token_manager.py — OAuth token refresh logic.

Handles refreshing expired HF tokens using stored refresh_tokens.
Called by background tasks (autobump, crawl) before marking a user
as dead and giving up.

Flow:
  1. Look up stored refresh_token for uid
  2. POST to HF token endpoint with grant_type=refresh_token
  3. On success: update users.token + refresh_token in DB, return new token
  4. On failure: mark token_dead=1, return None

Callers should then skip that uid and wait for the user to re-login.
"""

import os
import time
import logging
import aiohttp
import asyncio

import db

log = logging.getLogger("token_manager")

HF_TOKEN_URL  = "https://hackforums.net/api/v2/authorize"
CLIENT_ID     = os.environ.get("HF_CLIENT_ID", "")
CLIENT_SECRET = os.environ.get("HF_CLIENT_SECRET", "")

# Residential relay — required because Cloudflare blocks datacenter IPs
_RELAY_HOST   = os.environ.get("HF_RELAY_HOST", "")
_RELAY_PORT   = int(os.environ.get("HF_RELAY_PORT", "0"))
_RELAY_SECRET = os.environ.get("HF_RELAY_SECRET", "")

# Reuse a single session across all refresh calls — avoids the overhead of
# spinning up a new connector + TLS handshake for every token refresh.
# Created lazily on first use; closed connections are handled by aiohttp internally.
_session: aiohttp.ClientSession | None = None


def _get_refresh_session() -> aiohttp.ClientSession:
    global _session
    if _session is None or _session.closed:
        _session = aiohttp.ClientSession(
            timeout=aiohttp.ClientTimeout(total=20, connect=5, sock_connect=5, sock_read=15),
        )
    return _session


async def try_refresh_token(uid: str) -> str | None:
    """
    Attempt to refresh the HF OAuth token for uid using the stored refresh_token.

    Returns the new access_token string on success, None on failure.
    On failure, marks token_dead=1 in the DB so poll loops can skip this user
    immediately without wasting API calls.
    """
    refresh_token = await asyncio.to_thread(db.get_refresh_token, uid)
    if not refresh_token:
        log.warning("token_manager: uid=%s has no stored refresh_token — marking dead", uid)
        await asyncio.to_thread(db.mark_token_dead, uid)
        try:
            await asyncio.to_thread(db.add_notification, uid, "token_dead",
                "Token expired — re-authentication required",
                "Autobump and background sync are paused. Log in again to resume.",
                "/dashboard/settings", "token_dead",
            )
        except Exception:
            pass
        return None

    log.info("token_manager: attempting token refresh for uid=%s", uid)
    try:
        kwargs: dict = {}
        if _RELAY_HOST and _RELAY_PORT:
            kwargs["proxy"]      = f"http://{_RELAY_HOST}:{_RELAY_PORT}"
            kwargs["proxy_auth"] = aiohttp.BasicAuth("proxy", _RELAY_SECRET)

        session = _get_refresh_session()
        resp = await session.post(
            HF_TOKEN_URL,
            data={
                "grant_type":    "refresh_token",
                "client_id":     CLIENT_ID,
                "client_secret": CLIENT_SECRET,
                "refresh_token": refresh_token,
            },
            **kwargs,
        )
        body = await resp.json(content_type=None)
    except Exception as e:
        log.warning("token_manager: HTTP error refreshing uid=%s: %s", uid, e)
        # Don't mark dead on a transient network error — retry next cycle
        return None

    new_token = body.get("access_token")
    if not new_token:
        log.warning(
            "token_manager: refresh failed for uid=%s — no access_token in response: %s",
            uid, {k: v for k, v in body.items() if k != "refresh_token"},
        )
        await asyncio.to_thread(db.mark_token_dead, uid)
        try:
            await asyncio.to_thread(db.add_notification, uid, "token_dead",
                "Token refresh failed — re-authentication required",
                "Autobump and background sync are paused. Log in again to resume.",
                "/dashboard/settings", "token_dead",
            )
        except Exception:
            pass
        return None

    new_refresh = body.get("refresh_token") or refresh_token
    expires_in  = int(body.get("expires_in") or 0)
    new_expiry  = int(time.time()) + expires_in if expires_in else 0

    await asyncio.to_thread(db.update_token, uid, new_token)
    await asyncio.to_thread(db.store_refresh_token, uid, new_refresh, new_expiry)
    await asyncio.to_thread(db.mark_token_dead, uid, False)

    log.info("token_manager: token refreshed successfully for uid=%s", uid)
    return new_token
