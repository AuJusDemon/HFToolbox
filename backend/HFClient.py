"""
HFClient.py — HF API v2 client with dual-proxy support and session rotation.

Uses requests (sync) in asyncio.to_thread — avoids aiohttp CONNECT tunnel
quirks while keeping the async interface callers expect.

Flow: async caller → asyncio.to_thread → requests → proxy → HF

Configure via .env:

  Primary proxy (required if on a datacenter IP):
    HF_PROXY1_URL=http://user:pass@host:port
    HF_PROXY1_SESSION_LIFETIME=600   # seconds — used to build sticky session IDs

  Fallback proxy (optional — used when primary circuit-breaker opens):
    HF_PROXY2_URL=http://user:pass@host:port

  If neither is set, requests go direct (fine for residential IPs).

Both standard http/https proxy URLs are supported.
Rotating residential proxies: append session params to the password field
as your provider requires (e.g. _country-us_session-{id}_lifetime-{n}s).
HFClient injects the session ID automatically when HF_PROXY1_SESSION_LIFETIME is set.
"""
import asyncio
import json as _json
import logging
import os
import secrets
import threading
import time

import requests
import urllib3

urllib3.disable_warnings()

log = logging.getLogger("hftoolbox.api")


class AuthExpired(Exception):
    pass


# ── HF endpoints ───────────────────────────────────────────────────────────────
HF_READ  = "https://hackforums.net/api/v2/read"
HF_WRITE = "https://hackforums.net/api/v2/write"
HF_AUTH  = "https://hackforums.net/api/v2/authorize"

HEADERS = {
    "User-Agent":      "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Accept":          "application/json, text/plain, */*",
    "Accept-Language": "en-US,en;q=0.9",
}

HF_TIMEOUT = (4, 8)   # (connect, read) — fast fail, keeps threads from hanging

# ── Proxy config from environment ─────────────────────────────────────────────
# Primary proxy — rotating residential recommended
_PROXY1_RAW              = os.getenv("HF_PROXY1_URL", "").strip()
_PROXY1_SESSION_LIFETIME = int(os.getenv("HF_PROXY1_SESSION_LIFETIME", "0"))

# Fallback proxy — used when primary circuit-breaker opens
_PROXY2_RAW              = os.getenv("HF_PROXY2_URL", "").strip()

if _PROXY1_RAW:
    log.info("HFClient: proxy1 enabled (%s)", _PROXY1_RAW.split("@")[-1])
else:
    log.info("HFClient: no proxy configured — direct connection")

if _PROXY2_RAW:
    log.info("HFClient: proxy2 (fallback) enabled (%s)", _PROXY2_RAW.split("@")[-1])

# ── Session rotation (for rotating residential proxies) ───────────────────────
_session_lock = threading.Lock()
_session_id   = secrets.token_hex(4)
_rotate_count = 0


def _proxy1_proxies() -> dict:
    """
    Build proxy dict for the primary proxy.
    If HF_PROXY1_SESSION_LIFETIME is set, injects a sticky session ID into the
    password field in the format your provider expects — edit the f-string below
    to match your provider's sticky session syntax.
    """
    if not _PROXY1_RAW:
        return {}
    if _PROXY1_SESSION_LIFETIME:
        # Inject sticky session ID into password field.
        # Format: http://user:PASS_session-ID_lifetime-Ns@host:port
        # Adjust the suffix format to match your proxy provider's syntax.
        with _session_lock:
            sid = _session_id
        # Split on @ to isolate credentials, inject session into password
        at = _PROXY1_RAW.rfind("@")
        if at != -1:
            creds = _PROXY1_RAW[7:at]   # strip http:// prefix
            host  = _PROXY1_RAW[at+1:]
            user, pw = (creds.split(":", 1) + [""])[:2]
            pw_with_session = f"{pw}_session-{sid}_lifetime-{_PROXY1_SESSION_LIFETIME}s"
            url = f"http://{user}:{pw_with_session}@{host}"
        else:
            url = _PROXY1_RAW
    else:
        url = _PROXY1_RAW
    return {"http": url, "https": url}


def _proxy2_proxies() -> dict:
    if not _PROXY2_RAW:
        return {}
    return {"http": _PROXY2_RAW, "https": _PROXY2_RAW}


def _rotate_session(reason: str = "") -> None:
    global _session_id, _rotate_count
    with _session_lock:
        old           = _session_id
        _session_id   = secrets.token_hex(4)
        _rotate_count += 1
        count         = _rotate_count
        new           = _session_id
    log.warning("Rotated proxy session #%d (%s): %s -> %s", count, reason, old, new)


# ── Circuit breaker (primary → fallback) ──────────────────────────────────────
_cb_lock       = threading.Lock()
_cb_fails      = 0
_cb_open_since = 0.0
CB_THRESHOLD   = 5
CB_RESET_AFTER = 45.0


def _cb_is_open() -> bool:
    with _cb_lock:
        if _cb_open_since == 0.0:
            return False
        if time.time() - _cb_open_since >= CB_RESET_AFTER:
            return False
        return True


def _cb_fail() -> None:
    global _cb_fails, _cb_open_since
    with _cb_lock:
        _cb_fails += 1
        if _cb_fails >= CB_THRESHOLD and _cb_open_since == 0.0:
            _cb_open_since = time.time()
            log.warning("Primary proxy circuit OPEN after %d failures", _cb_fails)


