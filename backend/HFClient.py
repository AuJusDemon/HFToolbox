"""
HFClient.py — HF API v2 client.

Uses requests (sync) in asyncio.to_thread — avoids aiohttp CONNECT tunnel
quirks while keeping the async interface callers expect.

Flow: async caller → asyncio.to_thread → requests → (optional proxy) → HF

Set HF_PROXY_URL in .env if hosting on a datacenter IP:
    HF_PROXY_URL=http://user:password@proxy.example.com:8080
    HF_PROXY_URL=socks5://user:password@proxy.example.com:1080
"""
import asyncio
import json as _json
import logging
import os

import requests

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

HF_TIMEOUT = (5, 10)  # (connect, read)

# ── Proxy ──────────────────────────────────────────────────────────────────────
_PROXY_URL = os.environ.get("HF_PROXY_URL", "").strip()
_PROXIES   = {"http": _PROXY_URL, "https": _PROXY_URL} if _PROXY_URL else {}

if _PROXY_URL:
    log.info("HFClient: proxy enabled (%s)", _PROXY_URL.split("@")[-1])
else:
    log.info("HFClient: no proxy — direct connection")


# ── Rate limit tracking ────────────────────────────────────────────────────────
_rate_limits: dict[str, int] = {}


def is_rate_limited(token: str) -> bool:
    return _rate_limits.get(token, 9999) < 20


def get_rate_limit_remaining(token: str) -> int:
    return _rate_limits.get(token, 9999)


def _update_rate_limit(token: str, remaining: int) -> None:
    _rate_limits[token] = remaining


# ── Sync HTTP call (runs in thread pool) ───────────────────────────────────────

def _sync_call(token: str, url: str, form_data: dict) -> requests.Response:
    headers = {**HEADERS, "Authorization": f"Bearer {token}"}
    return requests.post(
        url,
        data=form_data,
        headers=headers,
        proxies=_PROXIES or None,
        timeout=HF_TIMEOUT,
        verify=True,
    )


# ── Request core ───────────────────────────────────────────────────────────────
_hf_sem       = asyncio.Semaphore(6)
_MAX_RETRIES  = 3
_RETRY_DELAYS = [2, 5, 10]


async def _request(
    token: str,
    route: str,
    body: dict,
    attempt: int = 0,
    max_retries: int = _MAX_RETRIES,
) -> dict | None:
    url       = HF_READ if route == "read" else HF_WRITE
    form_data = {"asks": _json.dumps(body)}

    try:
        async with _hf_sem:
            resp = await asyncio.to_thread(_sync_call, token, url, form_data)

        rl = resp.headers.get("x-rate-limit-remaining")
        if rl and rl.isdigit():
            _update_rate_limit(token, int(rl))

        if resp.status_code == 200:
            ct = resp.headers.get("Content-Type", "")
            if "text/html" in ct or resp.text.lstrip().startswith("<!"):
                log.warning("HF returned HTML (CF block) — attempt %d/%d", attempt + 1, max_retries)
                if attempt < max_retries:
                    await asyncio.sleep(2)
                    return await _request(token, route, body, attempt + 1, max_retries)
                return None
            return resp.json()

        if resp.status_code == 401:
            raise AuthExpired()

        if resp.status_code in (403, 502, 503):
            if attempt < max_retries:
                await asyncio.sleep(_RETRY_DELAYS[min(attempt, len(_RETRY_DELAYS) - 1)])
                return await _request(token, route, body, attempt + 1, max_retries)
            return None

        log.warning("HF HTTP %d (route=%s)", resp.status_code, route)
        return None

    except AuthExpired:
        raise
    except (requests.exceptions.Timeout,
            requests.exceptions.ProxyError,
            requests.exceptions.ConnectionError) as e:
        if attempt < max_retries:
            delay = _RETRY_DELAYS[min(attempt, len(_RETRY_DELAYS) - 1)]
            log.warning("%s — retrying in %ds (attempt %d/%d)",
                        type(e).__name__, delay, attempt + 1, max_retries)
            await asyncio.sleep(delay)
            return await _request(token, route, body, attempt + 1, max_retries)
        log.warning("%s — all retries exhausted", type(e).__name__)
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

def _sync_token_exchange(code: str, cfg: dict) -> requests.Response:
    return requests.post(
        HF_AUTH,
        data={
            "grant_type":    "authorization_code",
            "code":          code,
            "client_id":     cfg["hf_client_id"],
            "client_secret": cfg.get("hf_client_secret") or cfg.get("hf_secret"),
        },
        headers=HEADERS,
        proxies=_PROXIES or None,
        timeout=(5, 15),
        verify=True,
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
        log.error("Token exchange failed: HTTP %d", resp.status_code)
        return None, None, None
    except Exception as e:
        log.error("Token exchange error: %s", e)
        return None, None, None