"""HF API v2 client.

Uses requests in asyncio.to_thread so callers keep the async interface while
outbound HF traffic goes directly to HackForums.
"""
import asyncio
import json as _json
import logging
import os
import time

import requests
import urllib3

urllib3.disable_warnings()

log = logging.getLogger("hftoolbox.api")


class AuthExpired(Exception):
    pass


# ?? HF endpoints ???????????????????????????????????????????????????????????????
HF_READ  = "https://hackforums.net/api/v2/read"
HF_WRITE = "https://hackforums.net/api/v2/write"
HF_AUTH  = "https://hackforums.net/api/v2/authorize"

HEADERS = {
    "User-Agent":      "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Accept":          "application/json, text/plain, */*",
    "Accept-Language": "en-US,en;q=0.9",
}

HF_TIMEOUT = (5, 12)
log.info("HFClient: direct HF connection")


# ?? Rate limit tracking ????????????????????????????????????????????????????????
_rate_limits: dict[str, int] = {}
_rate_limit_seen_at: dict[str, float] = {}
_hf_blocked_until = 0.0
_HF_BLOCK_COOLDOWN = int(os.environ.get("HF_CIRCUIT_COOLDOWN_SECONDS", "900"))


def _is_hf_blocked() -> bool:
    return time.time() < _hf_blocked_until


def _trip_hf_circuit(reason: str) -> None:
    global _hf_blocked_until
    _hf_blocked_until = max(_hf_blocked_until, time.time() + _HF_BLOCK_COOLDOWN)
    log.warning("HF circuit opened for %ds: %s", _HF_BLOCK_COOLDOWN, reason)


def is_rate_limited(token: str) -> bool:
    return _rate_limits.get(token, 9999) < 20


def get_rate_limit_remaining(token: str) -> int:
    return _rate_limits.get(token, 9999)


def _update_rate_limit(token: str, remaining: int) -> None:
    _rate_limits[token] = remaining
    _rate_limit_seen_at[token] = time.time()


# ?? Sync HTTP call (runs in thread pool) ??????????????????????????????????????

def _sync_call(token: str, url: str, form_data: dict) -> requests.Response:
    headers = {**HEADERS, "Authorization": f"Bearer {token}"}
    return requests.post(
        url,
        data=form_data,
        headers=headers,
        timeout=HF_TIMEOUT,
        verify=False,
    )


# ?? Concurrency limiter ????????????????????????????????????????????????????????
_hf_sem          = asyncio.Semaphore(2)
_MAX_RETRIES     = 1               # one retry only for real network timeouts
_RETRY_DELAYS    = [1, 2, 4, 8]   # backoff for Timeout/ConnectionError
_CF_RETRY_DELAYS = [4, 8, 16, 30] # longer backoff for CF/HF 403/502/503 blocks


async def _request(
    token: str,
    route: str,
    body: dict,
    attempt: int = 0,
    max_retries: int = _MAX_RETRIES,
) -> dict | None:
    url       = HF_READ if route == "read" else HF_WRITE
    form_data = {"asks": _json.dumps(body)}

    if _is_hf_blocked():
        log.warning("HF circuit open; skipping route=%s", route)
        return None

    try:
        async with _hf_sem:
            resp = await asyncio.to_thread(_sync_call, token, url, form_data)

        rl = resp.headers.get("x-rate-limit-remaining")
        if rl and rl.isdigit():
            _update_rate_limit(token, int(rl))

        if resp.status_code == 200:
            ct = resp.headers.get("Content-Type", "")
            if "text/html" in ct or resp.text.lstrip().startswith("<!"):
                log.warning("HF returned HTML challenge (route=%s) - circuit open, not retrying", route)
                _trip_hf_circuit(f"HTML challenge route={route}")
                return None
            return resp.json()

        if resp.status_code == 401:
            raise AuthExpired()

        if resp.status_code in (403, 502, 503):
            log.warning("HF HTTP %d (route=%s) - circuit open, not retrying", resp.status_code, route)
            _trip_hf_circuit(f"HTTP {resp.status_code} route={route}")
            return None

        log.warning("HF HTTP %d (route=%s)", resp.status_code, route)
        return None

    except AuthExpired:
        raise
    except requests.exceptions.Timeout:
        if attempt < max_retries:
            delay = _RETRY_DELAYS[min(attempt, len(_RETRY_DELAYS) - 1)]
            log.warning("HF ReadTimeout (attempt %d/%d) ? retrying in %ds",
                        attempt + 1, max_retries, delay)
            await asyncio.sleep(delay)
            return await _request(token, route, body, attempt + 1, max_retries)
        log.warning("HF ReadTimeout ? all %d retries exhausted", max_retries)
        return None
    except requests.exceptions.ConnectionError as e:
        if attempt < max_retries:
            delay = _RETRY_DELAYS[min(attempt, len(_RETRY_DELAYS) - 1)]
            log.warning("HF %s (attempt %d/%d) ? retrying in %ds",
                        type(e).__name__, attempt + 1, max_retries, delay)
            await asyncio.sleep(delay)
            return await _request(token, route, body, attempt + 1, max_retries)
        log.warning("HF %s ? all %d retries exhausted", type(e).__name__, max_retries)
        return None
    except Exception as e:
        log.error("HF request error %s: %s", type(e).__name__, e)
        return None


# ?? HFClient ???????????????????????????????????????????????????????????????????

class HFClient:
    def __init__(self, token: str, **kwargs):
        self.token = token

    async def read(self, asks: dict) -> dict | None:
        return await _request(self.token, "read", asks)

    async def write(self, asks: dict) -> dict | None:
        if os.environ.get("DEV_DISABLE_HF_WRITES") == "1":
            log.warning("DEV_DISABLE_HF_WRITES=1 ? write blocked: %s", list(asks.keys()))
            return None
        return await _request(self.token, "write", asks, max_retries=0)

    async def ping(self) -> bool:
        try:
            result = await self.read({"me": {"uid": True}})
            return result is not None and "me" in result
        except AuthExpired:
            return False
        except Exception:
            return False


# ?? OAuth token exchange ???????????????????????????????????????????????????????

def _sync_token_exchange(code: str, cfg: dict):
    payload = {
        "grant_type":    "authorization_code",
        "code":          code,
        "client_id":     cfg["hf_client_id"],
        "client_secret": cfg.get("hf_client_secret") or cfg.get("hf_secret"),
    }
    if cfg.get("redirect_uri"):
        payload["redirect_uri"] = cfg["redirect_uri"]
    return requests.post(
        HF_AUTH,
        data=payload,
        headers=HEADERS,
        timeout=(5, 15),
        verify=False,
    )


async def exchange_code_for_token(code: str, cfg: dict):
    try:
        resp = await asyncio.to_thread(_sync_token_exchange, code, cfg)
        if resp.status_code == 200:
            data = resp.json()
            return (
                data.get("access_token"),
                data.get("expires_in"),
                data.get("refresh_token"),
            )
        log.error("Token exchange failed: HTTP %d ? %s", resp.status_code, resp.text[:300])
        return None, None, None
    except Exception as e:
        log.error("Token exchange error: %s", e)
        return None, None, None