def _cb_success() -> None:
    global _cb_fails, _cb_open_since
    with _cb_lock:
        if _cb_open_since != 0.0:
            log.info("Primary proxy circuit CLOSED")
        _cb_fails      = 0
        _cb_open_since = 0.0


# ── Rate limit tracking ────────────────────────────────────────────────────────
_rate_limits: dict[str, int] = {}


def is_rate_limited(token: str) -> bool:
    return _rate_limits.get(token, 9999) < 20


def get_rate_limit_remaining(token: str) -> int:
    return _rate_limits.get(token, 9999)


def _update_rate_limit(token: str, remaining: int) -> None:
    _rate_limits[token] = remaining


# ── Sync HTTP call (runs in thread pool) ──────────────────────────────────────

def _sync_call(token: str, url: str, form_data: dict, proxies: dict) -> requests.Response:
    headers = {**HEADERS, "Authorization": f"Bearer {token}"}
    return requests.post(
        url,
        data=form_data,
        headers=headers,
        proxies=proxies,
        timeout=HF_TIMEOUT,
        verify=False,
    )


# ── Concurrency limiter ────────────────────────────────────────────────────────
_hf_sem         = asyncio.Semaphore(6)
_MAX_RETRIES    = 2
_CF_MAX_RETRIES = 1
_RETRY_DELAYS   = [1, 3]


async def _request(
    token: str,
    route: str,
    body: dict,
    attempt: int = 0,
    max_retries: int = _MAX_RETRIES,
) -> dict | None:
    url       = HF_READ if route == "read" else HF_WRITE
    proxies   = _proxy2_proxies() if _cb_is_open() else _proxy1_proxies()
    form_data = {"asks": _json.dumps(body)}

    try:
        async with _hf_sem:
            resp = await asyncio.to_thread(_sync_call, token, url, form_data, proxies)

        rl = resp.headers.get("x-rate-limit-remaining")
        if rl and rl.isdigit():
            _update_rate_limit(token, int(rl))

        if resp.status_code == 200:
            ct = resp.headers.get("Content-Type", "")
            if "text/html" in ct or resp.text.lstrip().startswith("<!"):
                log.warning("HF returned CF challenge HTML — rotating and retrying")
                _rotate_session("CF HTML block")
                _cb_fail()
                if attempt < _CF_MAX_RETRIES:
                    await asyncio.sleep(1)
                    return await _request(token, route, body, attempt + 1, max_retries)
                return None
            _cb_success()
            return resp.json()

        if resp.status_code == 401:
            raise AuthExpired()

        if resp.status_code in (403, 502):
            _rotate_session(f"HTTP {resp.status_code}")
            _cb_fail()
            if attempt < max_retries:
                await asyncio.sleep(1)
                return await _request(token, route, body, attempt + 1, max_retries)
            return None

        log.warning("HF HTTP %d (route=%s)", resp.status_code, route)
        return None

    except AuthExpired:
        raise
    except (requests.exceptions.Timeout,
            requests.exceptions.ProxyError,
            requests.exceptions.ConnectionError) as e:
        _rotate_session(f"{type(e).__name__}")
        _cb_fail()
        if attempt < max_retries:
            delay = _RETRY_DELAYS[min(attempt, len(_RETRY_DELAYS) - 1)]
            log.warning("Proxy %s (attempt %d/%d) — retrying in %ds",
                        type(e).__name__, attempt + 1, max_retries, delay)
            await asyncio.sleep(delay)
            return await _request(token, route, body, attempt + 1, max_retries)
        log.warning("Proxy %s — all %d retries exhausted", type(e).__name__, max_retries)
        return None
    except Exception as e:
        log.error("HF request error %s: %s", type(e).__name__, e)
        return None


# ── HFClient ───────────────────────────────────────────────────────────────────

class HFClient:
    def __init__(self, token: str, **kwargs):
        self.token = token

    async def read(self, asks: dict) -> dict | None:
        return await _request(self.token, "read", asks)

    async def write(self, asks: dict) -> dict | None:
        return await _request(self.token, "write", asks, max_retries=0)

    async def ping(self) -> bool:
        try:
            result = await self.read({"me": {"uid": True}})
            return result is not None and "me" in result
        except AuthExpired:
            return False
        except Exception:
            return False


# ── OAuth token exchange ───────────────────────────────────────────────────────

def _sync_token_exchange(code: str, cfg: dict, proxies: dict):
    return requests.post(
        HF_AUTH,
        data={
            "grant_type":    "authorization_code",
            "code":          code,
            "client_id":     cfg["hf_client_id"],
            "client_secret": cfg.get("hf_client_secret") or cfg.get("hf_secret"),
        },
        headers=HEADERS,
        proxies=proxies,
        timeout=(5, 15),
        verify=False,
    )


async def exchange_code_for_token(code: str, cfg: dict):
    proxies = _proxy2_proxies() if _cb_is_open() else _proxy1_proxies()
    try:
        resp = await asyncio.to_thread(_sync_token_exchange, code, cfg, proxies)
        if resp.status_code == 200:
            data = resp.json()
            return (
                data.get("access_token"),
                data.get("expires_in"),
                data.get("refresh_token"),
            )
        log.error("Token exchange failed: HTTP %d", resp.status_code)
        return None, None, None
    except Exception as e:
        log.error("Token exchange error: %s", e)
        return None, None, None
