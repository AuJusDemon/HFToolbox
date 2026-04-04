"""
HFClient.py — HackForums API v2 client.

Makes direct requests to https://hackforums.net/api/v2.

⚠️  Cloudflare note: HackForums uses Cloudflare, which blocks most datacenter
    IP ranges. If you're hosting on a VPS/cloud server you may get 403 errors.
    In that case you need to route requests through a residential proxy.
    Set HF_PROXY_URL in your .env to a proxy URL (e.g. http://user:pass@host:port)
    and it will be used for all HF API calls.
"""
import asyncio
import logging
import os

import aiohttp

log = logging.getLogger("hftoolbox.api")

HF_API_BASE = "https://hackforums.net/api/v2"
PROXY_URL   = os.environ.get("HF_PROXY_URL")  # Optional — set if on datacenter IP

# ── Rate limit tracking ────────────────────────────────────────────────────────
_rate_limits: dict[str, int] = {}  # token → remaining calls


def is_rate_limited(token: str) -> bool:
    """Return True if this token has fewer than 20 calls remaining."""
    return _rate_limits.get(token, 9999) < 20


def get_rate_limit_remaining(token: str) -> int:
    return _rate_limits.get(token, 9999)


# ── Shared aiohttp session ─────────────────────────────────────────────────────
_sessions: dict[int, aiohttp.ClientSession] = {}


def _get_session() -> aiohttp.ClientSession:
    loop_id = id(asyncio.get_running_loop())
    if loop_id not in _sessions or _sessions[loop_id].closed:
        connector = aiohttp.TCPConnector(limit=20, ttl_dns_cache=300)
        _sessions[loop_id] = aiohttp.ClientSession(
            connector=connector,
            timeout=aiohttp.ClientTimeout(total=30, connect=10),
        )
    return _sessions[loop_id]


# ── Core request ───────────────────────────────────────────────────────────────
_TRANSIENT = {503, 520, 521, 522, 523, 524}
_MAX_RETRIES = 3
_RETRY_DELAYS = [1, 3, 6]


class AuthExpired(Exception):
    """Raised when HF returns 401 — token is expired or invalid."""
    pass


async def _request(token: str, route: str, body: dict, attempt: int = 0) -> dict | None:
    url = f"{HF_API_BASE}/{route}"
    headers = {"Authorization": f"Bearer {token}"}
    proxy = PROXY_URL or None

    try:
        session = _get_session()
        async with session.post(url, json=body, headers=headers, proxy=proxy) as resp:
            rl = resp.headers.get("x-rate-limit-remaining")
            if rl and rl.isdigit():
                _rate_limits[token] = int(rl)

            if resp.status == 200:
                return await resp.json()
            if resp.status == 401:
                raise AuthExpired()
            if resp.status == 403:
                log.warning("HF returned 403 — likely Cloudflare blocking your IP. "
                            "Set HF_PROXY_URL in .env to use a residential proxy.")
                return None
            if resp.status in _TRANSIENT and attempt < _MAX_RETRIES:
                await asyncio.sleep(_RETRY_DELAYS[min(attempt, 2)])
                return await _request(token, route, body, attempt + 1)

            log.warning("HF API /%s returned HTTP %d", route, resp.status)
            return None

    except AuthExpired:
        raise
    except (aiohttp.ClientConnectionError, asyncio.TimeoutError) as e:
        if attempt < _MAX_RETRIES:
            await asyncio.sleep(_RETRY_DELAYS[min(attempt, 2)])
            return await _request(token, route, body, attempt + 1)
        log.warning("HF API /%s connection failed after %d retries: %s", route, _MAX_RETRIES, e)
        return None
    except Exception as e:
        log.error("HF API /%s unexpected error: %s", route, e)
        return None


# ── HFClient ───────────────────────────────────────────────────────────────────

class HFClient:
    def __init__(self, token: str, **kwargs):
        self.token = token

    async def read(self, asks: dict) -> dict | None:
        """POST to /read endpoint. `asks` is the nested request dict."""
        return await _request(self.token, "read", asks)

    async def write(self, asks: dict) -> dict | None:
        """POST to /write endpoint."""
        return await _request(self.token, "write", asks)

    async def ping(self) -> bool:
        try:
            result = await self.read({"me": {"uid": True}})
            return result is not None and "me" in result
        except AuthExpired:
            return False


# ── OAuth token exchange ───────────────────────────────────────────────────────

async def exchange_code_for_token(code: str, cfg: dict):
    """
    Exchange an OAuth authorization code for an access token.
    Returns (access_token, expires_in, refresh_token) or (None, None, None).
    """
    url = "https://hackforums.net/api/v2/authorize"
    proxy = PROXY_URL or None
    try:
        session = _get_session()
        async with session.post(
            url,
            data={
                "grant_type":    "authorization_code",
                "code":          code,
                "client_id":     cfg["hf_client_id"],
                "client_secret": cfg.get("hf_client_secret") or cfg.get("hf_secret"),
            },
            proxy=proxy,
            timeout=aiohttp.ClientTimeout(total=30),
        ) as resp:
            if resp.status == 200:
                data = await resp.json()
                return data.get("access_token"), data.get("expires_in"), data.get("refresh_token")
            log.error("Token exchange failed: HTTP %d", resp.status)
            return None, None, None
    except Exception as e:
        log.error("Token exchange error: %s", e)
        return None, None, None
